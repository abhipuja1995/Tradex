"""Hybrid strategy combining TradingAgents AI signals with RSI technical analysis."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

from config.settings import settings
from config.constants import SignalAction, DEFAULT_WATCHLIST

logger = logging.getLogger(__name__)


@dataclass
class TradeSignal:
    symbol: str
    action: SignalAction
    current_price: float
    rsi: float
    support: float
    ai_signal: SignalAction
    ai_confidence: float
    ai_reasoning: str
    combined_confidence: float


class HybridStrategy:
    """Combines TradingAgents AI signals with RSI reversal for trade decisions.

    Both layers must agree for a trade to execute:
    1. TradingAgents provides BUY/SELL/HOLD with confidence
    2. RSI confirms entry timing (RSI < 30 near support = BUY)
    3. Learning rules can override either layer
    """

    def __init__(self, ai_signal_generator, openalgo_client, learning_rules: list[dict] | None = None):
        self.ai = ai_signal_generator
        self.openalgo = openalgo_client
        self.learning_rules = learning_rules or []
        self.watchlist = list(DEFAULT_WATCHLIST)

    def update_watchlist(self, symbols: list[str]) -> None:
        self.watchlist = symbols
        logger.info(f"Watchlist updated: {len(symbols)} symbols")

    def update_rules(self, rules: list[dict]) -> None:
        self.learning_rules = rules

    def _should_skip(self, symbol: str, rsi: float, price: float) -> tuple[bool, str]:
        """Check learning rules for skip conditions."""
        for rule in self.learning_rules:
            if not rule.get("is_active"):
                continue

            condition = rule.get("condition_json", {})

            # Symbol-specific rules
            blocked_symbols = condition.get("blocked_symbols", [])
            if symbol in blocked_symbols:
                return True, f"Rule '{rule['rule_name']}': symbol blocked"

            # RSI range rules
            rsi_min = condition.get("rsi_min")
            rsi_max = condition.get("rsi_max")
            if rsi_min is not None and rsi_max is not None:
                if rsi_min <= rsi <= rsi_max:
                    return True, f"Rule '{rule['rule_name']}': RSI {rsi:.1f} in blocked range"

            # Time-based rules
            time_block = condition.get("block_before_time")
            if time_block:
                from datetime import datetime
                import zoneinfo
                ist = zoneinfo.ZoneInfo("Asia/Kolkata")
                now = datetime.now(ist)
                h, m = map(int, time_block.split(":"))
                if now.hour < h or (now.hour == h and now.minute < m):
                    return True, f"Rule '{rule['rule_name']}': blocked before {time_block}"

        return False, ""

    async def scan(self) -> list[TradeSignal]:
        """Scan watchlist for trade signals using hybrid AI + RSI approach."""
        from core.indicators import compute_rsi, support_level, is_near_support
        from dhanhq import dhanhq

        signals: list[TradeSignal] = []
        today_str = date.today().isoformat()

        for symbol in self.watchlist:
            try:
                # Get current price from OpenAlgo
                ltp = await self.openalgo.get_ltp(symbol)
                if not ltp:
                    continue

                # Get historical candles for RSI computation
                # Using Dhan API directly for OHLCV data (OpenAlgo may not expose this)
                candles = await self._get_candles(symbol)
                if candles is None or len(candles) < settings.rsi_period + 1:
                    continue

                rsi_series = compute_rsi(candles, settings.rsi_period)
                current_rsi = float(rsi_series.iloc[-1]) if not rsi_series.empty else 50
                support = support_level(candles)

                # Check RSI condition (oversold near support)
                rsi_buy = current_rsi < settings.rsi_oversold and is_near_support(ltp, support)

                if not rsi_buy:
                    continue  # RSI doesn't confirm, skip AI call to save LLM costs

                # Check learning rules before expensive AI call
                skip, skip_reason = self._should_skip(symbol, current_rsi, ltp)
                if skip:
                    logger.info(f"Skipping {symbol}: {skip_reason}")
                    continue

                # Get AI signal (only if RSI confirms)
                ai_signal = await self.ai.get_signal(symbol, today_str)

                # Both must agree on BUY
                if ai_signal.action != SignalAction.BUY:
                    logger.info(
                        f"{symbol}: RSI says BUY but AI says {ai_signal.action} "
                        f"(confidence: {ai_signal.confidence:.2f}). Skipping."
                    )
                    continue

                # Minimum AI confidence threshold
                if ai_signal.confidence < 0.5:
                    logger.info(
                        f"{symbol}: AI confidence too low ({ai_signal.confidence:.2f}). Skipping."
                    )
                    continue

                # Combined confidence: weighted average (AI 60%, RSI 40%)
                rsi_confidence = max(0, (settings.rsi_oversold - current_rsi) / settings.rsi_oversold)
                combined = 0.6 * ai_signal.confidence + 0.4 * rsi_confidence

                signals.append(TradeSignal(
                    symbol=symbol,
                    action=SignalAction.BUY,
                    current_price=ltp,
                    rsi=current_rsi,
                    support=support,
                    ai_signal=ai_signal.action,
                    ai_confidence=ai_signal.confidence,
                    ai_reasoning=ai_signal.reasoning,
                    combined_confidence=combined,
                ))

                logger.info(
                    f"Signal: BUY {symbol} @ ₹{ltp:.2f} | "
                    f"RSI: {current_rsi:.1f} | AI: {ai_signal.confidence:.2f} | "
                    f"Combined: {combined:.2f}"
                )

            except Exception as e:
                logger.error(f"Error scanning {symbol}: {e}")
                continue

        # Sort by combined confidence (highest first)
        signals.sort(key=lambda s: s.combined_confidence, reverse=True)
        return signals

    async def _get_candles(self, symbol: str, interval: str = "5") -> Any:
        """Fetch OHLCV candles from Dhan API.

        Uses dhanhq SDK directly since OpenAlgo may not expose historical data.
        """
        from config.constants import DHAN_SECURITY_IDS
        from core.indicators import candles_from_dhan_data

        security_id = DHAN_SECURITY_IDS.get(symbol)
        if not security_id:
            logger.warning(f"No Dhan security ID for {symbol}")
            return None

        try:
            dhan = dhanhq(settings.dhan_client_id, settings.dhan_access_token)
            from datetime import datetime, timedelta
            to_date = datetime.now()
            from_date = to_date - timedelta(days=5)

            response = dhan.intraday_daily_candle_data(
                security_id=str(security_id),
                exchange_segment=dhan.NSE,
                instrument_type=dhan.EQUITY,
            )

            if response and response.get("data"):
                return candles_from_dhan_data(response["data"])
        except Exception as e:
            logger.error(f"Failed to fetch candles for {symbol}: {e}")

        return None

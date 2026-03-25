"""Hybrid strategy combining TradingAgents AI signals with RSI technical analysis.

Architecture:
- Dhan SDK: execution layer (orders, positions, funds)
- OpenAlgo: strategy & automation signals (optional enhancement)
- TradingAgents: multi-agent AI signal generation
- RSI + Support: technical confirmation layer
"""

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

    Dhan is used for execution; OpenAlgo provides optional strategy signals.
    """

    def __init__(self, ai_signal_generator, broker_client, learning_rules: list[dict] | None = None):
        self.ai = ai_signal_generator
        self.broker = broker_client  # Dhan broker for market data (LTP, candles)
        self.learning_rules = learning_rules or []
        self.watchlist = list(DEFAULT_WATCHLIST)

        # Optional OpenAlgo strategy connection
        self._openalgo = None
        self._init_openalgo()

    def _init_openalgo(self):
        """Connect to OpenAlgo for strategy signals if configured."""
        if settings.openalgo_api_key:
            try:
                from core.openalgo_client import OpenAlgoClient
                self._openalgo = OpenAlgoClient()
                logger.info("OpenAlgo connected as strategy/automation layer")
            except Exception as e:
                logger.warning(f"OpenAlgo not available: {e}")

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

    async def _get_openalgo_signal(self, symbol: str) -> SignalAction | None:
        """Get strategy signal from OpenAlgo if available.

        OpenAlgo can provide additional strategy signals from its
        built-in strategy engine (moving average crossovers, etc.)
        This is used as an optional third confirmation layer.
        """
        if not self._openalgo:
            return None

        try:
            positions = await self._openalgo.get_positions()
            # If OpenAlgo already has a position in this symbol, it confirms the signal
            for pos in positions:
                if pos.get("symbol") == symbol:
                    net_qty = int(pos.get("netqty", pos.get("net_qty", 0)))
                    if net_qty > 0:
                        return SignalAction.BUY
                    elif net_qty < 0:
                        return SignalAction.SELL
            return SignalAction.HOLD
        except Exception as e:
            logger.debug(f"OpenAlgo signal unavailable for {symbol}: {e}")
            return None

    async def scan(self) -> list[TradeSignal]:
        """Scan watchlist for trade signals using hybrid AI + RSI approach."""
        from core.indicators import compute_rsi, support_level, is_near_support

        signals: list[TradeSignal] = []
        today_str = date.today().isoformat()

        for symbol in self.watchlist:
            try:
                # Get current price from Dhan broker
                ltp = await self.broker.get_ltp(symbol)
                if not ltp:
                    continue

                # Get historical candles for RSI computation (via Dhan)
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

                # Optional: check OpenAlgo strategy signal as third layer
                openalgo_signal = await self._get_openalgo_signal(symbol)
                openalgo_boost = 0.05 if openalgo_signal == SignalAction.BUY else 0.0

                # Combined confidence: weighted average (AI 60%, RSI 40%) + OpenAlgo boost
                rsi_confidence = max(0, (settings.rsi_oversold - current_rsi) / settings.rsi_oversold)
                combined = 0.6 * ai_signal.confidence + 0.4 * rsi_confidence + openalgo_boost

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
                    f"OpenAlgo: {openalgo_signal or 'N/A'} | "
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

        Uses Dhan SDK directly for historical data.
        """
        from config.constants import DHAN_SECURITY_IDS
        from core.indicators import candles_from_dhan_data

        security_id = DHAN_SECURITY_IDS.get(symbol)
        if not security_id:
            logger.warning(f"No Dhan security ID for {symbol}")
            return None

        try:
            from dhanhq import dhanhq
            dhan = dhanhq(settings.dhan_client_id, settings.dhan_access_token)

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

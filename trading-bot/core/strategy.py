"""Hybrid strategy combining AI signals with multi-indicator technical analysis.

Paper trading strategy uses relaxed entry conditions:
- RSI oversold bounce (RSI < 40)
- DMA crossover (price crosses above 20 EMA)
- Momentum plays (RSI 40-60 + above 50 DMA + volume spike)
- Support bounce (price within 1.5% of 20-day support)
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
    """Multi-strategy scanner for paper trading.

    Entry strategies (any one can trigger):
    1. Oversold Bounce: RSI < 40 near support
    2. Momentum: RSI 40-60, price > 50 DMA, volume spike
    3. DMA Crossover: price crosses above 20 EMA
    4. Support Bounce: price within 1.5% of support, RSI < 50

    All strategies require AI signal confirmation (RSI fallback if no LLM).
    """

    def __init__(self, ai_signal_generator, broker_client, learning_rules: list[dict] | None = None):
        self.ai = ai_signal_generator
        self.broker = broker_client
        self.learning_rules = learning_rules or []
        self.watchlist = list(DEFAULT_WATCHLIST)
        self._scan_count = 0

        self._openalgo = None
        self._init_openalgo()

    def _init_openalgo(self):
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
        for rule in self.learning_rules:
            if not rule.get("is_active"):
                continue
            condition = rule.get("condition_json", {})
            blocked_symbols = condition.get("blocked_symbols", [])
            if symbol in blocked_symbols:
                return True, f"Rule '{rule['rule_name']}': symbol blocked"
            rsi_min = condition.get("rsi_min")
            rsi_max = condition.get("rsi_max")
            if rsi_min is not None and rsi_max is not None:
                if rsi_min <= rsi <= rsi_max:
                    return True, f"Rule '{rule['rule_name']}': RSI {rsi:.1f} in blocked range"
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
        """Scan watchlist using multiple entry strategies."""
        from core.indicators import compute_rsi, support_level, is_near_support, volume_spike, ema

        self._scan_count += 1
        signals: list[TradeSignal] = []
        today_str = date.today().isoformat()

        scanned = 0
        ltp_failures = 0
        candle_failures = 0
        strategy_hits = {}

        logger.info(f"=== Scan #{self._scan_count} starting ({len(self.watchlist)} symbols) ===")

        for symbol in self.watchlist:
            try:
                # Get current price
                ltp = await self.broker.get_ltp(symbol)
                if not ltp:
                    ltp_failures += 1
                    continue

                scanned += 1

                # Get candles for indicators
                candles = await self._get_candles(symbol)
                if candles is None or len(candles) < 15:
                    candle_failures += 1
                    continue

                rsi_series = compute_rsi(candles, settings.rsi_period)
                current_rsi = float(rsi_series.iloc[-1]) if not rsi_series.empty and rsi_series.iloc[-1] is not None else 50
                support = support_level(candles)
                near_support = is_near_support(ltp, support, tolerance_pct=2.5)
                has_volume_spike = volume_spike(candles, threshold=1.5)

                # Compute moving averages
                ema20 = None
                dma50 = None
                if len(candles) >= 20:
                    ema20_series = ema(candles, 20)
                    ema20 = float(ema20_series.iloc[-1]) if not ema20_series.empty and ema20_series.iloc[-1] is not None else None
                if len(candles) >= 50:
                    from core.indicators import sma
                    sma50_series = sma(candles, 50)
                    dma50 = float(sma50_series.iloc[-1]) if not sma50_series.empty and sma50_series.iloc[-1] is not None else None

                # --- Entry Strategy Evaluation ---
                entry_reason = None
                entry_confidence_boost = 0.0

                # Strategy 1: Oversold Bounce (RSI < 40 near support)
                if current_rsi < 40 and near_support:
                    entry_reason = "OVERSOLD_BOUNCE"
                    entry_confidence_boost = 0.15
                    # Extra strong if deeply oversold
                    if current_rsi < 30:
                        entry_confidence_boost = 0.25

                # Strategy 2: Momentum (RSI 40-60, price > DMA50, volume spike)
                elif 40 <= current_rsi <= 60 and dma50 and ltp > dma50 and has_volume_spike:
                    entry_reason = "MOMENTUM"
                    entry_confidence_boost = 0.10

                # Strategy 3: DMA Crossover (price just crossed above 20 EMA)
                elif ema20 and len(candles) >= 2:
                    prev_close = float(candles["close"].iloc[-2])
                    if prev_close < ema20 and ltp >= ema20 and current_rsi < 65:
                        entry_reason = "EMA_CROSSOVER"
                        entry_confidence_boost = 0.10

                # Strategy 4: Support Bounce (price near support, RSI < 50)
                elif near_support and current_rsi < 50:
                    entry_reason = "SUPPORT_BOUNCE"
                    entry_confidence_boost = 0.05

                if not entry_reason:
                    continue

                strategy_hits[entry_reason] = strategy_hits.get(entry_reason, 0) + 1

                # Check learning rules
                skip, skip_reason = self._should_skip(symbol, current_rsi, ltp)
                if skip:
                    logger.info(f"Skipping {symbol}: {skip_reason}")
                    continue

                # Get AI signal
                ai_signal = await self.ai.get_signal(symbol, today_str)

                # AI must agree on BUY
                if ai_signal.action != SignalAction.BUY:
                    logger.debug(
                        f"{symbol}: {entry_reason} but AI says {ai_signal.action}. Skipping."
                    )
                    continue

                # Minimum confidence
                if ai_signal.confidence < 0.4:
                    logger.debug(f"{symbol}: AI confidence too low ({ai_signal.confidence:.2f})")
                    continue

                # Combined confidence
                rsi_confidence = max(0, (50 - current_rsi) / 50)  # Higher when RSI is lower
                combined = 0.5 * ai_signal.confidence + 0.3 * rsi_confidence + 0.2 * entry_confidence_boost + entry_confidence_boost

                signals.append(TradeSignal(
                    symbol=symbol,
                    action=SignalAction.BUY,
                    current_price=ltp,
                    rsi=current_rsi,
                    support=support,
                    ai_signal=ai_signal.action,
                    ai_confidence=ai_signal.confidence,
                    ai_reasoning=f"{entry_reason}: {ai_signal.reasoning[:200]}",
                    combined_confidence=combined,
                ))

                logger.info(
                    f"✅ Signal: BUY {symbol} @ ₹{ltp:.2f} | "
                    f"RSI: {current_rsi:.1f} | Strategy: {entry_reason} | "
                    f"AI: {ai_signal.confidence:.2f} | Combined: {combined:.2f}"
                )

            except Exception as e:
                logger.error(f"Error scanning {symbol}: {e}")
                continue

        # Log scan summary
        logger.info(
            f"=== Scan #{self._scan_count} complete: "
            f"scanned={scanned}/{len(self.watchlist)} | "
            f"ltp_fail={ltp_failures} | candle_fail={candle_failures} | "
            f"signals={len(signals)} | strategies={strategy_hits} ==="
        )

        signals.sort(key=lambda s: s.combined_confidence, reverse=True)
        return signals

    async def _get_candles(self, symbol: str, interval: str = "5") -> Any:
        """Fetch OHLCV candles from Dhan API, with Yahoo Finance fallback."""
        from config.constants import DHAN_SECURITY_IDS
        from core.indicators import candles_from_dhan_data

        security_id = DHAN_SECURITY_IDS.get(symbol)
        if not security_id:
            # No Dhan ID — go straight to Yahoo
            return await self._yahoo_candles(symbol)

        try:
            from dhanhq import dhanhq
            dhan = dhanhq(settings.dhan_client_id, settings.dhan_access_token)
            from datetime import datetime, timedelta

            response = dhan.intraday_minute_data(
                security_id=str(security_id),
                exchange_segment=dhan.NSE,
                instrument_type="EQUITY",
            )

            if response and response.get("data"):
                df = candles_from_dhan_data(response["data"])
                if df is not None and len(df) >= 15:
                    return df

            # Fallback: historical daily
            to_date = datetime.now().strftime("%Y-%m-%d")
            from_date = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
            response = dhan.historical_daily_data(
                security_id=str(security_id),
                exchange_segment=dhan.NSE,
                instrument_type="EQUITY",
                from_date=from_date,
                to_date=to_date,
            )

            if response and response.get("data"):
                df = candles_from_dhan_data(response["data"])
                if df is not None and len(df) >= 15:
                    return df
        except Exception as e:
            logger.debug(f"Dhan candles failed for {symbol}: {e}")

        return await self._yahoo_candles(symbol)

    async def _yahoo_candles(self, symbol: str) -> Any:
        """Fallback: fetch daily candles from Yahoo Finance."""
        import aiohttp
        import pandas as pd

        yahoo_sym = f"{symbol}.NS" if not symbol.endswith(".NS") else symbol
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_sym}?interval=1d&range=3mo"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
                    result = data.get("chart", {}).get("result", [{}])[0]
                    timestamps = result.get("timestamp", [])
                    quote = result.get("indicators", {}).get("quote", [{}])[0]
                    if not timestamps or not quote:
                        return None
                    df = pd.DataFrame({
                        "open": quote.get("open", []),
                        "high": quote.get("high", []),
                        "low": quote.get("low", []),
                        "close": quote.get("close", []),
                        "volume": quote.get("volume", []),
                    })
                    df = df.dropna(subset=["close"])
                    if len(df) < 15:
                        return None
                    return df
        except Exception as e:
            logger.debug(f"Yahoo candles fallback failed for {symbol}: {e}")
            return None

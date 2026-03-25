"""Pre-market scanner for tomorrow's probable trade candidates.

Scans the watchlist using historical data to identify stocks
approaching oversold territory or near support levels.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from config.settings import settings
from config.constants import DHAN_SECURITY_IDS, DEFAULT_WATCHLIST

logger = logging.getLogger(__name__)


@dataclass
class ForecastSignal:
    symbol: str
    last_close: float
    rsi: float
    support: float
    resistance: float
    distance_to_support_pct: float
    estimated_entry: float
    estimated_target: float
    estimated_sl: float
    strength: str  # "Strong", "Medium", "Weak"
    score: float   # 0-100 ranking score
    reason: str


class PreMarketScanner:
    """Scans watchlist for tomorrow's probable trade candidates.

    Uses historical data (no real-time quotes needed) to identify
    stocks approaching buy signals based on RSI + support analysis.
    """

    def __init__(self, watchlist: list[str] | None = None):
        self.watchlist = watchlist or list(DEFAULT_WATCHLIST)

    async def scan_tomorrow(self) -> list[ForecastSignal]:
        """Scan all watchlist stocks and return ranked candidates."""
        signals: list[ForecastSignal] = []

        for symbol in self.watchlist:
            try:
                signal = await self._analyze_symbol(symbol)
                if signal:
                    signals.append(signal)
            except Exception as e:
                logger.error(f"Forecast failed for {symbol}: {e}")
                continue

        # Sort by score (highest first)
        signals.sort(key=lambda s: s.score, reverse=True)
        return signals[:5]  # Top 5

    async def _analyze_symbol(self, symbol: str) -> ForecastSignal | None:
        """Analyze a single symbol for tomorrow's trade potential."""
        security_id = DHAN_SECURITY_IDS.get(symbol)
        if not security_id:
            return None

        candles = await self._fetch_historical(symbol, security_id)
        if candles is None or len(candles) < 20:
            return None

        from core.indicators import compute_rsi, support_level, resistance_level

        # Compute indicators
        rsi_series = compute_rsi(candles, settings.rsi_period)
        if rsi_series is None or rsi_series.empty:
            return None

        current_rsi = float(rsi_series.iloc[-1])
        support = support_level(candles, lookback=20)
        resistance = resistance_level(candles, lookback=20)
        last_close = float(candles["close"].iloc[-1])

        # Score the signal
        score, strength, reason = self._score_signal(
            current_rsi, last_close, support, resistance
        )

        if score < 20:
            return None  # Too weak, skip

        # Estimate entry/target/SL
        estimated_entry = last_close  # Use last close as proxy
        estimated_sl = round(estimated_entry * (1 - settings.stop_loss_percent / 100), 2)
        estimated_target = round(estimated_entry * (1 + settings.target_profit_percent / 100), 2)

        distance_to_support = ((last_close - support) / support * 100) if support > 0 else 99

        return ForecastSignal(
            symbol=symbol,
            last_close=last_close,
            rsi=round(current_rsi, 1),
            support=round(support, 2),
            resistance=round(resistance, 2),
            distance_to_support_pct=round(distance_to_support, 2),
            estimated_entry=estimated_entry,
            estimated_target=estimated_target,
            estimated_sl=estimated_sl,
            strength=strength,
            score=round(score, 1),
            reason=reason,
        )

    def _score_signal(
        self,
        rsi: float,
        price: float,
        support: float,
        resistance: float,
    ) -> tuple[float, str, str]:
        """Score a stock's trade potential (0-100).

        Scoring:
        - RSI proximity to oversold (30): 0-50 points
        - Price proximity to support: 0-30 points
        - Price distance from resistance: 0-20 points (room to grow)
        """
        score = 0.0
        reasons = []

        # RSI score (closer to 30 or below = higher score)
        if rsi <= 25:
            score += 50
            reasons.append(f"RSI deeply oversold ({rsi:.0f})")
        elif rsi <= 30:
            score += 45
            reasons.append(f"RSI oversold ({rsi:.0f})")
        elif rsi <= 35:
            score += 35
            reasons.append(f"RSI approaching oversold ({rsi:.0f})")
        elif rsi <= 40:
            score += 25
            reasons.append(f"RSI moderately low ({rsi:.0f})")
        elif rsi <= 45:
            score += 15
            reasons.append(f"RSI neutral-low ({rsi:.0f})")
        else:
            score += max(0, 10 - (rsi - 45) * 0.5)

        # Support proximity score
        if support > 0:
            dist_pct = (price - support) / support * 100
            if dist_pct <= 1:
                score += 30
                reasons.append("At support level")
            elif dist_pct <= 2:
                score += 25
                reasons.append("Very near support")
            elif dist_pct <= 3:
                score += 20
                reasons.append("Near support")
            elif dist_pct <= 5:
                score += 15
                reasons.append("Approaching support")
            elif dist_pct <= 8:
                score += 8

        # Upside room score (distance to resistance)
        if resistance > price and resistance > 0:
            upside_pct = (resistance - price) / price * 100
            if upside_pct >= 5:
                score += 20
                reasons.append(f"{upside_pct:.1f}% upside to resistance")
            elif upside_pct >= 3:
                score += 15
                reasons.append(f"{upside_pct:.1f}% upside room")
            elif upside_pct >= 1.5:
                score += 10

        # Determine strength
        if score >= 70:
            strength = "Strong"
        elif score >= 45:
            strength = "Medium"
        else:
            strength = "Weak"

        reason = " • ".join(reasons) if reasons else "Neutral"
        return score, strength, reason

    async def _fetch_historical(self, symbol: str, security_id: int):
        """Fetch 30 days of historical daily candles from Dhan."""
        from core.indicators import candles_from_dhan_data

        if not settings.dhan_client_id or not settings.dhan_access_token:
            return None

        try:
            from dhanhq import dhanhq
            dhan = dhanhq(settings.dhan_client_id, settings.dhan_access_token)

            to_date = datetime.now().strftime("%Y-%m-%d")
            from_date = (datetime.now() - timedelta(days=45)).strftime("%Y-%m-%d")

            response = dhan.historical_daily_data(
                security_id=str(security_id),
                exchange_segment=dhan.NSE,
                instrument_type="EQUITY",
                from_date=from_date,
                to_date=to_date,
            )

            if response and response.get("data"):
                return candles_from_dhan_data(response["data"])

            # Fallback to intraday minute data
            response = dhan.intraday_minute_data(
                security_id=str(security_id),
                exchange_segment=dhan.NSE,
                instrument_type="EQUITY",
            )

            if response and response.get("data"):
                return candles_from_dhan_data(response["data"])

        except Exception as e:
            logger.error(f"Historical data fetch failed for {symbol}: {e}")

        return None

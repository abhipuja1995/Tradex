"""Risk manager with all safety guards."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime

from config.settings import settings
from config.constants import TradeStatus

logger = logging.getLogger(__name__)


@dataclass
class RiskCheck:
    allowed: bool
    reason: str


class RiskManager:
    """Enforces all trading risk rules:

    1. Daily investment cap (₹840)
    2. Per-trade cap (₹168)
    3. Max trades per day (5)
    4. Stop loss per trade (1%)
    5. Daily max loss (3% of daily cap)
    6. Consecutive loss guard (3 in a row → pause)
    7. Daily profit target (5% → stop trading)
    """

    def __init__(self):
        self._pause_until: datetime | None = None

    def can_trade(
        self,
        daily_invested: float,
        daily_pnl: float,
        trades_today: list[dict],
    ) -> RiskCheck:
        """Check all risk guards before allowing a new trade."""

        # Check pause
        if self._pause_until and datetime.now() < self._pause_until:
            remaining = (self._pause_until - datetime.now()).seconds // 60
            return RiskCheck(False, f"Bot paused for {remaining} more minutes (consecutive losses)")

        # 1. Daily investment cap
        if daily_invested >= settings.daily_cap_inr:
            return RiskCheck(False, f"Daily cap reached: ₹{daily_invested:.2f} / ₹{settings.daily_cap_inr}")

        # 2. Max trades per day
        trade_count = len(trades_today)
        if trade_count >= settings.max_trades_per_day:
            return RiskCheck(False, f"Max trades reached: {trade_count} / {settings.max_trades_per_day}")

        # 3. Daily max loss guard
        max_loss = settings.daily_cap_inr * settings.daily_max_loss_percent / 100
        if daily_pnl <= -max_loss:
            return RiskCheck(False, f"Daily loss limit hit: ₹{daily_pnl:.2f} (max: -₹{max_loss:.2f})")

        # 4. Daily profit target reached
        target = settings.daily_cap_inr * settings.daily_target_percent / 100
        if daily_pnl >= target:
            return RiskCheck(False, f"Daily profit target reached: ₹{daily_pnl:.2f} (target: ₹{target:.2f})")

        # 5. Consecutive loss guard
        recent_closed = [
            t for t in trades_today
            if t.get("status") in (TradeStatus.CLOSED, TradeStatus.STOPPED_OUT)
        ]
        if len(recent_closed) >= settings.consecutive_loss_limit:
            last_n = recent_closed[-settings.consecutive_loss_limit:]
            all_losses = all(
                (t.get("pnl") or 0) < 0 for t in last_n
            )
            if all_losses:
                from datetime import timedelta
                self._pause_until = datetime.now() + timedelta(minutes=30)
                return RiskCheck(
                    False,
                    f"{settings.consecutive_loss_limit} consecutive losses. Pausing 30 minutes."
                )

        # 6. Check remaining daily cap allows at least one trade
        remaining_cap = settings.daily_cap_inr - daily_invested
        if remaining_cap < 10:  # Less than ₹10 remaining
            return RiskCheck(False, f"Insufficient remaining cap: ₹{remaining_cap:.2f}")

        return RiskCheck(True, "All guards passed")

    def size_position(self, price: float) -> int:
        """Calculate position size (quantity) within per-trade cap.

        Returns 0 if stock price exceeds per-trade cap.
        """
        if price <= 0:
            return 0
        qty = math.floor(settings.per_trade_cap_inr / price)
        return max(qty, 0)

    def calculate_stop_loss(self, entry_price: float) -> float:
        """Calculate stop loss price (1% below entry)."""
        return round(entry_price * (1 - settings.stop_loss_percent / 100), 2)

    def calculate_target(self, entry_price: float) -> float:
        """Calculate target price (1.5% above entry)."""
        return round(entry_price * (1 + settings.target_profit_percent / 100), 2)

    def should_exit(self, entry_price: float, current_price: float) -> tuple[bool, str]:
        """Check if position should be exited."""
        stop_loss = self.calculate_stop_loss(entry_price)
        target = self.calculate_target(entry_price)

        if current_price <= stop_loss:
            return True, "STOP_LOSS"
        if current_price >= target:
            return True, "TARGET_HIT"
        return False, ""

    def clear_pause(self):
        """Manually clear the consecutive loss pause."""
        self._pause_until = None
        logger.info("Consecutive loss pause cleared")

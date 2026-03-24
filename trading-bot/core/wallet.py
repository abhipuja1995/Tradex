"""Wallet balance tracking — syncs with OpenAlgo funds API and Supabase."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from config.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class WalletState:
    total_balance: float
    available_balance: float
    locked_in_trades: float
    daily_invested: float
    daily_pnl: float
    trade_date: date

    @property
    def remaining_daily_cap(self) -> float:
        return max(0, settings.daily_cap_inr - self.daily_invested)

    @property
    def daily_pnl_percent(self) -> float:
        if self.daily_invested <= 0:
            return 0.0
        return (self.daily_pnl / self.daily_invested) * 100


class WalletTracker:
    """Manages wallet state with Supabase persistence and OpenAlgo fund sync."""

    def __init__(self):
        self._state: WalletState | None = None

    @property
    def state(self) -> WalletState:
        if self._state is None:
            raise RuntimeError("Wallet not initialized. Call sync() first.")
        return self._state

    async def sync(self, openalgo_client) -> WalletState:
        """Sync wallet from OpenAlgo funds API and DB.

        On a new day, resets daily counters.
        """
        from db.client import get_wallet, reset_daily_wallet

        today = date.today()
        db_wallet = await get_wallet(today)

        # Fetch real balance from OpenAlgo
        funds = await openalgo_client.get_funds()
        total_balance = float(funds.get("availablecash", 0))
        available_balance = total_balance

        if db_wallet and db_wallet["trade_date"] == today.isoformat():
            self._state = WalletState(
                total_balance=total_balance,
                available_balance=available_balance,
                locked_in_trades=db_wallet["locked_in_trades"],
                daily_invested=db_wallet["daily_invested"],
                daily_pnl=db_wallet["daily_pnl"],
                trade_date=today,
            )
        else:
            # New day — reset daily counters
            logger.info(f"New trading day: {today}. Resetting daily counters.")
            await reset_daily_wallet(total_balance, available_balance)
            self._state = WalletState(
                total_balance=total_balance,
                available_balance=available_balance,
                locked_in_trades=0,
                daily_invested=0,
                daily_pnl=0,
                trade_date=today,
            )

        logger.info(
            f"Wallet synced: balance=₹{self._state.total_balance:.2f}, "
            f"invested=₹{self._state.daily_invested:.2f}, "
            f"pnl=₹{self._state.daily_pnl:.2f}, "
            f"remaining=₹{self._state.remaining_daily_cap:.2f}"
        )
        return self._state

    async def record_entry(self, amount: float) -> None:
        """Record a new trade entry (deduct from available, add to invested)."""
        from db.client import upsert_wallet

        state = self.state
        state.daily_invested += amount
        state.locked_in_trades += amount
        state.available_balance -= amount

        await upsert_wallet({
            "total_balance": state.total_balance,
            "available_balance": state.available_balance,
            "locked_in_trades": state.locked_in_trades,
            "daily_invested": state.daily_invested,
            "daily_pnl": state.daily_pnl,
            "trade_date": state.trade_date.isoformat(),
        })

    async def record_exit(self, invested_amount: float, pnl: float) -> None:
        """Record a trade exit (return capital + pnl to available)."""
        from db.client import upsert_wallet

        state = self.state
        state.locked_in_trades -= invested_amount
        state.available_balance += invested_amount + pnl
        state.daily_pnl += pnl

        await upsert_wallet({
            "total_balance": state.total_balance,
            "available_balance": state.available_balance,
            "locked_in_trades": state.locked_in_trades,
            "daily_invested": state.daily_invested,
            "daily_pnl": state.daily_pnl,
            "trade_date": state.trade_date.isoformat(),
        })

        logger.info(f"Exit recorded: invested=₹{invested_amount:.2f}, pnl=₹{pnl:.2f}")

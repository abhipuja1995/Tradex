"""Main trading engine — orchestrates the trading loop."""

from __future__ import annotations

import asyncio
import logging
import signal
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from config.settings import settings
from config.constants import BotState, TradeStatus, JournalEntryType, SignalAction

logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")


def _create_broker():
    """Create the Dhan broker adapter for order execution.

    Architecture:
    - Dhan SDK = execution layer (orders, positions, funds, LTP)
    - OpenAlgo = strategy & automation layer (connected separately)
    """
    from core.dhan_broker import DhanBroker
    logger.info("Using Dhan SDK for order execution")
    return DhanBroker()


class TradingEngine:
    """Main trading loop that orchestrates all components.

    Execution flow (every scan_interval during market hours):
    1. risk_manager.can_trade() — check all guards
    2. ai_signals.get_signal() — TradingAgents multi-agent analysis
    3. strategy.evaluate() — hybrid AI + RSI confirmation
    4. broker.place_order() — execute via Dhan (direct or OpenAlgo)
    5. Position monitor (every 15s): check LTP vs stop_loss/target
    6. At 15:25: force-close open positions
    7. At 15:30: learning.analyze_day(), daily summary alert
    """

    def __init__(self):
        self.state = BotState.STOPPED
        self._shutdown = False

        # Components (initialized in start())
        self.broker = None
        self.strategy = None
        self.risk_manager = None
        self.wallet = None
        self.alerter = None
        self.learning = None

    async def start(self):
        """Initialize all components and start the trading loop."""
        from core.ai_signals import AISignalGenerator
        from core.strategy import HybridStrategy
        from core.risk_manager import RiskManager
        from core.wallet import WalletTracker
        from core.telegram_bot import TelegramBot
        from core.learning import LearningEngine
        from db.client import get_active_rules

        logger.info("Starting trading engine...")

        # Create broker adapter (Dhan direct or OpenAlgo)
        self.broker = _create_broker()

        self.risk_manager = RiskManager()
        self.wallet = WalletTracker()
        self.learning = LearningEngine()

        # Use TelegramBot as the alerter (it has both commands + notifications)
        # The bot instance may be injected by run_bot.py before start()
        if not self.alerter:
            self.alerter = TelegramBot()

        ai_generator = AISignalGenerator()
        rules = await get_active_rules()
        self.strategy = HybridStrategy(ai_generator, self.broker, rules)

        # Sync wallet (graceful — don't crash if broker is unavailable)
        try:
            await self.wallet.sync(self.broker)
        except Exception as e:
            logger.warning(f"Wallet sync failed (broker may be offline): {e}")
            self.wallet.init_default()

        self.state = BotState.RUNNING
        logger.info("Trading engine started")
        await self.alerter.send_message("🤖 <b>Trading bot started</b>")

        # Start main loops
        await asyncio.gather(
            self._scan_loop(),
            self._position_monitor_loop(),
            self._end_of_day_loop(),
        )

    async def shutdown(self):
        """Graceful shutdown: close open positions, then stop."""
        if self._shutdown:
            return
        self._shutdown = True
        self.state = BotState.STOPPED

        logger.info("Shutting down... closing open positions")
        await self._force_close_all()

        if self.alerter:
            await self.alerter.send_message("🛑 <b>Trading bot stopped</b>")

        if self.broker:
            await self.broker.close()
        if self.alerter:
            await self.alerter.close()

        logger.info("Trading engine shut down")

    def pause(self):
        self.state = BotState.PAUSED
        logger.info("Trading engine paused")

    def resume(self):
        self.state = BotState.RUNNING
        self.risk_manager.clear_pause()
        logger.info("Trading engine resumed")

    def update_dhan_token(self, token: str):
        """Update Dhan access token (called from postback endpoint)."""
        settings.dhan_access_token = token
        if self.broker and hasattr(self.broker, "refresh_token"):
            self.broker.refresh_token(token)
            logger.info("Dhan token updated in broker adapter")

    # --- Main Loops ---

    async def _scan_loop(self):
        """Main scanning loop — runs every scan_interval during market hours."""
        while not self._shutdown:
            try:
                if not self._is_scan_window():
                    if self.state not in (BotState.STOPPED, BotState.PAUSED):
                        self.state = BotState.WAITING_MARKET
                    await asyncio.sleep(30)
                    continue

                if self.state == BotState.PAUSED:
                    await asyncio.sleep(10)
                    continue

                self.state = BotState.RUNNING
                await self._run_scan_cycle()

            except Exception as e:
                logger.error(f"Scan loop error: {e}", exc_info=True)
                if self.alerter:
                    await self.alerter.notify_error(f"Scan loop error: {e}")

            await asyncio.sleep(settings.scan_interval_seconds)

    async def _position_monitor_loop(self):
        """Monitor open positions every 15 seconds for stop loss / target."""
        while not self._shutdown:
            try:
                if self.state in (BotState.STOPPED,):
                    await asyncio.sleep(5)
                    continue

                await self._check_open_positions()
            except Exception as e:
                logger.error(f"Position monitor error: {e}", exc_info=True)

            await asyncio.sleep(15)

    async def _end_of_day_loop(self):
        """End-of-day tasks: force close, analysis, summary."""
        while not self._shutdown:
            now = datetime.now(IST)
            force_close_h, force_close_m = map(int, settings.force_close.split(":"))
            market_close_h, market_close_m = map(int, settings.market_close.split(":"))

            # Force close at 15:25
            if now.hour == force_close_h and now.minute == force_close_m:
                logger.info("Force close time reached")
                await self._force_close_all()
                await asyncio.sleep(60)

            # End-of-day analysis at 15:30
            if now.hour == market_close_h and now.minute == market_close_m:
                logger.info("Market close: running end-of-day analysis")
                await self._end_of_day()
                await asyncio.sleep(60)

            await asyncio.sleep(30)

    # --- Core Logic ---

    async def _run_scan_cycle(self):
        """Single scan cycle: check guards → scan signals → execute trades."""
        from db.client import get_trades_today

        trades_today = await get_trades_today()
        wallet_state = self.wallet.state

        # Check risk guards
        check = self.risk_manager.can_trade(
            daily_invested=wallet_state.daily_invested,
            daily_pnl=wallet_state.daily_pnl,
            trades_today=trades_today,
        )

        if not check.allowed:
            logger.info(f"Cannot trade: {check.reason}")
            if "loss" in check.reason.lower() or "pause" in check.reason.lower():
                await self.alerter.notify_guard_triggered(check.reason)
            return

        # Scan for signals
        signals = await self.strategy.scan()
        if not signals:
            return

        # Execute top signal (one trade per scan cycle)
        signal = signals[0]
        await self._execute_trade(signal)

    async def _execute_trade(self, signal) -> None:
        """Execute a trade from a signal."""
        from db.client import insert_trade, insert_ai_decision

        qty = self.risk_manager.size_position(signal.current_price)
        if qty == 0:
            logger.info(f"Stock {signal.symbol} too expensive for per-trade cap")
            return

        invested_amount = qty * signal.current_price
        stop_loss = self.risk_manager.calculate_stop_loss(signal.current_price)
        target = self.risk_manager.calculate_target(signal.current_price)

        # Place order
        if settings.paper_trading:
            order_id = f"PAPER-{datetime.now().strftime('%H%M%S')}"
            logger.info(f"PAPER TRADE: BUY {qty}x {signal.symbol} @ ₹{signal.current_price:.2f}")
        else:
            order_resp = await self.broker.place_order(
                symbol=signal.symbol,
                action="BUY",
                quantity=qty,
                price_type="MARKET",
            )
            order_id = order_resp.order_id

        # Save AI decision
        await insert_ai_decision({
            "symbol": signal.symbol,
            "signal": signal.ai_signal.value,
            "confidence": signal.ai_confidence,
            "final_reasoning": signal.ai_reasoning,
        })

        # Save trade
        trade = {
            "symbol": signal.symbol,
            "direction": "BUY",
            "quantity": qty,
            "entry_price": signal.current_price,
            "stop_loss_price": stop_loss,
            "target_price": target,
            "status": TradeStatus.OPEN,
            "openalgo_order_id": order_id,
            "strategy": "HYBRID_AI_RSI",
            "rsi_at_entry": signal.rsi,
            "support_level": signal.support,
            "ai_signal": signal.ai_signal.value,
            "ai_confidence": signal.ai_confidence,
            "ai_reasoning": signal.ai_reasoning[:500],
            "paper_trade": settings.paper_trading,
        }
        saved = await insert_trade(trade)

        # Update wallet
        await self.wallet.record_entry(invested_amount)

        # Alert
        await self.alerter.notify_entry({**trade, "id": saved["id"]})

        logger.info(
            f"Trade executed: BUY {qty}x {signal.symbol} @ ₹{signal.current_price:.2f} | "
            f"SL: ₹{stop_loss:.2f} | Target: ₹{target:.2f}"
        )

    async def _check_open_positions(self):
        """Check all open positions against stop loss and target."""
        from db.client import get_open_trades

        open_trades = await get_open_trades()
        if not open_trades:
            return

        for trade in open_trades:
            symbol = trade["symbol"]
            ltp = await self.broker.get_ltp(symbol)
            if ltp is None:
                continue

            entry_price = float(trade["entry_price"])
            should_exit, reason = self.risk_manager.should_exit(entry_price, ltp)

            if should_exit:
                await self._exit_trade(trade, ltp, reason)

    async def _exit_trade(self, trade: dict[str, Any], exit_price: float, reason: str):
        """Exit an open trade."""
        from db.client import update_trade, insert_journal_entry

        entry_price = float(trade["entry_price"])
        qty = trade["quantity"]
        pnl = (exit_price - entry_price) * qty
        pnl_pct = ((exit_price - entry_price) / entry_price) * 100
        invested = entry_price * qty

        status = TradeStatus.STOPPED_OUT if reason == "STOP_LOSS" else TradeStatus.CLOSED

        # Close position (if not paper)
        if not settings.paper_trading:
            await self.broker.close_position(trade["symbol"])

        # Update trade in DB
        await update_trade(trade["id"], {
            "exit_price": exit_price,
            "pnl": round(pnl, 2),
            "pnl_percent": round(pnl_pct, 3),
            "status": status,
            "exit_time": datetime.utcnow().isoformat(),
        })

        # Update wallet
        await self.wallet.record_exit(invested, pnl)

        # Journal entry
        await insert_journal_entry(
            JournalEntryType.TRADE,
            f"{'Win' if pnl >= 0 else 'Loss'}: {trade['symbol']} — {reason}",
            (
                f"Entry: ₹{entry_price:.2f} → Exit: ₹{exit_price:.2f}\n"
                f"Qty: {qty} | PnL: ₹{pnl:+.2f} ({pnl_pct:+.2f}%)\n"
                f"Reason: {reason}"
            ),
            trade_id=trade["id"],
            tags=["win" if pnl >= 0 else "loss", reason.lower()],
        )

        # Alert
        trade_with_exit = {
            **trade,
            "exit_price": exit_price,
            "pnl": pnl,
            "pnl_percent": pnl_pct,
            "status": status,
        }
        await self.alerter.notify_exit(trade_with_exit)

        logger.info(
            f"Trade exited: {trade['symbol']} @ ₹{exit_price:.2f} | "
            f"PnL: ₹{pnl:+.2f} ({pnl_pct:+.2f}%) | Reason: {reason}"
        )

    async def _force_close_all(self):
        """Force close all open positions (end of day or shutdown)."""
        from db.client import get_open_trades

        open_trades = await get_open_trades()
        for trade in open_trades:
            ltp = await self.broker.get_ltp(trade["symbol"])
            if ltp:
                await self._exit_trade(trade, ltp, "FORCE_CLOSE")

    async def _end_of_day(self):
        """Run end-of-day analysis and send summary."""
        from db.client import get_trades_today, upsert_daily_performance

        trades = await get_trades_today()
        closed = [t for t in trades if t["status"] in (TradeStatus.CLOSED, TradeStatus.STOPPED_OUT)]

        wins = sum(1 for t in closed if (t.get("pnl") or 0) >= 0)
        losses = sum(1 for t in closed if (t.get("pnl") or 0) < 0)
        total_pnl = sum(t.get("pnl", 0) for t in closed)
        total_invested = self.wallet.state.daily_invested

        pnl_pct = (total_pnl / total_invested * 100) if total_invested > 0 else 0

        perf = {
            "trade_date": date.today().isoformat(),
            "total_trades": len(closed),
            "winning_trades": wins,
            "losing_trades": losses,
            "total_invested": total_invested,
            "total_pnl": round(total_pnl, 2),
            "pnl_percent": round(pnl_pct, 3),
            "daily_cap_hit": total_invested >= settings.daily_cap_inr,
            "profit_target_hit": total_pnl >= settings.daily_cap_inr * settings.daily_target_percent / 100,
        }
        await upsert_daily_performance(perf)

        # Run learning analysis
        await self.learning.analyze_day()

        # Send summary
        await self.alerter.notify_daily_summary(perf)

        logger.info(f"End of day complete: {perf}")

    # --- Helpers ---

    def _is_scan_window(self) -> bool:
        """Check if current time is within the scanning window."""
        now = datetime.now(IST)
        open_h, open_m = map(int, settings.market_open.split(":"))
        stop_h, stop_m = map(int, settings.scan_stop.split(":"))

        market_open = now.replace(hour=open_h, minute=open_m, second=0)
        scan_stop = now.replace(hour=stop_h, minute=stop_m, second=0)

        return market_open <= now <= scan_stop

    def get_status(self) -> dict[str, Any]:
        """Get current bot status for API."""
        wallet = self.wallet.state if self.wallet and self.wallet._state else None
        return {
            "state": self.state.value,
            "paper_trading": settings.paper_trading,
            "market_open": self._is_scan_window(),
            "wallet": {
                "total_balance": wallet.total_balance if wallet else 0,
                "daily_invested": wallet.daily_invested if wallet else 0,
                "daily_pnl": wallet.daily_pnl if wallet else 0,
                "remaining_cap": wallet.remaining_daily_cap if wallet else settings.daily_cap_inr,
            } if wallet else None,
        }

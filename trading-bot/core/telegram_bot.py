"""Telegram bot with command handler for interactive control.

Handles commands: /start, /status, /trades, /balance, /pause, /resume, /stop, /help
Runs as a long-polling bot alongside the trading engine.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Any

import httpx

from config.settings import settings

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"


class TelegramBot:
    """Interactive Telegram bot for controlling the trading engine."""

    def __init__(self):
        self.token = settings.telegram_bot_token
        self.chat_id = settings.telegram_chat_id
        self._client = httpx.AsyncClient(timeout=30.0)
        self._engine = None
        self._offset = 0
        self._running = False
        self.enabled = bool(self.token)

    def set_engine(self, engine):
        self._engine = engine

    @property
    def base_url(self) -> str:
        return f"{TELEGRAM_API}/bot{self.token}"

    async def send_message(self, text: str, chat_id: str | None = None) -> bool:
        """Send a message to a Telegram chat."""
        if not self.enabled:
            logger.debug(f"Telegram disabled. Would send: {text[:100]}...")
            return False

        target = chat_id or self.chat_id
        if not target:
            return False

        try:
            resp = await self._client.post(
                f"{self.base_url}/sendMessage",
                json={
                    "chat_id": target,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
            )
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return False

    async def start_polling(self):
        """Start long-polling for Telegram updates."""
        if not self.enabled:
            logger.info("Telegram bot disabled (no token configured)")
            return

        self._running = True
        logger.info("Telegram bot started polling for commands")

        # Auto-detect chat_id if not set
        if not self.chat_id:
            logger.info("No TELEGRAM_CHAT_ID set — will auto-detect from first message")

        while self._running:
            try:
                updates = await self._get_updates()
                for update in updates:
                    await self._handle_update(update)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Telegram polling error: {e}")
                await asyncio.sleep(5)

    async def stop_polling(self):
        self._running = False

    async def _get_updates(self) -> list[dict]:
        """Long-poll for new messages."""
        try:
            resp = await self._client.get(
                f"{self.base_url}/getUpdates",
                params={
                    "offset": self._offset,
                    "timeout": 20,
                    "allowed_updates": '["message"]',
                },
                timeout=30.0,
            )
            data = resp.json()
            if data.get("ok") and data.get("result"):
                updates = data["result"]
                if updates:
                    self._offset = updates[-1]["update_id"] + 1
                return updates
        except httpx.TimeoutException:
            pass  # Normal for long polling
        except Exception as e:
            logger.error(f"getUpdates error: {e}")
            await asyncio.sleep(2)
        return []

    async def _handle_update(self, update: dict):
        """Route incoming messages to command handlers."""
        message = update.get("message", {})
        text = message.get("text", "").strip()
        chat_id = str(message.get("chat", {}).get("id", ""))

        if not text or not chat_id:
            return

        # Auto-set chat_id from first message
        if not self.chat_id:
            self.chat_id = chat_id
            settings.telegram_chat_id = chat_id
            logger.info(f"Auto-detected Telegram chat_id: {chat_id}")
            await self.send_message("✅ Chat linked! I'll send trade alerts here.", chat_id)

        # Security: only respond to configured chat
        if self.chat_id and chat_id != self.chat_id:
            await self.send_message("⛔ Unauthorized. This bot is private.", chat_id)
            return

        # Route commands
        command = text.split()[0].lower().split("@")[0]  # Handle /cmd@botname

        handlers = {
            "/start": self._cmd_start,
            "/help": self._cmd_help,
            "/status": self._cmd_status,
            "/trades": self._cmd_trades,
            "/balance": self._cmd_balance,
            "/pnl": self._cmd_pnl,
            "/pause": self._cmd_pause,
            "/resume": self._cmd_resume,
            "/stop": self._cmd_stop,
            "/rules": self._cmd_rules,
            "/watchlist": self._cmd_watchlist,
        }

        handler = handlers.get(command)
        if handler:
            await handler(chat_id)
        elif text.startswith("/"):
            await self.send_message(f"Unknown command: {command}\nUse /help for available commands.", chat_id)

    # --- Command Handlers ---

    async def _cmd_start(self, chat_id: str):
        await self.send_message(
            "🤖 <b>TradeX Micro-Trading Bot</b>\n\n"
            "I'm your automated trading assistant for Indian stocks.\n\n"
            f"Mode: <b>{'📝 PAPER' if settings.paper_trading else '💰 LIVE'}</b>\n"
            f"Daily Cap: <b>₹{settings.daily_cap_inr:.0f}</b>\n"
            f"Max Trades: <b>{settings.max_trades_per_day}/day</b>\n\n"
            "Use /help to see all commands.",
            chat_id,
        )

    async def _cmd_help(self, chat_id: str):
        await self.send_message(
            "📋 <b>Available Commands</b>\n\n"
            "/status — Bot state & market info\n"
            "/trades — Today's trades\n"
            "/balance — Wallet & fund details\n"
            "/pnl — Today's P&L summary\n"
            "/pause — Pause the trading engine\n"
            "/resume — Resume trading\n"
            "/stop — Stop the bot\n"
            "/rules — Active learning rules\n"
            "/watchlist — Current watchlist\n"
            "/help — This help message",
            chat_id,
        )

    async def _cmd_status(self, chat_id: str):
        if not self._engine:
            await self.send_message("⚠️ Engine not initialized", chat_id)
            return

        try:
            status = self._engine.get_status()
            state = status.get("state", "UNKNOWN")
            state_emoji = {"RUNNING": "🟢", "PAUSED": "🟡", "STOPPED": "🔴", "WAITING_MARKET": "⏳"}.get(state, "❓")

            wallet = status.get("wallet", {})
            text = (
                f"{state_emoji} <b>Bot Status: {state}</b>\n\n"
                f"Mode: {'📝 Paper' if status.get('paper_trading') else '💰 Live'}\n"
                f"Market: {'Open ✅' if status.get('market_open') else 'Closed ❌'}\n"
            )

            if wallet:
                text += (
                    f"\n💰 <b>Wallet</b>\n"
                    f"Balance: ₹{wallet.get('total_balance', 0):.2f}\n"
                    f"Invested: ₹{wallet.get('daily_invested', 0):.2f}\n"
                    f"PnL: ₹{wallet.get('daily_pnl', 0):+.2f}\n"
                    f"Remaining: ₹{wallet.get('remaining_cap', 0):.2f}\n"
                )

            await self.send_message(text, chat_id)
        except Exception as e:
            await self.send_message(f"Error getting status: {e}", chat_id)

    async def _cmd_trades(self, chat_id: str):
        from db.client import get_trades_today

        try:
            trades = await get_trades_today()
            if not trades:
                await self.send_message("📭 No trades today", chat_id)
                return

            text = f"📊 <b>Today's Trades ({len(trades)})</b>\n\n"
            for t in trades[:10]:
                pnl = t.get("pnl", 0) or 0
                status = t.get("status", "UNKNOWN")
                emoji = "🟢" if pnl > 0 else "🔴" if pnl < 0 else "⏳"
                paper = "📝" if t.get("paper_trade") else ""

                text += (
                    f"{emoji}{paper} <b>{t['symbol']}</b> "
                    f"₹{t.get('entry_price', 0):.2f}"
                )
                if t.get("exit_price"):
                    text += f" → ₹{t['exit_price']:.2f}"
                text += f" | {status}"
                if pnl:
                    text += f" | ₹{pnl:+.2f}"
                text += "\n"

            await self.send_message(text, chat_id)
        except Exception as e:
            await self.send_message(f"Error fetching trades: {e}", chat_id)

    async def _cmd_balance(self, chat_id: str):
        if not self._engine or not self._engine.wallet._state:
            # Try fetching from broker directly
            try:
                from core.dhan_broker import DhanBroker
                broker = DhanBroker()
                funds = await broker.get_funds()
                await self.send_message(
                    f"💰 <b>Dhan Funds</b>\n"
                    f"Available: ₹{funds.get('availablecash', 0):.2f}\n"
                    f"Utilized: ₹{funds.get('utilized', 0):.2f}",
                    chat_id,
                )
            except Exception as e:
                await self.send_message(f"⚠️ Could not fetch balance: {e}", chat_id)
            return

        w = self._engine.wallet.state
        await self.send_message(
            f"💰 <b>Wallet — {w.trade_date}</b>\n\n"
            f"Total Balance: ₹{w.total_balance:.2f}\n"
            f"Available: ₹{w.available_balance:.2f}\n"
            f"Locked in Trades: ₹{w.locked_in_trades:.2f}\n"
            f"Daily Invested: ₹{w.daily_invested:.2f}\n"
            f"Daily PnL: ₹{w.daily_pnl:+.2f} ({w.daily_pnl_percent:+.2f}%)\n"
            f"Remaining Cap: ₹{w.remaining_daily_cap:.2f}",
            chat_id,
        )

    async def _cmd_pnl(self, chat_id: str):
        from db.client import get_trades_today

        try:
            trades = await get_trades_today()
            closed = [t for t in trades if t.get("status") in ("CLOSED", "STOPPED_OUT")]

            if not closed:
                await self.send_message("📭 No closed trades today", chat_id)
                return

            wins = sum(1 for t in closed if (t.get("pnl") or 0) >= 0)
            losses = len(closed) - wins
            total_pnl = sum(t.get("pnl", 0) or 0 for t in closed)
            total_invested = sum(
                float(t.get("entry_price", 0)) * int(t.get("quantity", 0))
                for t in closed
            )
            pnl_pct = (total_pnl / total_invested * 100) if total_invested > 0 else 0
            win_rate = (wins / len(closed) * 100) if closed else 0

            emoji = "🟢" if total_pnl >= 0 else "🔴"

            await self.send_message(
                f"{emoji} <b>Today's P&L</b>\n\n"
                f"Trades: {len(closed)} (W: {wins} / L: {losses})\n"
                f"Win Rate: {win_rate:.0f}%\n"
                f"Invested: ₹{total_invested:.2f}\n"
                f"PnL: ₹{total_pnl:+.2f} ({pnl_pct:+.2f}%)",
                chat_id,
            )
        except Exception as e:
            await self.send_message(f"Error: {e}", chat_id)

    async def _cmd_pause(self, chat_id: str):
        if not self._engine:
            await self.send_message("⚠️ Engine not initialized", chat_id)
            return
        self._engine.pause()
        await self.send_message("⏸️ Trading engine <b>PAUSED</b>", chat_id)

    async def _cmd_resume(self, chat_id: str):
        if not self._engine:
            await self.send_message("⚠️ Engine not initialized", chat_id)
            return
        self._engine.resume()
        await self.send_message("▶️ Trading engine <b>RESUMED</b>", chat_id)

    async def _cmd_stop(self, chat_id: str):
        if not self._engine:
            await self.send_message("⚠️ Engine not initialized", chat_id)
            return
        await self.send_message("🛑 Stopping trading engine...", chat_id)
        await self._engine.shutdown()
        await self.send_message("✅ Engine stopped. Open positions have been closed.", chat_id)

    async def _cmd_rules(self, chat_id: str):
        from db.client import get_active_rules

        try:
            rules = await get_active_rules()
            if not rules:
                await self.send_message("📭 No active learning rules", chat_id)
                return

            text = f"📏 <b>Active Rules ({len(rules)})</b>\n\n"
            for r in rules:
                text += f"• <b>{r['rule_name']}</b>\n  {r.get('description', '')}\n"

            await self.send_message(text, chat_id)
        except Exception as e:
            await self.send_message(f"Error: {e}", chat_id)

    async def _cmd_watchlist(self, chat_id: str):
        if self._engine and self._engine.strategy:
            symbols = self._engine.strategy.watchlist
        else:
            from config.constants import DEFAULT_WATCHLIST
            symbols = DEFAULT_WATCHLIST

        text = f"📋 <b>Watchlist ({len(symbols)} stocks)</b>\n\n"
        for i, s in enumerate(symbols, 1):
            text += f"{i}. {s}\n"

        await self.send_message(text, chat_id)

    # --- Notification Methods (same as TelegramAlerter) ---

    async def notify_entry(self, trade: dict[str, Any]) -> None:
        symbol = trade["symbol"]
        qty = trade["quantity"]
        price = trade["entry_price"]
        sl = trade["stop_loss_price"]
        target = trade["target_price"]
        rsi = trade.get("rsi_at_entry", "N/A")
        ai = trade.get("ai_signal", "N/A")
        confidence = trade.get("ai_confidence", 0)
        paper = "PAPER " if trade.get("paper_trade") else ""

        text = (
            f"📈 <b>{paper}BUY {symbol}</b>\n"
            f"Price: ₹{price:.2f} | Qty: {qty}\n"
            f"SL: ₹{sl:.2f} | Target: ₹{target:.2f}\n"
            f"RSI: {rsi} | AI: {ai} ({confidence:.0%})\n"
            f"Strategy: {trade.get('strategy', 'HYBRID_AI_RSI')}"
        )
        await self.send_message(text)

    async def notify_exit(self, trade: dict[str, Any]) -> None:
        symbol = trade["symbol"]
        entry = trade["entry_price"]
        exit_price = trade.get("exit_price", 0)
        pnl = trade.get("pnl", 0)
        pnl_pct = trade.get("pnl_percent", 0)
        status = trade.get("status", "CLOSED")
        paper = "PAPER " if trade.get("paper_trade") else ""

        emoji = "✅" if pnl >= 0 else "❌"
        reason = "Target Hit" if status == "CLOSED" and pnl >= 0 else "Stop Loss" if status == "STOPPED_OUT" else "Closed"

        text = (
            f"{emoji} <b>{paper}SOLD {symbol}</b>\n"
            f"Entry: ₹{entry:.2f} → Exit: ₹{exit_price:.2f}\n"
            f"PnL: ₹{pnl:+.2f} ({pnl_pct:+.2f}%)\n"
            f"Reason: {reason}"
        )
        await self.send_message(text)

    async def notify_guard_triggered(self, reason: str) -> None:
        await self.send_message(f"⚠️ <b>GUARD TRIGGERED</b>\n{reason}\nBot is paused.")

    async def notify_daily_summary(self, perf: dict[str, Any]) -> None:
        total = perf.get("total_trades", 0)
        wins = perf.get("winning_trades", 0)
        losses = perf.get("losing_trades", 0)
        pnl = perf.get("total_pnl", 0)
        pnl_pct = perf.get("pnl_percent", 0)
        invested = perf.get("total_invested", 0)
        win_rate = (wins / total * 100) if total > 0 else 0
        emoji = "🟢" if pnl >= 0 else "🔴"

        text = (
            f"{emoji} <b>DAILY SUMMARY — {perf.get('trade_date', 'Today')}</b>\n\n"
            f"Trades: {total} (W: {wins} / L: {losses})\n"
            f"Win Rate: {win_rate:.0f}%\n"
            f"Invested: ₹{invested:.2f}\n"
            f"PnL: ₹{pnl:+.2f} ({pnl_pct:+.2f}%)"
        )

        if perf.get("daily_cap_hit"):
            text += "\n📊 Daily cap was reached"
        if perf.get("loss_guard_triggered"):
            text += "\n🛑 Loss guard was triggered"
        if perf.get("profit_target_hit"):
            text += "\n🎯 Profit target was hit"

        await self.send_message(text)

    async def notify_error(self, error: str) -> None:
        await self.send_message(f"🚨 <b>ERROR</b>\n{error}")

    async def close(self):
        self._running = False
        await self._client.aclose()

"""Telegram notification system for trade alerts."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from config.settings import settings

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"


class TelegramAlerter:
    """Sends trading alerts via Telegram Bot API."""

    def __init__(self):
        self.token = settings.telegram_bot_token
        self.chat_id = settings.telegram_chat_id
        self._client = httpx.AsyncClient(timeout=10.0)
        self.enabled = bool(self.token and self.chat_id)

    async def _send(self, text: str) -> bool:
        if not self.enabled:
            logger.debug(f"Telegram disabled. Would send: {text[:100]}...")
            return False

        try:
            url = f"{TELEGRAM_API}/bot{self.token}/sendMessage"
            resp = await self._client.post(url, json={
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            })
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return False

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
        await self._send(text)

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
        await self._send(text)

    async def notify_guard_triggered(self, reason: str) -> None:
        text = f"⚠️ <b>GUARD TRIGGERED</b>\n{reason}\nBot is paused."
        await self._send(text)

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
            f"PnL: ₹{pnl:+.2f} ({pnl_pct:+.2f}%)\n"
        )

        if perf.get("daily_cap_hit"):
            text += "📊 Daily cap was reached\n"
        if perf.get("loss_guard_triggered"):
            text += "🛑 Loss guard was triggered\n"
        if perf.get("profit_target_hit"):
            text += "🎯 Profit target was hit\n"

        await self._send(text)

    async def notify_error(self, error: str) -> None:
        text = f"🚨 <b>ERROR</b>\n{error}"
        await self._send(text)

    async def close(self):
        await self._client.aclose()

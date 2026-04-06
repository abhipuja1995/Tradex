"""Telegram bot with command handler for interactive control.

Handles commands: /start, /status, /trades, /balance, /pnl,
/pause, /resume, /stop, /rules, /watchlist, /portfolio, /tomorrow, /help

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
        self._consecutive_errors = 0
        self._backoff_seconds = 2
        self.enabled = bool(self.token)
        self.bot_username = ""

    def set_engine(self, engine):
        self._engine = engine

    @property
    def base_url(self) -> str:
        return f"{TELEGRAM_API}/bot{self.token}"

    # --- Token Validation ---

    async def validate_token(self) -> bool:
        """Validate bot token via getMe API call."""
        if not self.enabled:
            return False

        try:
            resp = await self._client.get(f"{self.base_url}/getMe", timeout=10.0)
            data = resp.json()
            if data.get("ok"):
                bot_info = data["result"]
                self.bot_username = bot_info.get("username", "")
                logger.info(
                    f"✅ Telegram bot validated: @{self.bot_username} "
                    f"(id: {bot_info.get('id')})"
                )
                return True
            else:
                logger.error(
                    f"❌ Telegram bot token INVALID: {data.get('description', 'Unknown error')}. "
                    "Get a new token from @BotFather on Telegram."
                )
                return False
        except Exception as e:
            logger.error(f"❌ Telegram token validation failed: {e}")
            return False

    # --- Message Sending ---

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
            if resp.status_code == 401:
                logger.error("Telegram sendMessage: 401 Unauthorized — token is invalid")
                return False
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return False

    # --- Polling Loop ---

    async def start_polling(self):
        """Start long-polling for Telegram updates with token validation."""
        if not self.enabled:
            logger.info("Telegram bot disabled (no TELEGRAM_BOT_TOKEN)")
            return

        # Validate token before starting
        is_valid = await self.validate_token()
        if not is_valid:
            logger.error(
                "🛑 Telegram bot will NOT start — invalid token. "
                "Set a valid TELEGRAM_BOT_TOKEN env var."
            )
            return

        self._running = True
        self._consecutive_errors = 0
        self._backoff_seconds = 2

        if not self.chat_id:
            logger.info("No TELEGRAM_CHAT_ID set — will auto-detect from first message")

        logger.info(f"Telegram bot @{self.bot_username} polling started")

        while self._running:
            try:
                updates = await self._get_updates()
                if updates is None:
                    # Fatal error (401) — stop polling
                    break
                self._consecutive_errors = 0
                self._backoff_seconds = 2
                for update in updates:
                    await self._handle_update(update)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._consecutive_errors += 1
                logger.error(
                    f"Telegram polling error ({self._consecutive_errors}): {e}"
                )

                if self._consecutive_errors >= 10:
                    logger.error(
                        "🛑 Too many consecutive Telegram errors. Stopping bot."
                    )
                    break

                # Exponential backoff: 2s → 4s → 8s → 16s → 32s → max 60s
                await asyncio.sleep(self._backoff_seconds)
                self._backoff_seconds = min(self._backoff_seconds * 2, 60)

        self._running = False
        logger.info("Telegram bot polling stopped")

    async def stop_polling(self):
        self._running = False

    async def _get_updates(self) -> list[dict] | None:
        """Long-poll for new messages. Returns None on fatal 401 error."""
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

            # Check for 401 — token is invalid, stop polling
            if resp.status_code == 401:
                logger.error(
                    "❌ Telegram API returned 401 Unauthorized. "
                    "Token is invalid or revoked. Stopping polling."
                )
                return None

            data = resp.json()
            if data.get("ok") and data.get("result"):
                updates = data["result"]
                if updates:
                    self._offset = updates[-1]["update_id"] + 1
                return updates
            return []
        except httpx.TimeoutException:
            return []  # Normal for long polling
        except Exception as e:
            raise  # Let caller handle with backoff

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
            await self.send_message(
                "✅ Chat linked! I'll send trade alerts here.\n"
                "Use /help to see all commands.",
                chat_id,
            )

        # Security: only respond to configured chat
        if self.chat_id and chat_id != self.chat_id:
            await self.send_message("⛔ Unauthorized. This bot is private.", chat_id)
            return

        # Route commands
        command = text.split()[0].lower().split("@")[0]

        handlers = {
            "/start": self._cmd_start,
            "/help": self._cmd_help,
            "/status": self._cmd_status,
            "/trades": self._cmd_trades,
            "/balance": self._cmd_balance,
            "/pnl": self._cmd_pnl,
            "/tomorrow": self._cmd_tomorrow,
            "/pause": self._cmd_pause,
            "/resume": self._cmd_resume,
            "/stop": self._cmd_stop,
            "/rules": self._cmd_rules,
            "/watchlist": self._cmd_watchlist,
            "/portfolio": self._cmd_portfolio,
        }

        handler = handlers.get(command)
        if handler:
            try:
                await handler(chat_id)
            except Exception as e:
                logger.error(f"Command {command} failed: {e}", exc_info=True)
                await self.send_message(
                    f"❌ Command failed: {str(e)[:200]}", chat_id
                )
        elif text.startswith("/"):
            await self.send_message(
                f"Unknown command: {command}\nUse /help for available commands.",
                chat_id,
            )

    # ─── Command Handlers ───────────────────────────────────────

    async def _cmd_start(self, chat_id: str):
        """Send daily picks brief with LTP on /start."""
        await self.send_message("🔄 Fetching latest picks & prices...", chat_id)
        try:
            brief = await self._build_daily_brief()
            if brief:
                await self.send_message(brief, chat_id)
                return
        except Exception as e:
            logger.error(f"/start brief failed: {e}", exc_info=True)

        # Fallback: basic welcome
        await self.send_message(
            "🤖 <b>TradeX Micro-Trading Bot</b>\n\n"
            "I'm your automated trading assistant for Indian stocks.\n\n"
            f"Mode: <b>{'📝 PAPER' if settings.paper_trading else '💰 LIVE'}</b>\n"
            f"Daily Cap: <b>₹{settings.daily_cap_inr:.0f}</b>\n"
            f"Max Trades: <b>{settings.max_trades_per_day}/day</b>\n"
            f"Market: <b>{settings.market_open} – {settings.market_close} IST</b>\n\n"
            "Use /help to see all commands.",
            chat_id,
        )

    async def _cmd_help(self, chat_id: str):
        await self.send_message(
            "📋 <b>Available Commands</b>\n\n"
            "📊 <b>Trading</b>\n"
            "/status — Bot state & market info\n"
            "/trades — Today's trades\n"
            "/balance — Wallet & fund details\n"
            "/pnl — Today's P&L summary\n"
            "/tomorrow — Tomorrow's probable trades\n\n"
            "⚙️ <b>Control</b>\n"
            "/pause — Pause the trading engine\n"
            "/resume — Resume trading\n"
            "/stop — Stop the bot\n\n"
            "📋 <b>Info</b>\n"
            "/rules — Active learning rules\n"
            "/watchlist — Current watchlist\n"
            "/portfolio — Weekly portfolio P&L\n"
            "/help — This help message",
            chat_id,
        )

    async def _cmd_status(self, chat_id: str):
        # Always show basic info even without engine
        from datetime import datetime
        from zoneinfo import ZoneInfo

        ist = ZoneInfo("Asia/Kolkata")
        now = datetime.now(ist)
        open_h, open_m = map(int, settings.market_open.split(":"))
        close_h, close_m = map(int, settings.market_close.split(":"))
        market_open_t = now.replace(hour=open_h, minute=open_m, second=0)
        market_close_t = now.replace(hour=close_h, minute=close_m, second=0)
        is_market_open = market_open_t <= now <= market_close_t

        if self._engine:
            try:
                status = self._engine.get_status()
                state = status.get("state", "UNKNOWN")
                state_emoji = {
                    "RUNNING": "🟢", "PAUSED": "🟡",
                    "STOPPED": "🔴", "WAITING_MARKET": "⏳",
                }.get(state, "❓")

                text = (
                    f"{state_emoji} <b>Bot Status: {state}</b>\n\n"
                    f"Mode: {'📝 Paper' if status.get('paper_trading') else '💰 Live'}\n"
                    f"Market: {'Open ✅' if is_market_open else 'Closed ❌'}\n"
                    f"Time: {now.strftime('%H:%M IST')}\n"
                )

                wallet = status.get("wallet")
                if wallet:
                    text += (
                        f"\n💰 <b>Wallet</b>\n"
                        f"Balance: ₹{wallet.get('total_balance', 0):.2f}\n"
                        f"Invested: ₹{wallet.get('daily_invested', 0):.2f}\n"
                        f"PnL: ₹{wallet.get('daily_pnl', 0):+.2f}\n"
                        f"Remaining: ₹{wallet.get('remaining_cap', 0):.2f}\n"
                    )

                await self.send_message(text, chat_id)
                return
            except Exception as e:
                logger.error(f"/status error: {e}")

        # Fallback: no engine or engine error
        await self.send_message(
            f"🔴 <b>Bot Status: ENGINE OFFLINE</b>\n\n"
            f"Mode: {'📝 Paper' if settings.paper_trading else '💰 Live'}\n"
            f"Market: {'Open ✅' if is_market_open else 'Closed ❌'}\n"
            f"Time: {now.strftime('%H:%M IST')}\n"
            f"Daily Cap: ₹{settings.daily_cap_inr:.0f}\n"
            f"\n⚠️ Engine not running. Check server logs.",
            chat_id,
        )

    async def _cmd_trades(self, chat_id: str):
        try:
            from db.client import get_trades_today
            trades = await get_trades_today()
        except Exception as e:
            await self.send_message(
                f"⚠️ Could not fetch trades from database.\nError: {str(e)[:150]}",
                chat_id,
            )
            return

        if not trades:
            await self.send_message("📭 No trades today", chat_id)
            return

        text = f"📊 <b>Today's Trades ({len(trades)})</b>\n\n"
        for t in trades[:10]:
            pnl = t.get("pnl", 0) or 0
            status = t.get("status", "UNKNOWN")
            emoji = "🟢" if pnl > 0 else "🔴" if pnl < 0 else "⏳"
            paper = "📝" if t.get("paper_trade") else ""

            text += f"{emoji}{paper} <b>{t['symbol']}</b> "
            text += f"₹{float(t.get('entry_price', 0)):.2f}"
            if t.get("exit_price"):
                text += f" → ₹{float(t['exit_price']):.2f}"
            text += f" | {status}"
            if pnl:
                text += f" | ₹{pnl:+.2f}"
            text += "\n"

        await self.send_message(text, chat_id)

    async def _cmd_balance(self, chat_id: str):
        # Try engine wallet first
        if self._engine and self._engine.wallet:
            try:
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
                return
            except Exception as e:
                logger.debug(f"Wallet state unavailable: {e}")

        # Fallback: query Dhan directly
        try:
            from core.dhan_broker import DhanBroker
            broker = DhanBroker()
            funds = await broker.get_funds()

            if funds.get("error"):
                raise Exception(funds["error"])

            await self.send_message(
                f"💰 <b>Dhan Account Funds</b>\n\n"
                f"Available: ₹{float(funds.get('availablecash', 0)):.2f}\n"
                f"Utilized: ₹{float(funds.get('utilized', 0)):.2f}",
                chat_id,
            )
        except Exception as e:
            await self.send_message(
                f"💰 <b>Wallet (Default)</b>\n\n"
                f"Daily Cap: ₹{settings.daily_cap_inr:.2f}\n"
                f"Per Trade: ₹{settings.per_trade_cap_inr:.2f}\n"
                f"\n⚠️ Live balance unavailable: {str(e)[:100]}",
                chat_id,
            )

    async def _cmd_pnl(self, chat_id: str):
        try:
            from db.client import get_trades_today
            trades = await get_trades_today()
        except Exception as e:
            await self.send_message(
                f"⚠️ Could not fetch P&L from database.\nError: {str(e)[:150]}",
                chat_id,
            )
            return

        closed = [t for t in trades if t.get("status") in ("CLOSED", "STOPPED_OUT")]

        if not closed:
            open_count = sum(1 for t in trades if t.get("status") == "OPEN")
            msg = "📭 No closed trades today"
            if open_count:
                msg += f"\n⏳ {open_count} trade(s) still open"
            await self.send_message(msg, chat_id)
            return

        wins = sum(1 for t in closed if (t.get("pnl") or 0) >= 0)
        losses = len(closed) - wins
        total_pnl = sum(float(t.get("pnl", 0) or 0) for t in closed)
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

    async def _cmd_tomorrow(self, chat_id: str):
        """Scan watchlist for tomorrow's probable trade candidates."""
        await self.send_message("🔍 Scanning watchlist for tomorrow's signals...", chat_id)

        try:
            from core.forecast import PreMarketScanner

            watchlist = None
            if self._engine and self._engine.strategy:
                watchlist = self._engine.strategy.watchlist

            scanner = PreMarketScanner(watchlist)
            signals = await scanner.scan_tomorrow()

            if not signals:
                await self.send_message(
                    "📭 <b>No strong candidates found</b>\n\n"
                    "No watchlist stocks are near oversold/support levels.\n"
                    "The bot will continue scanning during market hours.",
                    chat_id,
                )
                return

            text = f"🔮 <b>Tomorrow's Probable Trades ({len(signals)})</b>\n\n"

            for i, s in enumerate(signals, 1):
                strength_emoji = {"Strong": "🟢", "Medium": "🟡", "Weak": "🟠"}.get(
                    s.strength, "⚪"
                )

                text += (
                    f"{strength_emoji} <b>{i}. {s.symbol}</b> — {s.strength} ({s.score:.0f}/100)\n"
                    f"   Close: ₹{s.last_close:.2f} | RSI: {s.rsi}\n"
                    f"   Support: ₹{s.support:.2f} ({s.distance_to_support_pct:+.1f}%)\n"
                    f"   Entry: ~₹{s.estimated_entry:.2f} → Target: ₹{s.estimated_target:.2f}\n"
                    f"   SL: ₹{s.estimated_sl:.2f}\n"
                    f"   📝 {s.reason}\n\n"
                )

            text += (
                "<i>⚠️ These are estimates based on historical data. "
                "Actual entry will depend on market open conditions.</i>"
            )

            await self.send_message(text, chat_id)

        except Exception as e:
            logger.error(f"/tomorrow failed: {e}", exc_info=True)
            await self.send_message(
                f"❌ Forecast scan failed: {str(e)[:200]}\n\n"
                "This may happen if Dhan API is unavailable or market data isn't accessible.",
                chat_id,
            )

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
        await self.send_message(
            "✅ Engine stopped. Open positions have been closed.", chat_id
        )

    async def _cmd_rules(self, chat_id: str):
        try:
            from db.client import get_active_rules
            rules = await get_active_rules()
        except Exception as e:
            await self.send_message(
                f"⚠️ Could not fetch rules: {str(e)[:150]}", chat_id
            )
            return

        if not rules:
            await self.send_message("📭 No active learning rules", chat_id)
            return

        text = f"📏 <b>Active Rules ({len(rules)})</b>\n\n"
        for r in rules:
            text += f"• <b>{r.get('rule_name', 'Unnamed')}</b>\n  {r.get('description', 'No description')}\n"

        await self.send_message(text, chat_id)

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

    async def _cmd_portfolio(self, chat_id: str):
        """Show weekly portfolio P&L."""
        await self.send_message("🔄 Updating portfolio prices...", chat_id)
        try:
            from core.weekly_portfolio import get_portfolio_summary
            summary = await get_portfolio_summary()
            await self.send_message(summary, chat_id)
        except Exception as e:
            logger.error(f"/portfolio error: {e}", exc_info=True)
            await self.send_message(f"❌ Portfolio error: {str(e)[:200]}", chat_id)

    # ─── Daily Brief Builder ─────────────────────────────────────

    async def _build_daily_brief(self) -> str | None:
        """Build daily brief directly from Yahoo Finance data."""
        import aiohttp
        from datetime import datetime
        from zoneinfo import ZoneInfo

        ist = ZoneInfo("Asia/Kolkata")
        now = datetime.now(ist)
        date_str = now.strftime("%a, %d %b %Y")
        time_str = now.strftime("%I:%M %p")

        # Nifty 50 watchlist (top liquid stocks)
        NIFTY_STOCKS = [
            "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
            "HINDUNILVR", "ITC", "SBIN", "BHARTIARTL", "KOTAKBANK",
            "LT", "AXISBANK", "BAJFINANCE", "MARUTI", "TITAN",
            "SUNPHARMA", "TATAMOTORS", "WIPRO", "HCLTECH", "ADANIENT",
            "NTPC", "ONGC", "POWERGRID", "COALINDIA", "TATASTEEL",
            "ULTRACEMCO", "NESTLEIND", "BAJAJFINSV", "TECHM", "JSWSTEEL",
        ]

        async def yahoo_chart(symbol: str, session: aiohttp.ClientSession) -> dict | None:
            """Fetch 1Y daily chart from Yahoo Finance."""
            yahoo_sym = f"{symbol}.NS"
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_sym}?interval=1d&range=1y"
            try:
                async with session.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
                    result = data.get("chart", {}).get("result", [{}])[0]
                    meta = result.get("meta", {})
                    closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
                    closes = [c for c in closes if c is not None]
                    if not closes:
                        return None

                    price = meta.get("regularMarketPrice", closes[-1])
                    high_52w = max(closes)
                    low_52w = min(closes)

                    # RSI-14
                    rsi = None
                    if len(closes) >= 15:
                        gains, losses = [], []
                        for j in range(1, min(15, len(closes))):
                            diff = closes[-j] - closes[-j - 1]
                            if diff > 0:
                                gains.append(diff)
                            else:
                                losses.append(abs(diff))
                        avg_gain = sum(gains) / 14 if gains else 0.001
                        avg_loss = sum(losses) / 14 if losses else 0.001
                        rs = avg_gain / avg_loss
                        rsi = 100 - (100 / (1 + rs))

                    # DMA 50/200
                    dma50 = sum(closes[-50:]) / min(50, len(closes)) if len(closes) >= 50 else None
                    dma200 = sum(closes[-200:]) / min(200, len(closes)) if len(closes) >= 200 else None

                    # Fibonacci levels
                    fib_range = high_52w - low_52w
                    fib_levels = {
                        "fib236": high_52w - fib_range * 0.236,
                        "fib382": high_52w - fib_range * 0.382,
                        "fib50": high_52w - fib_range * 0.5,
                        "fib618": high_52w - fib_range * 0.618,
                        "fib786": high_52w - fib_range * 0.786,
                    }
                    # Find nearest support below price (fib floor)
                    supports = sorted([v for v in fib_levels.values() if v < price], reverse=True)
                    fib_floor = supports[0] if supports else low_52w

                    return {
                        "symbol": symbol,
                        "price": round(price, 2),
                        "rsi": round(rsi, 1) if rsi else None,
                        "dma50": round(dma50, 2) if dma50 else None,
                        "dma200": round(dma200, 2) if dma200 else None,
                        "high52w": round(high_52w, 2),
                        "low52w": round(low_52w, 2),
                        "fibFloor": round(fib_floor, 2),
                        "fibLevels": {k: round(v, 2) for k, v in fib_levels.items()},
                    }
            except Exception as e:
                logger.debug(f"Yahoo chart failed for {symbol}: {e}")
                return None

        # Fetch all stocks + gold + macro indicators
        async with aiohttp.ClientSession() as session:
            # Batch: stocks + gold + VIX/DXY
            tasks = [yahoo_chart(s, session) for s in NIFTY_STOCKS]

            # Gold (GC=F) and USDINR
            async def fetch_quote(sym: str) -> dict | None:
                url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=5d"
                try:
                    async with session.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                        if resp.status != 200:
                            return None
                        data = await resp.json()
                        meta = data.get("chart", {}).get("result", [{}])[0].get("meta", {})
                        return {"symbol": sym, "price": meta.get("regularMarketPrice", 0)}
                except Exception:
                    return None

            tasks.extend([fetch_quote("GC=F"), fetch_quote("USDINR=X"), fetch_quote("^VIX"), fetch_quote("DX-Y.NYB")])
            all_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Parse results
        stock_results = []
        for r in all_results[:len(NIFTY_STOCKS)]:
            if isinstance(r, dict) and r:
                stock_results.append(r)

        gold_usd = all_results[len(NIFTY_STOCKS)]
        usdinr = all_results[len(NIFTY_STOCKS) + 1]
        vix_data = all_results[len(NIFTY_STOCKS) + 2]
        dxy_data = all_results[len(NIFTY_STOCKS) + 3]

        if not stock_results:
            return None

        # Score stocks for different horizons
        def score_weekly(s: dict) -> float:
            """Weekly: favor momentum plays with RSI 45-65, above 50DMA."""
            score = 0
            rsi = s.get("rsi")
            if rsi:
                if 45 <= rsi <= 65:
                    score += 40
                elif 30 <= rsi < 45:
                    score += 25
            if s.get("dma50") and s["price"] > s["dma50"]:
                score += 30
            if s.get("dma200") and s["price"] > s["dma200"]:
                score += 15
            # Near fib support bonus
            if s.get("fibFloor"):
                dist = (s["price"] - s["fibFloor"]) / s["price"] * 100
                if 0 < dist < 3:
                    score += 15
            return score

        def score_longterm(s: dict) -> float:
            """6-12M: favor oversold recovery plays, near 52w low."""
            score = 0
            rsi = s.get("rsi")
            if rsi:
                if rsi < 35:
                    score += 40
                elif rsi < 45:
                    score += 25
            # Distance from 52w low
            if s.get("low52w") and s["price"] > 0:
                dist_from_low = (s["price"] - s["low52w"]) / s["price"] * 100
                if dist_from_low < 15:
                    score += 30
                elif dist_from_low < 30:
                    score += 15
            if s.get("dma200") and s["price"] < s["dma200"]:
                score += 15  # Below 200DMA = potential recovery
            return score

        # Generate picks
        weekly_picks = sorted(stock_results, key=score_weekly, reverse=True)[:5]
        longterm_picks = sorted(stock_results, key=score_longterm, reverse=True)[:5]

        # Build message
        lines = [
            "📊 <b>TradeX Daily Brief</b>",
            f"📅 {date_str} | {time_str} IST",
            "",
        ]

        # Macro overview
        macro_parts = []
        if isinstance(vix_data, dict) and vix_data:
            macro_parts.append(f"VIX: {vix_data['price']:.1f}")
        if isinstance(dxy_data, dict) and dxy_data:
            macro_parts.append(f"DXY: {dxy_data['price']:.1f}")
        if macro_parts:
            lines.append(f"🌐 <b>Macro:</b> {' | '.join(macro_parts)}")
            lines.append("")

        # Weekly picks
        lines.append("🇮🇳 <b>📅 Weekly Picks</b>")
        for i, s in enumerate(weekly_picks, 1):
            price = s["price"]
            target = round(price * 1.05, 2)  # 5% target for weekly
            sl = round(price * 0.97, 2)  # 3% SL for weekly
            rsi_str = f" | RSI: {s['rsi']}" if s.get("rsi") else ""
            fib_str = f" | Fib Floor: ₹{s['fibFloor']:,.0f}" if s.get("fibFloor") else ""
            setup = "Momentum" if (s.get("rsi") or 50) >= 45 else "Oversold Bounce"
            signal_emoji = "🟢" if (s.get("rsi") or 50) < 65 else "🟡"

            lines.append(f"{i}. <b>{s['symbol']}</b> {signal_emoji} {setup}")
            lines.append(f"   LTP: ₹{price:,.2f} → Target: ₹{target:,.0f} (+5%) | SL: ₹{sl:,.0f} (-3%)")
            lines.append(f"   {rsi_str.lstrip(' | ')}{fib_str}")
        lines.append("")

        # Long-term picks
        lines.append("🇮🇳 <b>📅 6-12 Month Picks</b>")
        for i, s in enumerate(longterm_picks, 1):
            price = s["price"]
            target = round(price * 1.20, 2)  # 20% target
            sl = round(price * 0.90, 2)  # 10% SL
            rsi_str = f" | RSI: {s['rsi']}" if s.get("rsi") else ""
            fib_str = f" | Fib Floor: ₹{s['fibFloor']:,.0f}" if s.get("fibFloor") else ""
            setup = "Recovery Play" if (s.get("rsi") or 50) < 40 else "Value Buy"

            lines.append(f"{i}. <b>{s['symbol']}</b> 🟢 {setup}")
            lines.append(f"   LTP: ₹{price:,.2f} → Target: ₹{target:,.0f} (+20%) | SL: ₹{sl:,.0f} (-10%)")
            lines.append(f"   {rsi_str.lstrip(' | ')}{fib_str}")
        lines.append("")

        # Gold
        if isinstance(gold_usd, dict) and gold_usd and isinstance(usdinr, dict) and usdinr:
            gold_price = gold_usd["price"]
            fx_rate = usdinr["price"]
            inr_per_10g = round(gold_price * fx_rate / 31.1035 * 10, 0)
            gold_target = round(gold_price * 1.08, 0)
            gold_sl = round(gold_price * 0.95, 0)

            lines.append("🪙 <b>Gold Setup</b>")
            lines.append(f"   USD: ${gold_price:,.0f} | INR: ₹{inr_per_10g:,.0f}/10g")
            lines.append(f"   Entry: ${gold_price:,.0f} → Target: ${gold_target:,.0f} (+8%) | SL: ${gold_sl:,.0f} (-5%)")
            lines.append("")

        # Today's paper trades
        try:
            from db.client import get_trades_today
            trades = await get_trades_today()
            if trades:
                open_trades = [t for t in trades if t.get("status") == "OPEN"]
                closed_trades = [t for t in trades if t.get("status") in ("CLOSED", "STOPPED_OUT")]
                total_pnl = sum(float(t.get("pnl", 0) or 0) for t in closed_trades)

                lines.append("📈 <b>Today's Paper Trades</b>")
                if open_trades:
                    lines.append(f"   Open: {len(open_trades)}")
                    for t in open_trades[:3]:
                        lines.append(f"   • {t['symbol']} @ ₹{float(t.get('entry_price', 0)):.2f}")
                if closed_trades:
                    pnl_emoji = "🟢" if total_pnl >= 0 else "🔴"
                    lines.append(f"   Closed: {len(closed_trades)} | PnL: {pnl_emoji} ₹{total_pnl:+.2f}")
                lines.append("")
        except Exception:
            pass

        # Weekly portfolio summary
        try:
            from core.weekly_portfolio import get_portfolio_summary
            portfolio = await get_portfolio_summary()
            if portfolio and "No active" not in portfolio:
                lines.append("")
                lines.append(portfolio)
        except Exception:
            pass

        lines.append("<i>Generated by TradeX AI Engine</i>")
        return "\n".join(lines)

    async def send_daily_brief(self) -> bool:
        """Send the daily brief to the configured chat. Called by scheduler."""
        if not self.enabled or not self.chat_id:
            logger.warning("Cannot send daily brief: bot disabled or no chat_id")
            return False

        try:
            brief = await self._build_daily_brief()
            if brief:
                return await self.send_message(brief)
            else:
                logger.warning("Daily brief returned empty — API may be down")
                return False
        except Exception as e:
            logger.error(f"Daily brief send failed: {e}", exc_info=True)
            return False

    # ─── Notification Methods ───────────────────────────────────

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
        reason = (
            "Target Hit"
            if status == "CLOSED" and pnl >= 0
            else "Stop Loss"
            if status == "STOPPED_OUT"
            else "Closed"
        )

        text = (
            f"{emoji} <b>{paper}SOLD {symbol}</b>\n"
            f"Entry: ₹{entry:.2f} → Exit: ₹{exit_price:.2f}\n"
            f"PnL: ₹{pnl:+.2f} ({pnl_pct:+.2f}%)\n"
            f"Reason: {reason}"
        )
        await self.send_message(text)

    async def notify_guard_triggered(self, reason: str) -> None:
        await self.send_message(
            f"⚠️ <b>GUARD TRIGGERED</b>\n{reason}\nBot is paused."
        )

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

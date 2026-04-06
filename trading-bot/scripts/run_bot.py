"""Entry point: starts FastAPI server + Trading Engine + Telegram Bot concurrently."""

import asyncio
import logging
import sys
import threading
from pathlib import Path

import uvicorn

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import settings


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(),
        ],
    )


def start_api_server():
    """Run FastAPI in a background thread."""
    port = settings.effective_port
    uvicorn.run(
        "api.server:app",
        host=settings.fastapi_host,
        port=port,
        log_level="info",
    )


async def setup_telegram_webhook(telegram_bot, logger) -> bool:
    """Set up Telegram webhook so bot can receive /start commands without polling."""
    import httpx

    webhook_url = "https://tradex-bot-production.up.railway.app/api/telegram/webhook"

    try:
        # First validate the token
        is_valid = await telegram_bot.validate_token()
        if not is_valid:
            logger.error("Cannot set webhook — bot token is invalid")
            return False

        # Delete any existing webhook first, then set new one
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Delete old webhook
            await client.post(
                f"{telegram_bot.base_url}/deleteWebhook",
                json={"drop_pending_updates": False},
            )

            # Set new webhook
            resp = await client.post(
                f"{telegram_bot.base_url}/setWebhook",
                json={
                    "url": webhook_url,
                    "allowed_updates": ["message"],
                },
            )
            data = resp.json()
            if data.get("ok"):
                logger.info(f"✅ Telegram webhook set: {webhook_url}")
                return True
            else:
                logger.error(f"Webhook setup failed: {data.get('description')}")
                return False
    except Exception as e:
        logger.error(f"Webhook setup error: {e}")
        return False


async def daily_brief_scheduler(telegram_bot):
    """Send daily brief at 8:45 AM and 10:00 AM IST every day."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    sched_logger = logging.getLogger("scheduler")
    ist = ZoneInfo("Asia/Kolkata")

    # Schedule times (hour, minute) in IST
    SCHEDULE_TIMES = [(8, 45), (10, 0)]

    sent_today: set[tuple[str, int, int]] = set()

    sched_logger.info(
        f"Daily brief scheduler started — will send at "
        f"{', '.join(f'{h}:{m:02d}' for h, m in SCHEDULE_TIMES)} IST"
    )

    while True:
        now = datetime.now(ist)
        today_key = now.strftime("%Y-%m-%d")

        for sched_h, sched_m in SCHEDULE_TIMES:
            key = (today_key, sched_h, sched_m)
            if key in sent_today:
                continue

            # Check if we're within the 2-minute window after scheduled time
            if now.hour == sched_h and sched_m <= now.minute < sched_m + 2:
                sched_logger.info(f"Triggering daily brief for {sched_h}:{sched_m:02d} IST")
                try:
                    success = await telegram_bot.send_daily_brief()
                    if success:
                        sched_logger.info(f"Daily brief sent successfully at {now.strftime('%H:%M')} IST")
                    else:
                        sched_logger.warning(f"Daily brief returned False at {now.strftime('%H:%M')} IST")
                except Exception as e:
                    sched_logger.error(f"Daily brief scheduler error: {e}", exc_info=True)
                sent_today.add(key)

        # Clean up old entries at midnight
        current_date = now.strftime("%Y-%m-%d")
        sent_today = {k for k in sent_today if k[0] == current_date}

        # Check every 30 seconds
        await asyncio.sleep(30)


async def weekly_portfolio_scheduler(telegram_bot):
    """Manage weekly portfolio: backfill, create new entries on Monday, update prices daily."""
    from datetime import datetime, date
    from zoneinfo import ZoneInfo

    sched_logger = logging.getLogger("portfolio_scheduler")
    ist = ZoneInfo("Asia/Kolkata")

    # Check table exists first
    try:
        from db.client import ensure_weekly_portfolio_table
        table_ok = await ensure_weekly_portfolio_table()
        if not table_ok:
            sched_logger.error(
                "weekly_portfolio table missing! Run migrations/001_weekly_portfolio.sql "
                "in Supabase SQL Editor. Portfolio scheduler will retry in 5 minutes."
            )
            await asyncio.sleep(300)
            table_ok = await ensure_weekly_portfolio_table()
            if not table_ok:
                sched_logger.error("Table still missing. Portfolio scheduler exiting.")
                return
    except Exception as e:
        sched_logger.error(f"Table check error: {e}")
        return

    # One-time backfill check on startup
    try:
        from db.client import get_weekly_portfolio
        from core.weekly_portfolio import backfill_from_date

        existing = await get_weekly_portfolio(status="OPEN")
        if not existing:
            sched_logger.info("No portfolio entries found — running March 31 backfill...")
            backfill_date = date(2025, 3, 31)
            entries = await backfill_from_date(backfill_date)
            if entries:
                sched_logger.info(f"Backfilled {len(entries)} entries from {backfill_date}")
                if telegram_bot.enabled:
                    from core.weekly_portfolio import get_portfolio_summary
                    summary = await get_portfolio_summary()
                    await telegram_bot.send_message(
                        f"📊 <b>Weekly Portfolio Backfilled</b>\n"
                        f"Starting from March 31, 2025\n\n{summary}"
                    )
            else:
                sched_logger.warning("Backfill produced no entries")
        else:
            sched_logger.info(f"Portfolio has {len(existing)} open entries — skipping backfill")
    except Exception as e:
        sched_logger.error(f"Portfolio backfill error: {e}", exc_info=True)

    done_today: set[str] = set()

    while True:
        now = datetime.now(ist)
        today_key = now.strftime("%Y-%m-%d")

        # Monday 9:00 AM IST — create new weekly portfolio from weekly picks
        if now.weekday() == 0 and now.hour == 9 and 0 <= now.minute < 2:
            key = f"{today_key}-weekly-create"
            if key not in done_today:
                sched_logger.info("Monday — creating new weekly portfolio entries")
                try:
                    from core.weekly_portfolio import create_weekly_portfolio, _fetch_yahoo_price
                    from config.constants import DEFAULT_WATCHLIST
                    import httpx

                    picks = []
                    async with httpx.AsyncClient(timeout=15.0) as session:
                        for symbol in DEFAULT_WATCHLIST[:10]:
                            price = await _fetch_yahoo_price(symbol, session)
                            if price and price > 0:
                                picks.append({"symbol": symbol, "price": round(price, 2)})

                    if picks:
                        # Take top 5 by cheapest
                        picks.sort(key=lambda p: p["price"])
                        entries = await create_weekly_portfolio(
                            picks[:5], date.today(), source="weekly"
                        )
                        sched_logger.info(f"Created {len(entries)} weekly portfolio entries")
                except Exception as e:
                    sched_logger.error(f"Weekly portfolio creation error: {e}", exc_info=True)
                done_today.add(key)

        # Daily 9:30 AM IST — update portfolio prices
        if now.hour == 9 and 30 <= now.minute < 32:
            key = f"{today_key}-price-update"
            if key not in done_today:
                sched_logger.info("Updating weekly portfolio prices")
                try:
                    from core.weekly_portfolio import update_portfolio_prices
                    result = await update_portfolio_prices()
                    sched_logger.info(
                        f"Portfolio update: {result['updated']} entries, "
                        f"total P&L: ₹{result['total_pnl']:+,.0f}"
                    )
                except Exception as e:
                    sched_logger.error(f"Portfolio price update error: {e}", exc_info=True)
                done_today.add(key)

        # Clean up at midnight
        current_date = now.strftime("%Y-%m-%d")
        done_today = {k for k in done_today if k.startswith(current_date)}

        await asyncio.sleep(30)


async def main():
    setup_logging()
    logger = logging.getLogger("run_bot")

    port = settings.effective_port

    logger.info("=" * 60)
    logger.info("TRADEX MICRO-TRADING BOT")
    logger.info(f"Mode: {'PAPER' if settings.paper_trading else 'LIVE'}")
    logger.info(f"Daily cap: ₹{settings.daily_cap_inr}")
    logger.info(f"Per trade: ₹{settings.per_trade_cap_inr}")
    logger.info(f"Max trades/day: {settings.max_trades_per_day}")
    logger.info(f"Market hours: {settings.market_open} - {settings.market_close} IST")
    logger.info(f"API server: http://{settings.fastapi_host}:{port}")
    logger.info(f"Dhan configured: {bool(settings.dhan_client_id)}")
    logger.info(f"Telegram configured: {bool(settings.telegram_bot_token)}")
    logger.info("=" * 60)

    # Start FastAPI server in background thread FIRST (so healthcheck passes)
    api_thread = threading.Thread(target=start_api_server, daemon=True)
    api_thread.start()
    logger.info(f"FastAPI server started on port {port}")

    # Give FastAPI a moment to bind
    await asyncio.sleep(2)

    # Initialize Telegram bot
    from core.telegram_bot import TelegramBot
    telegram_bot = TelegramBot()

    # Initialize engine
    from core.engine import TradingEngine
    from api.server import set_engine, set_telegram_bot

    engine = TradingEngine()
    engine.alerter = telegram_bot  # Inject telegram bot as alerter
    set_engine(engine)
    set_telegram_bot(telegram_bot)
    telegram_bot.set_engine(engine)

    # Start engine + telegram bot + scheduler concurrently
    tasks = []

    # Telegram bot: try webhook first, fall back to polling
    if telegram_bot.enabled:
        webhook_ok = await setup_telegram_webhook(telegram_bot, logger)
        if not webhook_ok:
            # Fallback to polling if webhook setup fails
            tasks.append(asyncio.create_task(telegram_bot.start_polling()))
            logger.info("Telegram bot polling started (webhook unavailable)")

        # Daily brief scheduler (runs alongside bot)
        tasks.append(asyncio.create_task(daily_brief_scheduler(telegram_bot)))
        logger.info("Daily brief scheduler started (8:45 AM + 10:00 AM IST)")

        # Weekly portfolio scheduler (backfill + auto-create + price updates)
        tasks.append(asyncio.create_task(weekly_portfolio_scheduler(telegram_bot)))
        logger.info("Weekly portfolio scheduler started")
    else:
        logger.info("Telegram bot disabled (no TELEGRAM_BOT_TOKEN)")

    # Trading engine
    try:
        engine_task = asyncio.create_task(engine.start())
        tasks.append(engine_task)
        logger.info("Trading engine starting...")

        # Wait for all tasks
        await asyncio.gather(*tasks, return_exceptions=True)

    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
        await engine.shutdown()
        await telegram_bot.stop_polling()
    except Exception as e:
        logger.error(f"Engine failed to start: {e}", exc_info=True)
        logger.info("Engine offline. FastAPI + Telegram bot still running.")

        # Keep process alive for healthcheck and Telegram commands
        if telegram_bot.enabled:
            await telegram_bot.send_message(
                f"⚠️ <b>Engine failed to start</b>\n{str(e)[:200]}\n\n"
                "FastAPI & Telegram bot are still running."
            )
            # Keep polling Telegram
            await telegram_bot.start_polling()
        else:
            while True:
                await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(main())

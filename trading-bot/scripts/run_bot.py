"""Entry point: starts FastAPI server + Trading Engine concurrently."""

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
            logging.FileHandler("trading-bot.log"),
        ],
    )


def start_api_server():
    """Run FastAPI in a background thread."""
    uvicorn.run(
        "api.server:app",
        host=settings.fastapi_host,
        port=settings.fastapi_port,
        log_level="info",
    )


async def main():
    setup_logging()
    logger = logging.getLogger("run_bot")

    logger.info("=" * 60)
    logger.info("MICRO-TRADING BOT")
    logger.info(f"Mode: {'PAPER' if settings.paper_trading else 'LIVE'}")
    logger.info(f"Daily cap: ₹{settings.daily_cap_inr}")
    logger.info(f"Per trade: ₹{settings.per_trade_cap_inr}")
    logger.info(f"Max trades/day: {settings.max_trades_per_day}")
    logger.info(f"Market hours: {settings.market_open} - {settings.market_close} IST")
    logger.info(f"API server: http://{settings.fastapi_host}:{settings.fastapi_port}")
    logger.info("=" * 60)

    # Start FastAPI server in background thread
    api_thread = threading.Thread(target=start_api_server, daemon=True)
    api_thread.start()
    logger.info(f"FastAPI server started on port {settings.fastapi_port}")

    # Initialize and set engine in API server
    from core.engine import TradingEngine
    from api.server import set_engine

    engine = TradingEngine()
    set_engine(engine)

    # Start the trading engine (blocking)
    # If broker is not configured, engine stays in STOPPED state
    # but FastAPI healthcheck still works
    try:
        await engine.start()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
        await engine.shutdown()
    except Exception as e:
        logger.error(f"Engine failed to start: {e}", exc_info=True)
        logger.info("Engine offline. FastAPI server still running for dashboard.")
        # Keep process alive for FastAPI healthcheck
        while True:
            await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(main())

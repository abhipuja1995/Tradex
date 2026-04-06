"""Weekly portfolio tracker — tracks paper investments in weekly recommendation picks."""

from __future__ import annotations

import logging
import math
from datetime import date, datetime
from uuid import uuid4

import httpx

from config.settings import settings
from config.constants import DEFAULT_WATCHLIST

logger = logging.getLogger(__name__)

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart"


async def _fetch_yahoo_price(symbol: str, session: httpx.AsyncClient) -> float | None:
    """Fetch current LTP from Yahoo Finance."""
    try:
        url = f"{YAHOO_CHART_URL}/{symbol}.NS?interval=1d&range=1d"
        resp = await session.get(url, headers={"User-Agent": "Mozilla/5.0"})
        data = resp.json()
        meta = data["chart"]["result"][0]["meta"]
        return float(meta["regularMarketPrice"])
    except Exception as e:
        logger.warning(f"Yahoo price fetch failed for {symbol}: {e}")
        return None


async def _fetch_yahoo_historical_price(
    symbol: str, target_date: date, session: httpx.AsyncClient
) -> float | None:
    """Fetch closing price on a specific date from Yahoo Finance."""
    try:
        # Fetch a range around the target date to handle weekends/holidays
        from datetime import timedelta

        start = target_date - timedelta(days=5)
        end = target_date + timedelta(days=3)
        start_ts = int(datetime.combine(start, datetime.min.time()).timestamp())
        end_ts = int(datetime.combine(end, datetime.min.time()).timestamp())

        url = (
            f"{YAHOO_CHART_URL}/{symbol}.NS"
            f"?period1={start_ts}&period2={end_ts}&interval=1d"
        )
        resp = await session.get(url, headers={"User-Agent": "Mozilla/5.0"})
        data = resp.json()
        result = data["chart"]["result"][0]

        timestamps = result.get("timestamp", [])
        closes = result["indicators"]["quote"][0].get("close", [])

        if not timestamps or not closes:
            return None

        # Find the closest date on or before target_date
        target_ts = int(datetime.combine(target_date, datetime.min.time()).timestamp())
        best_price = None
        best_ts = 0
        for ts, close in zip(timestamps, closes):
            if close is not None and ts <= target_ts + 86400:
                if ts >= best_ts:
                    best_ts = ts
                    best_price = close

        # If no price on or before target, take the first available
        if best_price is None and closes:
            for close in closes:
                if close is not None:
                    best_price = close
                    break

        return float(best_price) if best_price else None
    except Exception as e:
        logger.warning(f"Yahoo historical price failed for {symbol} on {target_date}: {e}")
        return None


async def create_weekly_portfolio(
    picks: list[dict], week_start_date: date, source: str = "weekly"
) -> list[dict]:
    """Create portfolio entries from weekly picks.

    Each pick dict should have: symbol, price (entry price).
    Quantity is calculated based on per_trade_cap_inr.
    """
    from db.client import upsert_weekly_portfolio

    entries = []
    for pick in picks:
        symbol = pick["symbol"]
        entry_price = pick["price"]
        if entry_price <= 0:
            continue

        qty = math.floor(settings.per_trade_cap_inr / entry_price)
        if qty < 1:
            qty = 1  # At least 1 share for tracking

        invested = round(entry_price * qty, 2)

        entry = {
            "id": str(uuid4()),
            "week_start_date": week_start_date.isoformat(),
            "symbol": symbol,
            "entry_price": entry_price,
            "entry_date": week_start_date.isoformat(),
            "quantity": qty,
            "invested_amount": invested,
            "current_price": entry_price,
            "pnl": 0.0,
            "pnl_percent": 0.0,
            "status": "OPEN",
            "source": source,
        }

        try:
            result = await upsert_weekly_portfolio(entry)
            entries.append(result)
            logger.info(
                f"Portfolio entry: {symbol} x{qty} @ {entry_price:.2f} "
                f"(invested: {invested:.2f}, source: {source})"
            )
        except Exception as e:
            logger.error(f"Failed to create portfolio entry for {symbol}: {e}")

    return entries


async def update_portfolio_prices() -> dict:
    """Fetch current prices and update P&L for all open portfolio entries."""
    from db.client import get_weekly_portfolio, update_weekly_portfolio_price

    open_entries = await get_weekly_portfolio(status="OPEN")
    if not open_entries:
        return {"updated": 0, "total_pnl": 0}

    total_pnl = 0.0
    updated = 0

    async with httpx.AsyncClient(timeout=15.0) as session:
        for entry in open_entries:
            symbol = entry["symbol"]
            current_price = await _fetch_yahoo_price(symbol, session)
            if current_price is None:
                continue

            entry_price = entry["entry_price"]
            qty = entry["quantity"]
            pnl = round((current_price - entry_price) * qty, 2)
            pnl_percent = round(((current_price - entry_price) / entry_price) * 100, 2)

            await update_weekly_portfolio_price(entry["id"], current_price, pnl, pnl_percent)
            total_pnl += pnl
            updated += 1

    logger.info(f"Portfolio update: {updated}/{len(open_entries)} entries, total P&L: {total_pnl:.2f}")
    return {"updated": updated, "total_pnl": total_pnl}


async def get_portfolio_summary() -> str:
    """Return a formatted summary of the weekly portfolio for Telegram."""
    from db.client import get_weekly_portfolio

    open_entries = await get_weekly_portfolio(status="OPEN")
    if not open_entries:
        return "No active weekly portfolio positions."

    # Update prices first
    await update_portfolio_prices()

    # Re-fetch after update
    open_entries = await get_weekly_portfolio(status="OPEN")

    total_invested = 0.0
    total_current = 0.0
    total_pnl = 0.0

    lines = ["<b>Weekly Portfolio</b>", ""]

    # Group by week
    weeks: dict[str, list] = {}
    for e in open_entries:
        w = e.get("week_start_date", "unknown")
        weeks.setdefault(w, []).append(e)

    for week, entries in sorted(weeks.items()):
        lines.append(f"<b>Week of {week}</b>")
        for e in entries:
            symbol = e["symbol"]
            entry_price = e["entry_price"]
            current_price = e.get("current_price", entry_price)
            qty = e["quantity"]
            pnl = e.get("pnl", 0)
            pnl_pct = e.get("pnl_percent", 0)
            invested = entry_price * qty

            total_invested += invested
            total_current += current_price * qty
            total_pnl += pnl

            emoji = "🟢" if pnl >= 0 else "🔴"
            lines.append(
                f"  {emoji} <b>{symbol}</b> x{qty} | "
                f"Entry: {entry_price:,.2f} → LTP: {current_price:,.2f} | "
                f"P&L: {pnl:+,.0f} ({pnl_pct:+.1f}%)"
            )
        lines.append("")

    pnl_emoji = "🟢" if total_pnl >= 0 else "🔴"
    pnl_pct_total = (total_pnl / total_invested * 100) if total_invested > 0 else 0
    lines.append(
        f"{pnl_emoji} <b>Total:</b> Invested: {total_invested:,.0f} | "
        f"Current: {total_current:,.0f} | P&L: {total_pnl:+,.0f} ({pnl_pct_total:+.1f}%)"
    )

    return "\n".join(lines)


async def backfill_from_date(start_date: date, symbols: list[str] | None = None) -> list[dict]:
    """Backfill portfolio from a specific date using historical prices.

    Fetches closing prices on start_date for the given symbols (or DEFAULT_WATCHLIST),
    scores them the same way as the daily brief weekly picks, and creates portfolio entries.
    """
    if symbols is None:
        symbols = list(DEFAULT_WATCHLIST)

    logger.info(f"Backfilling portfolio from {start_date} for {len(symbols)} symbols")

    stock_data = []
    async with httpx.AsyncClient(timeout=15.0) as session:
        for symbol in symbols:
            price = await _fetch_yahoo_historical_price(symbol, start_date, session)
            if price and price > 0:
                stock_data.append({"symbol": symbol, "price": round(price, 2)})
                logger.info(f"  {symbol}: {price:.2f} on {start_date}")
            else:
                logger.warning(f"  {symbol}: no price data for {start_date}")

    if not stock_data:
        logger.error("No price data fetched for backfill")
        return []

    # Take top 5 by cheapest-first (budget-friendly for paper trading)
    # In real usage, weekly picks would come from the scoring logic
    stock_data.sort(key=lambda s: s["price"])
    picks = stock_data[:5]

    logger.info(f"Backfill picks: {[p['symbol'] for p in picks]}")
    entries = await create_weekly_portfolio(picks, start_date, source="backfill")

    # Now fetch current prices to calculate P&L
    await update_portfolio_prices()

    return entries

"""Weekly portfolio tracker — rotates paper investments every week using weekly picks scoring."""

from __future__ import annotations

import logging
import math
from datetime import date, datetime, timedelta
from uuid import uuid4

import httpx

from config.settings import settings
from config.constants import DEFAULT_WATCHLIST

logger = logging.getLogger(__name__)

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart"

# Extended watchlist for better pick diversity
EXTENDED_WATCHLIST = list(DEFAULT_WATCHLIST) + [
    "NTPC", "ONGC", "POWERGRID", "COALINDIA", "TATASTEEL",
    "ULTRACEMCO", "NESTLEIND", "BAJAJFINSV", "TECHM", "JSWSTEEL",
]


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


async def _fetch_yahoo_chart(symbol: str, session: httpx.AsyncClient) -> dict | None:
    """Fetch 1Y chart data for scoring (RSI, DMA, Fib)."""
    try:
        url = f"{YAHOO_CHART_URL}/{symbol}.NS?interval=1d&range=1y"
        resp = await session.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10.0)
        data = resp.json()
        result = data["chart"]["result"][0]
        meta = result["meta"]
        closes = result["indicators"]["quote"][0].get("close", [])
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

        # DMA
        dma50 = sum(closes[-50:]) / min(50, len(closes)) if len(closes) >= 50 else None
        dma200 = sum(closes[-200:]) / min(200, len(closes)) if len(closes) >= 200 else None

        # Fibonacci
        fib_range = high_52w - low_52w
        fib_levels = {
            "fib236": high_52w - fib_range * 0.236,
            "fib382": high_52w - fib_range * 0.382,
            "fib50": high_52w - fib_range * 0.5,
            "fib618": high_52w - fib_range * 0.618,
        }
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
        }
    except Exception as e:
        logger.debug(f"Yahoo chart failed for {symbol}: {e}")
        return None


def _score_weekly(s: dict) -> float:
    """Score stocks for weekly picks — same logic as daily brief."""
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
    if s.get("fibFloor"):
        dist = (s["price"] - s["fibFloor"]) / s["price"] * 100
        if 0 < dist < 3:
            score += 15
    return score


async def _fetch_yahoo_historical_price(
    symbol: str, target_date: date, session: httpx.AsyncClient
) -> float | None:
    """Fetch closing price on a specific date from Yahoo Finance."""
    try:
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

        target_ts = int(datetime.combine(target_date, datetime.min.time()).timestamp())
        best_price = None
        best_ts = 0
        for ts, close in zip(timestamps, closes):
            if close is not None and ts <= target_ts + 86400:
                if ts >= best_ts:
                    best_ts = ts
                    best_price = close

        if best_price is None and closes:
            for close in closes:
                if close is not None:
                    best_price = close
                    break

        return float(best_price) if best_price else None
    except Exception as e:
        logger.warning(f"Yahoo historical price failed for {symbol} on {target_date}: {e}")
        return None


# ─── Core Portfolio Operations ─────────────────────────────────

async def close_current_week() -> dict:
    """Close all OPEN portfolio entries with final P&L. Called before creating new week."""
    from db.client import get_weekly_portfolio, close_weekly_portfolio_entry

    open_entries = await get_weekly_portfolio(status="OPEN")
    if not open_entries:
        return {"closed": 0, "total_pnl": 0}

    total_pnl = 0.0
    closed = 0

    async with httpx.AsyncClient(timeout=15.0) as session:
        for entry in open_entries:
            symbol = entry["symbol"]
            current_price = await _fetch_yahoo_price(symbol, session)
            if current_price is None:
                current_price = entry.get("current_price", entry["entry_price"])

            entry_price = entry["entry_price"]
            qty = entry["quantity"]
            pnl = round((current_price - entry_price) * qty, 2)
            pnl_percent = round(((current_price - entry_price) / entry_price) * 100, 2)

            await close_weekly_portfolio_entry(entry["id"], current_price, pnl, pnl_percent)
            total_pnl += pnl
            closed += 1

    logger.info(f"Closed {closed} portfolio entries, total P&L: ₹{total_pnl:+,.2f}")
    return {"closed": closed, "total_pnl": total_pnl}


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
            qty = 1

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
                f"Portfolio entry: {symbol} x{qty} @ ₹{entry_price:.2f} "
                f"(invested: ₹{invested:.2f}, source: {source})"
            )
        except Exception as e:
            logger.error(f"Failed to create portfolio entry for {symbol}: {e}")

    return entries


async def rotate_weekly_portfolio() -> dict:
    """Close last week's portfolio and create fresh picks for this week.

    Returns summary of what happened.
    """
    # 1. Close existing open entries with final P&L
    close_result = await close_current_week()

    # 2. Fetch fresh chart data and score for new weekly picks
    logger.info("Fetching chart data for new weekly picks...")
    stock_data = []
    async with httpx.AsyncClient(timeout=15.0) as session:
        for symbol in EXTENDED_WATCHLIST:
            chart = await _fetch_yahoo_chart(symbol, session)
            if chart:
                stock_data.append(chart)

    if not stock_data:
        logger.error("No chart data fetched — cannot create new portfolio")
        return {**close_result, "created": 0}

    # 3. Score and pick top 5
    stock_data.sort(key=_score_weekly, reverse=True)
    picks = stock_data[:5]

    logger.info(f"New weekly picks: {[p['symbol'] for p in picks]}")

    # 4. Create new portfolio entries
    today = date.today()
    entries = await create_weekly_portfolio(picks, today, source="weekly")

    return {
        **close_result,
        "created": len(entries),
        "picks": [p["symbol"] for p in picks],
    }


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

    logger.info(f"Portfolio update: {updated}/{len(open_entries)} entries, total P&L: ₹{total_pnl:+,.2f}")
    return {"updated": updated, "total_pnl": total_pnl}


async def get_portfolio_summary() -> str:
    """Return a formatted summary of the weekly portfolio for Telegram."""
    from db.client import get_weekly_portfolio, get_all_portfolio_entries

    # Update open prices first
    await update_portfolio_prices()

    open_entries = await get_weekly_portfolio(status="OPEN")
    all_entries = await get_all_portfolio_entries(limit=50)

    if not all_entries:
        return "No weekly portfolio history."

    lines = ["📈 <b>Weekly Portfolio</b>", ""]

    # --- Current week (OPEN) ---
    if open_entries:
        total_invested = 0.0
        total_current = 0.0
        total_pnl = 0.0
        week_date = open_entries[0].get("week_start_date", "")

        lines.append(f"🟢 <b>Active Week — {week_date}</b>")
        for e in open_entries:
            symbol = e["symbol"]
            entry_price = float(e["entry_price"])
            current_price = float(e.get("current_price", entry_price))
            qty = int(e["quantity"])
            pnl = float(e.get("pnl", 0))
            pnl_pct = float(e.get("pnl_percent", 0))

            total_invested += entry_price * qty
            total_current += current_price * qty
            total_pnl += pnl

            emoji = "🟢" if pnl >= 0 else "🔴"
            lines.append(
                f"  {emoji} <b>{symbol}</b> x{qty} | "
                f"₹{entry_price:,.0f} → ₹{current_price:,.0f} | "
                f"{pnl:+,.0f} ({pnl_pct:+.1f}%)"
            )

        pnl_emoji = "🟢" if total_pnl >= 0 else "🔴"
        pnl_pct_total = (total_pnl / total_invested * 100) if total_invested > 0 else 0
        lines.append(
            f"  {pnl_emoji} <b>Week Total:</b> ₹{total_invested:,.0f} → ₹{total_current:,.0f} | "
            f"{total_pnl:+,.0f} ({pnl_pct_total:+.1f}%)"
        )
        lines.append("")

    # --- Past weeks (CLOSED) — show last 4 weeks summary ---
    closed_entries = [e for e in all_entries if e.get("status") == "CLOSED"]
    if closed_entries:
        # Group by week
        weeks: dict[str, list] = {}
        for e in closed_entries:
            w = e.get("week_start_date", "unknown")
            weeks.setdefault(w, []).append(e)

        lines.append("📊 <b>Past Weeks</b>")
        cumulative_pnl = 0.0
        for week in sorted(weeks.keys(), reverse=True)[:4]:
            entries = weeks[week]
            week_invested = sum(float(e["entry_price"]) * int(e["quantity"]) for e in entries)
            week_pnl = sum(float(e.get("pnl", 0)) for e in entries)
            week_pct = (week_pnl / week_invested * 100) if week_invested > 0 else 0
            cumulative_pnl += week_pnl

            symbols = ", ".join(e["symbol"] for e in entries)
            emoji = "🟢" if week_pnl >= 0 else "🔴"
            lines.append(
                f"  {emoji} <b>{week}</b>: {week_pnl:+,.0f} ({week_pct:+.1f}%) — {symbols}"
            )

        lines.append(f"  📊 <b>Cumulative:</b> ₹{cumulative_pnl:+,.0f}")
        lines.append("")

    return "\n".join(lines)


async def backfill_from_date(start_date: date, symbols: list[str] | None = None) -> list[dict]:
    """Backfill portfolio from a specific date using historical prices and scoring."""
    if symbols is None:
        symbols = list(EXTENDED_WATCHLIST)

    logger.info(f"Backfilling portfolio from {start_date} for {len(symbols)} symbols")

    stock_data = []
    async with httpx.AsyncClient(timeout=15.0) as session:
        for symbol in symbols:
            price = await _fetch_yahoo_historical_price(symbol, start_date, session)
            if price and price > 0:
                stock_data.append({"symbol": symbol, "price": round(price, 2)})
                logger.info(f"  {symbol}: ₹{price:.2f} on {start_date}")
            else:
                logger.warning(f"  {symbol}: no price data for {start_date}")

    if not stock_data:
        logger.error("No price data fetched for backfill")
        return []

    # Score using price-based heuristic for historical (no RSI/DMA available easily)
    # Pick cheapest 5 so per_trade_cap buys meaningful qty
    stock_data.sort(key=lambda s: s["price"])
    picks = stock_data[:5]

    logger.info(f"Backfill picks: {[p['symbol'] for p in picks]}")
    entries = await create_weekly_portfolio(picks, start_date, source="backfill")

    # Fetch current prices to calculate P&L
    await update_portfolio_prices()

    return entries


async def backfill_all_weeks(start_date: date) -> list[dict]:
    """Backfill weekly portfolios from start_date to today, one week at a time.

    For each week: fetch Monday's prices, create portfolio, then close with Friday's prices.
    The current week stays OPEN.
    """
    today = date.today()
    current = start_date
    all_results = []

    # Find the Monday of start_date
    days_since_monday = current.weekday()
    if days_since_monday != 0:
        current = current - timedelta(days=days_since_monday)

    logger.info(f"Backfilling weekly portfolios from {current} to {today}")

    async with httpx.AsyncClient(timeout=15.0) as session:
        while current < today:
            week_end = current + timedelta(days=4)  # Friday
            is_current_week = today <= current + timedelta(days=7)

            logger.info(f"Processing week of {current}")

            # Fetch Monday entry prices
            picks = []
            for symbol in EXTENDED_WATCHLIST:
                price = await _fetch_yahoo_historical_price(symbol, current, session)
                if price and price > 0:
                    picks.append({"symbol": symbol, "price": round(price, 2)})

            if not picks:
                current += timedelta(days=7)
                continue

            # Pick top 5 cheapest
            picks.sort(key=lambda p: p["price"])
            week_picks = picks[:5]

            entries = await create_weekly_portfolio(week_picks, current, source="backfill")
            all_results.extend(entries)

            # If not current week, close with Friday prices
            if not is_current_week and entries:
                for entry in entries:
                    symbol = entry["symbol"]
                    exit_price = await _fetch_yahoo_historical_price(symbol, week_end, session)
                    if exit_price is None:
                        exit_price = entry["entry_price"]

                    from db.client import close_weekly_portfolio_entry
                    qty = entry["quantity"]
                    pnl = round((exit_price - entry["entry_price"]) * qty, 2)
                    pnl_pct = round(((exit_price - entry["entry_price"]) / entry["entry_price"]) * 100, 2)
                    await close_weekly_portfolio_entry(entry["id"], exit_price, pnl, pnl_pct)

            current += timedelta(days=7)

    # Update current week's prices
    await update_portfolio_prices()

    logger.info(f"Backfill complete: {len(all_results)} total entries across all weeks")
    return all_results

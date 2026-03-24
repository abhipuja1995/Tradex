"""Mistake learning engine — analyzes losses and proposes rules."""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Any

from config.constants import JournalEntryType, TradeStatus

logger = logging.getLogger(__name__)


class LearningEngine:
    """Analyzes losing trades to identify patterns and propose learning rules.

    End-of-day analysis:
    1. Query today's losing trades + AI decision logs
    2. Identify patterns (time, RSI range, symbol, conditions)
    3. Generate journal MISTAKE entries with root cause
    4. Propose learning rules (inactive by default, human activates)
    """

    async def analyze_day(self, trade_date: date | None = None) -> dict[str, Any]:
        """Run end-of-day analysis on all trades."""
        from db.client import (
            get_trades_today,
            get_ai_decisions,
            insert_journal_entry,
            insert_learning_rule,
            get_performance_history,
        )

        d = trade_date or date.today()
        trades = await get_trades_today(d)
        ai_decisions = await get_ai_decisions(trade_date=d)

        if not trades:
            logger.info("No trades today. Skipping analysis.")
            return {"trades": 0, "losses": 0, "mistakes": [], "rules_proposed": []}

        closed_trades = [
            t for t in trades
            if t["status"] in (TradeStatus.CLOSED, TradeStatus.STOPPED_OUT)
        ]
        losing_trades = [t for t in closed_trades if (t.get("pnl") or 0) < 0]
        winning_trades = [t for t in closed_trades if (t.get("pnl") or 0) >= 0]

        mistakes = []
        rules_proposed = []

        # --- Pattern 1: Time-based losses ---
        early_losses = [
            t for t in losing_trades
            if t.get("entry_time") and _is_first_30_min(t["entry_time"])
        ]
        if len(early_losses) >= 2:
            mistake = {
                "title": "Losses concentrated in first 30 minutes",
                "body": (
                    f"{len(early_losses)} out of {len(losing_trades)} losses occurred "
                    f"before 09:45 IST. Early market volatility may be causing false signals."
                ),
                "tags": ["timing", "early_market"],
            }
            mistakes.append(mistake)
            await insert_journal_entry(
                JournalEntryType.MISTAKE, mistake["title"], mistake["body"],
                tags=mistake["tags"],
            )

            rules_proposed.append({
                "rule_name": "block_early_trades",
                "condition_json": {"block_before_time": "09:45"},
                "action": "SKIP_TRADE",
                "reason": f"{len(early_losses)} early losses on {d.isoformat()}",
                "is_active": False,
                "created_from_trades": [t["id"] for t in early_losses],
            })

        # --- Pattern 2: Symbol-specific losses ---
        symbol_losses = Counter(t["symbol"] for t in losing_trades)
        for symbol, count in symbol_losses.items():
            if count >= 2:
                # Check historical performance for this symbol
                recent_history = await _get_symbol_loss_streak(symbol, days=5)
                if recent_history >= 3:
                    mistake = {
                        "title": f"Repeated losses on {symbol}",
                        "body": (
                            f"{symbol} has lost {recent_history} times in the last 5 days. "
                            f"Consider removing from watchlist."
                        ),
                        "tags": ["symbol", symbol],
                    }
                    mistakes.append(mistake)
                    await insert_journal_entry(
                        JournalEntryType.MISTAKE, mistake["title"], mistake["body"],
                        tags=mistake["tags"],
                    )

                    rules_proposed.append({
                        "rule_name": f"block_{symbol.lower()}",
                        "condition_json": {"blocked_symbols": [symbol]},
                        "action": "SKIP_TRADE",
                        "reason": f"{symbol} lost {recent_history}x in 5 days",
                        "is_active": False,
                        "created_from_trades": [
                            t["id"] for t in losing_trades if t["symbol"] == symbol
                        ],
                    })

        # --- Pattern 3: RSI was not deeply oversold ---
        shallow_rsi_losses = [
            t for t in losing_trades
            if t.get("rsi_at_entry") and 25 < float(t["rsi_at_entry"]) <= 30
        ]
        if len(shallow_rsi_losses) >= 2:
            mistake = {
                "title": "Losses at shallow RSI levels (25-30)",
                "body": (
                    f"{len(shallow_rsi_losses)} losses had RSI between 25-30. "
                    f"Tightening RSI threshold to < 25 may improve win rate."
                ),
                "tags": ["rsi", "threshold"],
            }
            mistakes.append(mistake)
            await insert_journal_entry(
                JournalEntryType.MISTAKE, mistake["title"], mistake["body"],
                tags=mistake["tags"],
            )

            rules_proposed.append({
                "rule_name": "tighten_rsi_threshold",
                "condition_json": {"rsi_min": 25, "rsi_max": 30},
                "action": "SKIP_TRADE",
                "reason": f"{len(shallow_rsi_losses)} losses with RSI 25-30",
                "is_active": False,
                "created_from_trades": [t["id"] for t in shallow_rsi_losses],
            })

        # --- Pattern 4: AI confidence was low on losers ---
        low_confidence_losses = [
            t for t in losing_trades
            if t.get("ai_confidence") and float(t["ai_confidence"]) < 0.6
        ]
        if len(low_confidence_losses) >= 2:
            mistake = {
                "title": "Losses with low AI confidence",
                "body": (
                    f"{len(low_confidence_losses)} losses had AI confidence below 60%. "
                    f"Consider raising the minimum confidence threshold."
                ),
                "tags": ["ai_confidence"],
            }
            mistakes.append(mistake)
            await insert_journal_entry(
                JournalEntryType.MISTAKE, mistake["title"], mistake["body"],
                tags=mistake["tags"],
            )

        # --- Insert proposed rules ---
        for rule in rules_proposed:
            await insert_learning_rule(rule)
            logger.info(f"Proposed rule: {rule['rule_name']} — {rule['reason']}")

        # --- Daily observation ---
        total_pnl = sum(t.get("pnl", 0) for t in closed_trades)
        win_rate = len(winning_trades) / len(closed_trades) * 100 if closed_trades else 0

        await insert_journal_entry(
            JournalEntryType.OBSERVATION,
            f"Day summary: {len(closed_trades)} trades, {win_rate:.0f}% win rate",
            (
                f"Date: {d.isoformat()}\n"
                f"Total trades: {len(closed_trades)}\n"
                f"Wins: {len(winning_trades)} | Losses: {len(losing_trades)}\n"
                f"Win rate: {win_rate:.1f}%\n"
                f"Total PnL: ₹{total_pnl:+.2f}\n"
                f"Mistakes identified: {len(mistakes)}\n"
                f"Rules proposed: {len(rules_proposed)}"
            ),
            tags=["daily_summary"],
        )

        result = {
            "trades": len(closed_trades),
            "wins": len(winning_trades),
            "losses": len(losing_trades),
            "pnl": total_pnl,
            "win_rate": win_rate,
            "mistakes": mistakes,
            "rules_proposed": [r["rule_name"] for r in rules_proposed],
        }
        logger.info(f"Day analysis complete: {result}")
        return result


def _is_first_30_min(entry_time: str) -> bool:
    """Check if trade was entered in the first 30 minutes of market."""
    from datetime import datetime
    try:
        dt = datetime.fromisoformat(entry_time.replace("Z", "+00:00"))
        # Market opens at 09:15 IST. First 30 min = before 09:45.
        import zoneinfo
        ist = zoneinfo.ZoneInfo("Asia/Kolkata")
        dt_ist = dt.astimezone(ist)
        return dt_ist.hour == 9 and dt_ist.minute < 45
    except Exception:
        return False


async def _get_symbol_loss_streak(symbol: str, days: int = 5) -> int:
    """Count losses for a symbol in the last N days."""
    from db.client import supabase

    d = date.today() - timedelta(days=days)
    result = (
        supabase().table("trades")
        .select("pnl")
        .eq("symbol", symbol)
        .gte("trade_date", d.isoformat())
        .in_("status", [TradeStatus.CLOSED, TradeStatus.STOPPED_OUT])
        .execute()
    )
    return sum(1 for t in result.data if (t.get("pnl") or 0) < 0)

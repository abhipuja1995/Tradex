"""Supabase client for trading bot database operations."""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any
from uuid import uuid4

from supabase import create_client, Client

from config.settings import settings
from config.constants import TradeStatus, JournalEntryType

logger = logging.getLogger(__name__)


def get_client() -> Client:
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


_supabase: Client | None = None


def supabase() -> Client:
    global _supabase
    if _supabase is None:
        _supabase = get_client()
    return _supabase


# --- Wallet ---

async def get_wallet(trade_date: date | None = None) -> dict[str, Any] | None:
    d = trade_date or date.today()
    result = supabase().table("trading_wallet").select("*").eq("trade_date", d.isoformat()).execute()
    return result.data[0] if result.data else None


async def upsert_wallet(wallet_data: dict[str, Any]) -> dict[str, Any]:
    wallet_data["updated_at"] = datetime.utcnow().isoformat()
    result = supabase().table("trading_wallet").upsert(wallet_data).execute()
    return result.data[0]


async def reset_daily_wallet(total_balance: float, available_balance: float) -> dict[str, Any]:
    return await upsert_wallet({
        "id": str(uuid4()),
        "total_balance": total_balance,
        "available_balance": available_balance,
        "locked_in_trades": 0,
        "daily_invested": 0,
        "daily_pnl": 0,
        "trade_date": date.today().isoformat(),
    })


# --- Trades ---

async def insert_trade(trade: dict[str, Any]) -> dict[str, Any]:
    if "id" not in trade:
        trade["id"] = str(uuid4())
    result = supabase().table("trades").insert(trade).execute()
    return result.data[0]


async def update_trade(trade_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    result = supabase().table("trades").update(updates).eq("id", trade_id).execute()
    return result.data[0]


async def get_open_trades() -> list[dict[str, Any]]:
    result = (
        supabase().table("trades")
        .select("*")
        .eq("status", TradeStatus.OPEN)
        .execute()
    )
    return result.data


async def get_trades_today(trade_date: date | None = None) -> list[dict[str, Any]]:
    d = trade_date or date.today()
    result = (
        supabase().table("trades")
        .select("*")
        .eq("trade_date", d.isoformat())
        .order("entry_time", desc=True)
        .execute()
    )
    return result.data


async def get_recent_trades(limit: int = 10) -> list[dict[str, Any]]:
    result = (
        supabase().table("trades")
        .select("*")
        .order("entry_time", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data


# --- Daily Performance ---

async def upsert_daily_performance(perf: dict[str, Any]) -> dict[str, Any]:
    if "id" not in perf:
        perf["id"] = str(uuid4())
    result = supabase().table("daily_performance").upsert(perf, on_conflict="trade_date").execute()
    return result.data[0]


async def get_performance_history(days: int = 30) -> list[dict[str, Any]]:
    result = (
        supabase().table("daily_performance")
        .select("*")
        .order("trade_date", desc=True)
        .limit(days)
        .execute()
    )
    return result.data


# --- Trade Journal ---

async def insert_journal_entry(
    entry_type: JournalEntryType,
    title: str,
    body: str,
    trade_id: str | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    entry = {
        "id": str(uuid4()),
        "trade_id": trade_id,
        "trade_date": date.today().isoformat(),
        "entry_type": entry_type.value,
        "title": title,
        "body": body,
        "tags": tags or [],
    }
    result = supabase().table("trade_journal").insert(entry).execute()
    return result.data[0]


async def get_journal_entries(
    trade_date: date | None = None,
    entry_type: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    query = supabase().table("trade_journal").select("*")
    if trade_date:
        query = query.eq("trade_date", trade_date.isoformat())
    if entry_type:
        query = query.eq("entry_type", entry_type)
    result = query.order("created_at", desc=True).limit(limit).execute()
    return result.data


# --- Learning Rules ---

async def get_active_rules() -> list[dict[str, Any]]:
    result = (
        supabase().table("learning_rules")
        .select("*")
        .eq("is_active", True)
        .execute()
    )
    return result.data


async def insert_learning_rule(rule: dict[str, Any]) -> dict[str, Any]:
    if "id" not in rule:
        rule["id"] = str(uuid4())
    result = supabase().table("learning_rules").insert(rule).execute()
    return result.data[0]


async def toggle_rule(rule_id: str, is_active: bool) -> dict[str, Any]:
    result = (
        supabase().table("learning_rules")
        .update({"is_active": is_active, "updated_at": datetime.utcnow().isoformat()})
        .eq("id", rule_id)
        .execute()
    )
    return result.data[0]


# --- AI Decisions ---

async def insert_ai_decision(decision: dict[str, Any]) -> dict[str, Any]:
    if "id" not in decision:
        decision["id"] = str(uuid4())
    result = supabase().table("ai_decisions").insert(decision).execute()
    return result.data[0]


async def get_ai_decisions(
    trade_date: date | None = None,
    symbol: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    query = supabase().table("ai_decisions").select("*")
    if trade_date:
        query = query.eq("decision_date", trade_date.isoformat())
    if symbol:
        query = query.eq("symbol", symbol)
    result = query.order("created_at", desc=True).limit(limit).execute()
    return result.data

"""FastAPI server for bot control and status queries."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Micro-Trading Bot API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# The engine instance is set by run_bot.py after initialization
_engine = None


def set_engine(engine):
    global _engine
    _engine = engine


def get_engine():
    if _engine is None:
        raise HTTPException(503, "Trading engine not initialized")
    return _engine


# --- Status ---

@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/status")
async def status():
    engine = get_engine()
    return engine.get_status()


# --- Trade Data ---

@app.get("/api/trades/today")
async def trades_today():
    from db.client import get_trades_today
    trades = await get_trades_today()
    return {"trades": trades, "count": len(trades)}


@app.get("/api/trades/open")
async def open_trades():
    from db.client import get_open_trades
    trades = await get_open_trades()
    return {"trades": trades, "count": len(trades)}


@app.get("/api/trades/recent")
async def recent_trades(limit: int = 20):
    from db.client import get_recent_trades
    trades = await get_recent_trades(limit)
    return {"trades": trades, "count": len(trades)}


# --- Performance ---

@app.get("/api/performance")
async def performance(days: int = 30):
    from db.client import get_performance_history
    history = await get_performance_history(days)
    return {"performance": history}


# --- Journal ---

@app.get("/api/journal")
async def journal(
    date_str: str | None = None,
    entry_type: str | None = None,
    limit: int = 50,
):
    from db.client import get_journal_entries
    d = date.fromisoformat(date_str) if date_str else None
    entries = await get_journal_entries(d, entry_type, limit)
    return {"entries": entries, "count": len(entries)}


# --- Learning Rules ---

@app.get("/api/rules")
async def get_rules():
    from db.client import get_active_rules
    rules = await get_active_rules()
    return {"rules": rules}


class ToggleRuleRequest(BaseModel):
    is_active: bool


@app.put("/api/rules/{rule_id}")
async def toggle_rule(rule_id: str, req: ToggleRuleRequest):
    from db.client import toggle_rule
    rule = await toggle_rule(rule_id, req.is_active)
    return {"rule": rule}


# --- AI Decisions ---

@app.get("/api/ai-decisions")
async def ai_decisions(
    date_str: str | None = None,
    symbol: str | None = None,
    limit: int = 20,
):
    from db.client import get_ai_decisions
    d = date.fromisoformat(date_str) if date_str else None
    decisions = await get_ai_decisions(d, symbol, limit)
    return {"decisions": decisions, "count": len(decisions)}


# --- Bot Control ---

@app.post("/api/control/start")
async def control_start():
    engine = get_engine()
    if engine.state.value == "RUNNING":
        return {"message": "Already running"}
    engine.resume()
    return {"message": "Bot started", "state": engine.state.value}


@app.post("/api/control/pause")
async def control_pause():
    engine = get_engine()
    engine.pause()
    return {"message": "Bot paused", "state": engine.state.value}


@app.post("/api/control/stop")
async def control_stop():
    engine = get_engine()
    await engine.shutdown()
    return {"message": "Bot stopped", "state": engine.state.value}


# --- Config ---

@app.get("/api/config")
async def get_config():
    from config.settings import settings
    return {
        "paper_trading": settings.paper_trading,
        "daily_cap_inr": settings.daily_cap_inr,
        "per_trade_cap_inr": settings.per_trade_cap_inr,
        "max_trades_per_day": settings.max_trades_per_day,
        "stop_loss_percent": settings.stop_loss_percent,
        "target_profit_percent": settings.target_profit_percent,
        "daily_max_loss_percent": settings.daily_max_loss_percent,
        "daily_target_percent": settings.daily_target_percent,
        "rsi_oversold": settings.rsi_oversold,
        "scan_interval_seconds": settings.scan_interval_seconds,
        "market_open": settings.market_open,
        "market_close": settings.market_close,
    }


class WatchlistUpdate(BaseModel):
    symbols: list[str]


@app.put("/api/config/watchlist")
async def update_watchlist(req: WatchlistUpdate):
    engine = get_engine()
    engine.strategy.update_watchlist(req.symbols)
    return {"message": "Watchlist updated", "symbols": req.symbols}

"""Trading system constants and enums."""

from enum import StrEnum

# Market
EXCHANGE = "NSE"
MARKET_TIMEZONE = "Asia/Kolkata"

# NIFTY 50 liquid stocks watchlist (Dhan security IDs mapped separately)
DEFAULT_WATCHLIST = [
    "RELIANCE",
    "TCS",
    "HDFCBANK",
    "INFY",
    "ICICIBANK",
    "HINDUNILVR",
    "ITC",
    "SBIN",
    "BHARTIARTL",
    "KOTAKBANK",
    "LT",
    "AXISBANK",
    "BAJFINANCE",
    "MARUTI",
    "TITAN",
    "SUNPHARMA",
    "TATAMOTORS",
    "WIPRO",
    "HCLTECH",
    "ADANIENT",
]

# Dhan security ID mapping for NSE equities
# Source: https://images.dhan.co/api-data/api-scrip-master.csv
DHAN_SECURITY_IDS: dict[str, int] = {
    "RELIANCE": 2885,
    "TCS": 11536,
    "HDFCBANK": 1333,
    "INFY": 1594,
    "ICICIBANK": 4963,
    "HINDUNILVR": 1394,
    "ITC": 1660,
    "SBIN": 3045,
    "BHARTIARTL": 10604,
    "KOTAKBANK": 1922,
    "LT": 11483,
    "AXISBANK": 5900,
    "BAJFINANCE": 317,
    "MARUTI": 10999,
    "TITAN": 3506,
    "SUNPHARMA": 3351,
    "TATAMOTORS": 3456,
    "WIPRO": 3787,
    "HCLTECH": 7229,
    "ADANIENT": 25,
}


class TradeDirection(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class TradeStatus(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    STOPPED_OUT = "STOPPED_OUT"
    CANCELLED = "CANCELLED"


class JournalEntryType(StrEnum):
    TRADE = "TRADE"
    MISTAKE = "MISTAKE"
    OBSERVATION = "OBSERVATION"
    RULE_CHANGE = "RULE_CHANGE"


class SignalAction(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class BotState(StrEnum):
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"
    WAITING_MARKET = "WAITING_MARKET"

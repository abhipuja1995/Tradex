"""Technical indicators using pandas-ta."""

from __future__ import annotations

import pandas as pd
import pandas_ta as ta


def compute_rsi(candles: pd.DataFrame, period: int = 14) -> pd.Series:
    """Compute RSI from OHLCV candle DataFrame.

    Args:
        candles: DataFrame with 'close' column
        period: RSI lookback period (default 14)

    Returns:
        Series of RSI values
    """
    return ta.rsi(candles["close"], length=period)


def support_level(candles: pd.DataFrame, lookback: int = 20) -> float:
    """Rolling minimum of lows as support level."""
    return float(candles["low"].tail(lookback).min())


def resistance_level(candles: pd.DataFrame, lookback: int = 20) -> float:
    """Rolling maximum of highs as resistance level."""
    return float(candles["high"].tail(lookback).max())


def sma(candles: pd.DataFrame, period: int = 20) -> pd.Series:
    """Simple moving average of close prices."""
    return ta.sma(candles["close"], length=period)


def ema(candles: pd.DataFrame, period: int = 20) -> pd.Series:
    """Exponential moving average of close prices."""
    return ta.ema(candles["close"], length=period)


def macd(candles: pd.DataFrame) -> pd.DataFrame:
    """MACD indicator (12, 26, 9)."""
    return ta.macd(candles["close"])


def volume_spike(candles: pd.DataFrame, threshold: float = 2.0) -> bool:
    """Check if current volume is a spike (> threshold * average)."""
    avg_volume = candles["volume"].tail(20).mean()
    current_volume = candles["volume"].iloc[-1]
    return bool(current_volume > threshold * avg_volume)


def is_near_support(price: float, support: float, tolerance_pct: float = 2.0) -> bool:
    """Check if price is within tolerance_pct of support level."""
    return price <= support * (1 + tolerance_pct / 100)


def candles_from_dhan_data(ohlcv_data) -> pd.DataFrame:
    """Convert Dhan API OHLCV response to pandas DataFrame.

    Dhan SDK v2 can return data in two formats:
    1. List of dicts: [{open, high, low, close, volume, start_Time}, ...]
    2. Dict of lists: {open: [...], high: [...], low: [...], close: [...], volume: [...]}
    """
    if isinstance(ohlcv_data, list):
        df = pd.DataFrame(ohlcv_data)
    elif isinstance(ohlcv_data, dict):
        df = pd.DataFrame(ohlcv_data)
    else:
        return pd.DataFrame()

    # Normalize column names to lowercase
    df.columns = [c.lower().replace("start_time", "timestamp") for c in df.columns]

    for col in ["open", "high", "low", "close"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "volume" in df.columns:
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype(int)
    else:
        df["volume"] = 0

    return df

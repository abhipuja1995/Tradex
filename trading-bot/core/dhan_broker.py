"""Direct Dhan broker adapter — works without OpenAlgo middleware.

Uses dhanhq SDK directly for order execution and market data.
Falls back to this when OpenAlgo is not configured/reachable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from config.settings import settings
from config.constants import DHAN_SECURITY_IDS

logger = logging.getLogger(__name__)


@dataclass
class OrderResponse:
    order_id: str
    status: str
    message: str
    raw: dict[str, Any]


class DhanBroker:
    """Direct Dhan SDK broker — no OpenAlgo dependency.

    Implements the same interface as OpenAlgoClient so TradingEngine
    can swap between them transparently.
    """

    def __init__(self):
        from dhanhq import dhanhq
        self._dhan = dhanhq(settings.dhan_client_id, settings.dhan_access_token)
        self._initialized = bool(settings.dhan_client_id and settings.dhan_access_token)
        if self._initialized:
            logger.info("DhanBroker initialized (direct SDK mode)")
        else:
            logger.warning("DhanBroker: missing credentials — paper-only mode")

    def refresh_token(self, token: str):
        """Update access token (e.g., from postback)."""
        from dhanhq import dhanhq
        settings.dhan_access_token = token
        self._dhan = dhanhq(settings.dhan_client_id, token)
        self._initialized = True
        logger.info("DhanBroker token refreshed")

    # --- Order Management ---

    async def place_order(
        self,
        symbol: str,
        exchange: str = "NSE",
        action: str = "BUY",
        quantity: int = 1,
        price_type: str = "MARKET",
        product_type: str = "MIS",
        price: float = 0.0,
        trigger_price: float = 0.0,
    ) -> OrderResponse:
        security_id = DHAN_SECURITY_IDS.get(symbol)
        if not security_id:
            return OrderResponse("", "FAILED", f"Unknown symbol: {symbol}", {})

        if not self._initialized:
            return OrderResponse("", "FAILED", "Dhan not configured", {})

        try:
            from dhanhq import dhanhq as DhanHQ
            order_type = self._map_order_type(price_type)
            exchange_seg = self._dhan.NSE

            logger.info(f"Placing Dhan order: {action} {quantity}x {symbol} (secId={security_id})")

            resp = self._dhan.place_order(
                security_id=str(security_id),
                exchange_segment=exchange_seg,
                transaction_type=self._dhan.BUY if action == "BUY" else self._dhan.SELL,
                quantity=quantity,
                order_type=order_type,
                product_type=self._dhan.INTRA,
                price=price,
                trigger_price=trigger_price,
            )

            order_id = resp.get("data", {}).get("orderId", "") if resp.get("data") else ""
            status = resp.get("status", "unknown")

            return OrderResponse(
                order_id=str(order_id),
                status=status,
                message=resp.get("remarks", ""),
                raw=resp,
            )
        except Exception as e:
            logger.error(f"Dhan place_order failed: {e}")
            return OrderResponse("", "ERROR", str(e), {})

    async def close_position(
        self,
        symbol: str,
        exchange: str = "NSE",
        product_type: str = "MIS",
    ) -> OrderResponse:
        """Close position by placing opposite order."""
        # Get current position to determine quantity
        positions = await self.get_positions()
        for pos in positions:
            if pos.get("tradingSymbol") == symbol:
                qty = abs(int(pos.get("netQty", 0)))
                if qty > 0:
                    action = "SELL" if int(pos.get("netQty", 0)) > 0 else "BUY"
                    return await self.place_order(symbol, exchange, action, qty)

        return OrderResponse("", "NO_POSITION", f"No open position for {symbol}", {})

    # --- Portfolio & Data ---

    async def get_funds(self) -> dict[str, Any]:
        if not self._initialized:
            return {"availablecash": 0, "status": "not_configured"}
        try:
            resp = self._dhan.get_fund_limits()
            if resp and resp.get("data"):
                data = resp["data"]
                return {
                    "availablecash": float(data.get("availabelBalance", 0)),
                    "utilized": float(data.get("utilizedAmount", 0)),
                    "raw": data,
                }
            return {"availablecash": 0}
        except Exception as e:
            logger.error(f"Dhan get_funds failed: {e}")
            return {"availablecash": 0, "error": str(e)}

    async def get_positions(self) -> list[dict[str, Any]]:
        if not self._initialized:
            return []
        try:
            resp = self._dhan.get_positions()
            return resp.get("data", []) if resp else []
        except Exception as e:
            logger.error(f"Dhan get_positions failed: {e}")
            return []

    async def get_order_book(self) -> list[dict[str, Any]]:
        if not self._initialized:
            return []
        try:
            resp = self._dhan.get_order_list()
            return resp.get("data", []) if resp else []
        except Exception as e:
            logger.error(f"Dhan get_order_book failed: {e}")
            return []

    async def get_holdings(self) -> list[dict[str, Any]]:
        if not self._initialized:
            return []
        try:
            resp = self._dhan.get_holdings()
            return resp.get("data", []) if resp else []
        except Exception as e:
            logger.error(f"Dhan get_holdings failed: {e}")
            return []

    async def get_ltp(self, symbol: str, exchange: str = "NSE") -> float | None:
        """Get last traded price via Dhan market quotes."""
        security_id = DHAN_SECURITY_IDS.get(symbol)
        if not security_id or not self._initialized:
            return None

        try:
            resp = self._dhan.get_market_feed(
                security_id=str(security_id),
                exchange_segment=self._dhan.NSE,
            )
            if resp and resp.get("data"):
                return float(resp["data"].get("LTP", 0))
        except Exception as e:
            logger.error(f"Dhan LTP failed for {symbol}: {e}")

        # Fallback: try intraday candle data for last close
        try:
            resp = self._dhan.intraday_daily_candle_data(
                security_id=str(security_id),
                exchange_segment=self._dhan.NSE,
                instrument_type=self._dhan.EQUITY,
            )
            if resp and resp.get("data"):
                candles = resp["data"]
                if candles:
                    last = candles[-1] if isinstance(candles, list) else candles
                    return float(last.get("close", last.get("Close", 0)))
        except Exception as e:
            logger.error(f"Dhan candle fallback failed for {symbol}: {e}")

        return None

    # --- Helpers ---

    def _map_order_type(self, price_type: str):
        mapping = {
            "MARKET": self._dhan.MARKET,
            "LIMIT": self._dhan.LIMIT,
            "SL": self._dhan.SL,
            "SLM": self._dhan.SLM,
        }
        return mapping.get(price_type.upper(), self._dhan.MARKET)

    async def close(self):
        """Cleanup (noop for SDK-based client)."""
        pass

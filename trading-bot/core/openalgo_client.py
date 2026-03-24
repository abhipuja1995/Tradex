"""OpenAlgo unified API client for broker-agnostic order execution."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from config.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class OrderResponse:
    order_id: str
    status: str
    message: str
    raw: dict[str, Any]


class OpenAlgoClient:
    """Calls OpenAlgo REST API for broker-agnostic trading.

    OpenAlgo provides a unified API layer across 30+ Indian brokers.
    By routing through OpenAlgo instead of calling Dhan directly,
    we can switch brokers with a single config change.

    API docs: https://docs.openalgo.in
    """

    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base_url = (base_url or settings.openalgo_url).rstrip("/")
        self.api_key = api_key or settings.openalgo_api_key
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=30.0,
        )

    async def _post(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        resp = await self._client.post(path, json=data)
        resp.raise_for_status()
        return resp.json()

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        resp = await self._client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

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
        """Place an order through OpenAlgo → broker."""
        data = {
            "apikey": self.api_key,
            "strategy": "MicroTrader",
            "symbol": symbol,
            "exchange": exchange,
            "action": action,
            "quantity": quantity,
            "pricetype": price_type,
            "product": product_type,
            "price": str(price),
            "trigger_price": str(trigger_price),
        }
        logger.info(f"Placing order: {action} {quantity}x {symbol} @ {price_type}")
        result = await self._post("/api/v1/placeorder", data)
        return OrderResponse(
            order_id=result.get("orderid", ""),
            status=result.get("status", "unknown"),
            message=result.get("message", ""),
            raw=result,
        )

    async def place_smart_order(
        self,
        symbol: str,
        exchange: str = "NSE",
        action: str = "BUY",
        quantity: int = 1,
        position_size: int = 0,
        price_type: str = "MARKET",
        product_type: str = "MIS",
        price: float = 0.0,
        trigger_price: float = 0.0,
    ) -> OrderResponse:
        """Position-aware smart order (adjusts based on current position)."""
        data = {
            "apikey": self.api_key,
            "strategy": "MicroTrader",
            "symbol": symbol,
            "exchange": exchange,
            "action": action,
            "quantity": quantity,
            "position_size": position_size,
            "pricetype": price_type,
            "product": product_type,
            "price": str(price),
            "trigger_price": str(trigger_price),
        }
        result = await self._post("/api/v1/placesmartorder", data)
        return OrderResponse(
            order_id=result.get("orderid", ""),
            status=result.get("status", "unknown"),
            message=result.get("message", ""),
            raw=result,
        )

    async def modify_order(
        self,
        order_id: str,
        symbol: str,
        exchange: str = "NSE",
        action: str = "BUY",
        quantity: int = 1,
        price_type: str = "MARKET",
        product_type: str = "MIS",
        price: float = 0.0,
        trigger_price: float = 0.0,
    ) -> OrderResponse:
        data = {
            "apikey": self.api_key,
            "strategy": "MicroTrader",
            "symbol": symbol,
            "exchange": exchange,
            "action": action,
            "orderid": order_id,
            "quantity": quantity,
            "pricetype": price_type,
            "product": product_type,
            "price": str(price),
            "trigger_price": str(trigger_price),
        }
        result = await self._post("/api/v1/modifyorder", data)
        return OrderResponse(
            order_id=result.get("orderid", order_id),
            status=result.get("status", "unknown"),
            message=result.get("message", ""),
            raw=result,
        )

    async def cancel_order(self, order_id: str, strategy: str = "MicroTrader") -> dict[str, Any]:
        data = {
            "apikey": self.api_key,
            "strategy": strategy,
            "orderid": order_id,
        }
        return await self._post("/api/v1/cancelorder", data)

    async def cancel_all_orders(self, strategy: str = "MicroTrader") -> dict[str, Any]:
        data = {
            "apikey": self.api_key,
            "strategy": strategy,
        }
        return await self._post("/api/v1/cancelallorder", data)

    async def close_position(
        self,
        symbol: str,
        exchange: str = "NSE",
        product_type: str = "MIS",
    ) -> OrderResponse:
        """Close an existing position."""
        data = {
            "apikey": self.api_key,
            "strategy": "MicroTrader",
            "symbol": symbol,
            "exchange": exchange,
            "product": product_type,
        }
        result = await self._post("/api/v1/closeposition", data)
        return OrderResponse(
            order_id=result.get("orderid", ""),
            status=result.get("status", "unknown"),
            message=result.get("message", ""),
            raw=result,
        )

    # --- Portfolio & Data ---

    async def get_order_book(self) -> list[dict[str, Any]]:
        result = await self._post("/api/v1/orderbook", {"apikey": self.api_key})
        return result.get("data", [])

    async def get_trade_book(self) -> list[dict[str, Any]]:
        result = await self._post("/api/v1/tradebook", {"apikey": self.api_key})
        return result.get("data", [])

    async def get_positions(self) -> list[dict[str, Any]]:
        result = await self._post("/api/v1/positionbook", {"apikey": self.api_key})
        return result.get("data", [])

    async def get_holdings(self) -> list[dict[str, Any]]:
        result = await self._post("/api/v1/holdings", {"apikey": self.api_key})
        return result.get("data", [])

    async def get_funds(self) -> dict[str, Any]:
        result = await self._post("/api/v1/funds", {"apikey": self.api_key})
        return result

    # --- Market Data (via OpenAlgo quotes) ---

    async def get_ltp(self, symbol: str, exchange: str = "NSE") -> float | None:
        """Get last traded price for a symbol."""
        try:
            result = await self._post("/api/v1/quotes", {
                "apikey": self.api_key,
                "symbol": symbol,
                "exchange": exchange,
            })
            return float(result.get("ltp", 0))
        except Exception as e:
            logger.error(f"Failed to get LTP for {symbol}: {e}")
            return None

    async def close(self):
        await self._client.aclose()

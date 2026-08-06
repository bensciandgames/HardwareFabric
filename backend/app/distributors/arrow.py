"""
app/distributors/arrow.py

Arrow Electronics API client. Arrow uses a simpler API-key auth model than
Ingram (no OAuth token exchange) but the same P&A + Order Create shape.
Kept structurally parallel to IngramMicroClient so the pricing engine and
order router can treat both polymorphically via DistributorClient.
"""

from __future__ import annotations
import asyncio
import random
import uuid
from typing import Optional

import httpx

from app.config import get_settings
from app.models import (
    DistributorAvailability,
    DropshipOrderRequest,
    DistributorOrderResult,
    DistributorOrderStatus,
    DistributorCode,
)
from app.distributors.base import DistributorClient, DistributorAPIError

settings = get_settings()

_MAX_RETRIES = 3
_BASE_BACKOFF_SECONDS = 0.5


class ArrowClient(DistributorClient):
    code = DistributorCode.ARROW

    def __init__(self) -> None:
        self._base_url = settings.arrow_base_url.rstrip("/")
        self._api_key = settings.arrow_api_key
        self._account_number = settings.arrow_account_number
        self._http = httpx.AsyncClient(timeout=15.0)

    def _headers(self) -> dict:
        return {
            "Authorization": f"ApiKey {self._api_key}",
            "Content-Type": "application/json",
            "X-Arrow-Account-Number": self._account_number,
        }

    async def _request_with_retry(self, method: str, url: str, **kwargs) -> httpx.Response:
        last_exc: Optional[Exception] = None
        for attempt in range(_MAX_RETRIES):
            try:
                resp = await self._http.request(method, url, **kwargs)
                if resp.status_code == 429 or resp.status_code >= 500:
                    raise DistributorAPIError(self.code, "Retryable error", resp.status_code)
                return resp
            except (DistributorAPIError, httpx.TransportError) as exc:
                last_exc = exc
                backoff = _BASE_BACKOFF_SECONDS * (2 ** attempt) + random.uniform(0, 0.25)
                await asyncio.sleep(backoff)
        raise DistributorAPIError(self.code, f"Exhausted retries: {last_exc}")

    async def get_price_and_availability(self, mpns: list[str]) -> list[DistributorAvailability]:
        url = f"{self._base_url}/inventory/priceavailability"
        body = {"partNumbers": mpns, "currency": "USD"}

        resp = await self._request_with_retry("POST", url, headers=self._headers(), json=body)
        if resp.status_code != 200:
            raise DistributorAPIError(self.code, "Price & availability lookup failed", resp.status_code)

        data = resp.json()
        results: list[DistributorAvailability] = []
        for item in data.get("items", []):
            results.append(
                DistributorAvailability(
                    mpn=item.get("partNumber", ""),
                    distributor=self.code,
                    distributor_sku=item.get("arrowPartId", ""),
                    cost_cents=round(float(item.get("unitPrice", 0.0)) * 100),
                    quantity_available=int(item.get("quantityOnHand", 0)),
                    lead_time_days=item.get("leadTimeDays"),
                    raw_status=item.get("stockStatus"),
                )
            )
        return results

    async def submit_dropship_order(self, request: DropshipOrderRequest) -> DistributorOrderResult:
        addr = request.shipping_address
        url = f"{self._base_url}/orders"

        body = {
            "poNumber": request.order_id,
            "shipTo": {
                "attention": addr.name,
                "address1": addr.line1,
                "address2": addr.line2 or "",
                "city": addr.city,
                "region": addr.state,
                "postalCode": addr.postal_code,
                "country": addr.country,
                "phone": addr.phone or "",
            },
            # Arrow's dropship + branding-suppression flags.
            "fulfillment": {
                "type": "DROP_SHIP",
                "suppressArrowBranding": True,
                "customPackingSlipName": settings.ship_from_company_name_override,
            },
            "items": [
                {"partNumber": li.mpn, "quantity": li.quantity, "lineRef": str(idx + 1)}
                for idx, li in enumerate(request.line_items)
            ],
        }

        resp = await self._request_with_retry("POST", url, headers=self._headers(), json=body)
        if resp.status_code not in (200, 201, 202):
            raise DistributorAPIError(self.code, "Order submission failed", resp.status_code)

        data = resp.json()
        accepted = [ln["partNumber"] for ln in data.get("confirmedItems", [])]
        rejected = [ln["partNumber"] for ln in data.get("backorderedItems", [])]

        return DistributorOrderResult(
            distributor=self.code,
            distributor_order_number=data.get("arrowOrderNumber"),
            accepted_line_items=accepted,
            rejected_line_items=rejected,
            status="submitted" if accepted else "rejected",
        )

    async def get_order_status(self, distributor_order_number: str) -> DistributorOrderStatus:
        url = f"{self._base_url}/orders/{distributor_order_number}"
        resp = await self._request_with_retry("GET", url, headers=self._headers())
        if resp.status_code != 200:
            raise DistributorAPIError(self.code, "Order status lookup failed", resp.status_code)
        data = resp.json()
        # Field names to confirm against Arrow's real API docs once actual
        # reseller access exists — same caveat as the Ingram client.
        tracking_number = data.get("trackingNumber") or data.get("shipment", {}).get("trackingNumber")
        return DistributorOrderStatus(status=data.get("status", "unknown"), tracking_number=tracking_number)

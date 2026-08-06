"""
app/distributors/ingram_micro.py

Ingram Micro XML/REST Reseller API v6 client. Handles OAuth2 client-credential
token caching, Price & Availability batch lookup, and Order Create with
blind dropship flags.

Ingram's real endpoints (sandbox shown; swap host for production per your
account setup docs):
  POST /oauth/oauth20/token                -> access_token
  POST /resellers/v6/catalog/priceandavailability
  POST /resellers/v6/orders

Rate limits / retry: Ingram enforces per-second throttling on sandbox and
production tiers differently — this client backs off with jittered retry
on 429s and 5xx.
"""

from __future__ import annotations
import asyncio
import random
import time
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


class IngramMicroClient(DistributorClient):
    code = DistributorCode.INGRAM_MICRO

    def __init__(self) -> None:
        self._base_url = settings.ingram_micro_base_url.rstrip("/")
        self._client_id = settings.ingram_micro_client_id
        self._client_secret = settings.ingram_micro_client_secret
        self._customer_number = settings.ingram_micro_customer_number
        self._sender_id = settings.ingram_micro_sender_id
        self._token: Optional[str] = None
        self._token_expires_at: float = 0.0
        self._http = httpx.AsyncClient(timeout=15.0)

    # -- auth ----------------------------------------------------------------

    async def _get_access_token(self) -> str:
        if self._token and time.time() < self._token_expires_at - 30:
            return self._token

        token_url = f"{self._base_url}/oauth/oauth20/token"
        resp = await self._http.post(
            token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if resp.status_code != 200:
            raise DistributorAPIError(self.code, "OAuth token request failed", resp.status_code)

        payload = resp.json()
        self._token = payload["access_token"]
        self._token_expires_at = time.time() + int(payload.get("expires_in", 3600))
        return self._token

    def _standard_headers(self, correlation_id: str, token: str) -> dict:
        # Ingram requires these correlation/context headers on every call.
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "IM-CustomerNumber": self._customer_number,
            "IM-CountryCode": "US",
            "IM-CorrelationID": correlation_id[:32],
            "IM-SenderID": self._sender_id,
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

    # -- price & availability -------------------------------------------------

    async def get_price_and_availability(self, mpns: list[str]) -> list[DistributorAvailability]:
        token = await self._get_access_token()
        correlation_id = str(uuid.uuid4())
        url = f"{self._base_url}/catalog/priceandavailability"

        # Ingram batches by their part number; we query by vendor MPN and
        # request the ingramPartNumber back so order submission can use it.
        body = {
            "products": [{"vendorPartNumber": mpn} for mpn in mpns],
            "includeAvailability": True,
            "includePricing": True,
            "includeProductAttributes": False,
        }

        resp = await self._request_with_retry(
            "POST", url, headers=self._standard_headers(correlation_id, token), json=body
        )
        if resp.status_code != 200:
            raise DistributorAPIError(self.code, "Price & availability lookup failed", resp.status_code)

        data = resp.json()
        results: list[DistributorAvailability] = []
        for item in data.get("products", []):
            # Ingram returns cost in decimal dollars; normalize to integer cents
            # to avoid float drift downstream in the pricing engine / ledger.
            unit_cost_dollars = item.get("pricing", {}).get("customerPrice", 0.0)
            qty = sum(
                wh.get("quantityAvailable", 0)
                for wh in item.get("availability", {}).get("availabilityByWarehouse", [])
            )
            results.append(
                DistributorAvailability(
                    mpn=item.get("vendorPartNumber", ""),
                    distributor=self.code,
                    distributor_sku=item.get("ingramPartNumber", ""),
                    cost_cents=round(unit_cost_dollars * 100),
                    quantity_available=qty,
                    lead_time_days=item.get("leadTimeDays"),
                    raw_status=item.get("productStatusCode"),
                )
            )
        return results

    # -- order creation ---------------------------------------------------------

    async def submit_dropship_order(self, request: DropshipOrderRequest) -> DistributorOrderResult:
        token = await self._get_access_token()
        correlation_id = str(uuid.uuid4())
        url = f"{self._base_url}/orders"

        addr = request.shipping_address
        order_lines = [
            {
                "ingramPartNumber": None,          # resolved via distributor_sku upstream in orders.py
                "vendorPartNumber": li.mpn,
                "quantity": li.quantity,
                "customerLineNumber": str(idx + 1),
            }
            for idx, li in enumerate(request.line_items)
        ]

        body = {
            "customerOrderNumber": request.order_id,
            "acceptBackOrder": False,
            "shipToInfo": {
                "contact": addr.name,
                "addressLine1": addr.line1,
                "addressLine2": addr.line2 or "",
                "city": addr.city,
                "state": addr.state,
                "postalCode": addr.postal_code,
                "countryCode": addr.country,
                "phoneNumber": addr.phone or "",
            },
            # This is the actual "remove distributor branding" switch on
            # Ingram's order API — must be enabled on your reseller account
            # by Ingram before it will be honored.
            "shipmentDetails": {
                "shipMethod": "DROPSHIP",
                "blindShipment": True,
                "shipFromCompanyNameOverride": settings.ship_from_company_name_override,
                "packingSlipSupressPricing": True,
            },
            "lines": order_lines,
        }

        resp = await self._request_with_retry(
            "POST", url, headers=self._standard_headers(correlation_id, token), json=body
        )

        if resp.status_code not in (200, 201, 202):
            raise DistributorAPIError(self.code, "Order submission failed", resp.status_code)

        data = resp.json()
        accepted = [ln["vendorPartNumber"] for ln in data.get("acceptedLines", [])]
        rejected = [ln["vendorPartNumber"] for ln in data.get("rejectedLines", [])]

        return DistributorOrderResult(
            distributor=self.code,
            distributor_order_number=data.get("imOrderNumber"),
            accepted_line_items=accepted,
            rejected_line_items=rejected,
            status="submitted" if accepted else "rejected",
        )

    async def get_order_status(self, distributor_order_number: str) -> DistributorOrderStatus:
        token = await self._get_access_token()
        url = f"{self._base_url}/orders/{distributor_order_number}"
        resp = await self._request_with_retry(
            "GET", url, headers=self._standard_headers(str(uuid.uuid4()), token)
        )
        if resp.status_code != 200:
            raise DistributorAPIError(self.code, "Order status lookup failed", resp.status_code)
        data = resp.json()
        # Field names to confirm against Ingram's real reseller docs once
        # sandbox/production access is actually granted (blocked on the
        # business entity + reseller account — see the private roadmap).
        # trackingNumber is the documented top-level field on some Ingram
        # order-status responses; shipmentDetails is the nested fallback
        # others use — checking both so this doesn't silently no-op if
        # Ingram's real shape differs from what's assumed here.
        tracking_number = data.get("trackingNumber") or data.get("shipmentDetails", {}).get("trackingNumber")
        return DistributorOrderStatus(status=data.get("orderStatus", "unknown"), tracking_number=tracking_number)

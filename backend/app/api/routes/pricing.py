"""
app/api/routes/pricing.py

Real-time Price & Availability lookup: takes a batch of MPNs from the
Fabric Builder frontend and returns the best in-stock retail offer per part
(plus the full offer list so the UI can show "also available from X" if
desired). Resolution logic (cache read-through + live distributor fallback +
markup) lives in app/services/offer_lookup.py so checkout.py can reuse the
exact same pricing path — what the customer sees here has to match what
they're charged at checkout.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.models import PricedOffer
from app.services.offer_lookup import resolve_priced_offers

router = APIRouter(prefix="/api/v1/pricing", tags=["pricing"])


class PriceAvailabilityRequest(BaseModel):
    mpns: list[str]


class PriceAvailabilityResponse(BaseModel):
    best_offers: list[PricedOffer]
    all_offers: list[PricedOffer]
    unresolved_mpns: list[str]


@router.post("/lookup", response_model=PriceAvailabilityResponse)
async def lookup_price_and_availability(payload: PriceAvailabilityRequest) -> PriceAvailabilityResponse:
    if not payload.mpns:
        raise HTTPException(status_code=400, detail="mpns must be a non-empty list")
    if len(payload.mpns) > 200:
        raise HTTPException(status_code=400, detail="Batch too large; max 200 MPNs per request")

    result = await resolve_priced_offers(payload.mpns)
    return PriceAvailabilityResponse(
        best_offers=result.best_offers, all_offers=result.all_offers, unresolved_mpns=result.unresolved_mpns
    )

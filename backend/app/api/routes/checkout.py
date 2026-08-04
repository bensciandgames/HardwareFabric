"""
app/api/routes/checkout.py

POST /api/v1/checkout/create-payment-intent

This is the "known open item" flagged in the project brief: the orders
webhook (app/api/routes/orders.py) already assumes a PaymentIntent exists
with `cart`, `user_id`, and `build_id` in its metadata, and that
`cart.priced_line_items` is a locked snapshot of unit cost + unit price
per MPN — but nothing was creating that PaymentIntent yet. This route is
that missing piece.

Flow:
  1. Load the caller's cart_items from Postgres (server-side — the client
     never gets to assert what's in its own cart at checkout time).
  2. Price every line via the same resolve_priced_offers() path the builder
     UI itself calls, so what the customer sees while shopping matches what
     they're charged here.
  3. Snapshot { line_items, priced_line_items } into PaymentIntent metadata
     — prices are locked at this moment and the fulfillment webhook must
     NOT re-fetch live prices later (distributor cost can move between
     checkout and fulfillment).
  4. Create the Stripe PaymentIntent for the priced total and return its
     client_secret for Stripe Elements to confirm on the frontend.
"""

from __future__ import annotations

import logging

import stripe
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.auth import CurrentUser, get_current_user
from app.config import get_settings
from app.models import ShippingAddress
from app.services.offer_lookup import resolve_priced_offers
from app.db import fetch_cart_items, create_checkout_session

logger = logging.getLogger("hardwarefabric.checkout")
router = APIRouter(prefix="/api/v1/checkout", tags=["checkout"])

settings = get_settings()
stripe.api_key = settings.stripe_secret_key


class CreatePaymentIntentRequest(BaseModel):
    shipping_address: ShippingAddress


class CreatePaymentIntentResponse(BaseModel):
    client_secret: str
    payment_intent_id: str
    subtotal_cents: int
    unpriceable_mpns: list[str]


@router.post("/create-payment-intent", response_model=CreatePaymentIntentResponse)
async def create_payment_intent(
    payload: CreatePaymentIntentRequest, current_user: CurrentUser = Depends(get_current_user)
) -> CreatePaymentIntentResponse:
    cart_rows = await fetch_cart_items(current_user.user_id)
    if not cart_rows:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cart is empty")

    mpns = [r["mpn"] for r in cart_rows]
    result = await resolve_priced_offers(mpns)
    offer_by_mpn = {o.mpn: o for o in result.best_offers}

    line_items = []
    priced_line_items = []
    subtotal_cents = 0
    unpriceable: list[str] = []
    # Track a build_id to attach to the order for provenance, if every
    # cart item traces back to the same build; carts mixing multiple
    # builds (or ad-hoc single components) simply leave it unset.
    build_ids = {str(r["build_id"]) for r in cart_rows if r["build_id"]}
    single_build_id = next(iter(build_ids)) if len(build_ids) == 1 else None

    for row in cart_rows:
        offer = offer_by_mpn.get(row["mpn"])
        if offer is None or not offer.in_stock:
            unpriceable.append(row["mpn"])
            continue

        quantity = row["quantity"]
        unit_price_cents = offer.retail_price_cents
        unit_cost_cents = result.cost_by_mpn.get(row["mpn"], 0)
        distributor_sku = result.distributor_sku_by_mpn.get(row["mpn"], "")

        line_items.append(
            {
                "component_id": str(row["component_id"]),
                "mpn": row["mpn"],
                "quantity": quantity,
                "preferred_distributor": offer.distributor.value,
            }
        )
        priced_line_items.append(
            {
                "mpn": row["mpn"],
                "distributor_sku": distributor_sku,
                "unit_cost_cents": unit_cost_cents,
                "unit_price_cents": unit_price_cents,
            }
        )
        subtotal_cents += unit_price_cents * quantity

    if not line_items:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="None of the items in your cart are currently priceable/in stock",
        )

    cart_metadata = {"line_items": line_items, "priced_line_items": priced_line_items}
    shipping_dict = {
        "name": payload.shipping_address.name,
        "address": {
            "line1": payload.shipping_address.line1,
            "line2": payload.shipping_address.line2 or "",
            "city": payload.shipping_address.city,
            "state": payload.shipping_address.state,
            "postal_code": payload.shipping_address.postal_code,
            "country": payload.shipping_address.country,
        },
        "phone": payload.shipping_address.phone,
    }

    # Stripe caps each metadata VALUE at 500 characters — the full priced
    # cart JSON blows past that for anything but a tiny cart (confirmed in
    # production: stripe.error.InvalidRequestError, "up to 500 characters
    # ... 2111 characters"). Persist the snapshot server-side instead and
    # pass only this short opaque id; the webhook looks it back up by id.
    checkout_id = await create_checkout_session(
        user_id=current_user.user_id,
        build_id=single_build_id,
        cart_snapshot=cart_metadata,
        shipping_address=shipping_dict,
        subtotal_cents=subtotal_cents,
    )

    intent = stripe.PaymentIntent.create(
        amount=subtotal_cents,
        currency="usd",
        shipping=shipping_dict,
        metadata={
            "user_id": current_user.user_id,
            "build_id": single_build_id or "",
            "checkout_id": checkout_id,
        },
        automatic_payment_methods={"enabled": True},
    )

    logger.info(
        "Created PaymentIntent %s for user %s: subtotal=%s cents, %d line items (%d unpriceable)",
        intent.id, current_user.user_id, subtotal_cents, len(line_items), len(unpriceable),
    )

    return CreatePaymentIntentResponse(
        client_secret=intent.client_secret,
        payment_intent_id=intent.id,
        subtotal_cents=subtotal_cents,
        unpriceable_mpns=unpriceable,
    )

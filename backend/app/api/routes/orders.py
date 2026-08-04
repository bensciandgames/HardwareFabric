"""
app/api/routes/orders.py

POST /api/v1/webhooks/stripe
    Verifies the Stripe signature, and on `payment_intent.succeeded`,
    fans the cart out into per-distributor blind-dropship orders.

Design notes:
  - The cart -> line item mapping is looked up server-side from the stored
    build_configuration tied to the PaymentIntent's client_reference — the
    client never gets to tell us what it's paying for after the fact.
  - Idempotent: Stripe retries webhooks; we no-op if an order already
    exists for this payment_intent_id.
  - One HardwareFabric order can fan out into multiple distributor orders
    (e.g. CPU/board from Ingram, GPU from Arrow) — each is submitted with
    blind_dropship=True and its own shipping metadata.
"""

from __future__ import annotations
import json
import logging

import stripe
from fastapi import APIRouter, Depends, Request, HTTPException, Header
from pydantic import BaseModel

from app.auth import CurrentUser, get_current_user
from app.config import get_settings
from app.models import (
    ShippingAddress,
    CartLineItem,
    DropshipOrderRequest,
    DistributorCode,
)
from app.distributors.base import DistributorAPIError
from app.distributors.registry import get_distributor_client
from app.db import (
    clear_cart,
    order_exists_for_payment_intent,
    create_order,
    insert_order_item,
    insert_distributor_order,
    update_order_status,
    fetch_components_by_mpns,
    fetch_distributor_id_by_code,
    fetch_order,
    fetch_orders_for_user,
    fetch_order_items,
    fetch_distributor_orders,
    fetch_checkout_session,
)

logger = logging.getLogger("hardwarefabric.orders")
router = APIRouter(prefix="/api/v1", tags=["orders"])

settings = get_settings()
stripe.api_key = settings.stripe_secret_key


@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request, stripe_signature: str = Header(None, alias="Stripe-Signature")):
    payload = await request.body()

    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=stripe_signature,
            secret=settings.stripe_webhook_secret,
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    if event["type"] != "payment_intent.succeeded":
        # Ack everything else so Stripe stops retrying non-actionable events.
        return {"received": True, "handled": False}

    intent = event["data"]["object"]
    await _fulfill_order_from_payment_intent(intent)
    return {"received": True, "handled": True}


async def _fulfill_order_from_payment_intent(intent: dict) -> None:
    payment_intent_id = intent["id"]

    if await order_exists_for_payment_intent(payment_intent_id):
        logger.info("Order already exists for payment_intent %s — skipping (webhook retry)", payment_intent_id)
        return

    metadata = intent.get("metadata", {})
    user_id = metadata.get("user_id")
    build_id = metadata.get("build_id") or None  # checkout.py sends "" when the cart spans multiple/no builds
    checkout_id = metadata.get("checkout_id")  # points at the priced cart snapshot (see checkout.py)

    if not user_id or not checkout_id:
        logger.error("PaymentIntent %s missing required metadata (user_id/checkout_id); cannot fulfill", payment_intent_id)
        return

    checkout_session = await fetch_checkout_session(checkout_id)
    if checkout_session is None:
        logger.error(
            "PaymentIntent %s references checkout_session %s which no longer exists; cannot fulfill",
            payment_intent_id, checkout_id,
        )
        return

    cart_raw = checkout_session["cart_snapshot"]
    shipping_raw = intent.get("shipping") or checkout_session["shipping_address"]
    if isinstance(shipping_raw, str):
        import json
        shipping_raw = json.loads(shipping_raw)

    shipping_address = ShippingAddress(
        name=shipping_raw["name"],
        line1=shipping_raw["address"]["line1"],
        line2=shipping_raw["address"].get("line2"),
        city=shipping_raw["address"]["city"],
        state=shipping_raw["address"]["state"],
        postal_code=shipping_raw["address"]["postal_code"],
        country=shipping_raw["address"].get("country", "US"),
        phone=shipping_raw.get("phone"),
    )

    line_items = [
        CartLineItem(
            component_id=li["component_id"],
            mpn=li["mpn"],
            quantity=li["quantity"],
            preferred_distributor=DistributorCode(li["preferred_distributor"]) if li.get("preferred_distributor") else None,
        )
        for li in cart_raw["line_items"]
    ]

    subtotal_cents = intent["amount"]  # Stripe amount is already the final charged total, in cents
    order_id = await create_order(
        user_id=user_id,
        build_id=build_id,
        stripe_payment_intent_id=payment_intent_id,
        shipping_address=shipping_raw,
        subtotal_cents=subtotal_cents,
        total_cents=subtotal_cents,
        blind_dropship=True,
    )

    # Resolve MPN -> component metadata for order_items bookkeeping.
    mpns = [li.mpn for li in line_items]
    components = await fetch_components_by_mpns(mpns)
    component_by_mpn = {c["mpn"]: c for c in components}

    # Group line items by preferred distributor (fallback: Ingram first,
    # Arrow as failover) so each distributor gets exactly one PO for this order.
    groups: dict[DistributorCode, list[CartLineItem]] = {}
    for li in line_items:
        dist = li.preferred_distributor or DistributorCode.INGRAM_MICRO
        groups.setdefault(dist, []).append(li)

    overall_status = "sourcing"

    for dist_code, items in groups.items():
        client = get_distributor_client(dist_code)
        dropship_request = DropshipOrderRequest(
            order_id=order_id,
            line_items=items,
            shipping_address=shipping_address,
            blind_dropship=True,
        )

        try:
            result = await client.submit_dropship_order(dropship_request)
        except DistributorAPIError as exc:
            logger.error("Distributor order submission failed for order %s via %s: %s", order_id, dist_code, exc)
            await insert_distributor_order(order_id, await fetch_distributor_id_by_code(dist_code.value), None, "failed")
            overall_status = "failed"
            continue

        distributor_db_id = await fetch_distributor_id_by_code(dist_code.value)
        await insert_distributor_order(order_id, distributor_db_id, result.distributor_order_number, result.status)

        for li in items:
            component = component_by_mpn.get(li.mpn)
            if component is None:
                logger.warning("MPN %s not found in components table — skipping order_item record", li.mpn)
                continue
            # NOTE: unit_cost/unit_price here should be pulled from the
            # priced cart snapshot taken at checkout time (stored alongside
            # the PaymentIntent), not re-queried live — prices must not
            # drift between checkout and fulfillment. Wire that snapshot in
            # via cart_raw["priced_line_items"] in your checkout route.
            priced = next((p for p in cart_raw.get("priced_line_items", []) if p["mpn"] == li.mpn), None)
            await insert_order_item(
                order_id=order_id,
                component_id=component["id"],
                distributor_id=distributor_db_id,
                mpn=li.mpn,
                distributor_sku=priced.get("distributor_sku", "") if priced else "",
                quantity=li.quantity,
                unit_cost_cents=priced.get("unit_cost_cents", 0) if priced else 0,
                unit_price_cents=priced.get("unit_price_cents", 0) if priced else 0,
            )

        if result.rejected_line_items:
            logger.warning(
                "Order %s: distributor %s rejected line items %s — needs fallback sourcing",
                order_id, dist_code, result.rejected_line_items,
            )
            overall_status = "partially_shipped"

    final_status = "dropship_submitted" if overall_status != "failed" else "failed"
    await update_order_status(order_id, final_status)
    logger.info("Order %s fulfillment complete with status=%s", order_id, final_status)

    # The cart the customer paid for should no longer show up as "in cart" —
    # clear it now that an order has been recorded for this payment.
    await clear_cart(user_id)


# --- Order history (backs the "Completed Builds" page) -----------------------

class OrderSummary(BaseModel):
    id: str
    build_id: str | None
    status: str
    subtotal_cents: int
    total_cents: int
    created_at: str


class OrderItemDetail(BaseModel):
    id: str
    component_id: str
    mpn: str
    name: str
    distributor_code: str
    distributor_sku: str
    quantity: int
    unit_cost_cents: int
    unit_price_cents: int


class DistributorOrderDetail(BaseModel):
    id: str
    distributor_code: str
    distributor_order_number: str | None
    status: str
    tracking_number: str | None
    submitted_at: str


class OrderDetail(OrderSummary):
    shipping_address: dict
    blind_dropship: bool
    items: list[OrderItemDetail]
    distributor_orders: list[DistributorOrderDetail]


@router.get("/orders", response_model=list[OrderSummary])
async def list_my_orders(current_user: CurrentUser = Depends(get_current_user)) -> list[OrderSummary]:
    rows = await fetch_orders_for_user(current_user.user_id)
    return [
        OrderSummary(
            id=str(r["id"]), build_id=str(r["build_id"]) if r["build_id"] else None,
            status=r["status"], subtotal_cents=r["subtotal_cents"], total_cents=r["total_cents"],
            created_at=r["created_at"].isoformat(),
        )
        for r in rows
    ]


@router.get("/orders/{order_id}", response_model=OrderDetail)
async def get_my_order(order_id: str, current_user: CurrentUser = Depends(get_current_user)) -> OrderDetail:
    order = await fetch_order(order_id, current_user.user_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    items = await fetch_order_items(order_id)
    dist_orders = await fetch_distributor_orders(order_id)

    return OrderDetail(
        id=str(order["id"]), build_id=str(order["build_id"]) if order["build_id"] else None,
        status=order["status"], subtotal_cents=order["subtotal_cents"], total_cents=order["total_cents"],
        created_at=order["created_at"].isoformat(),
        shipping_address=json.loads(order["shipping_address"]) if isinstance(order["shipping_address"], str) else order["shipping_address"],
        blind_dropship=order["blind_dropship"],
        items=[
            OrderItemDetail(
                id=str(i["id"]), component_id=str(i["component_id"]), mpn=i["mpn"], name=i["name"],
                distributor_code=i["distributor_code"], distributor_sku=i["distributor_sku"],
                quantity=i["quantity"], unit_cost_cents=i["unit_cost_cents"], unit_price_cents=i["unit_price_cents"],
            )
            for i in items
        ],
        distributor_orders=[
            DistributorOrderDetail(
                id=str(d["id"]), distributor_code=d["distributor_code"],
                distributor_order_number=d["distributor_order_number"], status=d["status"],
                tracking_number=d["tracking_number"], submitted_at=d["submitted_at"].isoformat(),
            )
            for d in dist_orders
        ],
    )

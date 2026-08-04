"""
app/services/offer_lookup.py

Shared price/availability resolution used by both the live pricing-lookup
route and the checkout route (checkout needs the exact same priced offers
so what the customer is charged matches what they saw in the builder).

Read-through cache: distributor_offers rows synced within
DISTRIBUTOR_OFFER_CACHE_TTL_MINUTES (populated by app/worker/sync_offers.py)
are trusted without hitting the distributor API. Any MPN not freshly cached
falls back to a live concurrent lookup across all configured distributors,
same graceful-degradation behavior as before (one distributor being down
must not fail the whole batch).
"""

from __future__ import annotations

import asyncio
import logging

from app.config import get_settings
from app.models import ComponentCategory, DistributorAvailability, DistributorCode, PricedOffer
from app.distributors.base import DistributorAPIError
from app.distributors.registry import get_all_distributor_clients
from app.services.pricing import MarkupRule, PricingEngine
from app.db import (
    fetch_components_by_mpns,
    fetch_fresh_cached_offers,
    fetch_markup_rules,
)

logger = logging.getLogger("hardwarefabric.offer_lookup")
settings = get_settings()


async def _load_pricing_engine() -> PricingEngine:
    raw_rules = await fetch_markup_rules()
    rules = [
        MarkupRule(
            category=ComponentCategory(r["category"]) if r["category"] else None,
            distributor=None,  # extend by joining distributors.code if per-distributor rules are needed
            margin_percent=float(r["margin_percent"]),
            min_margin_cents=int(r["min_margin_cents"]),
            priority=int(r["priority"]),
        )
        for r in raw_rules
    ]
    return PricingEngine(rules)


async def _safe_live_lookup(client, mpns: list[str]) -> list[DistributorAvailability]:
    try:
        return await client.get_price_and_availability(mpns)
    except DistributorAPIError as exc:
        logger.warning("Distributor lookup failed: %s", exc)
        return []


class OfferLookupResult:
    def __init__(
        self,
        best_offers: list[PricedOffer],
        all_offers: list[PricedOffer],
        unresolved_mpns: list[str],
        cost_by_mpn: dict[str, int] | None = None,
        distributor_sku_by_mpn: dict[str, str] | None = None,
    ):
        self.best_offers = best_offers
        self.all_offers = all_offers
        self.unresolved_mpns = unresolved_mpns
        # Internal only — never serialized on a public response model.
        # Needed so checkout.py can snapshot unit_cost_cents +
        # distributor_sku into the PaymentIntent metadata per the required
        # priced_line_items shape.
        self.cost_by_mpn = cost_by_mpn or {}
        self.distributor_sku_by_mpn = distributor_sku_by_mpn or {}


async def resolve_priced_offers(mpns: list[str]) -> OfferLookupResult:
    components = await fetch_components_by_mpns(mpns)
    if not components:
        return OfferLookupResult([], [], mpns)

    category_lookup = {c["mpn"]: ComponentCategory(c["category"]) for c in components}
    sku_lookup = {c["mpn"]: c["sku"] for c in components}
    name_lookup = {c["mpn"]: c["name"] for c in components}
    known_mpns = set(category_lookup.keys())

    # 1. Read-through cache first.
    cached_rows = await fetch_fresh_cached_offers(
        list(known_mpns), settings.distributor_offer_cache_ttl_minutes
    )
    cached_availability = [
        DistributorAvailability(
            mpn=r["mpn"], distributor=DistributorCode(r["distributor_code"]),
            distributor_sku=r["distributor_sku"], cost_cents=r["cost_cents"],
            quantity_available=r["quantity_available"], lead_time_days=r["lead_time_days"],
        )
        for r in cached_rows
    ]
    cached_mpns = {a.mpn for a in cached_availability}
    live_needed_mpns = list(known_mpns - cached_mpns)

    # 2. Live lookup only for whatever the cache didn't cover.
    live_availability: list[DistributorAvailability] = []
    if live_needed_mpns:
        clients = get_all_distributor_clients()
        results_per_distributor = await asyncio.gather(
            *(_safe_live_lookup(client, live_needed_mpns) for client in clients.values())
        )
        live_availability = [a for sub in results_per_distributor for a in sub]

    all_availability = cached_availability + live_availability

    engine = await _load_pricing_engine()
    all_offers = engine.price_offers(all_availability, category_lookup, sku_lookup, name_lookup)

    best_by_mpn: dict[str, PricedOffer] = {}
    for offer in all_offers:
        current_best = best_by_mpn.get(offer.mpn)
        if current_best is None:
            best_by_mpn[offer.mpn] = offer
            continue
        if offer.in_stock and not current_best.in_stock:
            best_by_mpn[offer.mpn] = offer
        elif offer.in_stock == current_best.in_stock and offer.retail_price_cents < current_best.retail_price_cents:
            best_by_mpn[offer.mpn] = offer

    # Recover the wholesale cost behind each chosen best offer (matched by
    # mpn + distributor) purely for internal fulfillment bookkeeping —
    # never attached to anything returned from a public route.
    cost_by_mpn: dict[str, int] = {}
    sku_by_mpn: dict[str, str] = {}
    for mpn, offer in best_by_mpn.items():
        match = next(
            (a for a in all_availability if a.mpn == mpn and a.distributor == offer.distributor), None
        )
        if match is not None:
            cost_by_mpn[mpn] = match.cost_cents
            sku_by_mpn[mpn] = match.distributor_sku

    unresolved = list(known_mpns - set(o.mpn for o in all_offers))
    return OfferLookupResult(list(best_by_mpn.values()), all_offers, unresolved, cost_by_mpn, sku_by_mpn)

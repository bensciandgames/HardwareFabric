"""
app/services/pricing.py

Turns raw distributor cost into a retail price the frontend can show.
Rule precedence (most specific wins): category+distributor > category-only
> distributor-only > global default. Applies a percentage margin with a
per-line minimum dollar margin floor, so cheap commodity parts (cables,
fans) still clear a sane minimum profit instead of a few cents.
"""

from __future__ import annotations
import math
from dataclasses import dataclass

from app.config import get_settings
from app.models import DistributorAvailability, PricedOffer, ComponentCategory, DistributorCode

settings = get_settings()


@dataclass
class MarkupRule:
    category: ComponentCategory | None
    distributor: DistributorCode | None
    margin_percent: float
    min_margin_cents: int
    priority: int = 0


class PricingEngine:
    """In production, `rules` is loaded from the markup_rules table (see
    schema.sql) via a repository — injected here so this class stays a pure
    function of (offer, rules) and is trivially unit-testable."""

    def __init__(self, rules: list[MarkupRule]):
        self._rules = rules

    def _select_rule(self, category: ComponentCategory, distributor: DistributorCode) -> MarkupRule:
        candidates = [
            r for r in self._rules
            if (r.category is None or r.category == category)
            and (r.distributor is None or r.distributor == distributor)
        ]
        if not candidates:
            return MarkupRule(
                category=None,
                distributor=None,
                margin_percent=settings.default_markup_percent,
                min_margin_cents=settings.default_min_margin_cents,
            )

        # Rank by specificity first (both fields matched > one field > neither),
        # then explicit priority, then highest margin as a final tiebreaker.
        def specificity(r: MarkupRule) -> int:
            return (1 if r.category else 0) + (1 if r.distributor else 0)

        candidates.sort(key=lambda r: (specificity(r), r.priority, r.margin_percent), reverse=True)
        return candidates[0]

    def price_offer(
        self,
        availability: DistributorAvailability,
        category: ComponentCategory,
        sku: str,
        name: str,
    ) -> PricedOffer:
        rule = self._select_rule(category, availability.distributor)

        margin_from_percent = math.floor(availability.cost_cents * (rule.margin_percent / 100.0))
        applied_margin = max(margin_from_percent, rule.min_margin_cents)
        retail_price_cents = availability.cost_cents + applied_margin

        return PricedOffer(
            mpn=availability.mpn,
            sku=sku,
            name=name,
            category=category,
            distributor=availability.distributor,
            retail_price_cents=retail_price_cents,
            quantity_available=availability.quantity_available,
            lead_time_days=availability.lead_time_days,
            in_stock=availability.quantity_available > 0,
        )

    def price_offers(
        self,
        availabilities: list[DistributorAvailability],
        category_lookup: dict[str, ComponentCategory],
        sku_lookup: dict[str, str],
        name_lookup: dict[str, str],
    ) -> list[PricedOffer]:
        """Batch helper: lookups are keyed by MPN, sourced from `components`."""
        priced: list[PricedOffer] = []
        for a in availabilities:
            category = category_lookup.get(a.mpn)
            if category is None:
                continue  # unknown/unmapped MPN — skip rather than mis-price
            priced.append(
                self.price_offer(
                    a,
                    category=category,
                    sku=sku_lookup.get(a.mpn, a.mpn),
                    name=name_lookup.get(a.mpn, a.mpn),
                )
            )
        return priced

    def cheapest_in_stock(self, offers: list[PricedOffer]) -> PricedOffer | None:
        in_stock = [o for o in offers if o.in_stock]
        if not in_stock:
            return None
        return min(in_stock, key=lambda o: o.retail_price_cents)

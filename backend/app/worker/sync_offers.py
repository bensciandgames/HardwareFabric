"""
app/worker/sync_offers.py

Distributor sync worker (backlog item: "a background job to populate/refresh
distributor_offers on a schedule, since the live lookup route currently
calls distributors synchronously on every pricing request rather than
reading a warm cache").

This script batches every active component's MPN, queries all configured
distributors concurrently, and upserts distributor_offers. The live pricing
route (app/services/offer_lookup.py) reads through this cache first
(DISTRIBUTOR_OFFER_CACHE_TTL_MINUTES) and only falls back to a live call
for MPNs that aren't freshly cached — so keeping this worker running on a
schedule is what keeps most pricing requests off the distributor APIs
entirely.

Run once:
    python -m app.worker.sync_offers

Run continuously (re-syncs every INTERVAL_SECONDS):
    python -m app.worker.sync_offers --loop

In production this is meant to run as a scheduled job (cron / Celery beat /
a simple systemd timer) rather than a long-lived process, but --loop is
provided for local development so you don't need a scheduler to see the
cache warm up.
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from app.db import (
    close_pool,
    fetch_all_active_components,
    fetch_distributor_id_by_code,
    init_pool,
    upsert_distributor_offer,
)
from app.distributors.base import DistributorAPIError
from app.distributors.registry import get_all_distributor_clients

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("hardwarefabric.worker.sync_offers")

_BATCH_SIZE = 100
_DEFAULT_INTERVAL_SECONDS = 15 * 60


async def sync_once() -> None:
    components = await fetch_all_active_components()
    if not components:
        logger.info("No active components to sync.")
        return

    mpn_by_component: dict[str, str] = {c["mpn"]: str(c["id"]) for c in components}
    mpns = list(mpn_by_component.keys())
    clients = get_all_distributor_clients()

    total_upserted = 0
    for i in range(0, len(mpns), _BATCH_SIZE):
        batch = mpns[i : i + _BATCH_SIZE]

        for dist_code, client in clients.items():
            try:
                availabilities = await client.get_price_and_availability(batch)
            except DistributorAPIError as exc:
                # One distributor being unreachable must not stop the sync
                # for the other — same graceful-degradation posture as the
                # live lookup route.
                logger.warning("Sync skipped distributor %s for this batch: %s", dist_code, exc)
                continue

            if not availabilities:
                continue

            distributor_id = await fetch_distributor_id_by_code(dist_code.value)
            for availability in availabilities:
                component_id = mpn_by_component.get(availability.mpn)
                if component_id is None:
                    continue
                await upsert_distributor_offer(
                    component_id=component_id,
                    distributor_id=distributor_id,
                    distributor_sku=availability.distributor_sku,
                    cost_cents=availability.cost_cents,
                    quantity_available=availability.quantity_available,
                    lead_time_days=availability.lead_time_days,
                )
                total_upserted += 1

    logger.info("Sync complete: %d offer rows upserted across %d components.", total_upserted, len(mpns))


async def main() -> None:
    parser = argparse.ArgumentParser(description="Sync distributor_offers cache.")
    parser.add_argument("--loop", action="store_true", help="Run continuously instead of once.")
    parser.add_argument(
        "--interval", type=int, default=_DEFAULT_INTERVAL_SECONDS, help="Seconds between syncs in --loop mode."
    )
    args = parser.parse_args()

    await init_pool()
    try:
        if args.loop:
            logger.info("Starting distributor sync loop (every %ss).", args.interval)
            while True:
                await sync_once()
                await asyncio.sleep(args.interval)
        else:
            await sync_once()
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())

"""
app/worker/sync_order_status.py

Order tracking sync worker (backlog item: populate status/tracking_number
on distributor_orders once a distributor actually ships, instead of
"Completed Builds" showing every order stuck at "dropship_submitted"
forever).

Polls every open distributor sub-order (no tracking number yet, not
failed/cancelled — see app/db.py's fetch_open_distributor_orders) via
DistributorClient.get_order_status(), writes back whatever status/tracking
comes back, and once every sub-order on a given HardwareFabric order has
shipped, bumps the parent order to 'shipped'.

Run once:
    python -m app.worker.sync_order_status

Run continuously (re-checks every INTERVAL_SECONDS):
    python -m app.worker.sync_order_status --loop

Structurally parallel to sync_offers.py. Meant to run as a Render Cron Job
alongside it — deliberately not wired up yet: distributor credentials are
sandbox-only until the HardwareFabric reseller accounts exist (see the
private roadmap), and Render Cron Jobs need a paid plan / card on file,
which is being deferred until just before public launch.
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from app.db import (
    close_pool,
    fetch_open_distributor_orders,
    init_pool,
    maybe_mark_order_shipped,
    update_distributor_order_tracking,
)
from app.distributors.base import DistributorAPIError
from app.distributors.registry import get_distributor_client
from app.models import DistributorCode

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("hardwarefabric.worker.sync_order_status")

_DEFAULT_INTERVAL_SECONDS = 15 * 60


async def sync_once() -> None:
    open_orders = await fetch_open_distributor_orders()
    if not open_orders:
        logger.info("No open distributor orders to check.")
        return

    touched_order_ids: set[str] = set()

    for row in open_orders:
        dist_code = DistributorCode(row["distributor_code"])
        client = get_distributor_client(dist_code)
        try:
            result = await client.get_order_status(row["distributor_order_number"])
        except DistributorAPIError as exc:
            # One distributor/order being unreachable must not stop the
            # sync for the rest — same graceful-degradation posture as
            # sync_offers.py and the live pricing lookup route.
            logger.warning(
                "Status check failed for distributor_order %s (%s): %s",
                row["id"], dist_code, exc,
            )
            continue

        await update_distributor_order_tracking(str(row["id"]), result.status, result.tracking_number)
        touched_order_ids.add(str(row["order_id"]))
        logger.info(
            "distributor_order %s (%s) -> status=%s tracking=%s",
            row["id"], dist_code, result.status, result.tracking_number,
        )

    for order_id in touched_order_ids:
        await maybe_mark_order_shipped(order_id)

    logger.info("Tracking sync complete: checked %d distributor order(s).", len(open_orders))


async def main() -> None:
    parser = argparse.ArgumentParser(description="Sync distributor_orders status/tracking.")
    parser.add_argument("--loop", action="store_true", help="Run continuously instead of once.")
    parser.add_argument(
        "--interval", type=int, default=_DEFAULT_INTERVAL_SECONDS, help="Seconds between syncs in --loop mode."
    )
    args = parser.parse_args()

    await init_pool()
    try:
        if args.loop:
            logger.info("Starting order status sync loop (every %ss).", args.interval)
            while True:
                await sync_once()
                await asyncio.sleep(args.interval)
        else:
            await sync_once()
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())

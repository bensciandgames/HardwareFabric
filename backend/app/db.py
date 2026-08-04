"""
app/db.py
Async connection pool + small repository functions backing the schema in
db/schema.sql. Kept as raw asyncpg (no ORM) so the SQL stays visible and
easy to reason about for a build this early.
"""

from __future__ import annotations
import asyncpg
from app.config import get_settings

settings = get_settings()
_pool: asyncpg.Pool | None = None


async def init_pool() -> None:
    global _pool
    # asyncpg's DSN doesn't use the SQLAlchemy-style "+asyncpg" driver suffix.
    dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    _pool = await asyncpg.create_pool(dsn=dsn, min_size=2, max_size=10)


async def close_pool() -> None:
    if _pool is not None:
        await _pool.close()


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialized — call init_pool() during app startup")
    return _pool


# --- Repository functions used by the pricing & orders routes ---------------

async def fetch_markup_rules() -> list[dict]:
    query = """
        SELECT category, distributor_id, margin_percent, min_margin_cents, priority
        FROM markup_rules
    """
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(query)
        return [dict(r) for r in rows]


async def fetch_components_by_mpns(mpns: list[str]) -> list[dict]:
    query = """
        SELECT id, sku, mpn, category, name
        FROM components
        WHERE mpn = ANY($1::text[]) AND is_active = TRUE
    """
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(query, mpns)
        return [dict(r) for r in rows]


async def fetch_distributor_id_by_code(code: str) -> str:
    query = "SELECT id FROM distributors WHERE code = $1"
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(query, code)
        if row is None:
            raise ValueError(f"Unknown distributor code: {code}")
        return str(row["id"])


async def create_order(
    user_id: str,
    build_id: str | None,
    stripe_payment_intent_id: str,
    shipping_address: dict,
    subtotal_cents: int,
    total_cents: int,
    blind_dropship: bool = True,
) -> str:
    query = """
        INSERT INTO orders (
            user_id, build_id, stripe_payment_intent_id, status,
            shipping_address, blind_dropship, subtotal_cents, total_cents
        ) VALUES ($1, $2, $3, 'paid', $4::jsonb, $5, $6, $7)
        RETURNING id
    """
    import json
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(
            query, user_id, build_id, stripe_payment_intent_id,
            json.dumps(shipping_address), blind_dropship, subtotal_cents, total_cents,
        )
        return str(row["id"])


async def insert_order_item(
    order_id: str, component_id: str, distributor_id: str, mpn: str,
    distributor_sku: str, quantity: int, unit_cost_cents: int, unit_price_cents: int,
) -> None:
    query = """
        INSERT INTO order_items (
            order_id, component_id, distributor_id, mpn, distributor_sku,
            quantity, unit_cost_cents, unit_price_cents
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
    """
    async with get_pool().acquire() as conn:
        await conn.execute(
            query, order_id, component_id, distributor_id, mpn,
            distributor_sku, quantity, unit_cost_cents, unit_price_cents,
        )


async def insert_distributor_order(
    order_id: str, distributor_id: str, distributor_order_number: str | None, status: str,
) -> None:
    query = """
        INSERT INTO distributor_orders (order_id, distributor_id, distributor_order_number, status)
        VALUES ($1, $2, $3, $4)
    """
    async with get_pool().acquire() as conn:
        await conn.execute(query, order_id, distributor_id, distributor_order_number, status)


async def update_order_status(order_id: str, status: str) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute("UPDATE orders SET status = $1 WHERE id = $2", status, order_id)


async def order_exists_for_payment_intent(stripe_payment_intent_id: str) -> bool:
    """Idempotency guard — Stripe can and will retry webhook delivery."""
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM orders WHERE stripe_payment_intent_id = $1", stripe_payment_intent_id
        )
        return row is not None


async def fetch_order(order_id: str, user_id: str) -> dict | None:
    query = """
        SELECT id, user_id, build_id, status, shipping_address, blind_dropship,
               subtotal_cents, total_cents, created_at
        FROM orders WHERE id = $1 AND user_id = $2
    """
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(query, order_id, user_id)
        return dict(row) if row else None


async def fetch_orders_for_user(user_id: str) -> list[dict]:
    query = """
        SELECT id, build_id, status, subtotal_cents, total_cents, created_at
        FROM orders WHERE user_id = $1 ORDER BY created_at DESC
    """
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(query, user_id)
        return [dict(r) for r in rows]


async def fetch_order_items(order_id: str) -> list[dict]:
    query = """
        SELECT oi.id, oi.component_id, oi.mpn, oi.distributor_sku, oi.quantity,
               oi.unit_cost_cents, oi.unit_price_cents, c.name, d.code AS distributor_code
        FROM order_items oi
        JOIN components c ON c.id = oi.component_id
        JOIN distributors d ON d.id = oi.distributor_id
        WHERE oi.order_id = $1
    """
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(query, order_id)
        return [dict(r) for r in rows]


async def fetch_distributor_orders(order_id: str) -> list[dict]:
    query = """
        SELECT do_.id, do_.distributor_order_number, do_.status, do_.tracking_number,
               do_.submitted_at, d.code AS distributor_code
        FROM distributor_orders do_
        JOIN distributors d ON d.id = do_.distributor_id
        WHERE do_.order_id = $1
    """
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(query, order_id)
        return [dict(r) for r in rows]


# --- Users --------------------------------------------------------------

async def create_user(email: str, password_hash: str, full_name: str | None) -> dict:
    query = """
        INSERT INTO users (email, password_hash, full_name)
        VALUES ($1, $2, $3)
        RETURNING id, email, full_name, created_at
    """
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(query, email, password_hash, full_name)
        return dict(row)


async def fetch_user_by_email(email: str) -> dict | None:
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE email = $1", email)
        return dict(row) if row else None


async def fetch_user_by_id(user_id: str) -> dict | None:
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, email, full_name, created_at FROM users WHERE id = $1", user_id
        )
        return dict(row) if row else None


# --- Components (for the picker) -----------------------------------------

async def fetch_components(
    category: str | None = None,
    workspace_mode: str | None = None,
    search: str | None = None,
    limit: int = 100,
) -> list[dict]:
    conditions = ["is_active = TRUE"]
    params: list = []

    if category:
        params.append(category)
        conditions.append(f"category = ${len(params)}")
    if workspace_mode:
        params.append(workspace_mode)
        conditions.append(f"${len(params)} = ANY(min_workspace_scope)")
    if search:
        params.append(f"%{search}%")
        conditions.append(f"(name ILIKE ${len(params)} OR mpn ILIKE ${len(params)})")

    params.append(limit)
    query = f"""
        SELECT id, sku, mpn, category, name, msrp_cents, specs
        FROM components
        WHERE {' AND '.join(conditions)}
        ORDER BY name
        LIMIT ${len(params)}
    """
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(query, *params)
        return [dict(r) for r in rows]


async def fetch_component_by_id(component_id: str) -> dict | None:
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, sku, mpn, category, name, msrp_cents, specs FROM components WHERE id = $1",
            component_id,
        )
        return dict(row) if row else None


async def fetch_pcie_slots_for_motherboard(motherboard_component_id: str) -> list[dict]:
    query = """
        SELECT id, slot_label, physical_form, max_electrical_lanes, pcie_version,
               root_source, shares_lane_group, bifurcation_capable, bifurcation_modes
        FROM pcie_slots WHERE motherboard_component_id = $1
        ORDER BY slot_label
    """
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(query, motherboard_component_id)
        return [dict(r) for r in rows]


# --- Build configurations --------------------------------------------------

async def create_build(user_id: str, workspace_mode: str, name: str = "Untitled Build") -> dict:
    query = """
        INSERT INTO build_configurations (user_id, name, workspace_mode)
        VALUES ($1, $2, $3)
        RETURNING id, user_id, name, workspace_mode, status, created_at, updated_at
    """
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(query, user_id, name, workspace_mode)
        return dict(row)


async def fetch_build(build_id: str, user_id: str) -> dict | None:
    query = """
        SELECT id, user_id, name, workspace_mode, status, created_at, updated_at
        FROM build_configurations WHERE id = $1 AND user_id = $2
    """
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(query, build_id, user_id)
        return dict(row) if row else None


async def fetch_builds_for_user(user_id: str, status_filter: str | None = None) -> list[dict]:
    if status_filter:
        query = """
            SELECT id, name, workspace_mode, status, created_at, updated_at
            FROM build_configurations WHERE user_id = $1 AND status = $2
            ORDER BY updated_at DESC
        """
        async with get_pool().acquire() as conn:
            rows = await conn.fetch(query, user_id, status_filter)
            return [dict(r) for r in rows]

    query = """
        SELECT id, name, workspace_mode, status, created_at, updated_at
        FROM build_configurations WHERE user_id = $1
        ORDER BY updated_at DESC
    """
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(query, user_id)
        return [dict(r) for r in rows]


async def update_build(build_id: str, user_id: str, name: str | None, status_value: str | None) -> dict | None:
    build = await fetch_build(build_id, user_id)
    if build is None:
        return None
    new_name = name if name is not None else build["name"]
    new_status = status_value if status_value is not None else build["status"]
    query = """
        UPDATE build_configurations SET name = $1, status = $2, updated_at = now()
        WHERE id = $3 AND user_id = $4
        RETURNING id, user_id, name, workspace_mode, status, created_at, updated_at
    """
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(query, new_name, new_status, build_id, user_id)
        return dict(row) if row else None


async def delete_build(build_id: str, user_id: str) -> bool:
    async with get_pool().acquire() as conn:
        result = await conn.execute(
            "DELETE FROM build_configurations WHERE id = $1 AND user_id = $2", build_id, user_id
        )
        return result.endswith(" 1")


async def fetch_build_components(build_id: str) -> list[dict]:
    query = """
        SELECT bc.id, bc.component_id, bc.pcie_slot_id, bc.quantity,
               c.sku, c.mpn, c.name, c.category, c.msrp_cents,
               ps.slot_label
        FROM build_components bc
        JOIN components c ON c.id = bc.component_id
        LEFT JOIN pcie_slots ps ON ps.id = bc.pcie_slot_id
        WHERE bc.build_id = $1
        ORDER BY c.category
    """
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(query, build_id)
        return [dict(r) for r in rows]


class BuildComponentConflict(Exception):
    """Raised when the DB trigger layer (fn_validate_pcie_allocation /
    fn_validate_memory_compatibility) rejects an insert — surfaced to the
    API as a 409 with the trigger's own message, since Postgres is the
    source of truth for these rules, not the app."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


async def add_build_component(
    build_id: str, component_id: str, pcie_slot_id: str | None, quantity: int = 1
) -> dict:
    query = """
        INSERT INTO build_components (build_id, component_id, pcie_slot_id, quantity)
        VALUES ($1, $2, $3, $4)
        RETURNING id, build_id, component_id, pcie_slot_id, quantity
    """
    async with get_pool().acquire() as conn:
        try:
            row = await conn.fetchrow(query, build_id, component_id, pcie_slot_id, quantity)
        except asyncpg.PostgresError as exc:
            raise BuildComponentConflict(str(exc)) from exc
        return dict(row)


async def remove_build_component(build_component_id: str, build_id: str) -> bool:
    async with get_pool().acquire() as conn:
        result = await conn.execute(
            "DELETE FROM build_components WHERE id = $1 AND build_id = $2", build_component_id, build_id
        )
        return result.endswith(" 1")


async def fetch_bottleneck_warnings(build_id: str) -> list[dict]:
    query = "SELECT * FROM v_build_bottleneck_warnings WHERE build_id = $1"
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(query, build_id)
        return [dict(r) for r in rows]


# --- Cart --------------------------------------------------------------

async def fetch_cart_items(user_id: str) -> list[dict]:
    query = """
        SELECT ci.id, ci.build_id, ci.component_id, ci.quantity, ci.preferred_distributor, ci.added_at,
               c.sku, c.mpn, c.name, c.category, c.msrp_cents
        FROM cart_items ci
        JOIN components c ON c.id = ci.component_id
        WHERE ci.user_id = $1
        ORDER BY ci.added_at
    """
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(query, user_id)
        return [dict(r) for r in rows]


async def upsert_cart_item(
    user_id: str, component_id: str, quantity: int, build_id: str | None, preferred_distributor: str | None
) -> dict:
    query = """
        INSERT INTO cart_items (user_id, component_id, quantity, build_id, preferred_distributor)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (user_id, component_id, build_id)
        DO UPDATE SET quantity = cart_items.quantity + EXCLUDED.quantity
        RETURNING id, build_id, component_id, quantity, preferred_distributor, added_at
    """
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(query, user_id, component_id, quantity, build_id, preferred_distributor)
        return dict(row)


async def update_cart_item_quantity(cart_item_id: str, user_id: str, quantity: int) -> dict | None:
    query = """
        UPDATE cart_items SET quantity = $1 WHERE id = $2 AND user_id = $3
        RETURNING id, build_id, component_id, quantity, preferred_distributor, added_at
    """
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(query, quantity, cart_item_id, user_id)
        return dict(row) if row else None


async def remove_cart_item(cart_item_id: str, user_id: str) -> bool:
    async with get_pool().acquire() as conn:
        result = await conn.execute(
            "DELETE FROM cart_items WHERE id = $1 AND user_id = $2", cart_item_id, user_id
        )
        return result.endswith(" 1")


async def clear_cart(user_id: str) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute("DELETE FROM cart_items WHERE user_id = $1", user_id)


# --- Distributor offer cache (populated by app/worker/sync_offers.py) -----

async def upsert_distributor_offer(
    component_id: str, distributor_id: str, distributor_sku: str,
    cost_cents: int, quantity_available: int, lead_time_days: int | None,
) -> None:
    query = """
        INSERT INTO distributor_offers (
            component_id, distributor_id, distributor_sku, cost_cents,
            quantity_available, lead_time_days, last_synced_at
        ) VALUES ($1, $2, $3, $4, $5, $6, now())
        ON CONFLICT (component_id, distributor_id)
        DO UPDATE SET distributor_sku = EXCLUDED.distributor_sku,
                      cost_cents = EXCLUDED.cost_cents,
                      quantity_available = EXCLUDED.quantity_available,
                      lead_time_days = EXCLUDED.lead_time_days,
                      last_synced_at = now()
    """
    async with get_pool().acquire() as conn:
        await conn.execute(
            query, component_id, distributor_id, distributor_sku,
            cost_cents, quantity_available, lead_time_days,
        )


async def fetch_all_active_components() -> list[dict]:
    async with get_pool().acquire() as conn:
        rows = await conn.fetch("SELECT id, mpn FROM components WHERE is_active = TRUE")
        return [dict(r) for r in rows]


async def fetch_fresh_cached_offers(mpns: list[str], ttl_minutes: int) -> list[dict]:
    """Read-through cache for the live pricing lookup route: offers synced
    within `ttl_minutes` are trusted without hitting the distributor API."""
    query = """
        SELECT c.mpn, d.code AS distributor_code, do_.distributor_sku, do_.cost_cents,
               do_.quantity_available, do_.lead_time_days
        FROM distributor_offers do_
        JOIN components c ON c.id = do_.component_id
        JOIN distributors d ON d.id = do_.distributor_id
        WHERE c.mpn = ANY($1::text[])
          AND do_.last_synced_at > now() - ($2 || ' minutes')::interval
    """
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(query, mpns, str(ttl_minutes))
        return [dict(r) for r in rows]

-- ============================================================================
-- HardwareFabric.tech — Core Schema (PostgreSQL 15+)
-- Covers: component graph, memory structural flags (UDIMM/RDIMM/LRDIMM),
-- PCIe 5.0 lane allocation + bifurcation enforcement, distributor pricing,
-- and order/dropship pipeline.
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "btree_gist";

-- ----------------------------------------------------------------------------
-- 1. ENUMS
-- ----------------------------------------------------------------------------

CREATE TYPE memory_module_type AS ENUM ('UDIMM', 'RDIMM', 'LRDIMM');

CREATE TYPE component_category AS ENUM (
    'cpu', 'motherboard', 'memory', 'gpu', 'storage_nvme', 'storage_sata',
    'psu', 'case', 'cooler', 'nic', 'raid_hba', 'riser_backplane'
);

CREATE TYPE workspace_mode AS ENUM (
    'consumer_tower', 'workstation_rig', 'rackmount_server'
);

CREATE TYPE pcie_root_source AS ENUM ('cpu', 'chipset', 'pch', 'switch');

CREATE TYPE order_status AS ENUM (
    'pending_payment', 'paid', 'sourcing', 'dropship_submitted',
    'partially_shipped', 'shipped', 'cancelled', 'failed'
);

-- ----------------------------------------------------------------------------
-- 2. CORE COMPONENT GRAPH
-- ----------------------------------------------------------------------------

CREATE TABLE manufacturers (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            TEXT NOT NULL UNIQUE
);

-- Base "node" for every physical part in the graph. Category-specific
-- attributes live in the satellite tables below (1:1 extension pattern),
-- keeping the graph traversable via component_id regardless of type.
CREATE TABLE components (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    sku                 TEXT NOT NULL UNIQUE,
    mpn                 TEXT NOT NULL,           -- Manufacturer Part Number (used for distributor mapping)
    manufacturer_id     UUID NOT NULL REFERENCES manufacturers(id),
    category            component_category NOT NULL,
    name                TEXT NOT NULL,
    msrp_cents          INTEGER NOT NULL CHECK (msrp_cents >= 0),
    min_workspace_scope workspace_mode[] NOT NULL DEFAULT ARRAY['consumer_tower','workstation_rig','rackmount_server']::workspace_mode[],
    specs               JSONB NOT NULL DEFAULT '{}'::jsonb,   -- free-form spec bag for UI filtering
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_components_category ON components(category);
CREATE INDEX idx_components_mpn ON components(mpn);
CREATE INDEX idx_components_specs_gin ON components USING GIN (specs);
CREATE INDEX idx_components_scope_gin ON components USING GIN (min_workspace_scope);

-- ----------------------------------------------------------------------------
-- 3. MEMORY — structural flags (UDIMM / RDIMM / LRDIMM)
-- ----------------------------------------------------------------------------

CREATE TABLE memory_modules (
    component_id    UUID PRIMARY KEY REFERENCES components(id) ON DELETE CASCADE,
    module_type     memory_module_type NOT NULL,
    ecc             BOOLEAN NOT NULL,
    capacity_gb     INTEGER NOT NULL CHECK (capacity_gb > 0),
    speed_mts       INTEGER NOT NULL CHECK (speed_mts > 0),   -- MT/s
    rank_count      SMALLINT NOT NULL DEFAULT 1 CHECK (rank_count BETWEEN 1 AND 8),
    voltage_mv      INTEGER NOT NULL,
    -- Structural rule: LRDIMM/RDIMM require ECC; UDIMM in server contexts is rare but not banned here —
    -- enforcement of "which type is allowed on which board" happens at the motherboard-compat layer below,
    -- not baked into the part's own row.
    CONSTRAINT ck_registered_requires_ecc CHECK (
        module_type = 'UDIMM' OR ecc = TRUE
    )
);

-- Motherboard memory support: a board declares which structural DIMM types
-- it will physically clock/train. This is the join point that prevents,
-- e.g., an LRDIMM being added to a consumer UDIMM-only board.
CREATE TABLE motherboard_memory_support (
    motherboard_component_id   UUID NOT NULL REFERENCES components(id) ON DELETE CASCADE,
    module_type                memory_module_type NOT NULL,
    max_capacity_gb_per_slot   INTEGER NOT NULL,
    max_speed_mts              INTEGER NOT NULL,
    PRIMARY KEY (motherboard_component_id, module_type)
);

-- ----------------------------------------------------------------------------
-- 4. MOTHERBOARDS + PCIe TOPOLOGY (lane allocation & bifurcation)
-- ----------------------------------------------------------------------------

CREATE TABLE motherboards (
    component_id        UUID PRIMARY KEY REFERENCES components(id) ON DELETE CASCADE,
    socket               TEXT NOT NULL,
    chipset               TEXT NOT NULL,
    form_factor            TEXT NOT NULL,             -- ATX, E-ATX, SSI-EEB, SSI-CEB, Proprietary-Rack...
    memory_slots            SMALLINT NOT NULL,
    cpu_pcie_lanes_total     SMALLINT NOT NULL,         -- lanes the CPU socket itself exposes (root complex)
    chipset_pcie_lanes_total SMALLINT NOT NULL DEFAULT 0,
    workspace_scope          workspace_mode NOT NULL
);

-- Every physical PCIe slot / M.2 site / OCP site on a board is a node with
-- a declared root source (which lane pool it draws from) and whether it
-- supports bifurcation and into what shapes.
CREATE TABLE pcie_slots (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    motherboard_component_id UUID NOT NULL REFERENCES components(id) ON DELETE CASCADE,
    slot_label              TEXT NOT NULL,             -- e.g. "PCIE1", "M2_1", "OCP_A"
    physical_form           TEXT NOT NULL,             -- 'x16_slot','x8_slot','m2_2280','ocp3'
    max_electrical_lanes    SMALLINT NOT NULL,          -- e.g. 16
    pcie_version            NUMERIC(2,1) NOT NULL,       -- 5.0, 4.0, ...
    root_source             pcie_root_source NOT NULL,
    -- shares_with points at another slot when two physical slots draw from
    -- the *same* physical lane group and populating both forces a split
    -- (classic "PCIe1 x16 becomes x8/x8 when PCIe2 populated").
    shares_lane_group       TEXT,
    bifurcation_capable      BOOLEAN NOT NULL DEFAULT FALSE,
    bifurcation_modes        TEXT[] DEFAULT '{}',        -- e.g. {'x16','x8x8','x4x4x4x4'}
    UNIQUE (motherboard_component_id, slot_label)
);

CREATE INDEX idx_pcie_slots_board ON pcie_slots(motherboard_component_id);
CREATE INDEX idx_pcie_slots_lane_group ON pcie_slots(motherboard_component_id, shares_lane_group);

-- PCIe-consuming components (GPU, NVMe, HBA, NIC) declare their lane demand.
CREATE TABLE pcie_devices (
    component_id      UUID PRIMARY KEY REFERENCES components(id) ON DELETE CASCADE,
    lanes_required     SMALLINT NOT NULL CHECK (lanes_required IN (1,2,4,8,16)),
    pcie_version        NUMERIC(2,1) NOT NULL,
    physical_form       TEXT NOT NULL,                  -- 'x16_card','m2_2280','ocp3'
    -- High-VRAM enterprise GPUs are flagged so the allocator can prioritize
    -- them for full x16 Gen5 and warn before starving them via bifurcation.
    is_high_vram_accelerator BOOLEAN NOT NULL DEFAULT FALSE,
    vram_gb              INTEGER
);

-- ----------------------------------------------------------------------------
-- 5. BUILD CONFIGURATIONS (the user's in-progress / saved system)
-- ----------------------------------------------------------------------------

CREATE TABLE build_configurations (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL,
    name            TEXT NOT NULL DEFAULT 'Untitled Build',
    workspace_mode  workspace_mode NOT NULL,
    status          TEXT NOT NULL DEFAULT 'draft',   -- draft | validated | in_cart | ordered
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE build_components (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    build_id            UUID NOT NULL REFERENCES build_configurations(id) ON DELETE CASCADE,
    component_id         UUID NOT NULL REFERENCES components(id),
    -- pcie_slot_id is set only when this component occupies a specific
    -- physical slot on the build's motherboard (GPU/NVMe/HBA/NIC).
    pcie_slot_id          UUID REFERENCES pcie_slots(id),
    quantity              INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0),
    UNIQUE (build_id, pcie_slot_id)   -- a physical slot can only hold one occupant
);

CREATE INDEX idx_build_components_build ON build_components(build_id);

-- ----------------------------------------------------------------------------
-- 6. PCIe LANE / BIFURCATION VALIDATION (trigger-enforced, not app-trusted)
-- ----------------------------------------------------------------------------
-- Rationale: lane math must be enforced at the DB layer because build_components
-- rows can be written by multiple app paths (builder UI, cart re-price, admin
-- tools) — a single trigger is the one place this can't be bypassed.

CREATE OR REPLACE FUNCTION fn_validate_pcie_allocation()
RETURNS TRIGGER AS $$
DECLARE
    v_board_id UUID;
    v_group    TEXT;
    v_group_total_available SMALLINT;
    v_group_total_claimed    SMALLINT;
    v_device_lanes SMALLINT;
    v_slot_max_lanes SMALLINT;
    v_bifurcation_capable BOOLEAN;
    v_modes TEXT[];
BEGIN
    IF NEW.pcie_slot_id IS NULL THEN
        RETURN NEW;  -- non-PCIe component (RAM, PSU, case, cooler...)
    END IF;

    SELECT ps.motherboard_component_id, ps.shares_lane_group, ps.max_electrical_lanes,
           ps.bifurcation_capable, ps.bifurcation_modes
      INTO v_board_id, v_group, v_slot_max_lanes, v_bifurcation_capable, v_modes
      FROM pcie_slots ps WHERE ps.id = NEW.pcie_slot_id;

    SELECT pd.lanes_required INTO v_device_lanes
      FROM pcie_devices pd WHERE pd.component_id = NEW.component_id;

    IF v_device_lanes IS NULL THEN
        RAISE EXCEPTION 'Component % assigned to a PCIe slot but has no pcie_devices row', NEW.component_id;
    END IF;

    -- Rule 1: device must not physically exceed the slot's max electrical lanes,
    -- unless the slot is bifurcation-capable into a matching sub-width.
    IF v_device_lanes > v_slot_max_lanes THEN
        RAISE EXCEPTION 'Slot % supports max x% lanes; component requires x%',
            NEW.pcie_slot_id, v_slot_max_lanes, v_device_lanes;
    END IF;

    IF v_device_lanes < v_slot_max_lanes AND v_device_lanes <> v_slot_max_lanes THEN
        IF NOT v_bifurcation_capable THEN
            RAISE EXCEPTION 'Slot % is fixed-width x%; cannot accept an x% device without bifurcation support',
                NEW.pcie_slot_id, v_slot_max_lanes, v_device_lanes;
        END IF;
    END IF;

    -- Rule 2: if this slot shares a physical lane group with sibling slots
    -- (e.g. PCIe1/PCIe2 both drawing from the same 16 CPU lanes), sum what's
    -- claimed across the whole group in this build and ensure it fits.
    IF v_group IS NOT NULL THEN
        SELECT COALESCE(SUM(pd.lanes_required), 0)
          INTO v_group_total_claimed
          FROM build_components bc
          JOIN pcie_slots ps2 ON ps2.id = bc.pcie_slot_id
          JOIN pcie_devices pd ON pd.component_id = bc.component_id
         WHERE bc.build_id = NEW.build_id
           AND ps2.motherboard_component_id = v_board_id
           AND ps2.shares_lane_group = v_group;

        SELECT MAX(max_electrical_lanes) INTO v_group_total_available
          FROM pcie_slots WHERE motherboard_component_id = v_board_id AND shares_lane_group = v_group;

        IF v_group_total_claimed > v_group_total_available THEN
            RAISE EXCEPTION 'Lane group % on board % oversubscribed: % lanes claimed, % available (bifurcation limit)',
                v_group, v_board_id, v_group_total_claimed, v_group_total_available;
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_validate_pcie_allocation
    BEFORE INSERT OR UPDATE ON build_components
    FOR EACH ROW EXECUTE FUNCTION fn_validate_pcie_allocation();

-- Companion warning view (not a hard block): flags builds where a
-- high-VRAM accelerator got bifurcated below x16 because of a
-- co-populated NVMe/second GPU — surfaced in the UI as a performance
-- warning rather than a rejection, since it's sometimes intentional.
CREATE VIEW v_build_bottleneck_warnings AS
SELECT bc.build_id, c.name AS component_name, pd.vram_gb,
       ps.slot_label, ps.max_electrical_lanes AS slot_capacity,
       pd.lanes_required AS device_ideal_lanes
FROM build_components bc
JOIN components c ON c.id = bc.component_id
JOIN pcie_devices pd ON pd.component_id = bc.component_id
JOIN pcie_slots ps ON ps.id = bc.pcie_slot_id
WHERE pd.is_high_vram_accelerator = TRUE
  AND pd.lanes_required = 16
  AND ps.max_electrical_lanes < 16;

-- ----------------------------------------------------------------------------
-- 7. MEMORY TYPE COMPATIBILITY VALIDATION (build-time check, mirrors PCIe pattern)
-- ----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION fn_validate_memory_compatibility()
RETURNS TRIGGER AS $$
DECLARE
    v_board_id UUID;
    v_mod_type memory_module_type;
    v_supported BOOLEAN;
BEGIN
    SELECT module_type INTO v_mod_type FROM memory_modules WHERE component_id = NEW.component_id;
    IF v_mod_type IS NULL THEN
        RETURN NEW;  -- not a memory component
    END IF;

    SELECT c.id INTO v_board_id
      FROM build_components bc2
      JOIN components c ON c.id = bc2.component_id
     WHERE bc2.build_id = NEW.build_id AND c.category = 'motherboard'
     LIMIT 1;

    IF v_board_id IS NULL THEN
        RETURN NEW;  -- motherboard not yet selected; validated later on build finalization
    END IF;

    SELECT EXISTS (
        SELECT 1 FROM motherboard_memory_support
         WHERE motherboard_component_id = v_board_id AND module_type = v_mod_type
    ) INTO v_supported;

    IF NOT v_supported THEN
        RAISE EXCEPTION 'Motherboard % does not support memory type %', v_board_id, v_mod_type;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_validate_memory_compatibility
    BEFORE INSERT OR UPDATE ON build_components
    FOR EACH ROW EXECUTE FUNCTION fn_validate_memory_compatibility();

-- ----------------------------------------------------------------------------
-- 8. DISTRIBUTORS, PRICING, MARKUP
-- ----------------------------------------------------------------------------

CREATE TABLE distributors (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    code            TEXT NOT NULL UNIQUE,     -- 'ingram_micro', 'arrow'
    display_name    TEXT NOT NULL,
    api_base_url    TEXT NOT NULL,
    supports_blind_dropship BOOLEAN NOT NULL DEFAULT TRUE,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE
);

-- Cached distributor price/availability snapshot (populated by the sync
-- worker; the live lookup engine reads-through this cache first).
CREATE TABLE distributor_offers (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    component_id         UUID NOT NULL REFERENCES components(id) ON DELETE CASCADE,
    distributor_id        UUID NOT NULL REFERENCES distributors(id),
    distributor_sku        TEXT NOT NULL,
    cost_cents             INTEGER NOT NULL CHECK (cost_cents >= 0),
    quantity_available       INTEGER NOT NULL DEFAULT 0,
    lead_time_days           INTEGER,
    last_synced_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (component_id, distributor_id)
);

CREATE INDEX idx_distributor_offers_component ON distributor_offers(component_id);

-- Markup rules: most-specific-wins (category+distributor > category > global).
CREATE TABLE markup_rules (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    category            component_category,          -- NULL = applies to all categories
    distributor_id        UUID REFERENCES distributors(id),  -- NULL = applies to all distributors
    margin_percent          NUMERIC(5,2) NOT NULL CHECK (margin_percent >= 0),
    min_margin_cents         INTEGER NOT NULL DEFAULT 0,
    priority                SMALLINT NOT NULL DEFAULT 0    -- higher wins on tie
);

-- ----------------------------------------------------------------------------
-- 9. ORDERS / DROPSHIP PIPELINE
-- ----------------------------------------------------------------------------

CREATE TABLE orders (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id                  UUID NOT NULL,
    build_id                  UUID REFERENCES build_configurations(id),
    stripe_payment_intent_id    TEXT NOT NULL UNIQUE,
    status                     order_status NOT NULL DEFAULT 'pending_payment',
    shipping_address            JSONB NOT NULL,
    blind_dropship               BOOLEAN NOT NULL DEFAULT TRUE,
    subtotal_cents               INTEGER NOT NULL,
    total_cents                   INTEGER NOT NULL,
    created_at                    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE order_items (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    order_id             UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    component_id           UUID NOT NULL REFERENCES components(id),
    distributor_id           UUID NOT NULL REFERENCES distributors(id),
    mpn                       TEXT NOT NULL,
    distributor_sku            TEXT NOT NULL,
    quantity                    INTEGER NOT NULL CHECK (quantity > 0),
    unit_cost_cents               INTEGER NOT NULL,
    unit_price_cents                INTEGER NOT NULL
);

-- One row per distributor sub-order (a single HardwareFabric order can
-- fan out into multiple distributor purchase orders / shipments).
CREATE TABLE distributor_orders (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    order_id                 UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    distributor_id             UUID NOT NULL REFERENCES distributors(id),
    distributor_order_number     TEXT,
    status                        TEXT NOT NULL DEFAULT 'submitted',
    tracking_number                 TEXT,
    submitted_at                     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_order_items_order ON order_items(order_id);
CREATE INDEX idx_distributor_orders_order ON distributor_orders(order_id);

-- ----------------------------------------------------------------------------
-- 10. USERS + CART PERSISTENCE
-- ----------------------------------------------------------------------------
-- Added to back real auth and a real cart (previously build_configurations
-- and orders referenced a bare user_id UUID with no owning table, and there
-- was no persisted cart at all — "Add build to cart" had no backing state).

CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email           TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    full_name       TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE build_configurations
    ADD CONSTRAINT fk_build_configurations_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE orders
    ADD CONSTRAINT fk_orders_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

-- One row per line item currently sitting in a user's cart. build_id is set
-- when the line item was added via "Add build to cart" (bulk-adds every
-- populated socket of a build_configuration) so the cart UI can still group
-- items by originating build; it stays nullable because a line item can
-- also be added directly without going through a build.
CREATE TABLE cart_items (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id                 UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    build_id                UUID REFERENCES build_configurations(id) ON DELETE SET NULL,
    component_id            UUID NOT NULL REFERENCES components(id),
    quantity                INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0),
    preferred_distributor   TEXT,
    added_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, component_id, build_id)
);

CREATE INDEX idx_cart_items_user ON cart_items(user_id);

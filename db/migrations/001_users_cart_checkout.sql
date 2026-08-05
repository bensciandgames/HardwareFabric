-- Migration 001: users + cart persistence + checkout sessions
--
-- Run this once against the live Supabase database (SQL Editor or psql).
-- Purely additive — no existing table is altered destructively, no data
-- is touched. Safe to run even though build_configurations/orders already
-- exist and may have rows: this only adds new tables and two new foreign
-- key constraints on the existing user_id columns.
--
-- Pulled verbatim from db/schema.sql sections 9 (checkout_sessions) and 10
-- (users + cart_items) — keep this file and schema.sql in sync if either
-- changes again.

BEGIN;

-- --- checkout_sessions -------------------------------------------------
-- Stripe caps each PaymentIntent metadata VALUE at 500 characters, so the
-- priced cart can't be JSON-dumped straight into metadata for anything but
-- a tiny cart. The checkout route persists the priced snapshot here and
-- puts only this row's id in Stripe metadata; the webhook looks it back up
-- by id.
CREATE TABLE IF NOT EXISTS checkout_sessions (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id             UUID NOT NULL,
    build_id            UUID REFERENCES build_configurations(id),
    cart_snapshot       JSONB NOT NULL,
    shipping_address    JSONB NOT NULL,
    subtotal_cents      INTEGER NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_checkout_sessions_user ON checkout_sessions(user_id);

-- --- users ---------------------------------------------------------------
-- Previously build_configurations and orders referenced a bare user_id
-- UUID with no owning table.
CREATE TABLE IF NOT EXISTS users (
    id                              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email                           TEXT NOT NULL UNIQUE,
    password_hash                   TEXT NOT NULL,
    full_name                       TEXT,
    created_at                      TIMESTAMPTZ NOT NULL DEFAULT now(),
    email_verified                  BOOLEAN NOT NULL DEFAULT FALSE,
    verification_token              TEXT,
    verification_token_expires_at   TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_users_verification_token
    ON users(verification_token) WHERE verification_token IS NOT NULL;

-- Add the FKs now that users exists. Guarded so this migration can be
-- re-run safely if it partially failed previously.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_build_configurations_user'
    ) THEN
        ALTER TABLE build_configurations
            ADD CONSTRAINT fk_build_configurations_user
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_orders_user'
    ) THEN
        ALTER TABLE orders
            ADD CONSTRAINT fk_orders_user
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
    END IF;
END $$;

-- --- cart_items ------------------------------------------------------------
-- One row per line item currently sitting in a user's cart. build_id is set
-- when the line item was added via "Add build to cart" so the cart UI can
-- still group items by originating build; nullable because a line item can
-- also be added directly without going through a build.
CREATE TABLE IF NOT EXISTS cart_items (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id                 UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    build_id                UUID REFERENCES build_configurations(id) ON DELETE SET NULL,
    component_id            UUID NOT NULL REFERENCES components(id),
    quantity                INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0),
    preferred_distributor   TEXT,
    added_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, component_id, build_id)
);

CREATE INDEX IF NOT EXISTS idx_cart_items_user ON cart_items(user_id);

COMMIT;

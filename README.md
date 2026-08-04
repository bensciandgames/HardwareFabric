# HardwareFabric.tech

An all-in-one hardware configuration and instant procurement platform spanning
consumer, workstation, and rackmount-server builds in one unified cart. See
`PROJECT_BRIEF.md` for full architectural context.

This pass implements the backlog items that were previously missing:

1. **Checkout / PaymentIntent creation** (`backend/app/api/routes/checkout.py`)
   — prices the cart via the same offer-resolution path the builder uses,
   snapshots `priced_line_items` (unit cost + unit price per MPN) into the
   Stripe PaymentIntent metadata, and returns a `client_secret`. This is the
   piece the fulfillment webhook already assumed existed.
2. **Component picker** (`frontend/components/ComponentPickerModal.tsx`) —
   "Insert component" now opens a real modal backed by `GET /api/v1/components`
   and `POST /api/v1/pricing/lookup`, optionally letting you assign a
   populated motherboard's PCIe slot for lane-consuming parts.
3. **Cart persistence** (`cart_items` table + `backend/app/api/routes/cart.py`
   + `frontend/contexts/CartContext.tsx`) — the Cart tab and "Add build to
   cart" now have real backing state.
4. **Saved Builds / Completed Builds pages** (`frontend/app/saved`,
   `frontend/app/completed`) — backed by `build_configurations` and `orders`.
5. **Auth** (`users` table, `backend/app/auth.py`, `/api/v1/auth/*`) — minimal
   email/password + JWT, deliberately small so it's easy to swap out later.
6. **Distributor sync worker** (`backend/app/worker/sync_offers.py`) —
   populates `distributor_offers` on a schedule; the live pricing lookup
   (`backend/app/services/offer_lookup.py`) now reads through that cache
   first and only calls out to distributors live for whatever isn't freshly
   cached.
7. **Compatibility surfaced in the UI** — the Postgres triggers
   (`fn_validate_pcie_allocation`, `fn_validate_memory_compatibility`) remain
   the source of truth; `POST /api/v1/builds/{id}/components` now catches a
   trigger rejection and returns it as a 409, which the picker modal shows
   verbatim. `GET /api/v1/builds/{id}/compatibility` surfaces the soft
   bottleneck-warning view as a banner in the builder.

## Running it locally

### Database

```bash
createdb hardwarefabric
psql hardwarefabric -f db/schema.sql
```

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in Stripe / Ingram / Arrow / JWT secrets
uvicorn app.main:app --reload --port 8000
```

Optional — warm the distributor offer cache in a second terminal:

```bash
python -m app.worker.sync_offers --loop
```

Local Stripe webhook forwarding:

```bash
stripe listen --forward-to localhost:8000/api/v1/webhooks/stripe
```

### Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local   # set NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY
npm run dev
```

Visit `http://localhost:3000` — it redirects to `/builder`.

## Known simplifications in this pass

- Switching workspace scale in the builder starts a fresh build rather than
  attempting to migrate parts across scales; the previous draft stays saved
  under Saved Builds.
- The PCIe slot picker in the component modal is manual (a dropdown of open
  slots on the currently selected motherboard) rather than an automatic
  best-fit allocator — the DB trigger still rejects anything electrically
  invalid regardless of what the UI suggests.
- Auth is intentionally minimal (no refresh tokens, no password reset, no
  OAuth) — swap `backend/app/auth.py` out when real auth requirements land.
- `automatic_payment_methods` is enabled on the PaymentIntent for simplicity;
  restrict to specific payment method types if you need tighter control over
  what shows up in Stripe's PaymentElement.

# HardwareFabric.tech — Project Context & Working Brief

Paste this into your Claude Project's custom instructions (or as a pinned
first message) so any future conversation has full architectural context
without re-explaining the platform from scratch.

---

## 1. What this platform is

HardwareFabric.tech is an all-in-one hardware configuration and instant
procurement platform. Unlike PCPartPicker, it is not a comparison/linkout
site — it is a full commerce platform that spans three distinct scales of
machine in one unified builder and cart:

- **Consumer Tower** — standard ATX/mATX desktops, UDIMM memory
- **Workstation Rig** — HEDT/workstation builds, E-ATX, RDIMM memory
- **Rackmount Server Blade** — enterprise server components, SSI-EEB,
  RDIMM/LRDIMM memory, RAID/HBA controllers, riser/backplane hardware

Users configure a build, add it to a single cart regardless of scale,
check out directly via Stripe, and the backend automatically places
**blind dropship** orders through industrial distributor APIs (Ingram
Micro, Arrow Electronics) shipped straight to the end user with
distributor branding suppressed.

## 2. Tech stack (decided — don't re-litigate unless there's a real reason)

- **Database:** PostgreSQL 15+ (relational, not graph DB — the component
  graph is modeled via foreign keys + a trigger-enforced constraint layer,
  not Neo4j)
- **Backend:** Python 3.11+, FastAPI, asyncpg (raw SQL, no ORM), httpx for
  outbound distributor calls, `stripe` SDK for payments
- **Frontend:** Next.js 14 (App Router), TypeScript, Tailwind CSS, no
  component library — all custom components
- **Payments:** Stripe (PaymentIntents + webhook-driven fulfillment)
- **Distributors integrated so far:** Ingram Micro (OAuth2 client
  credentials), Arrow Electronics (API key auth)

## 3. Core architectural decisions already made

### Database (`db/schema.sql`)
- Every physical part is a row in `components` (base node), with
  category-specific satellite tables (`memory_modules`, `motherboards`,
  `pcie_devices`, etc.) — a 1:1 extension pattern, not single-table
  inheritance.
- **Memory structural flags:** `memory_module_type` enum
  (`UDIMM`/`RDIMM`/`LRDIMM`) lives on `memory_modules`.
  `motherboard_memory_support` is the join table declaring which types a
  given board will actually train — this is what prevents an LRDIMM being
  added to a UDIMM-only consumer board.
- **PCIe lane/bifurcation enforcement is done at the DB layer, not the app
  layer.** `pcie_slots` models every physical slot/M.2 site with a
  `shares_lane_group` column; slots that share a physical lane pool
  (e.g. PCIe1/PCIe2 both drawing from the same 16 CPU lanes) share a group
  string. A `BEFORE INSERT/UPDATE` trigger on `build_components`
  (`fn_validate_pcie_allocation`) sums claimed lanes per group and rejects
  oversubscription. This is deliberate: multiple app code paths write to
  `build_components` (builder UI, cart re-price, admin tools), so the
  constraint has to live where it can't be bypassed.
- A companion view (`v_build_bottleneck_warnings`) flags high-VRAM
  accelerators bifurcated below x16 as a **soft warning**, not a hard
  block — sometimes intentional.
- Orders fan out 1:many into `distributor_orders` — one HardwareFabric
  order can become multiple distributor purchase orders.

### Backend (`backend/`)
- `DistributorClient` (abstract base in `app/distributors/base.py`) is the
  contract every distributor integration implements. Adding a new
  distributor (TD SYNNEX, D&H, etc.) = new subclass + one line in
  `registry.py`. Nothing else changes.
- Distributor **cost** is never exposed to the frontend — `PricingEngine`
  (`app/services/pricing.py`) converts `DistributorAvailability` (internal,
  has cost) into `PricedOffer` (external, retail price only) using
  most-specific-wins markup rules (category+distributor > category >
  distributor > global default), with a per-line minimum-margin floor so
  cheap parts don't clear pennies of profit.
- `POST /api/v1/pricing/lookup` queries all configured distributors
  concurrently and degrades gracefully — one distributor being down must
  not fail the whole lookup.
- `POST /api/v1/webhooks/stripe` is the **only** order-creation entrypoint.
  It verifies the Stripe signature, is idempotent on
  `stripe_payment_intent_id` (Stripe retries webhooks), and rebuilds the
  order server-side from PaymentIntent metadata — it never trusts a
  resubmitted cart from the client.
- Blind dropship is enabled via each distributor's actual API fields
  (Ingram: `blindShipment` + `packingSlipSupressPricing`; Arrow:
  `suppressArrowBranding`) — **these require the flag enabled on our
  reseller account by each distributor first**; this is an account-setup
  step with Ingram/Arrow reps, not something code alone controls.
- **Known open item:** checkout must snapshot `priced_line_items`
  (unit cost + unit price per MPN) into the PaymentIntent metadata at
  checkout time. The order fulfillment route currently expects this
  snapshot and must NOT re-fetch live prices during fulfillment — prices
  have to be locked at the moment of checkout, or we could charge the
  customer one price while distributor cost has moved by fulfillment time.
  **This checkout route has not been built yet.**

### Frontend (`frontend/`)
- Next.js App Router, path alias `@/*` → project root.
- **Design system:** dark "PCB substrate" background (`#0A0F1E`), medium
  blue `#3B7DFF` for structural/trace elements, signal yellow `#FFD60A`
  reserved for power/action (CTAs, active states, pulse animation) — the
  two accent colors are role-separated, not just alternated decoratively.
  Space Grotesk (display/headers), Inter (body), JetBrains Mono (any
  actual data: MPNs, prices, lane counts).
- **Signature UI element:** in `BuildCanvas.tsx`, every populated
  component socket connects to one continuous animated "trace bus" line —
  this is the literal representation of "unlimited procurement capacity":
  current that keeps flowing and extending as the build grows, rather
  than a static "unlimited" badge. Implemented via CSS `stroke-dashoffset`
  animation (`.trace-line` in `globals.css`), respects
  `prefers-reduced-motion`.
- Top nav (`TopNav.tsx`) has four tabs: **Fabric Builder / Saved Builds /
  Completed Builds / Cart** (with live item-count badge), styled as PCB
  edge-connector pads with a glowing underline on the active tab.
- Workspace mode toggle (`WorkspaceModeToggle.tsx`) is a 3-position
  relay-switch metaphor (Consumer Tower / Workstation Rig / Rackmount
  Server Blade) with a yellow LED indicator — switching it re-filters
  `ComponentRail.tsx` categories and swaps the socket template in
  `BuildCanvas.tsx`.
- Currently all part/pricing data in the builder page is **hardcoded mock
  data** (`SLOT_TEMPLATES` in `app/builder/page.tsx`) — not yet wired to
  `POST /api/v1/pricing/lookup`.

## 4. What's built so far (file inventory)

```
hardwarefabric/
├── db/
│   └── schema.sql                          # full PostgreSQL schema, triggers, views
├── backend/
│   ├── requirements.txt
│   ├── .env.example
│   └── app/
│       ├── main.py                         # FastAPI entrypoint
│       ├── config.py                       # env-based settings
│       ├── models.py                       # shared Pydantic schemas
│       ├── db.py                           # asyncpg pool + repository functions
│       ├── distributors/
│       │   ├── base.py                     # abstract DistributorClient
│       │   ├── ingram_micro.py             # Ingram Micro client
│       │   ├── arrow.py                    # Arrow Electronics client
│       │   └── registry.py                 # code -> client instance map
│       ├── services/
│       │   └── pricing.py                  # markup engine
│       └── api/routes/
│           ├── pricing.py                  # POST /api/v1/pricing/lookup
│           └── orders.py                   # POST /api/v1/webhooks/stripe
└── frontend/
    ├── package.json / tsconfig.json / next.config.js / postcss.config.js
    ├── tailwind.config.ts                  # color/type/animation tokens
    └── app/
        ├── layout.tsx                      # fonts, circuit substrate, TopNav
        ├── globals.css                     # trace bus animation, substrate bg
        ├── page.tsx                        # redirects to /builder
        └── builder/page.tsx                # Fabric Builder page (mock data)
    └── components/
        ├── TopNav.tsx
        ├── WorkspaceModeToggle.tsx
        ├── ComponentRail.tsx
        ├── BuildCanvas.tsx                 # signature trace-bus element
        └── PricingManifest.tsx
```

## 5. Not built yet — the realistic next-steps backlog

1. **Checkout flow / PaymentIntent creation route** (backend) — takes the
   cart, prices it via `PricingEngine`, creates the Stripe PaymentIntent
   with `priced_line_items` + `cart` + `user_id` + `build_id` in metadata.
   This is the missing piece the orders webhook already assumes exists.
2. **Component picker drawer/modal** (frontend) — "Insert component" in
   `BuildCanvas.tsx` currently does nothing; needs to open a filtered list
   of `PricedOffer[]` fetched from `/api/v1/pricing/lookup` for the active
   category, filtered further by physical/electrical compatibility with
   the currently selected motherboard (memory type, PCIe slot lanes).
3. **Cart persistence** — a real cart store (session/DB-backed), since
   "Add build to cart" and the Cart tab currently have no backing state.
4. **Saved Builds / Completed Builds pages** — tabs exist in nav, pages
   don't exist yet.
5. **Auth** — `user_id` is referenced throughout the schema and backend
   but no auth system has been chosen yet.
6. **Distributor sync worker** — a background job to populate/refresh
   `distributor_offers` on a schedule, since the live lookup route
   currently calls distributors synchronously on every pricing request
   rather than reading a warm cache.
7. **Compatibility validation surfaced in the UI** — the DB triggers
   reject bad lane/memory combinations on write, but the frontend doesn't
   yet call anything that would show *why* a part can't be added before
   the user tries.

## 6. Conventions to keep following

- All money handled as **integer cents**, never floats, until formatted
  for display.
- Distributor **cost** never crosses into any Pydantic model exposed on a
  public route — only `PricedOffer.retail_price_cents`.
- New distributor integrations extend `DistributorClient`; never special-
  case a distributor by name outside the `distributors/` package.
- Compatibility rules (memory type, PCIe lanes) are enforced in Postgres
  triggers first; the frontend should treat those as the source of truth
  and only pre-filter for UX smoothness, not as the actual guarantee.
- Design tokens live in `tailwind.config.ts` + `globals.css` — new UI
  should pull from those, not introduce ad hoc colors.

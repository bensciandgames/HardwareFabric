"""
app/main.py
FastAPI application entrypoint.

Run locally:
    uvicorn app.main:app --reload --port 8000

Stripe CLI (for local webhook testing):
    stripe listen --forward-to localhost:8000/api/v1/webhooks/stripe

Distributor offer cache warmer (optional but recommended so pricing lookups
read from a warm cache instead of hitting distributor APIs synchronously):
    python -m app.worker.sync_offers --loop
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import init_pool, close_pool
from app.api.routes import auth, cart, checkout, components, builds, pricing, orders

logging.basicConfig(level=logging.INFO)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    yield
    await close_pool()


app = FastAPI(
    title="HardwareFabric.tech API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(components.router)
app.include_router(builds.router)
app.include_router(cart.router)
app.include_router(pricing.router)
app.include_router(checkout.router)
app.include_router(orders.router)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}

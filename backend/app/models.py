"""
app/models.py
Shared Pydantic schemas used across the distributor abstraction layer,
pricing engine, and API routes.
"""

from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class DistributorCode(str, Enum):
    INGRAM_MICRO = "ingram_micro"
    ARROW = "arrow"


class WorkspaceMode(str, Enum):
    CONSUMER_TOWER = "consumer_tower"
    WORKSTATION_RIG = "workstation_rig"
    RACKMOUNT_SERVER = "rackmount_server"


class ComponentCategory(str, Enum):
    CPU = "cpu"
    MOTHERBOARD = "motherboard"
    MEMORY = "memory"
    GPU = "gpu"
    STORAGE_NVME = "storage_nvme"
    STORAGE_SATA = "storage_sata"
    PSU = "psu"
    CASE = "case"
    COOLER = "cooler"
    NIC = "nic"
    RAID_HBA = "raid_hba"
    RISER_BACKPLANE = "riser_backplane"


class DistributorAvailability(BaseModel):
    """Normalized shape every distributor client must map its raw response into."""
    mpn: str
    distributor: DistributorCode
    distributor_sku: str
    cost_cents: int = Field(..., description="Distributor's wholesale cost, in cents, USD")
    quantity_available: int
    lead_time_days: Optional[int] = None
    raw_status: Optional[str] = None  # distributor's own status string, kept for audit/debug


class PricedOffer(BaseModel):
    """What the frontend actually receives — cost is never exposed to the client."""
    mpn: str
    sku: str
    name: str
    category: ComponentCategory
    distributor: DistributorCode
    retail_price_cents: int
    quantity_available: int
    lead_time_days: Optional[int] = None
    in_stock: bool


class ShippingAddress(BaseModel):
    name: str
    line1: str
    line2: Optional[str] = None
    city: str
    state: str
    postal_code: str
    country: str = "US"
    phone: Optional[str] = None


class CartLineItem(BaseModel):
    component_id: str
    mpn: str
    quantity: int = Field(..., gt=0)
    preferred_distributor: Optional[DistributorCode] = None


class DropshipOrderRequest(BaseModel):
    """Internal request built server-side after a Stripe payment succeeds.
    Never accepted directly from the client — see orders.py."""
    order_id: str
    line_items: list[CartLineItem]
    shipping_address: ShippingAddress
    blind_dropship: bool = True


class DistributorOrderResult(BaseModel):
    distributor: DistributorCode
    distributor_order_number: Optional[str]
    accepted_line_items: list[str]  # mpns
    rejected_line_items: list[str]
    status: str


class DistributorOrderStatus(BaseModel):
    """Result of polling a distributor for the current state of a
    previously-submitted order — used by the order tracking sync worker
    (app/worker/sync_order_status.py) to populate distributor_orders'
    status/tracking_number once a distributor actually ships."""
    status: str
    tracking_number: Optional[str] = None

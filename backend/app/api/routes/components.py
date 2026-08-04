"""
app/api/routes/components.py

Lets the frontend's component picker list real parts (filtered by category
and workspace scale) before asking /api/v1/pricing/lookup for live retail
prices on just that filtered set. Kept deliberately dumb — category and
workspace-scope filtering only — because the actual compatibility source of
truth (memory type, PCIe lanes) lives in the Postgres triggers on
build_components; this route is a UX pre-filter, not the guarantee.
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.models import ComponentCategory
from app.db import fetch_components, fetch_pcie_slots_for_motherboard

router = APIRouter(prefix="/api/v1/components", tags=["components"])


class ComponentSummary(BaseModel):
    id: str
    sku: str
    mpn: str
    category: ComponentCategory
    name: str
    msrp_cents: int
    specs: dict


class PcieSlotSummary(BaseModel):
    id: str
    slot_label: str
    physical_form: str
    max_electrical_lanes: int
    pcie_version: float
    root_source: str
    shares_lane_group: str | None
    bifurcation_capable: bool
    bifurcation_modes: list[str]


@router.get("", response_model=list[ComponentSummary])
async def list_components(
    category: ComponentCategory | None = None,
    workspace_mode: str | None = Query(None, description="consumer_tower | workstation_rig | rackmount_server"),
    search: str | None = None,
    limit: int = Query(100, le=200),
) -> list[ComponentSummary]:
    rows = await fetch_components(
        category=category.value if category else None,
        workspace_mode=workspace_mode,
        search=search,
        limit=limit,
    )
    return [
        ComponentSummary(
            id=str(r["id"]), sku=r["sku"], mpn=r["mpn"], category=r["category"],
            name=r["name"], msrp_cents=r["msrp_cents"], specs=r["specs"] or {},
        )
        for r in rows
    ]


@router.get("/{motherboard_component_id}/pcie-slots", response_model=list[PcieSlotSummary])
async def list_pcie_slots(motherboard_component_id: str) -> list[PcieSlotSummary]:
    rows = await fetch_pcie_slots_for_motherboard(motherboard_component_id)
    return [
        PcieSlotSummary(
            id=str(r["id"]), slot_label=r["slot_label"], physical_form=r["physical_form"],
            max_electrical_lanes=r["max_electrical_lanes"], pcie_version=float(r["pcie_version"]),
            root_source=r["root_source"], shares_lane_group=r["shares_lane_group"],
            bifurcation_capable=r["bifurcation_capable"], bifurcation_modes=r["bifurcation_modes"] or [],
        )
        for r in rows
    ]

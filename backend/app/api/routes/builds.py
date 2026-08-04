"""
app/api/routes/builds.py

CRUD for build_configurations + build_components. This is what backs the
Fabric Builder, Saved Builds, and Completed Builds pages — previously the
builder page only held mock data in React state with nothing persisted.

Compatibility is enforced in Postgres (fn_validate_pcie_allocation,
fn_validate_memory_compatibility — see db/schema.sql section 6/7). This
route does not re-implement those rules; it catches the trigger's rejection
and turns it into a 409 with the trigger's own message, and separately
exposes the soft-warning view (v_build_bottleneck_warnings) so the UI can
show *why* a part is risky before the user even tries to add it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.auth import CurrentUser, get_current_user
from app.models import ComponentCategory, WorkspaceMode
from app.db import (
    BuildComponentConflict,
    add_build_component,
    create_build,
    delete_build,
    fetch_bottleneck_warnings,
    fetch_build,
    fetch_build_components,
    fetch_builds_for_user,
    remove_build_component,
    update_build,
)

router = APIRouter(prefix="/api/v1/builds", tags=["builds"])


class CreateBuildRequest(BaseModel):
    workspace_mode: WorkspaceMode
    name: str = "Untitled Build"


class UpdateBuildRequest(BaseModel):
    name: str | None = None
    status: str | None = None  # draft | validated | in_cart | ordered


class BuildResponse(BaseModel):
    id: str
    name: str
    workspace_mode: str
    status: str
    created_at: str
    updated_at: str


class BuildComponentResponse(BaseModel):
    id: str
    component_id: str
    pcie_slot_id: str | None
    quantity: int
    sku: str
    mpn: str
    name: str
    category: ComponentCategory
    msrp_cents: int
    slot_label: str | None


class AddBuildComponentRequest(BaseModel):
    component_id: str
    pcie_slot_id: str | None = None
    quantity: int = 1


class BottleneckWarning(BaseModel):
    component_name: str
    vram_gb: int | None
    slot_label: str
    slot_capacity: int
    device_ideal_lanes: int


def _to_build_response(row: dict) -> BuildResponse:
    return BuildResponse(
        id=str(row["id"]), name=row["name"], workspace_mode=row["workspace_mode"],
        status=row["status"], created_at=row["created_at"].isoformat(),
        updated_at=row["updated_at"].isoformat(),
    )


@router.post("", response_model=BuildResponse, status_code=status.HTTP_201_CREATED)
async def create_new_build(
    payload: CreateBuildRequest, current_user: CurrentUser = Depends(get_current_user)
) -> BuildResponse:
    row = await create_build(current_user.user_id, payload.workspace_mode.value, payload.name)
    return _to_build_response(row)


@router.get("", response_model=list[BuildResponse])
async def list_builds(
    status_filter: str | None = None, current_user: CurrentUser = Depends(get_current_user)
) -> list[BuildResponse]:
    rows = await fetch_builds_for_user(current_user.user_id, status_filter)
    return [_to_build_response(r) for r in rows]


@router.get("/{build_id}", response_model=BuildResponse)
async def get_build(build_id: str, current_user: CurrentUser = Depends(get_current_user)) -> BuildResponse:
    row = await fetch_build(build_id, current_user.user_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Build not found")
    return _to_build_response(row)


@router.patch("/{build_id}", response_model=BuildResponse)
async def patch_build(
    build_id: str, payload: UpdateBuildRequest, current_user: CurrentUser = Depends(get_current_user)
) -> BuildResponse:
    row = await update_build(build_id, current_user.user_id, payload.name, payload.status)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Build not found")
    return _to_build_response(row)


@router.delete("/{build_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_existing_build(build_id: str, current_user: CurrentUser = Depends(get_current_user)) -> None:
    deleted = await delete_build(build_id, current_user.user_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Build not found")


@router.get("/{build_id}/components", response_model=list[BuildComponentResponse])
async def list_build_components(
    build_id: str, current_user: CurrentUser = Depends(get_current_user)
) -> list[BuildComponentResponse]:
    build = await fetch_build(build_id, current_user.user_id)
    if build is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Build not found")
    rows = await fetch_build_components(build_id)
    return [
        BuildComponentResponse(
            id=str(r["id"]), component_id=str(r["component_id"]),
            pcie_slot_id=str(r["pcie_slot_id"]) if r["pcie_slot_id"] else None,
            quantity=r["quantity"], sku=r["sku"], mpn=r["mpn"], name=r["name"],
            category=r["category"], msrp_cents=r["msrp_cents"], slot_label=r["slot_label"],
        )
        for r in rows
    ]


@router.post("/{build_id}/components", response_model=BuildComponentResponse, status_code=status.HTTP_201_CREATED)
async def add_component_to_build(
    build_id: str, payload: AddBuildComponentRequest, current_user: CurrentUser = Depends(get_current_user)
) -> BuildComponentResponse:
    build = await fetch_build(build_id, current_user.user_id)
    if build is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Build not found")

    try:
        row = await add_build_component(build_id, payload.component_id, payload.pcie_slot_id, payload.quantity)
    except BuildComponentConflict as exc:
        # This is the Postgres trigger rejecting the insert — memory-type
        # mismatch or PCIe lane oversubscription. The message is the
        # trigger's own RAISE EXCEPTION text, which is written to be
        # human-readable in the UI as-is.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.message) from exc

    components = await fetch_build_components(build_id)
    match = next(c for c in components if str(c["id"]) == str(row["id"]))
    return BuildComponentResponse(
        id=str(match["id"]), component_id=str(match["component_id"]),
        pcie_slot_id=str(match["pcie_slot_id"]) if match["pcie_slot_id"] else None,
        quantity=match["quantity"], sku=match["sku"], mpn=match["mpn"], name=match["name"],
        category=match["category"], msrp_cents=match["msrp_cents"], slot_label=match["slot_label"],
    )


@router.delete("/{build_id}/components/{build_component_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_component_from_build(
    build_id: str, build_component_id: str, current_user: CurrentUser = Depends(get_current_user)
) -> None:
    build = await fetch_build(build_id, current_user.user_id)
    if build is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Build not found")
    removed = await remove_build_component(build_component_id, build_id)
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Component not found on this build")


@router.get("/{build_id}/compatibility", response_model=list[BottleneckWarning])
async def get_compatibility_warnings(
    build_id: str, current_user: CurrentUser = Depends(get_current_user)
) -> list[BottleneckWarning]:
    """Soft warnings only (v_build_bottleneck_warnings) — hard rule
    violations never make it into build_components in the first place
    because the INSERT trigger rejects them before this endpoint would
    ever see them."""
    build = await fetch_build(build_id, current_user.user_id)
    if build is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Build not found")
    rows = await fetch_bottleneck_warnings(build_id)
    return [
        BottleneckWarning(
            component_name=r["component_name"], vram_gb=r["vram_gb"], slot_label=r["slot_label"],
            slot_capacity=r["slot_capacity"], device_ideal_lanes=r["device_ideal_lanes"],
        )
        for r in rows
    ]

"""
app/api/routes/cart.py

Real cart persistence (cart_items table), backing the Cart tab and the
"Add build to cart" action — previously neither had any backing state.
Adding a whole build bulk-inserts one cart line per populated build_component.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.auth import CurrentUser, get_current_user
from app.models import ComponentCategory
from app.db import (
    clear_cart,
    fetch_build,
    fetch_build_components,
    fetch_cart_items,
    remove_cart_item,
    update_cart_item_quantity,
    upsert_cart_item,
)

router = APIRouter(prefix="/api/v1/cart", tags=["cart"])


class CartItemResponse(BaseModel):
    id: str
    build_id: str | None
    component_id: str
    quantity: int
    preferred_distributor: str | None
    sku: str
    mpn: str
    name: str
    category: ComponentCategory
    msrp_cents: int


class AddCartItemRequest(BaseModel):
    component_id: str
    quantity: int = 1
    build_id: str | None = None
    preferred_distributor: str | None = None


class AddBuildToCartRequest(BaseModel):
    build_id: str


class UpdateCartItemRequest(BaseModel):
    quantity: int


def _to_response(r: dict) -> CartItemResponse:
    return CartItemResponse(
        id=str(r["id"]), build_id=str(r["build_id"]) if r["build_id"] else None,
        component_id=str(r["component_id"]), quantity=r["quantity"],
        preferred_distributor=r["preferred_distributor"], sku=r["sku"], mpn=r["mpn"],
        name=r["name"], category=r["category"], msrp_cents=r["msrp_cents"],
    )


@router.get("", response_model=list[CartItemResponse])
async def get_cart(current_user: CurrentUser = Depends(get_current_user)) -> list[CartItemResponse]:
    rows = await fetch_cart_items(current_user.user_id)
    return [_to_response(r) for r in rows]


@router.post("/items", response_model=CartItemResponse, status_code=status.HTTP_201_CREATED)
async def add_cart_item(
    payload: AddCartItemRequest, current_user: CurrentUser = Depends(get_current_user)
) -> CartItemResponse:
    row = await upsert_cart_item(
        current_user.user_id, payload.component_id, payload.quantity,
        payload.build_id, payload.preferred_distributor,
    )
    items = await fetch_cart_items(current_user.user_id)
    match = next(i for i in items if str(i["id"]) == str(row["id"]))
    return _to_response(match)


@router.post("/add-build", response_model=list[CartItemResponse], status_code=status.HTTP_201_CREATED)
async def add_build_to_cart(
    payload: AddBuildToCartRequest, current_user: CurrentUser = Depends(get_current_user)
) -> list[CartItemResponse]:
    build = await fetch_build(payload.build_id, current_user.user_id)
    if build is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Build not found")

    components = await fetch_build_components(payload.build_id)
    if not components:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This build has no components to add")

    for c in components:
        await upsert_cart_item(current_user.user_id, str(c["component_id"]), c["quantity"], payload.build_id, None)

    rows = await fetch_cart_items(current_user.user_id)
    return [_to_response(r) for r in rows if r["build_id"] and str(r["build_id"]) == payload.build_id]


@router.patch("/items/{cart_item_id}", response_model=CartItemResponse)
async def update_cart_item(
    cart_item_id: str, payload: UpdateCartItemRequest, current_user: CurrentUser = Depends(get_current_user)
) -> CartItemResponse:
    if payload.quantity <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="quantity must be greater than 0")
    row = await update_cart_item_quantity(cart_item_id, current_user.user_id, payload.quantity)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart item not found")
    items = await fetch_cart_items(current_user.user_id)
    match = next(i for i in items if str(i["id"]) == str(row["id"]))
    return _to_response(match)


@router.delete("/items/{cart_item_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_cart_item(cart_item_id: str, current_user: CurrentUser = Depends(get_current_user)) -> None:
    removed = await remove_cart_item(cart_item_id, current_user.user_id)
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart item not found")


@router.delete("", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def empty_cart(current_user: CurrentUser = Depends(get_current_user)) -> None:
    await clear_cart(current_user.user_id)

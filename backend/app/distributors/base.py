"""
app/distributors/base.py
Abstract contract every distributor integration must satisfy. New
distributors (TD SYNNEX, D&H, etc.) plug in by subclassing this — nothing
else in the codebase needs to change.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional

from app.models import (
    DistributorAvailability,
    DropshipOrderRequest,
    DistributorOrderResult,
    DistributorCode,
)


class DistributorAPIError(Exception):
    """Raised when a distributor call fails after retries. Carries the raw
    status code / body so the caller can decide fallback behavior (e.g.
    route to the other distributor instead of failing the whole cart)."""

    def __init__(self, distributor: DistributorCode, message: str, status_code: Optional[int] = None):
        self.distributor = distributor
        self.status_code = status_code
        super().__init__(f"[{distributor.value}] {message} (status={status_code})")


class DistributorClient(ABC):
    code: DistributorCode

    @abstractmethod
    async def get_price_and_availability(self, mpns: list[str]) -> list[DistributorAvailability]:
        """Batch lookup. Distributors that only support single-MPN lookups
        should fan out internally and gather results here."""
        raise NotImplementedError

    @abstractmethod
    async def submit_dropship_order(self, request: DropshipOrderRequest) -> DistributorOrderResult:
        """Places a blind dropship order. Must not raise on partial
        rejection — return rejected_line_items so the caller can decide
        whether to retry via a fallback distributor."""
        raise NotImplementedError

    @abstractmethod
    async def get_order_status(self, distributor_order_number: str) -> str:
        raise NotImplementedError

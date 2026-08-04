"""
app/distributors/registry.py
Single place that knows about every live distributor client. Adding a new
distributor = write the client class + add one line here.
"""

from functools import lru_cache

from app.models import DistributorCode
from app.distributors.base import DistributorClient
from app.distributors.ingram_micro import IngramMicroClient
from app.distributors.arrow import ArrowClient


@lru_cache
def get_all_distributor_clients() -> dict[DistributorCode, DistributorClient]:
    return {
        DistributorCode.INGRAM_MICRO: IngramMicroClient(),
        DistributorCode.ARROW: ArrowClient(),
    }


def get_distributor_client(code: DistributorCode) -> DistributorClient:
    return get_all_distributor_clients()[code]

"""Pod E – BMW data and market context: full BMW import, sales-based market weights, "must not lose"
attributes and representativeness reports. Stub router registered by server/main.py.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/market-data", tags=["market-data"])

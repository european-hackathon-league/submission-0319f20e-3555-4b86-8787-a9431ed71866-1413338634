"""Pod A – signals and sentiment over time: PM watchlists over public web signals (Exa),
sentiment scoring and weekly time series. Stub router registered by server/main.py; Pod A fills it.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/signals", tags=["signals"])

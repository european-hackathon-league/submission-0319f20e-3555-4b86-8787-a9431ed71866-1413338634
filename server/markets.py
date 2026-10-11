"""Pod B – market balancer: cross-market comparison, conflict detection, sales-weighted
recommendations and the human resolution gate. Stub router registered by server/main.py; Pod B fills it.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/markets", tags=["markets"])

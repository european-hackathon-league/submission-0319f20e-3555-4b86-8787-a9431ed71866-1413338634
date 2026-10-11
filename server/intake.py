"""Pod C – request intake and triage: inbound requests from markets, dealers, engineering and sales,
clustering, aggregate demand and the human decision gate. Stub router registered by server/main.py.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/requests", tags=["requests"])

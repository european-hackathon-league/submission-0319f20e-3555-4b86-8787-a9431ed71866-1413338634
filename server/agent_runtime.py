"""Pod F – agent runtime substrate: agent registry, capability catalogue, task queue and board, runs,
threads and messages. No LLM agent loop yet. server/main.py registers every router in `routers`.
"""

from fastapi import APIRouter

agents_router = APIRouter(prefix="/agents", tags=["agents"])
capabilities_router = APIRouter(prefix="/capabilities", tags=["agents"])
tasks_router = APIRouter(prefix="/tasks", tags=["tasks"])
runs_router = APIRouter(prefix="/runs", tags=["runs"])
threads_router = APIRouter(prefix="/threads", tags=["threads"])
routers = (agents_router, capabilities_router, tasks_router, runs_router, threads_router)

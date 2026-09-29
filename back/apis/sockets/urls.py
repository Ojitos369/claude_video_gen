from fastapi import APIRouter, WebSocket

from .api import JobSocketApi
from core.websockets.manager import manager
from core.jobs.runner import JOBS_GROUP

router = APIRouter()

@router.websocket("/jobs/{job_id}")
async def job_socket_endpoint(websocket: WebSocket, job_id: str):
    handler = JobSocketApi(websocket=websocket, manager=manager, chat_id=JOBS_GROUP if job_id == "all" else job_id)
    await handler.handle_connection()

from fastapi import APIRouter
from .base.urls import router as base_router
from .jobs.urls import router as jobs_router
from .sockets.urls import router as socket_router
from .get_media.urls import router as get_media_router
from .settings.urls import router as settings_router

apis = APIRouter()
media = APIRouter()

media.include_router(get_media_router, prefix="")
apis.include_router(base_router, prefix="/base")
apis.include_router(jobs_router, prefix="/jobs")
apis.include_router(socket_router, prefix="/ws")
apis.include_router(settings_router, prefix="/settings")

from fastapi import APIRouter, Request
from .api import HelloWorld, GetModes, Status

router = APIRouter()

@router.get("/hh")
async def hh(request: Request):
    return await HelloWorld(request=request).run()

@router.get("/get_modes")
async def get_modes(request: Request):
    return await GetModes(request=request).run()

@router.get("/status")
async def status(request: Request):
    return await Status(request=request).run()

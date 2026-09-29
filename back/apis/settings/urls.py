from fastapi import APIRouter, Request
from .api import GetSettings, SaveSettings, TestProvider, CodexLogin, RefreshMachine

router = APIRouter()

@router.get("/get")
async def get_settings(request: Request):
    return await GetSettings(request=request).run()

@router.post("/save")
async def save_settings(request: Request):
    return await SaveSettings(request=request).run()

@router.post("/test/{provider}")
async def test_provider(request: Request, provider: str):
    return await TestProvider(request=request, provider=provider).run()

@router.post("/codex_login")
async def codex_login(request: Request):
    return await CodexLogin(request=request).run()

@router.post("/machine")
async def refresh_machine(request: Request):
    return await RefreshMachine(request=request).run()

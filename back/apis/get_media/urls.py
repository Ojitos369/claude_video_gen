from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
import os
from .api import GetMedia
from core.conf.settings import MEDIA_DIR

router = APIRouter()
P404_PATH = os.path.join(MEDIA_DIR, "pages", "p404.html")

@router.get("/{ruta:path}", response_class=FileResponse)
async def gm(request: Request, ruta: str):
    file = os.path.join(MEDIA_DIR, ruta)
    if not os.path.isabs(file):
        return {"error": "Invalid file path"}
    if not file.startswith(MEDIA_DIR):
        return {"error": "Invalid file path"}
    if not os.path.exists(file) or not os.path.isfile(file):
        if os.path.exists(P404_PATH):
            return HTMLResponse(content=open(P404_PATH).read(), status_code=404)
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file)

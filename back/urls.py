from fastapi import Request, FastAPI, APIRouter
from fastapi.responses import HTMLResponse
from apis.urls import apis, media
from core.conf.settings import MEDIA_DIR

urls_router = APIRouter()

urls_router.include_router(apis, prefix="/api")
urls_router.include_router(media, prefix="/media")

# ---------   INDEX   ---------
@urls_router.get("/", response_class=HTMLResponse)
async def read_index(request: Request):
    with open(f"{MEDIA_DIR}/dist/index.html") as f:
        html_content = f.read()
    # no-cache: after `make build` the browser must pick up the new hashed assets
    return HTMLResponse(content=html_content, headers={"Cache-Control": "no-cache"})

# ---------   404   ---------
def add_404_handler(app: FastAPI):
    @app.exception_handler(404)
    async def custom_404_handler(request: Request, exc):
        with open(f"{MEDIA_DIR}/pages/p404.html") as f:
            html_content = f.read()
        return HTMLResponse(content=html_content, status_code=404)


import asyncio
import secrets
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse

from urls import urls_router, add_404_handler
from core.conf.settings import allow_origins, allow_origin_regex, allow_credentials, allow_methods, allow_headers, MEDIA_DIR
from core.jobs.runner import runner
from core.conf.workspace import local_settings, machine

LOOPBACK = {"127.0.0.1", "::1", "localhost"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # machine details in settings.local.json: detected only when missing or when the hardware / drivers changed
    m, updated = await asyncio.to_thread(machine.ensure)
    print(f"[video-studio] equipo {'detectado' if updated else 'sin cambios'}: {machine.summary(m)}", flush=True)
    runner.start()      # job queue worker (one video at a time)
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=allow_origin_regex,
    allow_credentials=allow_credentials,
    allow_methods=allow_methods,
    allow_headers=allow_headers
)



@app.middleware("http")
async def lan_guard(request: Request, call_next):
    """The service may listen on the LAN (phone access). Only this machine is trusted without the access token;
    other devices open the link with ?token=… once (QR in the settings) and keep it in a cookie."""
    host = request.client.host if request.client else ""
    if host in LOOPBACK:
        return await call_next(request)
    token = local_settings.load()["access"]["token"]
    q = request.query_params.get("token", "")
    if q and secrets.compare_digest(q, token):
        resp = RedirectResponse(url=str(request.url.remove_query_params("token")), status_code=303)
        resp.set_cookie("vs_token", token, httponly=True, samesite="lax", max_age=180 * 24 * 3600)
        return resp
    if secrets.compare_digest(request.cookies.get("vs_token", ""), token):
        return await call_next(request)
    return HTMLResponse('<meta name="viewport" content="width=device-width,initial-scale=1"><body style="font-family:system-ui;background:#121015;color:#ece8f0;padding:32px">'
                        '<h2>Video Studio: acceso restringido</h2><p>Abre el enlace con token o escanea el código QR que aparece en '
                        '<b>Ajustes → Acceso desde el teléfono</b> en el equipo donde corre el servicio.</p></body>', status_code=401)


app.include_router(urls_router, prefix="")

add_404_handler(app)


# uvicorn main:app --host 127.0.0.1 --port 8470   (launcher.py uses 0.0.0.0 when LAN access is enabled in the settings)

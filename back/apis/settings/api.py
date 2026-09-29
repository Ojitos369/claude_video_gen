import json
import socket
import subprocess
import urllib.error
import urllib.request

from core.bases.apis import AsyncApi
from core.conf.settings import MYE
from core.conf.workspace import local_settings, machine, find_cli, command
from starlette.concurrency import run_in_threadpool


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))   # no packet is sent; picks the interface of the default route
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def codex_status():
    codex = find_cli("codex")
    if not codex:
        return {"installed": False, "logged_in": False, "detail": "Codex CLI no instalado"}
    try:
        out = subprocess.run(command(codex) + ["login", "status"], capture_output=True, text=True, timeout=30)
        txt = (out.stdout + out.stderr).strip()
    except Exception as e:
        txt = str(e)
    return {"installed": True, "bin": codex, "logged_in": "logged in" in txt.lower(), "detail": txt.splitlines()[0] if txt else ""}


def http_ok(url, headers):
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return True, f"OK ({r.status})"
    except urllib.error.HTTPError as e:
        return False, f"{e.code}: {e.read().decode(errors='replace')[:200]}"
    except Exception as e:
        return False, str(e)


class GetSettings(AsyncApi):
    async def main(self):
        s = local_settings.masked()
        port = self.request.url.port or 8470
        token = local_settings.load()["access"]["token"]
        s["access"]["token"] = token if self.request.client.host in ("127.0.0.1", "::1", "localhost") else ""
        s["access"]["lan_url"] = f"http://{lan_ip()}:{port}/?token={token}" if s["access"]["token"] else ""
        s["catalog"] = {"tts": local_settings.TTS_PROVIDERS, "images": local_settings.IMAGE_PROVIDERS}
        s["machine_summary"] = machine.summary(s.get("machine")) if s.get("machine") else ""
        s["codex"] = await run_in_threadpool(codex_status)
        self.response = {"settings": s}


class SaveSettings(AsyncApi):
    async def main(self):
        patch = {k: v for k, v in self.data.items() if k in ("theme", "providers", "tts", "images", "generation", "access")}
        local_settings.update(patch)
        self.response = {"ok": True}


class TestProvider(AsyncApi):
    async def main(self):
        name = self.data["provider"]
        s = local_settings.load()["providers"]
        k = (s.get(name) or {}).get("api_key", "")
        if name == "openai" and s["openai"]["auth"] == "subscription":
            st = await run_in_threadpool(codex_status)
            self.response = {"ok": st["logged_in"], "detail": st["detail"]}; return
        if not k:
            raise MYE("No hay API key guardada para esta plataforma")
        checks = {
            "google": ("https://generativelanguage.googleapis.com/v1beta/models?pageSize=1", {"x-goog-api-key": k}),
            "openai": ("https://api.openai.com/v1/models", {"Authorization": f"Bearer {k}"}),
            "anthropic": ("https://api.anthropic.com/v1/models", {"x-api-key": k, "anthropic-version": "2023-06-01"}),
            "elevenlabs": ("https://api.elevenlabs.io/v1/user", {"xi-api-key": k}),
        }
        if name not in checks:
            raise MYE("Plataforma desconocida")
        ok, detail = await run_in_threadpool(http_ok, *checks[name])
        self.response = {"ok": ok, "detail": detail}


class CodexLogin(AsyncApi):
    """Starts the official `codex login` (ChatGPT subscription). It opens the browser of the machine running the service."""
    async def main(self):
        codex = find_cli("codex")
        if not codex:
            raise MYE("Instala Codex CLI para iniciar sesión con tu suscripción de ChatGPT (npm i -g @openai/codex)")
        subprocess.Popen(command(codex) + ["login"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         **({"creationflags": 0x00000200} if __import__("os").name == "nt" else {"start_new_session": True}))
        self.response = {"ok": True, "detail": "Se abrió el inicio de sesión de ChatGPT en el navegador del equipo del servicio"}


class RefreshMachine(AsyncApi):
    async def main(self):
        m, updated = await run_in_threadpool(machine.ensure, bool(self.data.get("force")))
        self.response = {"updated": updated, "summary": machine.summary(m)}

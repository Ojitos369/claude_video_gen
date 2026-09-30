# Video jobs: one job = one folder in projects/<id>/ worked on by Claude Code (`claude -p`, stream-json).
# Every Claude event is normalised, appended to projects/<id>/.app/events.jsonl and broadcast over the websocket
# group of the job, so the front can replay the history and follow it live. Jobs run one at a time (shared GPU).
import asyncio
import json
import os
import re
import signal
import time
import unicodedata
from datetime import datetime

from core.conf.settings import (PROJECTS_DIR, WORKSPACE_DIR, CLAUDE_BIN, CLAUDE_MODEL, CLAUDE_MODELS, CLAUDE_EFFORT, CLAUDE_EFFORTS,
                                CLAUDE_PERMISSION_MODE)
from core.websockets.manager import manager
from core.conf.claude_bin import command as claude_command
from core.conf.workspace import local_settings, machine as machine_info

JOBS_GROUP = "jobs"          # websocket group that receives list updates of every job
VIDEO_EXT = (".mp4", ".webm", ".mov", ".mkv")
MAX_TEXT = 4000

SYSTEM_PROMPT = """Estás corriendo desde la app web local "Video Studio" del generador universal de videos. No hay un usuario
interactivo: NO hagas preguntas ni esperes confirmación; decide con criterio, anota los supuestos en PROGRESO.md y continúa.
- Sigue CLAUDE.md del workspace y el flujo del tipo de proyecto que corresponda. Usa el motor de engine/ y el venv .venv.
- Trabaja dentro de projects/{id}/ (y en engine/ solo si hay que extender el motor de forma genérica).
- Guarda las instrucciones del usuario en projects/{id}/prompt.md (a partir de engine/templates/prompt.md) y mantén PROGRESO.md
  actualizado en cada paso: la app lo muestra en vivo.
- Cada comando de Bash debe terminar en menos de 10 minutos: los renders largos se hacen por segmentos (engine/render.py reanuda
  los segmentos ya hechos si lo vuelves a ejecutar). No uses comandos en segundo plano.
- El video final debe quedar en projects/{id}/out/. Revisa fotogramas antes del render completo.
- Al terminar responde con un resumen breve en español: qué hiciste, la ruta del video y lo que convenga revisar."""


def context_prompt(job_id, tools):
    """Per-run context for claude: the host machine (from settings.local.json) and the generation tools allowed in this job."""
    s = local_settings.load()
    py = r".venv\Scripts\python.exe" if WIN else ".venv/bin/python"
    out = ["Equipo donde corre el servicio (settings.local.json -> sección machine; no leas el resto de ese archivo: tiene API keys): "
           + machine_info.summary(s.get("machine") or machine_info.ensure()[0])
           + " Ajusta resolución, procesos en paralelo y codificador a este equipo (el motor ya toma machine.video_encoder y render_jobs)."]
    img, tts, mus = s["images"], s["tts"], s["music"]
    if tools.get("images") and img["provider"] != "none":
        prov = local_settings.IMAGE_PROVIDERS.get(img["provider"], {}).get("label", img["provider"])
        if img["provider"] == "openai" and s["providers"]["openai"]["auth"] == "subscription": prov += " con la suscripción de ChatGPT"
        out.append(f"Herramienta de imágenes disponible ({prov}, modelo {img['model'] or 'por defecto'}, máximo {img['max_per_project']} por proyecto): "
                   f"`{py} engine/tools/gen_image.py {job_id} \"<prompt detallado>\" --out assets/<nombre>.png [--aspect 9:16] [--transparent] [--ref <imagen>]`. "
                   "Úsala solo cuando una imagen mejore claramente el video (fondos, personajes, objetos, portadas, texturas), con la paleta y "
                   "el estilo del proyecto; revisa cada imagen antes de usarla y anota en PROGRESO.md qué generaste y para qué.")
    elif tools.get("images"):
        out.append("La generación de imágenes está permitida, pero no hay proveedor configurado en los ajustes: no la uses.")
    else:
        out.append("No generes imágenes con IA en este trabajo.")
    if tools.get("tts") and tts["provider"] != "none":
        prov = local_settings.TTS_PROVIDERS.get(tts["provider"], {}).get("label", tts["provider"])
        out.append(f"Herramienta de voz (TTS) disponible ({prov}, modelo {tts['model'] or 'por defecto'}, voz {tts['voice'] or 'por defecto'}, idioma {tts['language']}): "
                   f"`{py} engine/tools/tts.py {job_id} --text \"…\" | --file <txt> --out audio/<nombre>.wav [--voice X] [--instructions \"tono\"]`. "
                   "Úsala cuando el pedido necesite narración o voz y no la haya en los archivos; genera por párrafos y concaténalos.")
    elif tools.get("tts"):
        out.append("La voz sintética está permitida, pero no hay proveedor de TTS configurado: no la uses.")
    else:
        out.append("No generes voz sintética en este trabajo.")
    if tools.get("music") and mus["provider"] != "none":
        prov = local_settings.MUSIC_PROVIDERS.get(mus["provider"], {}).get("label", mus["provider"])
        out.append(f"Herramienta de música disponible ({prov}, modelo {mus['model'] or 'por defecto'}, máximo {mus['max_per_project']} generaciones por proyecto; "
                   "cada una cuesta créditos y da 2 variantes): "
                   f"`{py} engine/tools/gen_music.py {job_id} --style \"<género, ánimo, instrumentos, tempo; en inglés>\" --out audio/<nombre>.wav "
                   "[--instrumental] [--lyrics-file <txt> --title \"…\"] [--gender male|female]`. Tarda unos minutos; si se agota el tiempo, vuelve a "
                   "ejecutar el mismo comando (retoma la tarea sin pagar otra). Úsala cuando el video necesite música y no venga en los archivos "
                   "(fondo instrumental para narraciones e historias, o una canción si el pedido la pide); escucha/revisa la duración y el ánimo "
                   "de las variantes, elige una, y anota en PROGRESO.md qué generaste y para qué.")
    elif tools.get("music"):
        out.append("La generación de música está permitida, pero no hay proveedor configurado: no la uses.")
    else:
        out.append("No generes música con IA en este trabajo.")
    return "\n".join(out)


def slugify(text, fallback="video"):
    t = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-zA-Z0-9]+", "-", t).strip("-").lower()[:40]
    return t or fallback


WIN = os.name == "nt"


def pid_alive(pid):
    """True while the process exists (and is not a zombie on Linux)."""
    if WIN:
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, pid)            # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        k.GetExitCodeProcess(h, ctypes.byref(code)); k.CloseHandle(h)
        return code.value == 259                         # STILL_ACTIVE
    try:
        with open(f"/proc/{pid}/stat") as f:
            return f.read().rsplit(")", 1)[1].split()[0] != "Z"
    except OSError:
        try:
            os.kill(pid, 0); return True                 # no /proc (macOS)
        except OSError:
            return False
    except IndexError:
        return False


def kill_tree(pid):
    """Stop claude and every command it started."""
    if WIN:
        import subprocess
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    else:
        try:
            os.killpg(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass


def valid_tools(tools):
    """Generation tools allowed in a job; defaults from settings.local.json -> generation."""
    base = dict(local_settings.load()["generation"])
    if isinstance(tools, str):
        try: tools = json.loads(tools)
        except ValueError: tools = None
    if isinstance(tools, dict):
        base.update({k: bool(v) for k, v in tools.items() if k in base})
    return base


def valid_effort(effort):
    return effort if effort in [e["id"] for e in CLAUDE_EFFORTS] else CLAUDE_EFFORT


def valid_model(model):
    """Only models offered by the app (never pass arbitrary strings to the CLI)."""
    return model if model in [m["id"] for m in CLAUDE_MODELS] else CLAUDE_MODEL


ASPECTS = {"9:16": (1080, 1920), "16:9": (1920, 1080), "3:4": (1080, 1440), "4:3": (1440, 1080),
           "16:10": (1920, 1200), "10:16": (1200, 1920), "1:1": (1080, 1080)}
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff")


def probe_size(path):
    import subprocess
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                          "-of", "csv=p=0:s=x", path], capture_output=True, text=True, timeout=30).stdout.strip()
    w, h = map(int, out.split("x")[:2])
    return w, h


def ratio_text(w, h):
    from fractions import Fraction
    r = Fraction(w, h).limit_denominator(20)
    return f"{r.numerator}:{r.denominator}" if abs(float(r) - w / h) < 0.01 else f"{w / h:.2f}:1"


def resolve_aspect(value, job_dir, saved, text=""):
    """Output format chosen in the app. Returns (aspect, label, instruction for claude):
    a known ratio, 'video:<file>' / 'image:<file>' (measured with ffprobe) or 'manual' (free text claude interprets)."""
    value = (value or "9:16").strip()
    if value == "manual" and (text or "").strip():
        t = text.strip()[:300]
        return "manual", f"manual: {t}", (
            f"Formato de salida descrito por el usuario (texto libre): \"{t}\". Interprétalo y decide la proporción y la "
            f"resolución adecuadas para ese uso (lado largo de 1920 px salvo que el destino pida más; máximo 3840). Escríbelas en "
            f"`config.json` (\"aspect\" o \"width\"/\"height\") y explica la decisión en PROGRESO.md.")
    for kind, exts in (("video", VIDEO_EXT), ("image", IMAGE_EXT)):
        if value.startswith(kind + ":"):
            name = os.path.basename(value[len(kind) + 1:])
            if not any(s["name"] == name for s in saved):
                name = next((s["name"] for s in saved if s["name"].lower().endswith(exts)), "")
            try:
                w, h = probe_size(os.path.join(job_dir, name))
                what = "del video" if kind == "video" else "de la imagen"
                label = f"{what} {name} ({w}x{h}, {ratio_text(w, h)})"
                return f"{w}:{h}", label, None
            except Exception:
                value = "9:16"
    if value not in ASPECTS: value = "9:16"
    w, h = ASPECTS[value]
    return value, f"{value} ({w}x{h})", None


def now():
    return datetime.now().isoformat(timespec="seconds")


async def save_uploads(job_dir, uploads):
    """uploads: list of (filename, async_read_chunk_fn) saved at the top of the project. An existing file is never
    overwritten: the new one gets a -2, -3… suffix. Returns [{name, size}]."""
    saved = []
    for filename, reader in uploads:
        fn = os.path.basename(filename).strip() or "archivo"
        stem, ext = os.path.splitext(fn)
        n = 2
        while os.path.exists(os.path.join(job_dir, fn)) or fn in (".app", "solicitud.md", "config.json", "PROGRESO.md", "prompt.md"):
            fn, n = f"{stem}-{n}{ext}", n + 1
        dest = os.path.join(job_dir, fn)
        with open(dest, "wb") as f:
            while chunk := await reader(1 << 20):
                f.write(chunk)
        saved.append({"name": fn, "size": os.path.getsize(dest)})
    return saved


def files_text(saved):
    return "\n".join(f"- {s['name']} ({s['size'] / 1e6:.1f} MB)" for s in saved) or "- (ninguno)"


def trunc(s, n=MAX_TEXT):
    s = s if isinstance(s, str) else json.dumps(s, ensure_ascii=False)
    return s if len(s) <= n else s[:n] + f"\n… ({len(s) - n} caracteres más)"


def tool_summary(name, inp):
    """One-line description of a tool call for the timeline."""
    inp = inp or {}
    if name == "Bash": return inp.get("description") or inp.get("command", "")[:160]
    if name in ("Read", "Write", "Edit", "NotebookEdit"): return inp.get("file_path", "").replace(WORKSPACE_DIR + "/", "")
    if name in ("Grep", "Glob"): return inp.get("pattern", "")
    if name == "WebSearch": return inp.get("query", "")
    if name == "WebFetch": return inp.get("url", "")
    if name in ("Agent", "Task"): return inp.get("description", "")
    if name == "TodoWrite": return f"{len(inp.get('todos', []))} tareas"
    return next((str(v)[:120] for v in inp.values() if isinstance(v, str)), "")


class Job:
    def __init__(self, job_id):
        self.id = job_id
        self.dir = os.path.join(PROJECTS_DIR, job_id)
        self.app = os.path.join(self.dir, ".app")
        self.meta_path = os.path.join(self.app, "job.json")
        self.events_path = os.path.join(self.app, "events.jsonl")

    # ---------------------------------------------------------- state
    def adopt(self):
        """Register a project created outside the app so it can be browsed and continued."""
        prompt = "(proyecto creado fuera de la app)"
        p = os.path.join(self.dir, "prompt.md")
        if os.path.exists(p):
            with open(p, errors="replace") as f:
                prompt = f.read()[:3000]
        created = datetime.fromtimestamp(os.path.getctime(self.dir)).isoformat(timespec="seconds")
        self.save(id=self.id, name=self.id, prompt=prompt, files=[], status="done", created=created, cost=0.0, model=CLAUDE_MODEL,
                  session_id=None, runs=[], step="Terminado", error=None, adopted=True)

    def exists(self):
        return os.path.exists(self.meta_path)

    def meta(self):
        with open(self.meta_path) as f:
            return json.load(f)

    def save(self, **changes):
        m = self.meta() if self.exists() else {}
        m.update(changes, updated=now())
        os.makedirs(self.app, exist_ok=True)
        tmp = self.meta_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(m, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.meta_path)
        return m

    def events(self, since=0):
        if not os.path.exists(self.events_path): return []
        with open(self.events_path) as f:
            ev = [json.loads(line) for line in f if line.strip()]
        return ev[since:]

    def outputs(self):
        out = os.path.join(self.dir, "out")
        if not os.path.isdir(out): return []
        files = []
        for name in sorted(os.listdir(out)):
            p = os.path.join(out, name)
            if os.path.isfile(p) and not name.endswith(".part.mp4"):
                files.append({"path": f"out/{name}", "name": name, "size": os.path.getsize(p), "mtime": os.path.getmtime(p),
                              "video": name.lower().endswith(VIDEO_EXT)})
        return files

    def files(self):
        """Top-level inputs + folders summary (ignores .app)."""
        res = []
        if not os.path.isdir(self.dir): return res
        for name in sorted(os.listdir(self.dir)):
            if name.startswith("."): continue
            p = os.path.join(self.dir, name)
            res.append({"name": name, "dir": os.path.isdir(p), "size": os.path.getsize(p) if os.path.isfile(p) else None})
        return res

    def progress(self):
        p = os.path.join(self.dir, "PROGRESO.md")
        if not os.path.exists(p): return ""
        with open(p, errors="replace") as f:
            return f.read()

    def summary(self):
        m = self.meta()
        return {k: m.get(k) for k in ("id", "name", "status", "created", "updated", "cost", "step", "error", "model", "effort", "aspect")} | {"outputs": len(self.outputs())}

    def detail(self):
        m = self.meta()
        return m | {"model": m.get("model") or CLAUDE_MODEL, "effort": m.get("effort") or CLAUDE_EFFORT, "outputs": self.outputs(), "files": self.files(), "progress": self.progress(),
                    "format": self.format()}

    def format(self):
        """Output format as configured now in the project's config.json (e.g. what claude chose for a manual format)."""
        try:
            with open(os.path.join(self.dir, "config.json")) as f:
                c = json.load(f)
        except (OSError, ValueError):
            return None
        if c.get("width") and c.get("height"):
            return f"{c['width']}x{c['height']}"
        return c.get("aspect")

    def safe_path(self, rel):
        p = os.path.realpath(os.path.join(self.dir, rel))
        if not p.startswith(os.path.realpath(self.dir) + os.sep): return None
        return p if os.path.isfile(p) else None


class Runner:
    def __init__(self):
        self.queue = asyncio.Queue()
        self.procs = {}          # job id -> asyncio subprocess
        self.worker_task = None
        self.counters = {}       # job id -> next event index

    # ---------------------------------------------------------- events
    async def emit(self, job, kind, **data):
        i = self.counters.get(job.id)
        if i is None:
            i = len(job.events())
        ev = {"i": i, "t": time.time(), "kind": kind, **data}
        self.counters[job.id] = i + 1
        with open(job.events_path, "a") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        await manager.broadcast_to_group(json.dumps({"type": "event", "event": ev}, ensure_ascii=False), job.id)
        return ev

    async def set_status(self, job, status, **extra):
        m = job.save(status=status, **extra)
        await self.emit(job, "status", status=status, **{k: v for k, v in extra.items() if k in ("error", "step")})
        await manager.broadcast_to_group(json.dumps({"type": "job", "job": job.summary()}, ensure_ascii=False), JOBS_GROUP)
        return m

    # ---------------------------------------------------------- lifecycle
    def start(self):
        """Claude runs detached from the server (its stream goes to a file), so a server restart does not lose jobs:
        running jobs are re-attached (or finalised if claude already ended) and queued jobs are queued again."""
        self.reattach, pending = [], []
        if os.path.isdir(PROJECTS_DIR):
            for name in os.listdir(PROJECTS_DIR):
                job = Job(name)
                if not job.exists(): continue
                m = job.meta()
                if m.get("status") == "running" and m.get("proc"):
                    self.reattach.append(job)
                elif m.get("status") in ("running", "queued") and m.get("pending"):
                    pending.append((m.get("updated") or "", job, m["pending"]))
                elif m.get("status") in ("running", "queued"):
                    job.save(status="interrupted", error="El servidor se detuvo durante la ejecución. Puedes continuar el trabajo.")
        for _, job, pd in sorted(pending, key=lambda x: x[0]):
            self.queue.put_nowait((job.id, pd["prompt"], pd["resume"], pd["model"], valid_effort(pd.get("effort"))))
        self.worker_task = asyncio.create_task(self.worker())

    async def worker(self):
        for job in self.reattach:          # finish what was running before the restart first (one job at a time)
            try:
                await self.follow(job, None)
            except Exception as e:
                await self.emit(job, "error", text=f"Error interno: {e}")
                await self.set_status(job, "error", error=str(e))
        while True:
            job_id, prompt, resume, model, effort = await self.queue.get()
            job = Job(job_id)
            try:
                if job.meta().get("status") == "cancelled": continue
                await self.run(job, prompt, resume, model, effort)
            except Exception as e:   # never kill the worker
                await self.emit(job, "error", text=f"Error interno: {e}")
                await self.set_status(job, "error", error=str(e), proc=None)
            finally:
                self.queue.task_done()

    async def enqueue(self, job, prompt, resume, model, effort):
        job.save(pending={"prompt": prompt, "resume": resume, "model": model, "effort": effort})
        await self.queue.put((job.id, prompt, resume, model, effort))

    async def create(self, name, prompt, uploads, model=None, aspect=None, aspect_text="", tools=None, effort=None):
        """uploads: list of (filename, async_read_chunk_fn). Returns the job."""
        base = slugify(name or prompt[:40])
        job_id, n = base, 2
        while os.path.exists(os.path.join(PROJECTS_DIR, job_id)):
            job_id, n = f"{base}-{n}", n + 1
        job = Job(job_id)
        os.makedirs(job.app, exist_ok=True)
        saved = await save_uploads(job.dir, uploads)
        with open(os.path.join(job.dir, "solicitud.md"), "w") as f:
            f.write(f"# Solicitud\n\n{prompt}\n\n## Archivos subidos\n" + "".join(f"- {s['name']}\n" for s in saved))
        model, effort = valid_model(model), valid_effort(effort)
        aspect, aspect_label, aspect_note = resolve_aspect(aspect, job.dir, saved, aspect_text)
        if aspect != "manual":   # starting config: the chosen format wins over the engine defaults
            with open(os.path.join(job.dir, "config.json"), "w") as f:
                json.dump({"aspect": aspect}, f, indent=1)
        job.save(id=job_id, name=name or prompt[:60], prompt=prompt, files=saved, status="queued", created=now(), model=model, effort=effort,
                 aspect=aspect, aspect_label=aspect_label, tools=valid_tools(tools),
                 cost=0.0, session_id=None, runs=[], step="En cola", error=None)
        await self.emit(job, "user", text=prompt, files=[s["name"] for s in saved], model=model, effort=effort)
        await manager.broadcast_to_group(json.dumps({"type": "job", "job": job.summary()}, ensure_ascii=False), JOBS_GROUP)
        files_txt = files_text(saved)
        first = (f"Nuevo proyecto de video en `projects/{job_id}/`.\n\nInstrucciones del usuario:\n{prompt}\n\n"
                 f"Archivos subidos (ya están en la carpeta del proyecto):\n{files_txt}\n\n"
                 + (aspect_note or
                    f"Formato de salida elegido en la app: {aspect_label}. Ya está en `projects/{job_id}/config.json` como "
                    f"\"aspect\": \"{aspect}\"; consérvalo al completar la configuración (tiene prioridad sobre el formato por defecto "
                    f"y sobre el del video, salvo que las instrucciones del usuario pidan otro formato explícitamente)."))
        await self.enqueue(job, first, False, model, effort)
        return job

    async def follow_up(self, job, text, model=None, effort=None, uploads=()):
        """A change request: same Claude session (--resume) when there is one. The request and its files are also written to
        solicitud.md, so the project folder holds the whole history even for a new session."""
        m = job.meta()
        model, effort = valid_model(model or m.get("model")), valid_effort(effort or m.get("effort"))
        saved = await save_uploads(job.dir, uploads)
        text = text or "Agregué archivos nuevos al proyecto: úsalos donde corresponda."
        with open(os.path.join(job.dir, "solicitud.md"), "a") as f:
            f.write(f"\n## Pedido de cambios · {now().replace('T', ' ')}\n\n{text}\n"
                    + (("\nArchivos agregados:\n" + "".join(f"- {s['name']}\n" for s in saved)) if saved else ""))
        job.save(model=model, effort=effort, files=(m.get("files") or []) + saved)
        await self.emit(job, "user", text=text, files=[s["name"] for s in saved], model=model, effort=effort)
        await self.set_status(job, "queued", step="En cola", error=None)
        new = f"\n\nArchivos nuevos (ya están en `projects/{job.id}/`):\n{files_text(saved)}" if saved else ""
        if m.get("session_id"):
            await self.enqueue(job, f"Pedido de cambios del usuario sobre `projects/{job.id}/`:\n{text}{new}\n\n"
                                    "Parte del estado actual del proyecto (lo que ya se hizo sigue en su carpeta); cambia solo lo necesario, "
                                    "vuelve a renderizar lo afectado y añade a PROGRESO.md una sección con esta iteración.", True, model, effort)
        else:   # no Claude session to resume (adopted from the terminal, or the session was lost)
            await self.enqueue(job, self.fresh_prompt(job, text, new), False, model, effort)

    def fresh_prompt(self, job, text, new=""):
        return (f"Proyecto existente en `projects/{job.id}/`; esta es una sesión nueva, así que primero ponte en contexto: lee "
                f"`solicitud.md` (todos los pedidos del usuario en orden, con sus archivos), `prompt.md`, `PROGRESO.md` (lo hecho, "
                f"supuestos y pendientes), `config.json` y la lista de archivos del proyecto.\n\n"
                f"Nuevo pedido de cambios del usuario:\n{text}{new}\n\n"
                "Cambia solo lo necesario, vuelve a renderizar lo afectado y añade a PROGRESO.md una sección con esta iteración.")

    async def rename(self, job, name):
        name = " ".join((name or "").split())[:120]
        if not name:
            raise ValueError("El nombre no puede estar vacío")
        job.save(name=name)
        await manager.broadcast_to_group(json.dumps({"type": "job", "job": job.summary()}, ensure_ascii=False), JOBS_GROUP)
        await manager.broadcast_to_group(json.dumps({"type": "renamed", "name": name}, ensure_ascii=False), job.id)

    async def cancel(self, job):
        p = job.meta().get("proc")
        if p and pid_alive(p["pid"]):
            kill_tree(p["pid"])
        await self.set_status(job, "cancelled", step="Cancelado", pending=None)

    # ---------------------------------------------------------- run claude
    async def run(self, job, prompt, resume, model, effort):
        m = job.meta()
        system = SYSTEM_PROMPT.format(id=job.id) + "\n" + context_prompt(job.id, m.get("tools") or valid_tools(None))
        cmd = claude_command(CLAUDE_BIN) + ["-p", prompt, "--model", model, "--effort", effort, "--output-format", "stream-json", "--verbose",
               "--permission-mode", CLAUDE_PERMISSION_MODE, "--append-system-prompt", system]
        env = dict(os.environ)
        ant = local_settings.load()["providers"]["anthropic"]
        if ant.get("use_api_key") and ant.get("api_key"):
            env["ANTHROPIC_API_KEY"] = ant["api_key"]      # bill the API key instead of the Claude Code login
        if resume and m.get("session_id"):
            cmd += ["--resume", m["session_id"]]
        await self.set_status(job, "running", step="Iniciando Claude", error=None)
        n = len(m.get("runs", []))
        stream, errlog = os.path.join(job.app, f"run-{n}.jsonl"), os.path.join(job.app, f"run-{n}.err")
        with open(stream, "wb") as out, open(errlog, "wb") as err:
            detach = {"creationflags": 0x00000200 | 0x08000000} if WIN else {"start_new_session": True}   # new group, no console
            proc = await asyncio.create_subprocess_exec(*cmd, cwd=WORKSPACE_DIR, stdin=asyncio.subprocess.DEVNULL,
                                                        stdout=out, stderr=err, env=env, **detach)
        run = {"started": now(), "prompt": trunc(prompt, 500), "status": "running", "model": model, "effort": effort,
               "resume": bool(resume and m.get("session_id")), "text": prompt}
        job.save(pending=None, proc={"pid": proc.pid, "stream": stream, "err": errlog, "offset": 0, "run": run, "result": None})
        self.procs[job.id] = proc
        await self.follow(job, proc)

    async def follow(self, job, proc):
        """Tail the claude stream file of the current run until claude exits, then close the run.
        proc is the asyncio process when we started it, None when re-attaching after a server restart."""
        p = job.meta()["proc"]
        pid, offset, tools = p["pid"], p.get("offset", 0), {}
        alive = (lambda: proc.returncode is None) if proc else (lambda: pid_alive(pid))
        watcher = asyncio.create_task(self.watch(job))
        if not proc:
            await self.emit(job, "system", text="Servidor reiniciado: retomando el seguimiento del trabajo en curso")
        try:
            with open(p["stream"], "rb") as f:
                f.seek(offset)
                buf = b""
                while True:
                    chunk = f.read()
                    if chunk:
                        buf += chunk
                        *lines, buf = buf.split(b"\n")
                        for raw in lines:
                            offset += len(raw) + 1
                            line = raw.decode(errors="replace").strip()
                            if line:
                                try:
                                    d = json.loads(line)
                                except json.JSONDecodeError:
                                    await self.emit(job, "log", text=trunc(line, 500)); d = None
                                if d is not None:
                                    res = await self.handle(job, d, tools)
                                    if res is not None:
                                        p["result"] = {k: res.get(k) for k in ("is_error", "result", "total_cost_usd", "num_turns", "duration_ms")}
                            p["offset"] = offset
                            job.save(proc=p)
                        continue
                    if not alive():
                        if f.read(1): f.seek(-1, 1); continue    # data written right before exiting
                        break
                    await asyncio.sleep(0.4)
            if proc: await proc.wait()
        finally:
            watcher.cancel()
            self.procs.pop(job.id, None)
        result, run = p.get("result"), p["run"]
        if job.meta().get("status") == "cancelled":
            run.update(status="cancelled", ended=now())
            job.save(runs=job.meta().get("runs", []) + [run], proc=None); return
        code = proc.returncode if proc else 0
        ok = code == 0 and result is not None and not result.get("is_error")
        cost = (job.meta().get("cost") or 0) + ((result or {}).get("total_cost_usd") or 0)
        run.update(status="done" if ok else "error", ended=now(), cost=(result or {}).get("total_cost_usd"),
                   turns=(result or {}).get("num_turns"), duration_ms=(result or {}).get("duration_ms"))
        job.save(runs=job.meta().get("runs", []) + [run], cost=cost, proc=None)
        await self.emit(job, "outputs", files=job.outputs())
        if ok:
            await self.set_status(job, "done", step="Terminado")
        else:
            err = ""
            try:
                with open(p["err"], errors="replace") as fe: err = fe.read().strip()
            except OSError:
                pass
            if run.get("resume") and result is None and "No conversation found" in err:
                # the Claude session is gone (e.g. cleaned history): continue in a new session with the project's own history
                await self.emit(job, "system", text="No se pudo retomar la sesión de Claude: se abre una nueva con el historial del proyecto")
                job.save(session_id=None)
                await self.set_status(job, "queued", step="En cola", error=None)
                await self.enqueue(job, self.fresh_prompt(job, run.get("text") or ""), False, run["model"], run["effort"])
                return
            msg = (result or {}).get("result") or err[-1500:] or (f"claude terminó con código {code}" if proc else "claude terminó sin resultado")
            await self.emit(job, "error", text=trunc(msg, 2000))
            await self.set_status(job, "error", step="Error", error=trunc(msg, 300))

    async def handle(self, job, d, tools):
        t, st = d.get("type"), d.get("subtype")
        if t == "system" and st == "init":
            job.save(session_id=d.get("session_id"))
            await self.emit(job, "system", text=f"Sesión de Claude iniciada · modelo {d.get('model')} · esfuerzo {job.meta().get('effort') or CLAUDE_EFFORT}")
        elif t == "assistant":
            for c in d.get("message", {}).get("content", []):
                if c.get("type") == "text" and c.get("text", "").strip():
                    await self.emit(job, "text", text=c["text"])
                elif c.get("type") == "tool_use":
                    name, inp = c.get("name"), c.get("input") or {}
                    tools[c.get("id")] = name
                    summ = tool_summary(name, inp)
                    await self.emit(job, "tool", id=c.get("id"), name=name, summary=summ, input=trunc(inp, 2500))
                    job.save(step=f"{name}: {summ}"[:140])
                    await manager.broadcast_to_group(json.dumps({"type": "job", "job": job.summary()}, ensure_ascii=False), JOBS_GROUP)
        elif t == "user":
            for c in d.get("message", {}).get("content", []) if isinstance(d.get("message", {}).get("content"), list) else []:
                if c.get("type") == "tool_result":
                    content = c.get("content")
                    if isinstance(content, list):
                        content = "\n".join(x.get("text", "") if x.get("type") == "text" else f"[{x.get('type')}]" for x in content)
                    await self.emit(job, "tool_result", id=c.get("tool_use_id"), name=tools.get(c.get("tool_use_id")),
                                    ok=not c.get("is_error"), text=trunc(content or "", 3000))
        elif t == "result":
            job.save(session_id=d.get("session_id") or job.meta().get("session_id"))
            await self.emit(job, "result", ok=not d.get("is_error"), text=d.get("result", ""), cost=d.get("total_cost_usd"),
                            duration_ms=d.get("duration_ms"), turns=d.get("num_turns"))
            return d
        return None

    async def watch(self, job):
        """While claude works: push PROGRESO.md changes and new output files."""
        last_prog, last_out = job.progress(), {o["path"]: o["mtime"] for o in job.outputs()}
        while True:
            await asyncio.sleep(3)
            prog = job.progress()
            if prog != last_prog:
                last_prog = prog
                await manager.broadcast_to_group(json.dumps({"type": "progress", "text": prog}, ensure_ascii=False), job.id)
            outs = job.outputs()
            cur = {o["path"]: o["mtime"] for o in outs}
            if cur != last_out:
                last_out = cur
                await self.emit(job, "outputs", files=outs)


runner = Runner()

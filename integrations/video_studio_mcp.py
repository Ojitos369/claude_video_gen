#!/usr/bin/env python3
"""MCP server (stdio, stdlib only) that lets any agent (Claude Code, Codex, Gemini CLI/Antigravity, Cursor...) order videos,
animations, HTML pages and 3D models from Video Studio. It talks to the local Video Studio service over HTTP and starts it
if it is not running (same machine only).

  python integrations/video_studio_mcp.py              # serve over stdio (what an agent runs)
  python integrations/video_studio_mcp.py --config claude|codex|gemini|json   # print the registration snippet for this checkout
Env: VIDEO_STUDIO_URL (default http://127.0.0.1:8470), VIDEO_STUDIO_TOKEN (access token when the service is on another machine),
     VIDEO_STUDIO_AUTOSTART=0 to never launch the service.
"""
import json
import mimetypes
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = os.environ.get("VIDEO_STUDIO_URL", "http://127.0.0.1:8470").rstrip("/")
TOKEN = os.environ.get("VIDEO_STUDIO_TOKEN", "")
LOCAL = urllib.parse.urlparse(URL).hostname in ("127.0.0.1", "localhost", "::1")
WIN = os.name == "nt"


# ------------------------------------------------------------------ HTTP
def http(method, path, body=None, headers=None, timeout=60):
    h = dict(headers or {})
    if TOKEN: h["Cookie"] = f"vs_token={TOKEN}"
    if isinstance(body, (dict, list)): body, h["Content-Type"] = json.dumps(body).encode(), "application/json"
    req = urllib.request.Request(URL + path, data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Video Studio {e.code}: {e.read().decode(errors='replace')[:400]}")


def ensure_running():
    def up():
        try: http("GET", "/api/jobs/list", timeout=5); return True
        except RuntimeError: return True          # answered (e.g. 401): it is up
        except Exception: return False
    if up(): return
    if not LOCAL or os.environ.get("VIDEO_STUDIO_AUTOSTART") == "0":
        raise RuntimeError(f"Video Studio no responde en {URL}. Arráncalo con ./run.sh --no-browser")
    script = [os.path.join(ROOT, "run.bat")] if WIN else ["bash", os.path.join(ROOT, "run.sh")]
    subprocess.Popen(script + ["--no-browser"], cwd=ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     **({"creationflags": 0x00000200 | 0x08000000} if WIN else {"start_new_session": True}))
    for _ in range(90):
        time.sleep(1)
        if up(): return
    raise RuntimeError("No pude arrancar Video Studio en 90 s (revisa ./run.sh a mano)")


def multipart(fields, files):
    b = uuid.uuid4().hex
    out = b""
    for k, v in fields.items():
        out += f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    for path in files:
        name = os.path.basename(path)
        out += (f'--{b}\r\nContent-Disposition: form-data; name="files"; filename="{name}"\r\n'
                f'Content-Type: {mimetypes.guess_type(name)[0] or "application/octet-stream"}\r\n\r\n').encode()
        out += open(path, "rb").read() + b"\r\n"
    return out + f"--{b}--\r\n".encode(), {"Content-Type": f"multipart/form-data; boundary={b}"}


# ------------------------------------------------------------------ tools
def job_dir(job_id): return os.path.join(ROOT, "projects", job_id)


def brief(job):
    return {k: job.get(k) for k in ("id", "name", "status", "step", "error", "cost")}


def create_video(a):
    ensure_running()
    prompt = a["prompt"].strip()
    ctx = a.get("context_dir")
    if ctx:
        prompt += (f"\n\nProyecto/carpeta de origen (solo lectura, léelo para basar el contenido en él): {os.path.abspath(ctx)}"
                   + (f"\nQué debe explicar o mostrar del proyecto: {a['context_note']}" if a.get("context_note") else ""))
    if a.get("deliverables"):
        prompt += f"\n\nEntregables pedidos: {', '.join(a['deliverables'])} (déjalos en out/)."
    tools = dict(a.get("tools") or {})
    if "ask_questions" in a: tools["ask"] = bool(a["ask_questions"])
    fields = {"prompt": prompt, "name": a.get("name", ""), "aspect": a.get("aspect", ""), "tools": json.dumps(tools)}
    for k in ("model", "effort"):
        if a.get(k): fields[k] = a[k]
    body, h = multipart(fields, [p for p in a.get("files", []) if os.path.isfile(p)])
    job = http("POST", "/api/jobs/create", body, h)["job"]
    return {"job_id": job["id"], "status": job["status"],
            "next": "Un video tarda varios minutos: consulta video_studio_status (con wait_seconds) hasta 'done' y luego video_studio_result. "
                    "Si video_studio_result trae `questions`, pregúntaselas al usuario (opción múltiple o respuesta propia) y envía video_studio_reply con answers."}


def status(a):
    ensure_running()
    deadline = time.time() + min(int(a.get("wait_seconds") or 0), 540)
    while True:
        d = http("GET", f"/api/jobs/detail/{a['job_id']}")["job"]
        if d["status"] not in ("queued", "running") or time.time() >= deadline: break
        time.sleep(5)
    ev = http("GET", f"/api/jobs/events/{a['job_id']}")["events"]
    last = [e.get("summary") or e.get("text") for e in ev if e.get("kind") in ("tool", "text")][-3:]
    return brief(d) | {"progress_tail": (d.get("progress") or "")[-1200:], "recent": last, "outputs": [o["name"] for o in d["outputs"]]}


def result(a):
    ensure_running()
    d = http("GET", f"/api/jobs/detail/{a['job_id']}")["job"]
    ev = http("GET", f"/api/jobs/events/{a['job_id']}")["events"]
    final = next((e.get("text") for e in reversed(ev) if e.get("kind") == "result"), "")
    files = []
    dest = os.path.abspath(a["copy_to"]) if a.get("copy_to") else None
    for o in d["outputs"]:
        src = os.path.join(job_dir(d["id"]), o["path"])
        if dest:   # also works when the service runs on another machine: download through HTTP
            os.makedirs(dest, exist_ok=True)
            tgt = os.path.join(dest, o["name"])
            if os.path.isfile(src): shutil.copyfile(src, tgt)
            else:
                req = urllib.request.Request(f"{URL}/api/jobs/file/{d['id']}/{urllib.parse.quote(o['path'])}", headers={"Cookie": f"vs_token={TOKEN}"} if TOKEN else {})
                with urllib.request.urlopen(req) as r, open(tgt, "wb") as f: shutil.copyfileobj(r, f)
            src = tgt
        kind = "video" if o.get("video") else "html" if o.get("html") else "otro"
        files.append({"type": kind, "path": src, "size": o["size"]})
    return brief(d) | {"final_message": final, "files": files, "questions": d.get("questions") or [],
                       "note": "Si status no es 'done' el trabajo sigue en curso o falló (ver error)."}


def reply(a):
    ensure_running()
    text = a.get("text") or ""
    if a.get("answers"):   # {pregunta_id: "opción" | ["opciones"] | "respuesta propia"} -> same text the app's form sends
        qs = {q["id"]: q for q in http("GET", f"/api/jobs/detail/{a['job_id']}")["job"].get("questions") or []}
        for qid, v in a["answers"].items():
            v = "; ".join(v) if isinstance(v, list) else str(v)
            text += f"\n- {qs.get(qid, {}).get('texto', qid)}\n  Respuesta: {v}"
    if not text.strip(): raise RuntimeError("Falta text o answers")
    body, h = multipart({"text": text.strip()}, [p for p in a.get("files", []) if os.path.isfile(p)])
    return brief(http("POST", f"/api/jobs/message/{a['job_id']}", body, h)["job"])


def list_jobs(a):
    ensure_running()
    return [brief(j) | {"outputs": j.get("outputs")} for j in http("GET", "/api/jobs/list")["jobs"][: int(a.get("limit") or 15)]]


def cancel(a):
    ensure_running()
    return http("POST", f"/api/jobs/cancel/{a['job_id']}", {})


S = lambda **p: {"type": "object", "properties": p, "additionalProperties": False}
STR, INT, BOOL = {"type": "string"}, {"type": "integer"}, {"type": "boolean"}
TOOLS = {
    "video_studio_create": (create_video, "Pide a Video Studio un video / animación (letra sincronizada, historia o explicación narrada, edición de clips, "
        "visualizador 3D) y, si hace falta, una página HTML o un modelo 3D (Blender). Describe qué debe mostrar; para basarlo en OTRO proyecto "
        "pasa context_dir (ruta absoluta) y context_note. Devuelve job_id al instante; el trabajo corre en segundo plano (minutos).",
        dict(S(prompt={**STR, "description": "Qué video/animación/modelo quieres, estilo, duración, idioma, narración, etc."},
               name=STR, aspect={**STR, "description": "9:16, 16:9, 1:1 o manual (texto libre en el prompt). Por defecto 9:16"},
               context_dir={**STR, "description": "Carpeta de origen que se explica/anima (solo lectura)"}, context_note=STR,
               files={"type": "array", "items": STR, "description": "Rutas absolutas de archivos a subir (audio, imágenes, guion, video fuente)"},
               deliverables={"type": "array", "items": {"type": "string", "enum": ["video", "html", "modelo3d"]}},
               tools={"type": "object", "description": "Permisos de generación: images, tts, music, models (booleans). Omitir = valores de los ajustes"},
               ask_questions={**BOOL, "description": "true = si hay dudas de estilo/contenido el trabajo termina con preguntas (opción múltiple) en vez de producir; false = decide solo. Omitir = ajuste de la app"},
               model=STR, effort=STR), required=["prompt"])),
    "video_studio_status": (status, "Estado de un trabajo (queued/running/done/error/cancelled), paso actual y avance. wait_seconds (máx 540) espera a que termine.",
        S(job_id=STR, wait_seconds=INT) | {"required": ["job_id"]}),
    "video_studio_result": (result, "Rutas de los entregables (video .mp4, .html, modelos) y el mensaje final de Claude, con preguntas pendientes si las hay. "
        "copy_to copia los archivos a esa carpeta (p. ej. el proyecto actual) y devuelve las nuevas rutas.",
        S(job_id=STR, copy_to=STR) | {"required": ["job_id"]}),
    "video_studio_reply": (reply, "Envía un pedido de cambios, o las respuestas a las `questions` pendientes (answers: {id: opción elegida | lista | texto propio}), a un trabajo terminado (misma sesión); si sigue en curso, el texto lo complementa sin detenerlo.",
        S(job_id=STR, text=STR, answers={"type": "object"}, files={"type": "array", "items": STR}) | {"required": ["job_id"]}),
    "video_studio_list": (list_jobs, "Lista los trabajos recientes de Video Studio.", S(limit=INT)),
    "video_studio_cancel": (cancel, "Cancela un trabajo en curso.", S(job_id=STR) | {"required": ["job_id"]}),
}


# ------------------------------------------------------------------ MCP stdio (JSON-RPC, one message per line)
def handle(m):
    method, mid = m.get("method"), m.get("id")
    if mid is None: return None                      # notifications: nothing to answer
    if method == "initialize":
        res = {"protocolVersion": (m.get("params") or {}).get("protocolVersion", "2025-03-26"), "capabilities": {"tools": {}},
               "serverInfo": {"name": "video-studio", "version": "1.0"}}
    elif method == "tools/list":
        res = {"tools": [{"name": n, "description": d, "inputSchema": sch} for n, (_, d, sch) in TOOLS.items()]}
    elif method == "tools/call":
        p = m["params"]
        try:
            out = TOOLS[p["name"]][0](p.get("arguments") or {})
            res = {"content": [{"type": "text", "text": json.dumps(out, ensure_ascii=False, indent=1)}]}
        except Exception as e:
            res = {"isError": True, "content": [{"type": "text", "text": f"{type(e).__name__}: {e}"}]}
    elif method == "ping":
        res = {}
    else:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"método desconocido: {method}"}}
    return {"jsonrpc": "2.0", "id": mid, "result": res}


def config(kind):
    py, me = sys.executable, os.path.abspath(__file__)
    if kind == "claude": return f'claude mcp add video-studio --scope user -- "{py}" "{me}"'
    if kind == "codex": return f'[mcp_servers.video-studio]\ncommand = "{py}"\nargs = ["{me}"]\n# pega esto en ~/.codex/config.toml'
    snippet = {"mcpServers": {"video-studio": {"command": py, "args": [me]}}}
    return json.dumps(snippet, indent=2)   # gemini (~/.gemini/settings.json), antigravity (mcp_config.json), cursor, etc.


if __name__ == "__main__":
    if "--config" in sys.argv:
        print(config(sys.argv[sys.argv.index("--config") + 1] if len(sys.argv) > sys.argv.index("--config") + 1 else "json"))
        sys.exit(0)
    for line in sys.stdin:
        if not line.strip(): continue
        try: out = handle(json.loads(line))
        except Exception as e: out = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(e)}}
        if out: sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n"); sys.stdout.flush()

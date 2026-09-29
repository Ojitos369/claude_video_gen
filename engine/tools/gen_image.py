# Image generation tool for video projects (Claude uses it when an image would improve the video: a background, a character,
# a prop, a title card...). Provider and model come from settings.local.json -> images; keys from -> providers.
#   python engine/tools/gen_image.py <project> "prompt" --out assets/fondo.png [--aspect 9:16] [--transparent] [--ref img.png]
# Providers: google (Gemini image models, API key) · openai (API key, or the ChatGPT subscription through the Codex CLI).
# Every image is logged in projects/<id>/assets/images.json (prompt, provider, model) and counted against images.max_per_project.
import argparse
import base64
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from engine.tools import local_settings  # noqa: E402
from engine.tools.binaries import find_cli, command  # noqa: E402

DEFAULT_MODEL = {"google": "gemini-2.5-flash-image", "openai": "gpt-image-1"}


def post_json(url, body, headers, timeout=300):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"error {e.code} de la API: {e.read().decode(errors='replace')[:800]}")


def google(prompt, model, aspect, ref):
    k = local_settings.key("google")
    if not k: raise SystemExit("Falta la API key de Google (ajustes de la app)")
    parts = [{"text": prompt}]
    if ref:
        mime = "image/png" if ref.lower().endswith(".png") else "image/jpeg"
        parts.append({"inline_data": {"mime_type": mime, "data": base64.b64encode(open(ref, "rb").read()).decode()}})
    body = {"contents": [{"parts": parts}], "generationConfig": {"responseModalities": ["IMAGE"]}}
    if aspect: body["generationConfig"]["imageConfig"] = {"aspectRatio": aspect}
    d = post_json(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", body, {"x-goog-api-key": k})
    for c in d.get("candidates", []):
        for p in c.get("content", {}).get("parts", []):
            data = (p.get("inlineData") or p.get("inline_data") or {}).get("data")
            if data: return base64.b64decode(data)
    raise SystemExit(f"la respuesta no trae imagen: {json.dumps(d)[:600]}")


def openai_size(aspect):
    if not aspect: return "1024x1024"
    w, h = map(float, aspect.split(":"))
    return "1024x1536" if h > w * 1.15 else "1536x1024" if w > h * 1.15 else "1024x1024"


def openai_api(prompt, model, aspect, transparent, ref):
    k = local_settings.key("openai")
    if not k: raise SystemExit("Falta la API key de OpenAI (ajustes de la app)")
    if ref:   # edits endpoint takes multipart; keep stdlib-only by describing the reference instead
        prompt += f" (usa como referencia visual la imagen {os.path.basename(ref)})"
    body = {"model": model, "prompt": prompt, "size": openai_size(aspect), "n": 1}
    if transparent: body["background"] = "transparent"
    d = post_json("https://api.openai.com/v1/images/generations", body, {"Authorization": f"Bearer {k}"})
    return base64.b64decode(d["data"][0]["b64_json"])


def openai_subscription(prompt, aspect, transparent, ref):
    """ChatGPT subscription through the official Codex CLI (login with `codex login`): codex saves the image it generates
    under ~/.codex/generated_images; we pick the new file."""
    codex = find_cli("codex", os.environ.get("CODEX_BIN"))
    if not codex: raise SystemExit("No encontré Codex CLI (necesario para usar la suscripción de ChatGPT)")
    root = os.path.join(os.path.expanduser("~"), ".codex", "generated_images")
    before = set(glob.glob(os.path.join(root, "**", "*.*"), recursive=True))
    t0 = time.time()
    extra = f" Proporción {aspect}." if aspect else ""
    extra += " Fondo transparente." if transparent else ""
    msg = (f"Usa tu herramienta de generación de imágenes para crear UNA imagen: {prompt}.{extra} "
           "No escribas código ni archivos; solo genera la imagen y responde 'listo'.")
    cmd = command(codex) + ["exec", "--skip-git-repo-check", "--ephemeral", "-s", "read-only", msg]
    if ref: cmd[-1:-1] = ["-i", ref]
    with tempfile.TemporaryDirectory() as tmp:
        r = subprocess.run(cmd, cwd=tmp, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=600)
    new = [p for p in glob.glob(os.path.join(root, "**", "*.*"), recursive=True) if p not in before and os.path.getmtime(p) >= t0 - 1]
    if not new:
        raise SystemExit("Codex no generó ninguna imagen" + (f": {r.stderr[-500:]}" if r.returncode else " (revisa `codex login status`)"))
    return open(max(new, key=os.path.getmtime), "rb").read()


def main():
    ap = argparse.ArgumentParser(description="Genera una imagen para un proyecto de video")
    ap.add_argument("project"); ap.add_argument("prompt")
    ap.add_argument("--out", required=True, help="ruta dentro del proyecto, p. ej. assets/fondo.png")
    ap.add_argument("--aspect", help="proporción, p. ej. 9:16, 16:9, 1:1")
    ap.add_argument("--transparent", action="store_true", help="fondo transparente (sprites / personajes)")
    ap.add_argument("--ref", help="imagen de referencia dentro del proyecto")
    ap.add_argument("--provider"); ap.add_argument("--model")
    a = ap.parse_args()
    s = local_settings.load()
    proj = a.project if os.path.isdir(a.project) else os.path.join(local_settings.ROOT, "projects", a.project)
    if not os.path.isdir(proj): raise SystemExit(f"no existe el proyecto {a.project}")
    cfg = s["images"]; provider = a.provider or cfg["provider"]
    if provider in (None, "", "none"): raise SystemExit("La generación de imágenes no está configurada (ajustes de la app -> Imágenes)")
    log_path = os.path.join(proj, "assets", "images.json")
    log = json.load(open(log_path, encoding="utf-8")) if os.path.exists(log_path) else []
    if len(log) >= int(cfg.get("max_per_project") or 12):
        raise SystemExit(f"Límite de {cfg.get('max_per_project')} imágenes por proyecto alcanzado (ajustes -> Imágenes)")
    model = a.model or cfg.get("model") or DEFAULT_MODEL.get(provider, "")
    ref = os.path.join(proj, a.ref) if a.ref and not os.path.isabs(a.ref) else a.ref
    out = os.path.join(proj, a.out) if not os.path.isabs(a.out) else a.out
    os.makedirs(os.path.dirname(out), exist_ok=True)
    if provider == "google":
        data = google(a.prompt, model, a.aspect, ref)
    elif provider == "openai" and s["providers"]["openai"]["auth"] == "subscription":
        data, model = openai_subscription(a.prompt, a.aspect, a.transparent, ref), "chatgpt (codex)"
    elif provider == "openai":
        data = openai_api(a.prompt, model, a.aspect, a.transparent, ref)
    else:
        raise SystemExit(f"proveedor desconocido: {provider}")
    with open(out, "wb") as f:
        f.write(data)
    log.append({"file": os.path.relpath(out, proj), "prompt": a.prompt, "provider": provider, "model": model,
                "aspect": a.aspect, "transparent": a.transparent, "at": time.strftime("%Y-%m-%dT%H:%M:%S")})
    json.dump(log, open(log_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{os.path.relpath(out, proj)} ({len(data) / 1024:.0f} KB, {provider} {model})")


if __name__ == "__main__":
    main()

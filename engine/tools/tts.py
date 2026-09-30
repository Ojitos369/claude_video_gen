# Text-to-speech tool for video projects (narration, voice-overs). Provider / model / voice from settings.local.json -> tts.
#   python engine/tools/tts.py <project> --text "Hola…" --out audio/narracion.wav [--voice X] [--model Y] [--lang es]
#   python engine/tools/tts.py <project> --file guion.txt --out audio/narracion.wav
# Open source (local, free): piper, kokoro — installed into the engine venv and their voices downloaded on first use.
# Free online, no key: edge (Microsoft Edge neural voices).
# Services (API key in the app settings): google (Gemini TTS, e.g. gemini-3.8-flash-tts), openai, elevenlabs.
# Output: WAV (mono). Logged in projects/<id>/audio/tts.json. Online services also keep each request / answer / audio in
# projects/<id>/assets/{edge-tts,gemini-tts,openai-tts,elevenlabs-tts}/ (engine/tools/apilog.py).
import argparse
import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from engine.tools import local_settings  # noqa: E402
from engine.tools.apilog import Call  # noqa: E402

CACHE = os.path.join(os.path.expanduser("~"), ".cache", "video-studio", "tts")
DEFAULTS = {"edge": ("edge-tts", "es-MX-JorgeNeural"), "piper": ("es_MX-claude-high", ""), "kokoro": ("kokoro-v1.0", "ef_dora"), "google": ("gemini-3.8-flash-tts", "Kore"),
            "openai": ("gpt-4o-mini-tts", "coral"), "elevenlabs": ("eleven_multilingual_v2", "JBFqnCBsd6RMkjVDRZzb")}


def write_pcm(path, pcm, rate):
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(pcm)


def request(url, body, headers, rec, timeout=600):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read()
            try: rec.response(json.loads(data), status=r.status)
            except ValueError: rec.response(data, status=r.status, content_type=r.headers.get("Content-Type"))
            return data
    except urllib.error.HTTPError as e:
        err = e.read().decode(errors="replace")
        rec.response(err, status=e.code)
        raise SystemExit(f"error {e.code} de la API: {err[:800]}")


def download(url, dest):
    if os.path.exists(dest): return dest
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    print(f"descargando {os.path.basename(dest)}…", flush=True)
    urllib.request.urlretrieve(url, dest + ".part"); os.replace(dest + ".part", dest)
    return dest


def ensure_pkg(module, pip_name):
    try:
        __import__(module)
    except ImportError:   # install into the running (engine) venv, cross-platform
        uv = __import__("shutil").which("uv")
        cmd = [uv, "pip", "install", "--python", sys.executable, pip_name] if uv else [sys.executable, "-m", "pip", "install", pip_name]
        print(f"instalando {pip_name}…", flush=True)
        subprocess.run(cmd, check=True)


def piper(text, model, voice, out):
    ensure_pkg("piper", "piper-tts")
    from piper import PiperVoice
    lang, rest = model.split("-", 1)[0], model.split("-", 1)[1]        # es_MX-claude-high
    name, quality = rest.rsplit("-", 1)
    base = f"https://huggingface.co/rhasspy/piper-voices/resolve/main/{lang.split('_')[0]}/{lang}/{name}/{quality}/{model}"
    onnx = download(base + ".onnx", os.path.join(CACHE, "piper", model + ".onnx"))
    download(base + ".onnx.json", os.path.join(CACHE, "piper", model + ".onnx.json"))
    v = PiperVoice.load(onnx)
    with wave.open(out, "wb") as w:
        v.synthesize_wav(text, w)


def kokoro(text, model, voice, out, lang):
    ensure_pkg("kokoro_onnx", "kokoro-onnx")
    from kokoro_onnx import Kokoro
    rel = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
    m = download(f"{rel}/kokoro-v1.0.onnx", os.path.join(CACHE, "kokoro", "kokoro-v1.0.onnx"))
    vv = download(f"{rel}/voices-v1.0.bin", os.path.join(CACHE, "kokoro", "voices-v1.0.bin"))
    samples, sr = Kokoro(m, vv).create(text, voice=voice, speed=1.0, lang={"es": "es", "en": "en-us"}.get(lang, lang))
    import numpy as np
    write_pcm(out, (np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes(), sr)


def edge(text, voice, out, rate, proj):
    """Microsoft Edge neural voices (free, no key, online) -> mp3 -> wav with ffmpeg."""
    ensure_pkg("edge_tts", "edge-tts")
    import asyncio, shutil, edge_tts
    mp3 = out + ".mp3"
    rec = Call(proj, "edge-tts", {"service": "edge-tts", "body": {"text": text, "voice": voice, "rate": rate or "+0%"}})
    try:
        asyncio.run(edge_tts.Communicate(text, voice, rate=rate or "+0%").save(mp3))
    except Exception as e:
        rec.response(str(e), error=type(e).__name__); raise
    rec.response({"bytes": os.path.getsize(mp3)}, format="mp3")
    rec.file(mp3, os.path.splitext(os.path.basename(out))[0] + ".mp3")
    subprocess.run([shutil.which("ffmpeg") or "ffmpeg", "-y", "-loglevel", "error", "-i", mp3, "-ac", "1", "-ar", "24000", out], check=True)
    os.remove(mp3)
    return rec


def google(text, model, voice, out, proj):
    k = local_settings.key("google")
    if not k: raise SystemExit("Falta la API key de Google (ajustes de la app)")
    body = {"contents": [{"parts": [{"text": text}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}}
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    rec = Call(proj, "gemini-tts", {"method": "POST", "url": url, "body": body})
    d = json.loads(request(url, body, {"x-goog-api-key": k}, rec))
    for c in d.get("candidates", []):
        for p in c.get("content", {}).get("parts", []):
            inl = p.get("inlineData") or p.get("inline_data") or {}
            if inl.get("data"):
                mime = inl.get("mimeType", "")
                rate = int(mime.split("rate=")[1].split(";")[0]) if "rate=" in mime else 24000
                write_pcm(out, base64.b64decode(inl["data"]), rate); return rec
    raise SystemExit(f"la respuesta no trae audio: {json.dumps(d)[:600]}")


def openai(text, model, voice, out, instructions, proj):
    k = local_settings.key("openai")
    if not k: raise SystemExit("Falta la API key de OpenAI (ajustes de la app; el TTS no se puede usar con la suscripción)")
    body = {"model": model, "voice": voice, "input": text, "response_format": "wav"}
    if instructions: body["instructions"] = instructions
    url = "https://api.openai.com/v1/audio/speech"
    rec = Call(proj, "openai-tts", {"method": "POST", "url": url, "body": body})
    with open(out, "wb") as f:
        f.write(request(url, body, {"Authorization": f"Bearer {k}"}, rec))
    return rec


def elevenlabs(text, model, voice, out, proj):
    k = local_settings.key("elevenlabs")
    if not k: raise SystemExit("Falta la API key de ElevenLabs (ajustes de la app)")
    url, body = f"https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=pcm_24000", {"text": text, "model_id": model}
    rec = Call(proj, "elevenlabs-tts", {"method": "POST", "url": url, "body": body})
    write_pcm(out, request(url, body, {"xi-api-key": k}, rec), 24000)
    return rec


def main():
    ap = argparse.ArgumentParser(description="Genera voz (TTS) para un proyecto de video")
    ap.add_argument("project"); ap.add_argument("--text"); ap.add_argument("--file")
    ap.add_argument("--out", required=True, help="ruta dentro del proyecto, p. ej. audio/narracion.wav")
    ap.add_argument("--provider"); ap.add_argument("--model"); ap.add_argument("--voice"); ap.add_argument("--lang")
    ap.add_argument("--instructions", help="tono / estilo (proveedores que lo soportan)")
    ap.add_argument("--rate", help="velocidad para edge, p. ej. -5%%")
    a = ap.parse_args()
    s = local_settings.load()["tts"]
    proj = a.project if os.path.isdir(a.project) else os.path.join(local_settings.ROOT, "projects", a.project)
    if not os.path.isdir(proj): raise SystemExit(f"no existe el proyecto {a.project}")
    text = a.text or (open(os.path.join(proj, a.file) if not os.path.isabs(a.file) else a.file, encoding="utf-8").read() if a.file else "")
    if not text.strip(): raise SystemExit("falta el texto (--text o --file)")
    provider = a.provider or s["provider"]
    if provider in (None, "", "none"): raise SystemExit("El TTS no está configurado (ajustes de la app -> Voz)")
    dm, dv = DEFAULTS.get(provider, ("", ""))
    same = provider == s["provider"]   # the saved model / voice belong to the configured provider only
    model, voice = a.model or (same and s.get("model")) or dm, a.voice or (same and s.get("voice")) or dv
    lang = a.lang or s.get("language") or "es"
    out = os.path.join(proj, a.out) if not os.path.isabs(a.out) else a.out
    os.makedirs(os.path.dirname(out), exist_ok=True)
    t0 = time.time()
    rec = None   # service record (online providers only)
    if provider == "edge": rec = edge(text, voice, out, a.rate, proj)
    elif provider == "piper": piper(text, model, voice, out)
    elif provider == "kokoro": kokoro(text, model, voice, out, lang)
    elif provider == "google": rec = google(text, model, voice, out, proj)
    elif provider == "openai": rec = openai(text, model, voice, out, a.instructions, proj)
    elif provider == "elevenlabs": rec = elevenlabs(text, model, voice, out, proj)
    else: raise SystemExit(f"proveedor desconocido: {provider}")
    if rec and provider != "edge": rec.file(out)   # edge keeps its original mp3
    with wave.open(out) as w:
        dur = w.getnframes() / w.getframerate()
    log_path = os.path.join(proj, "audio", "tts.json")
    log = json.load(open(log_path, encoding="utf-8")) if os.path.exists(log_path) else []
    log.append({"file": os.path.relpath(out, proj), "provider": provider, "model": model, "voice": voice, "chars": len(text),
                "seconds": round(dur, 2), "at": time.strftime("%Y-%m-%dT%H:%M:%S")})
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    json.dump(log, open(log_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{os.path.relpath(out, proj)} ({dur:.1f} s, {provider} {model} {voice}, {time.time() - t0:.0f} s)")


if __name__ == "__main__":
    main()

# Local settings of the workspace (theme, API keys, TTS / image providers, LAN access). Stored in settings.local.json at the
# workspace root, which is git-ignored. Shared by the app backend and the engine tools; stdlib only (runs in both venvs).
import copy
import json
import os
import secrets

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PATH = os.environ.get("VIDEO_STUDIO_SETTINGS") or os.path.join(ROOT, "settings.local.json")

DEFAULTS = {
    "theme": "dark",                                   # dark | light
    "access": {"lan": False, "token": ""},             # lan: listen on the local network (phone), token required there
    "providers": {
        "anthropic": {"api_key": "", "use_api_key": False},   # default: Claude Code's own login
        "google": {"api_key": ""},
        "openai": {"auth": "api", "api_key": ""},             # auth: api | subscription (ChatGPT login through Codex CLI)
        "elevenlabs": {"api_key": ""},
    },
    "tts": {"provider": "none", "model": "", "voice": "", "language": "es"},
    "images": {"provider": "none", "model": "", "max_per_project": 12},
    "generation": {"images": True, "tts": False},     # tools offered to Claude by default in new jobs
}

# catalogue shown in the app (free text is also accepted for models)
TTS_PROVIDERS = {
    "none": {"label": "Ninguno", "kind": "", "models": [], "voices": []},
    "piper": {"label": "Piper (código abierto, local, CPU)", "kind": "open", "models": ["es_MX-claude-high", "es_MX-ald-medium", "es_ES-davefx-medium", "en_US-lessac-medium"], "voices": []},
    "kokoro": {"label": "Kokoro (código abierto, local)", "kind": "open", "models": ["kokoro-v1.0"], "voices": ["ef_dora", "em_alex", "af_heart", "am_michael"]},
    "edge": {"label": "Edge TTS (gratis, sin clave, requiere internet)", "kind": "free", "models": ["edge-tts"], "voices": ["es-MX-JorgeNeural", "es-MX-DaliaNeural", "es-ES-AlvaroNeural", "es-ES-ElviraNeural", "en-US-AriaNeural"]},
    "google": {"label": "Google Gemini TTS", "kind": "service", "key": "google", "models": ["gemini-3.8-flash-tts", "gemini-2.5-flash-preview-tts", "gemini-2.5-pro-preview-tts"], "voices": ["Kore", "Puck", "Charon", "Aoede", "Fenrir", "Leda", "Orus", "Zephyr"]},
    "openai": {"label": "OpenAI TTS", "kind": "service", "key": "openai", "models": ["gpt-4o-mini-tts", "tts-1-hd"], "voices": ["alloy", "ash", "coral", "echo", "nova", "sage", "shimmer"]},
    "elevenlabs": {"label": "ElevenLabs", "kind": "service", "key": "elevenlabs", "models": ["eleven_multilingual_v2", "eleven_flash_v2_5"], "voices": []},
}
IMAGE_PROVIDERS = {
    "none": {"label": "Ninguno", "models": []},
    "google": {"label": "Google Gemini (imagen)", "key": "google", "models": ["gemini-2.5-flash-image", "gemini-3-pro-image-preview"]},
    "openai": {"label": "OpenAI (API o suscripción ChatGPT)", "key": "openai", "models": ["gpt-image-1", "gpt-image-1-mini"]},
}
SECRET_FIELDS = ("api_key", "token")


def _merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        out[k] = _merge(out[k], v) if isinstance(out.get(k), dict) and isinstance(v, dict) else v
    return out


def load():
    try:
        with open(PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    s = _merge(DEFAULTS, data)
    if not s["access"]["token"]:
        s["access"]["token"] = secrets.token_urlsafe(18)
        save(s)
    return s


def save(s):
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=1)
    os.replace(tmp, PATH)
    if os.name != "nt":
        os.chmod(PATH, 0o600)   # it holds API keys


def masked(s=None):
    """Copy safe to send to the browser: secrets replaced by {set, hint}."""
    s = copy.deepcopy(s or load())
    def walk(d):
        for k, v in list(d.items()):
            if isinstance(v, dict): walk(v)
            elif k == "api_key":
                d[k] = ""; d["api_key_set"] = bool(v); d["api_key_hint"] = f"…{v[-4:]}" if v else ""
    walk(s["providers"])
    return s


def update(patch):
    """Partial update from the app. Empty api_key strings keep the stored key; `clear_api_key: true` removes it."""
    s = load()
    for name, p in (patch.get("providers") or {}).items():
        if name not in s["providers"]: continue
        p = dict(p)
        if p.pop("clear_api_key", False): p["api_key"] = ""
        elif not p.get("api_key"): p.pop("api_key", None)
        p.pop("api_key_set", None); p.pop("api_key_hint", None)
        s["providers"][name].update({k: v for k, v in p.items() if k in DEFAULTS["providers"][name]})
    for sec in ("tts", "images", "generation"):
        if isinstance(patch.get(sec), dict):
            s[sec].update({k: v for k, v in patch[sec].items() if k in DEFAULTS[sec]})
    if patch.get("theme") in ("dark", "light"):
        s["theme"] = patch["theme"]
    if isinstance(patch.get("access"), dict):
        if "lan" in patch["access"]: s["access"]["lan"] = bool(patch["access"]["lan"])
        if patch["access"].get("regenerate_token"): s["access"]["token"] = secrets.token_urlsafe(18)
    save(s)
    return s


def key(provider):
    return (load()["providers"].get(provider) or {}).get("api_key", "")

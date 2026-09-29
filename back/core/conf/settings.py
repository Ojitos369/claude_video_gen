import os
from pathlib import Path
import setproctitle
from dotenv import load_dotenv
from ojitos369.errors import CatchErrors as CE

setproctitle.setproctitle('video-studio-py')

# ----------------------   BASE   ----------------------
BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(os.path.join(BASE_DIR, '.env'))
MEDIA_DIR = os.path.join(BASE_DIR, 'media')

# ----------------------   VIDEO STUDIO   ----------------------
# workspace = repo root (engine/, projects/, CLAUDE.md); claude runs there so CLAUDE.md and the engine are in context
WORKSPACE_DIR = os.environ.get('WORKSPACE_DIR', str(BASE_DIR.parent))
PROJECTS_DIR = os.path.join(WORKSPACE_DIR, 'projects')
from core.conf.claude_bin import find_claude
CLAUDE_BIN = find_claude(os.environ.get('VS_CLAUDE_BIN')) or os.environ.get('VS_CLAUDE_BIN', 'claude')   # VS_ prefix: a Claude Code terminal exports CLAUDE_* of its own   # auto-detected install
CLAUDE_MODEL = os.environ.get('VS_CLAUDE_MODEL', 'claude-opus-5-5')   # default in the app
# models offered in the app (Claude Code accepts full names or the aliases fable/opus/sonnet/haiku).
# Override with VS_CLAUDE_MODELS="id:Label,id:Label" in back/.env
CLAUDE_MODELS = [
    {"id": "claude-opus-5-5", "label": "Opus 5.5", "note": "el más capaz para proyectos completos"},
    {"id": "claude-fable-5-1", "label": "Fable 5.1", "note": "requiere créditos de uso en la cuenta"},
    {"id": "claude-sonnet-5-5", "label": "Sonnet 5.5", "note": "más rápido y económico"},
    {"id": "claude-haiku-4-5-20251001", "label": "Haiku 4.5", "note": "el más rápido, para cambios pequeños"},
]
if os.environ.get('VS_CLAUDE_MODELS'):
    CLAUDE_MODELS = [{"id": m.split(':')[0].strip(), "label": (m.split(':', 1)[1] if ':' in m else m).strip(), "note": ""}
                     for m in os.environ['VS_CLAUDE_MODELS'].split(',') if m.strip()]
# reasoning effort (claude --effort). Chosen per job / per follow-up in the app; default high
CLAUDE_EFFORT = os.environ.get('VS_CLAUDE_EFFORT', 'high')
CLAUDE_EFFORTS = [
    {"id": "low", "label": "Bajo", "note": "rápido y económico; suficiente con los mejores modelos en tareas simples"},
    {"id": "medium", "label": "Medio", "note": "equilibrio entre rapidez y cuidado"},
    {"id": "high", "label": "Alto", "note": "recomendado para proyectos de video completos"},
    {"id": "xhigh", "label": "Muy alto", "note": "más razonamiento; útil con modelos más pequeños o pedidos complejos"},
    {"id": "max", "label": "Máximo", "note": "el más lento y costoso"},
]
if CLAUDE_EFFORT not in [e["id"] for e in CLAUDE_EFFORTS]:
    CLAUDE_EFFORT = "high"
if CLAUDE_MODEL not in [m["id"] for m in CLAUDE_MODELS]:
    CLAUDE_MODELS.insert(0, {"id": CLAUDE_MODEL, "label": CLAUDE_MODEL, "note": ""})
# local tool with no human in the loop: claude may run any command inside the workspace
CLAUDE_PERMISSION_MODE = os.environ.get('VS_CLAUDE_PERMISSION_MODE', 'bypassPermissions')
prod_mode = True if str(os.environ.get('RUN_PROD_MODE', True)).title() == 'True' else False
dev_mode = True if str(os.environ.get('RUN_DEV_MODE', False)).title() == 'True' else False

# ----------------------   CORS   ----------------------
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
allow_origin_regex = r"https?://(localhost|127\.0\.0\.1)(:[0-9]+)?"
allow_origins = origins
allow_credentials = True
allow_methods = ["*"]
allow_headers = ["*"]

# ----------------------   ERROR   ----------------------
class MYE(Exception):
    pass

ce = CE(name_project = 'VIDEO-STUDIO')

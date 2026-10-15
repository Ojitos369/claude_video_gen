# Usar Video Studio desde otros agentes

Cualquier agente con soporte MCP puede pedir videos, animaciones, páginas HTML y modelos 3D a Video Studio **desde otro proyecto**:
le dice qué explicar, el servidor MCP (`video_studio_mcp.py`, solo stdlib de Python 3) se lo pasa al servicio local, que lo lee en modo
solo lectura (`context_dir`), lo produce con el motor y devuelve las rutas del `.mp4` / `.html` / modelo `.glb`.

Piezas: `video_studio_mcp.py` (servidor MCP) y `skill/video-studio/SKILL.md` (cuándo y cómo usarlo, formato de skill de Claude Code).
El MCP arranca el servicio solo (`run.sh --no-browser`) si no está corriendo. Herramientas: `video_studio_create`, `_status`, `_result`,
`_reply`, `_list`, `_cancel`.

## Registrar
`python integrations/video_studio_mcp.py --config claude|codex|json` imprime el comando/fragmento con las rutas absolutas de este checkout.

| Agente | Servidor MCP | Instrucciones (skill) |
|---|---|---|
| Claude Code | `claude mcp add video-studio --scope user -- <python> <ruta>/integrations/video_studio_mcp.py` (`--scope project` crea `.mcp.json`) | `ln -s <ruta>/integrations/skill/video-studio ~/.claude/skills/video-studio` |
| Codex CLI | `~/.codex/config.toml`: `[mcp_servers.video-studio]` con `command` y `args` (lo imprime `--config codex`) | pegar el cuerpo de `SKILL.md` en `~/.codex/AGENTS.md` (o `AGENTS.md` del proyecto) |
| Gemini CLI | `~/.gemini/settings.json` -> `mcpServers` (fragmento `--config json`) | pegar el cuerpo de `SKILL.md` en `~/.gemini/GEMINI.md` |
| Antigravity | panel de agente -> MCP Servers -> Manage -> *View raw config* (`mcp_config.json`): fragmento `--config json` | regla global o del workspace con el cuerpo de `SKILL.md` |
| Cursor / Windsurf / Cline / otros | su `mcp.json` con el fragmento `--config json` | regla del proyecto (`.cursor/rules`, `AGENTS.md`…) con el cuerpo de `SKILL.md` |

Fragmento JSON genérico: `{"mcpServers": {"video-studio": {"command": "<python>", "args": ["<ruta>/integrations/video_studio_mcp.py"]}}}`.
Verificar: pedir al agente "lista los trabajos de video-studio" (`video_studio_list`).

## Variables
- `VIDEO_STUDIO_URL` (default `http://127.0.0.1:8470`): si el servicio corre en otra máquina. Activa "Acceso desde el teléfono" y pasa
  `VIDEO_STUDIO_TOKEN` (el token de Ajustes); no arranca el servicio remoto. `result` con `copy_to` descarga los archivos por HTTP.
- `VIDEO_STUDIO_AUTOSTART=0`: nunca lanzar el servicio.

## Sin MCP
La API es HTTP: `POST /api/jobs/create` (multipart: `prompt`, `name`, `aspect`, `tools` JSON, `files`), `GET /api/jobs/detail/<id>`,
`GET /api/jobs/events/<id>`, `POST /api/jobs/message/<id>`, `GET /api/jobs/file/<id>/<ruta>`. Los entregables quedan en `projects/<id>/out/`.

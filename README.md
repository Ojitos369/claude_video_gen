# Video Studio — generador universal de videos

App local (FastAPI + React) sobre un motor de video en Python. Subes archivos de contexto, describes el video y
Claude Code (`claude -p`, Opus 5.5 por defecto) arma el proyecto con el motor, lo renderiza en la GPU y la app muestra
cada paso en vivo y el resultado final. El motor también se usa directamente desde la terminal.

Tipos de video que ya produce:

| Tipo | Qué hace | Ejemplo |
|---|---|---|
| Letra + escenas 2D | letra sincronizada (karaoke, romanización y traducción según idioma) sobre escenas animadas acordes a la letra | canción en coreano, 9:16 |
| Letra sobre el video fuente | el video original bajo una cubierta negra, solo anima la letra | videoclip horizontal |
| Historia narrada | guion + narración + música + personajes: escenas por pasaje, pausas con difuminado entre partes, subtítulos | cuento de ciencia ficción |
| Explicación narrada | solo audio de voz: subtítulos palabra por palabra y escenas explicativas con ejemplos | resumen de un video tecnológico |
| Visualizador de vóxeles 3D | paisajes 3D que se desarman y rearman al ritmo, iluminación tipo shaders | reinos steampunk, 9:16 y 16:9 |

```
back/        FastAPI (base reapi): API de trabajos, websockets en vivo, sirve el front compilado (back/media/dist)
front/       React + Vite: subida con drag & drop, instrucciones, modelo, formato, proceso en vivo, resultado
engine/      motor de video
projects/    un proyecto por video (local, fuera de git)
run.sh / run.bat / launcher.py   arranque en Linux / Windows
Makefile     instalar / desarrollar / compilar / arrancar
```

## Instalación
Funciona en Linux y Windows. Requisitos: `uv`, `pnpm`, ffmpeg, fuentes Noto CJK y Claude Code instalado con sesión iniciada (`claude`).
Recomendado: GPU NVIDIA (CUDA para voz/transcripción, NVENC para codificar); sin ella se usa CPU y x264. Opcional: Codex CLI
(`codex login`) para generar imágenes con la suscripción de ChatGPT. El equipo se detecta solo al iniciar el servicio
(`settings.local.json` -> `machine`) y el motor elige con eso codificador y procesos en paralelo.
```bash
make install        # .venv del motor (requirements.txt), back/.venv y dependencias del front
```

## App local
```bash
./run.sh            # Linux/macOS: instala lo que falte, recompila el front si cambió, busca Claude, arranca y abre el navegador
run.bat             # Windows: lo mismo (doble clic)
#   opciones: --port 8470  --no-browser  --install-engine (entorno del motor, torch CUDA ~5 GB)  --rebuild
make start          # alternativa: compila el front y arranca http://127.0.0.1:8470
make dev            # desarrollo: back con reload (8470) + vite (http://127.0.0.1:5180)
```
`run.sh` / `run.bat` solo aseguran `back/.venv` con `uv` y llaman a `launcher.py`, que es el mismo en los dos sistemas. `--lan`
(o el ajuste "Acceso desde el teléfono") escucha en la red local: los demás dispositivos entran con el enlace/QR que incluye un token.
Claude Code se detecta solo (`back/core/conf/claude_bin.py`): PATH, `~/.local/bin`, `~/.claude/local`, npm global, nvm, bun,
volta, Homebrew y, en Windows, `%USERPROFILE%\.local\bin`, `%LOCALAPPDATA%\Programs\claude`, `%APPDATA%\npm`. Así funciona aunque
el servicio arranque sin el PATH de la terminal. `VS_CLAUDE_BIN` fuerza una ruta. En Windows la app funciona; el motor de video
está probado en Linux (NVENC y OpenGL sin ventana por EGL).
Configuración opcional en `back/.env` (ver `env.example`): `VS_CLAUDE_MODEL` (default `claude-opus-5-5`), `VS_CLAUDE_EFFORT` (default `high`), `VS_CLAUDE_MODELS` (lista del
selector), `VS_CLAUDE_BIN`, `VS_CLAUDE_PERMISSION_MODE` (default `bypassPermissions`: Claude ejecuta comandos sin pedir permiso, por eso el
servidor solo escucha en 127.0.0.1), `WORKSPACE_DIR`.

- **Mobile first**: en el teléfono la lista de trabajos es un menú lateral y cada trabajo se ve por pestañas (Proceso, Resultado,
  Progreso, Archivos); en escritorio, en columnas. Tema oscuro (por defecto) o claro.
- **Ajustes** (se guardan en `settings.local.json`, fuera de git; las claves no se muestran completas): tema; API keys de Anthropic
  (opcional, para facturar a la API en vez de la sesión de Claude Code), Google, OpenAI (API key o suscripción de ChatGPT vía Codex CLI)
  y ElevenLabs, con botón "Probar"; voz (Edge TTS gratis, Piper y Kokoro de código abierto locales, Google Gemini TTS
  `gemini-3.8-flash-tts`, OpenAI, ElevenLabs); imágenes (Google Gemini, OpenAI); herramientas permitidas por defecto; acceso desde el
  teléfono (QR); datos del equipo.
- **Nuevo video**: arrastra archivos (audio, video, imágenes, guiones, referencias), escribe qué quieres y elige formato y modelo.
  y qué herramientas puede usar Claude (generar imágenes / voz). Los archivos se guardan en `projects/<id>/` con `solicitud.md` y un
  `config.json` inicial; Claude recibe los datos del equipo y las herramientas disponibles (nunca las claves); el trabajo entra a una cola
  (uno a la vez, comparten la GPU).
- **Formato**: 9:16 por defecto; al subir un video cambia solo a "del video" (se puede cambiar a mano). Opciones: del video,
  de la imagen, 9:16 / 16:9, 3:4 / 4:3, wallpaper 10:16 / 16:10, 1:1 y **manual** (texto libre, p. ej. "monitor curvo de 72 pulgadas",
  que Claude interpreta y escribe en `config.json`).
- **Esfuerzo**: bajo, medio, alto (default), muy alto o máximo (`claude --effort`). Se elige a mano al crear el video y en cada pedido
  de cambios, junto con el modelo (p. ej. un modelo muy capaz con esfuerzo menor, o uno más pequeño con esfuerzo mayor).
- **Modelo**: Opus 5.5 (default), Fable 5.1 (requiere créditos de uso en la cuenta), Sonnet 5.5, Haiku 4.5. Se elige al crear el video
  y en cada pedido de cambios; el backend solo acepta modelos de la lista.
- **Proceso en vivo**: paso actual con tiempo, línea de tiempo de cada acción de Claude (comando, lectura, edición, búsqueda; se abre
  para ver entrada y salida), sus mensajes, costo y duración, `PROGRESO.md` y los archivos de `out/` en cuanto aparecen.
- **Resultado**: reproductor (prefiere el video final sobre las vistas previas), descargas y archivos del proyecto.
- **Cambios**: el cuadro de abajo continúa la misma sesión de Claude (`--resume`). Se puede cancelar o borrar un trabajo.
- **Renombrar**: lápiz junto al título. Cambia el nombre visible; la carpeta `projects/<id>/` no cambia (la sesión de Claude usa esa ruta).
- Claude corre desacoplado del servidor (su salida va a `projects/<id>/.app/run-N.jsonl`): reiniciar el servidor no corta un
  trabajo, se retoma al arrancar. Los proyectos creados desde la terminal aparecen en la lista y también se pueden continuar.

API: `GET /api/jobs/list`, `POST /api/jobs/create` (multipart: `prompt`, `name`, `model`, `effort`, `aspect`, `aspect_text`, `tools`, `files[]`),
`GET /api/jobs/detail/<id>`, `GET /api/jobs/events/<id>?since=N`, `POST /api/jobs/message/<id>` (`text`, `model`, `effort`),
`POST /api/jobs/rename/<id>` (`name`), `POST /api/jobs/cancel/<id>`, `POST /api/jobs/delete/<id>`, `GET /api/jobs/file/<id>/<ruta>`, `GET /api/base/status`,
`GET /api/settings/get`, `POST /api/settings/save`, `POST /api/settings/test/<plataforma>`, `POST /api/settings/codex_login`,
`POST /api/settings/machine`, websockets `/api/ws/jobs/<id>` (eventos de un trabajo) y `/api/ws/jobs/all` (estado de todos).

---

## Motor (uso desde la terminal)
Reglas generales, flujo por tipo y lecciones aprendidas: `CLAUDE.md` (local, fuera de git).

```
.venv/                 entorno del motor (uv, Python 3.11): torch+CUDA, demucs, faster-whisper, torchaudio (MMS_FA), librosa, pillow, moderngl, scipy
engine/
  common.py            carga de proyecto + config por defecto (formato, fps, `--aspect` para otra versión)
  new_project.py       crea projects/<id>/ a partir de un audio o video
  separate.py          Demucs: voz / instrumental
  transcribe.py        faster-whisper con timestamps por palabra (+ pasadas por ventanas)
  align.py             alineación forzada por palabra (MMS_FA) -> lyrics.json / .srt
  validate_sync.py     compara la alineación con Whisper
  beats.py             tempo, beats, downbeats, energía y bandas a 60 fps -> audio/beats.json
  script_to_src.py     historias: subtítulos desde el guion exacto + ventanas de tiempo
  story_timeline.py    historias: pausas entre partes, música en bucle con ducking -> audio/mix.wav, timeline.json
  render.py            fondo (escenas / video / vóxeles) + letra -> render/seg_*.mp4 -> out/<video>.mp4 (h264_nvenc + AAC)
  timing.py            pulso/energía compartidos
  scenes/              motivos 2D reutilizables (base.py = helpers y sprites, basic.py = motivos v1)
  voxel/               vóxeles 3D: vox.py (generador + horneado), structures.py (steampunk), gl.py (OpenGL), show.py, build.py
  tools/               local_settings.py (settings.local.json), machine.py (detección del equipo), binaries.py (claude/codex),
                       gen_image.py (imágenes), tts.py (voz)
  templates/prompt.md  plantilla de instrucciones por video
projects/<id>/
  prompt.md / solicitud.md   pedido de ESTE video
  config.json          audio, salida, formato, fps, fondo, subtítulos, colores...
  storyboard.json      secciones y escena por tramo
  scenes.py / voxscenes.py   (opcional) escenas propias de este video
  PROGRESO.md          pasos, supuestos y pendientes
  audio/ lyrics/ render/ out/   generados
  .app/                estado del trabajo en la app
```

```bash
source .venv/bin/activate
python engine/new_project.py mi_video ~/Descargas/audio.mp3     # también acepta un video (.mp4...)
# editar projects/mi_video/prompt.md y pedir a Claude: "revisa y ejecuta projects/mi_video/prompt.md"
```
Todos los comandos reciben el id del proyecto. Comunes a todos los tipos:
```bash
python engine/render.py mi_video --frame 30 60             # cuadros sueltos en render/
python engine/render.py mi_video --preview 50 70           # out/preview.mp4
python engine/render.py mi_video --force                   # video completo (sin --force reanuda segmentos)
python engine/render.py mi_video --aspect 16:9 --force     # otra versión de formato -> out/<nombre>_16x9.mp4
```

### Letra (canción) — con escenas o sobre el video fuente
```bash
python engine/separate.py mi_cancion
python engine/transcribe.py mi_cancion                       # idioma automático
python engine/transcribe.py mi_cancion --windows 0 200       # pasada extra por ventanas (opcional)
#   -> revisar y escribir lyrics/lyrics_src.json  {language, script, lines: [{win, text, rom, es}]}
python engine/align.py mi_cancion
python engine/beats.py mi_cancion
#   -> storyboard.json: sections [{start, kind}], blocks [{start, motif, cut_every?}]
#   fondo de video: "background": {"type": "video", "source": "clip.mp4", "dim": 0.6}
```

### Historia narrada (guion + narración + música)
```bash
python engine/transcribe.py mi_historia --lang es
python engine/script_to_src.py mi_historia historia.md
python engine/align.py mi_historia
python engine/story_timeline.py mi_historia        # config "story": parts, pause, intro, outro, music_gain_db, duck_db, crossfade, target_db
python engine/beats.py mi_historia                 # config "beats_audio": "audio/music_bed.wav"
#   -> storyboard.json con bloques {"para": n} o {"line": n} + parámetros propios; escenas en projects/<id>/scenes.py
```

### Explicación narrada (solo voz)
```bash
ffmpeg -i projects/mi_expl/audio.m4a -ac 1 -ar 24000 projects/mi_expl/audio/voice.wav   # config "voice": "audio/voice.wav"
python engine/transcribe.py mi_expl --lang es
#   -> corregir nombres propios, dividir en frases cortas: lyrics/lyrics_src.json
python engine/align.py mi_expl
python engine/beats.py mi_expl                      # solo para cortes suaves
#   -> storyboard.json por {"line": n}; scenes.py con un motivo explicativo por idea (cada elemento aparece al decirse)
```

### Herramientas de generación (las usa Claude si el trabajo las permite)
```bash
python engine/tools/gen_image.py mi_video "prompt detallado" --out assets/fondo.png --aspect 9:16 [--transparent] [--ref img.png]
python engine/tools/tts.py mi_video --file guion.txt --out audio/narracion.wav [--voice es-MX-JorgeNeural] [--rate -5%]
python engine/tools/machine.py [--force]      # datos del equipo guardados en settings.local.json
```

### Visualizador de vóxeles 3D
```bash
python engine/beats.py mi_tema                       # incluye bandas a 60 fps
#   -> projects/mi_tema/voxscenes.py: GRID, BUDGET, FOVY, FOVY_WIDE, SCENES = [{name, build(g), look{...}, cam(u)}]
#   -> storyboard.json: blocks [{start, motif}], accents, transition_beats, intro_assemble, outro_dissolve, fade_in, fade_out
python engine/voxel/build.py mi_tema --jobs 2        # config: "background": {"type": "voxels", "scenes": "voxscenes.py"}
```

## config.json (valores por defecto en `engine/common.py`)
- **Formato**: `aspect` ("9:16", "16:9"…) o `width`+`height`, `long_side` (1920), `fps` (número, "24000/1001" o "source").
  Sin ellos: aspecto/fps del video de fondo, o 9:16 a 30 fps.
- **Fondo**: `background` = `{"type": "scenes"}` (default) · `{"type": "video", "source", "dim"}` · `{"type": "voxels", "scenes"}`.
  `palette` sobrescribe colores con nombre de las escenas 2D (rose, pink, lilac, cream, gold, sky, hot, plum, deep).
- **Audio**: `audio` (también un video), `voice` (voz limpia aparte), `music`, `beats_audio`, `story`, `audio_bitrate`.
- **Letra / subtítulos**: `lyrics_mode` (auto | orig | orig+es | orig+rom+es), `caption_position` (center | bottom), `text_size`,
  `text_pulse`, `text_colors`, `font_bold` / `font_regular` / `font_index` (NotoSansCJK: 0 JP, 1 KR, 2 SC, 3 TC).
- **Render**: `fade_out`, `segment_seconds`, `jobs` (default: `machine.render_jobs`), `nvenc_cq` (calidad), `whisper_model`, `output`,
  `scene_canvas` (lienzo de las escenas 2D, p. ej. [540, 540] para 1:1). El codificador sale de `machine.video_encoder`.

## Escenas 2D
- `sc_<nombre>(t, lt, v, p, e, bt, blk)` devuelve un array RGB de 540x960 (lienzo vertical): `t` tiempo, `lt` tiempo en el corte,
  `v` variante, `p` pulso de beat, `e` energía, `bt` tiempo en el bloque, `blk` parámetros del bloque del storyboard.
  Todo `sc_*` de `engine/scenes/*.py` o de `projects/<id>/scenes.py` queda disponible como motivo en `storyboard.json`.
- Motivos v1: dream, world, screen, diary, box, chorus, petals, rain, childhood, home, book, door, heart, eyes, youth, thorns.
- Personajes desde imágenes: `cutout(path, size, tol, hue, sat, val)` + `put(ctx, key, x, y, h, ...)` en `engine/scenes/base.py`.
- Fuera de 9:16 la escena vertical se centra sobre una copia ampliada y desenfocada; para escenas nativas horizontales hay que
  escribir motivos pensados para ese lienzo (o usar vóxeles, que se adaptan a cualquier formato).
- Límite actual: gráficos 2D procedurales, sprites recortados y vóxeles 3D. Imágenes generadas por IA, metraje o modelos 3D externos
  requieren agregar herramientas nuevas.

# Videos con Claude

Un solo entorno (`.venv`) y un motor común (`engine/`); cada video vive en `projects/<nombre>/` con sus propias instrucciones.
Reglas generales y lecciones aprendidas: `CLAUDE.md`.

```
.venv/                 entorno compartido (uv, Python 3.11): torch+CUDA, demucs, faster-whisper, torchaudio (MMS_FA), librosa, pillow
engine/
  common.py            carga de proyecto + config por defecto
  new_project.py       crea projects/<nombre>/ a partir de un audio
  separate.py          Demucs: voz / instrumental
  transcribe.py        faster-whisper con timestamps por palabra (+ pasadas por ventanas)
  align.py             alineación forzada por palabra -> lyrics.json / .srt
  validate_sync.py     compara la alineación con Whisper
  beats.py             tempo, beats, downbeats, energía -> audio/beats.json
  script_to_src.py     historias: subtítulos desde el guion exacto + ventanas de tiempo
  story_timeline.py    historias: pausas entre partes, música en bucle con ducking -> audio/mix.wav, timeline.json
  render.py            escenas + letra karaoke -> render/seg_*.mp4 -> out/<video>.mp4 (h264_nvenc + AAC)
  timing.py            pulso/energía compartidos
  voxel/               visualizador 3D de vóxeles: vox.py (generador + horneado), structures.py (steampunk), gl.py (OpenGL),
                       show.py (tiempo/cámara/audio), build.py (caché de escenas)
  scenes/              librería de motivos reutilizables (base.py = helpers, basic.py = motivos v1)
  templates/prompt.md  plantilla de instrucciones por video
projects/<nombre>/
  prompt.md            instrucciones de ESTE video (editar la primera sección)
  config.json          audio, salida, formato, fps, modo de letra, fuentes, colores, paleta...
  storyboard.json      secciones y motivo visual por tramo
  scenes.py            (opcional) motivos exclusivos de este video
  PROGRESO.md          pasos hechos / pendientes
  audio/ lyrics/ render/ out/
```

## Instalación
```bash
uv venv .venv --python 3.11 && source .venv/bin/activate && uv pip install -r requirements.txt
```
Git versiona solo el motor base; `projects/`, `CLAUDE.md`, `.venv` y los medios quedan fuera (`.gitignore`).

## Nuevo video
```bash
source .venv/bin/activate
python engine/new_project.py mi_cancion ~/Descargas/mi_cancion.mp3     # también acepta un video (.mp4...)
# editar projects/mi_cancion/prompt.md y pedir a Claude: "revisa y ejecuta projects/mi_cancion/prompt.md"
```

## Flujo (todos los comandos reciben el nombre del proyecto)
```bash
python engine/separate.py mi_cancion
python engine/transcribe.py mi_cancion                       # idioma automático
python engine/transcribe.py mi_cancion --windows 0 200       # pasada extra por ventanas (opcional)
#   -> revisar a mano y escribir lyrics/lyrics_src.json
python engine/align.py mi_cancion
python engine/beats.py mi_cancion
#   -> escribir storyboard.json
python engine/render.py mi_cancion --frame 30 60             # fotogramas sueltos
python engine/render.py mi_cancion --preview 50 70           # out/preview.mp4
python engine/render.py mi_cancion --force                   # video completo (sin --force reanuda segmentos)
python engine/render.py mi_cancion --aspect 16:9 --force   # otra versión de formato -> out/<nombre>_16x9.mp4
```

## Historias narradas
```bash
python engine/transcribe.py mi_historia --lang es
python engine/script_to_src.py mi_historia historia.md
python engine/align.py mi_historia
python engine/story_timeline.py mi_historia        # config "story": parts, pause, intro, outro, music_gain_db, duck_db, crossfade, target_db
python engine/beats.py mi_historia                 # config "beats_audio": "audio/music_bed.wav"
#   -> storyboard.json con bloques {"para": n} o {"line": n} + parámetros propios; escenas en projects/<x>/scenes.py
python engine/render.py mi_historia --preview 50 70
```

## Visualizador de vóxeles 3D
```bash
python engine/beats.py mi_tema                       # incluye bandas a 60 fps
#   -> projects/mi_tema/voxscenes.py: GRID, BUDGET, FOVY, SCENES = [{name, build(g), look{...}, cam(u)}]
#   -> storyboard.json: blocks [{start, motif}], accents, transition_beats, intro_assemble, outro_dissolve, fade_in, fade_out
python engine/voxel/build.py mi_tema --jobs 2        # config: "background": {"type": "voxels", "scenes": "voxscenes.py"}
python engine/render.py mi_tema --preview 60 80
```

## config.json (valores por defecto en `engine/common.py`)
formato: `aspect` ("9:16", "16:9"...) o `width`+`height`, `long_side`, `fps` (número, "24000/1001" o "source");
sin ellos: aspecto/fps del video de fondo, o 9:16 a 30 fps · `background` (`{"type": "scenes"}` o
`{"type": "video", "source": "clip.mp4", "dim": 0.6}` = video fuente bajo cubierta negra, sin escenas) · `text_pulse` · `text_size` · `caption_position` (center | bottom) · `voice` (narración aparte) · `music` · `beats_audio` · `story` · `lyrics_mode` (auto | orig | orig+es | orig+rom+es) · `font_bold`/`font_regular`/`font_index`
(NotoSansCJK: 0 JP, 1 KR, 2 SC, 3 TC) · `text_colors` · `palette` (sobrescribe colores con nombre de las escenas: rose, pink, lilac, cream, gold, sky, hot, plum, deep)
· `fade_out` · `segment_seconds` · `jobs` · `nvenc_cq` · `audio_bitrate` · `whisper_model`.

## Escenas
- Función `sc_<nombre>(t, lt, v, p, e, bt, blk)` (blk = bloque del storyboard con parámetros propios) que devuelve un array RGB de 540x960 (lienzo vertical). Todo `sc_*` en `engine/scenes/*.py`
  o en `projects/<x>/scenes.py` queda disponible como motivo `<nombre>` en `storyboard.json`.
- Motivos v1: dream, world, screen, diary, box, chorus, petals, rain, childhood, home, book, door, heart, eyes, youth, thorns.
- Formatos no verticales (16:9, 1:1): la escena vertical se centra sobre una copia ampliada y desenfocada. Para escenas nativas
  horizontales habría que escribir motivos pensados para ese lienzo.
- Personajes desde imágenes: `cutout(path, size, tol, hue, sat, val)` + `put(ctx, key, x, y, h, ...)` en `engine/scenes/base.py`.
- Límite actual: gráficos 2D procedurales + sprites recortados. Imágenes IA, metraje, fotos o 3D requieren agregar herramientas/escenas nuevas.

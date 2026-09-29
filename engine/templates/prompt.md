# Prompt: video con letra sincronizada — {name}

## Instrucciones propias de este video
<!-- Edita esta sección para cada video. Lo que digas aquí manda sobre las reglas generales de abajo. -->
- Audio: `{audio}`
- Formato: automático (9:16; si hay video, el del video). Para forzar otro: `aspect` en `config.json`
- Fondo: escenas procedurales | video fuente con cubierta negra (`background` en `config.json`)
- Estilo visual / paleta: (p. ej. "neón oscuro", "acuarela pastel", "retro VHS")
- Idea / historia de las escenas: (opcional)
- Modo de letra: auto  (auto | orig | orig+es | orig+rom+es)
- Otros: (duración de la vista previa, secciones a destacar, cosas a evitar...)

## Entorno y motor
- Reglas generales y lecciones: `../../CLAUDE.md`. Usa el entorno compartido `../../.venv` y el motor `../../engine/` (ver `../../README.md`). No dupliques scripts por proyecto:
  si algo falta, mejora el motor de forma genérica o agrega motivos en `engine/scenes/` (reutilizables) o en `scenes.py` de este proyecto (solo para este video).
- Guarda todo en esta carpeta y mantén `PROGRESO.md` actualizado (léelo antes de empezar y continúa desde donde se quedó).

## Reglas generales
1. Separar voz (`engine/separate.py`), transcribir con timestamps por palabra (`engine/transcribe.py`, pasadas extra con `--windows`),
   detectar idioma y escritura.
2. Revisar la transcripción: corregir errores, eliminar alucinaciones en instrumentales, dividir en líneas naturales.
   Escribir `lyrics/lyrics_src.json` (texto, romanización si no es escritura latina, traducción natural al español, ventana de tiempo).
3. Alinear (`engine/align.py`) y validar: cada línea aparece al empezar a cantarse y desaparece al terminar (±100 ms). Sin letra en instrumentales.
4. Analizar beats y secciones (`engine/beats.py`) y escribir `storyboard.json` (secciones + motivos por tramo según la letra).
5. Escenas acordes a la letra; cortes ~cada 2 s siempre en beat/downbeat; cambios más marcados al inicio de sección; animación que reacciona al ritmo y energía; paleta coherente.
6. Letra centrada horizontal y verticalmente, legible (contorno/sombra/panel), efectos según el momento (karaoke, glow, escala en beat), fuente que soporte la escritura. Sin título ni créditos.
   - Español: solo original. Inglés: original + traducción al español. Otra escritura: original + romanización + traducción.
7. Render: primero vista previa corta (`--preview`) y revisarla; luego completo por segmentos (`engine/render.py`). H.264 + AAC con el audio original.
8. Verificar fotogramas (inicio, verso, coro, final), duración igual al audio y sin desfase. Resultado en `out/`.

# Video — {name}

## Pedido
<!-- Lo que pidió el usuario, tal cual, y lo que se entendió. Lo que diga aquí manda sobre las reglas generales. -->
- Archivos: `{audio}`
- Pedido:
- Tipo de proyecto (ver tabla en `../../CLAUDE.md`): letra + escenas 2D | letra sobre video fuente | historia con guion |
  explicación narrada | visualizador de vóxeles 3D
- Formato: 9:16 por defecto (si hay video fuente, el del video; si la app dejó `aspect` en `config.json`, ese)
- Estilo visual / paleta:
- Idea de las escenas:
- Subtítulos / letra: auto (canción: según idioma; narración: abajo, solo original; instrumental: ninguno)
- Otros (vista previa, secciones a destacar, cosas a evitar):

## Cómo trabajar
- Reglas generales, flujo de cada tipo y lecciones: `../../CLAUDE.md`. Comandos: `../../README.md`.
- Entorno compartido `../../.venv`, motor `../../engine/`. No dupliques scripts: si algo falta, mejora el motor de forma genérica,
  agrega motivos reutilizables en `engine/scenes/` o propios de este video en `scenes.py` / `voxscenes.py`.
- Todo en esta carpeta. Mantén `PROGRESO.md` al día (supuestos, pasos, comandos, lo que conviene revisar a oído).
- Siempre: revisar cuadros (`--frame`) -> vista previa (`--preview`) -> render completo por segmentos -> verificar
  (cuadros en varias partes, duración igual al audio, sin desfase). Resultado en `out/`.

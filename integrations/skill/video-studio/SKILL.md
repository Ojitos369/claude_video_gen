---
name: video-studio
description: Crea videos, animaciones explicativas, páginas HTML y modelos 3D (Blender) con la app local Video Studio. Úsalo cuando el usuario pida un video/animación/explicación animada/modelo 3D, sobre todo si debe basarse en el proyecto actual (arquitectura, flujo, demo, changelog, release).
---

# Video Studio (vía MCP `video-studio`)

Herramientas MCP: `video_studio_create`, `video_studio_status`, `video_studio_result`, `video_studio_reply`, `video_studio_list`, `video_studio_cancel`.
Si no existen en tu lista de herramientas, el MCP no está registrado: ver `integrations/README.md` del repo de Video Studio.

## Flujo
1. **Define el pedido** con lo que sabes del proyecto actual: qué explicar, público, duración, idioma, estilo, formato (9:16 por defecto; 16:9 para
   presentaciones). Mejor poco y claro que largo. No pegues secretos ni `.env`.
2. `video_studio_create` con `prompt`, y para basarlo en este proyecto `context_dir` = ruta absoluta de la raíz del proyecto (solo lectura; el servicio
   lo lee solo) y `context_note` = qué partes importan (p. ej. "explica el flujo de autenticación en `src/auth/`"). Sube con `files` lo que no esté
   en disco del proyecto (guion, audio, logos). `deliverables`: `["video"]`, `["video","html"]` o `["modelo3d"]`.
3. Devuelve el `job_id` al usuario y **espera sin bloquearte**: `video_studio_status` con `wait_seconds` (hasta 540) hasta `done`. Un video tarda
   de 5 a 40 min según duración y formato. `error`/`cancelled` → informa el motivo.
4. `video_studio_result` con `copy_to` = una carpeta del proyecto actual (p. ej. `<proyecto>/video-out`) para recibir el .mp4 / .html / modelo allí.
   Entrega al usuario las rutas y el `final_message` (incluye lo que conviene revisar a oído).
5. Cambios: `video_studio_reply` con el texto (misma sesión, solo cambia lo necesario); luego otra vez status → result.

## Modelos 3D (Blender)
- Pide `tools: {"models": true}` (o `deliverables: ["modelo3d"]`). Salen `.glb` (+ vistas previas PNG y giro 360° opcional).

## Preguntas (todo tipo de trabajo)

  (`id`, `texto`, `opciones`, `multiple`). Muéstraselas al usuario como opción múltiple **o respuesta propia** (siempre permitida; no las contestes
  tú salvo carta blanca) y envía `video_studio_reply` con `answers: {id: "opción" | ["opciones"] | "texto propio"}`; luego status → result.
- `ask_questions: false` → decide solo. Sin indicación: usa `true` para trabajos nuevos con pedido vago y `false` si el usuario dice "automático" / "sin preguntas".
- Las preguntas son de contenido, estilo o forma, nunca de procesos técnicos.

## Reglas
- No inventes datos del proyecto: el servicio los lee de `context_dir`; tu `prompt` solo orienta.
- Las generaciones de imagen/voz/música consumen cuota: actívalas en `tools` solo si el usuario las pidió o son claramente necesarias.
- No arranques ni detengas Video Studio a mano: el MCP lo levanta solo (ver `VIDEO_STUDIO_URL` si corre en otra máquina).

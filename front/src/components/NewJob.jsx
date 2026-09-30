import { useEffect, useRef, useState } from 'react'
import { api, fmtSize } from '../api.js'
import { Upload, X, Send, FileText, Film } from './Icons.jsx'
import ModelSelect from './ModelSelect.jsx'
import AspectSelect from './AspectSelect.jsx'

const EXAMPLES = [
  'Video con la letra sincronizada de esta canción, escenas que sigan la letra, formato 9:16.',
  'Usa el video subido como fondo con una cubierta negra y encima la letra, sin animación extra.',
  'Anima esta historia con los personajes adjuntos; pausa con difuminado entre partes.',
  'Visualizador de vóxeles 3D estilo steampunk que se arme y desarme al ritmo de la música.',
]

const isImage = (f) => f.type.startsWith('image') || /\.(png|jpe?g|webp|gif|bmp|tiff?)$/i.test(f.name)
const isVideo = (f) => f.type.startsWith('video') || /\.(mp4|mov|webm|mkv|m4v|avi)$/i.test(f.name)

// frame size of a local video / image (null when the browser cannot decode it; the backend measures it anyway)
const probe = (file) => new Promise((resolve) => {
  const url = URL.createObjectURL(file)
  const done = (r) => { URL.revokeObjectURL(url); resolve(r) }
  setTimeout(() => done(null), 5000)
  if (isImage(file)) {
    const im = new Image()
    im.onload = () => done({ w: im.naturalWidth, h: im.naturalHeight })
    im.onerror = () => done(null)
    im.src = url
    return
  }
  const v = document.createElement('video')
  v.preload = 'metadata'
  v.onloadedmetadata = () => done(v.videoWidth ? { w: v.videoWidth, h: v.videoHeight } : null)
  v.onerror = () => done(null)
  v.src = url
})

const kind = (f) => (f.type.startsWith('audio') ? 'audio' : f.type.startsWith('video') ? 'video' : f.type.startsWith('image') ? 'imagen' : 'archivo')

export default function NewJob({ status, settings, onCreated }) {
  const [files, setFiles] = useState([])
  const [prompt, setPrompt] = useState('')
  const [name, setName] = useState('')
  const [model, setModel] = useState('')
  const [aspect, setAspect] = useState('9:16')
  const [aspectText, setAspectText] = useState('')
  const [tools, setTools] = useState(null)                 // null = defaults from the settings
  const gen = tools || settings?.generation || { images: true, tts: false, music: false }
  const imgProv = settings?.images?.provider || 'none', ttsProv = settings?.tts?.provider || 'none', musProv = settings?.music?.provider || 'none'
  const [aspectAuto, setAspectAuto] = useState(true)   // follows the uploaded video until the user picks one
  const [dims, setDims] = useState({})                 // file key -> {w, h}
  const key = (f) => `${f.name}:${f.size}`
  const videos = files.filter(isVideo).map((f) => ({ name: f.name, ...(dims[key(f)] || {}) }))
  const images = files.filter(isImage).map((f) => ({ name: f.name, ...(dims[key(f)] || {}) }))

  useEffect(() => {
    files.filter((f) => isVideo(f) || isImage(f)).forEach((f) => {
      if (dims[key(f)] !== undefined) return
      setDims((d) => ({ ...d, [key(f)]: {} }))
      probe(f).then((r) => setDims((d) => ({ ...d, [key(f)]: r || {} })))
    })
    if (aspectAuto) setAspect(videos.length ? `video:${videos[0].name}` : '9:16')
    else if ((aspect.startsWith('video:') || aspect.startsWith('image:')) && ![...videos.map((v) => `video:${v.name}`), ...images.map((v) => `image:${v.name}`)].includes(aspect)) { setAspect('9:16'); setAspectAuto(true) }
  }, [files]) // eslint-disable-line
  const chosen = model || status?.model || ''
  const [effort, setEffort] = useState('')
  const chosenEffort = effort || status?.effort || 'high'
  const [drag, setDrag] = useState(false)
  const [progress, setProgress] = useState(null)
  const [error, setError] = useState('')
  const input = useRef(null)
  const depth = useRef(0)

  const add = (list) => {
    const incoming = Array.from(list || [])
    setFiles((fs) => [...fs, ...incoming.filter((f) => !fs.some((g) => g.name === f.name && g.size === f.size))])
  }
  const total = files.reduce((s, f) => s + f.size, 0)
  const busy = progress !== null
  const ready = prompt.trim() && !busy && !status?.offline && (aspect !== 'manual' || aspectText.trim())

  const submit = async (e) => {
    e?.preventDefault()
    if (!ready) return
    setError(''); setProgress(0)
    try {
      const job = await api.create({ prompt: prompt.trim(), name: name.trim(), model: chosen, effort: chosenEffort, aspect, aspectText: aspectText.trim(), tools: gen, files }, setProgress)
      onCreated(job)
    } catch (err) {
      setError(err.message); setProgress(null)
    }
  }

  return (
    <form className="new-job" onSubmit={submit}
      onDragEnter={(e) => { e.preventDefault(); depth.current++; setDrag(true) }}
      onDragOver={(e) => e.preventDefault()}
      onDragLeave={() => { depth.current = Math.max(0, depth.current - 1); if (!depth.current) setDrag(false) }}
      onDrop={(e) => { e.preventDefault(); depth.current = 0; setDrag(false); add(e.dataTransfer.files) }}>
      <header className="page-head">
        <h1>Nuevo video</h1>
        <p>Sube los archivos de contexto y describe el video. Claude arma el proyecto, lo renderiza y te muestra el resultado.</p>
      </header>

      {status && !status.offline && !status.claude && (
        <div className="notice notice-bad">No se encontró el comando <code>claude</code> en el servidor. Instala Claude Code o define <code>CLAUDE_BIN</code>.</div>
      )}

      <div className={`dropzone ${drag ? 'is-drag' : ''} ${files.length ? 'has-files' : ''}`}
        onClick={() => input.current?.click()} role="button" tabIndex={0}
        onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && input.current?.click()}>
        <input ref={input} type="file" multiple hidden onChange={(e) => { add(e.target.files); e.target.value = '' }} />
        <span className="dz-icon"><Upload /></span>
        <strong>{drag ? 'Suelta los archivos aquí' : 'Arrastra archivos o haz clic para elegir'}</strong>
        <span className="muted">Audio, video, imágenes, guiones, referencias… se guardan en la carpeta del proyecto</span>
      </div>

      {files.length > 0 && (
        <ul className="file-chips">
          {files.map((f, i) => (
            <li key={f.name + f.size} className="chip">
              <span className="chip-icon">{kind(f) === 'video' || kind(f) === 'audio' ? <Film /> : <FileText />}</span>
              <span className="chip-name" title={f.name}>{f.name}</span>
              <span className="muted">{fmtSize(f.size)}</span>
              <button type="button" className="icon-btn" aria-label={`Quitar ${f.name}`} disabled={busy}
                onClick={() => setFiles((fs) => fs.filter((_, j) => j !== i))}><X /></button>
            </li>
          ))}
          <li className="chip-total muted">{files.length} archivo{files.length > 1 ? 's' : ''} · {fmtSize(total)}</li>
        </ul>
      )}

      <label className="field">
        <span>¿Qué video quieres?</span>
        <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={6} disabled={busy}
          placeholder="Describe el video: estilo, formato, qué debe mostrar, idioma de la letra, duración de la vista previa…"
          onKeyDown={(e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) submit(e) }} />
      </label>
      <div className="examples">
        {EXAMPLES.map((ex) => <button type="button" key={ex} className="example" onClick={() => setPrompt(ex)} disabled={busy}>{ex}</button>)}
      </div>

      <div className="form-row">
        <label className="field grow">
          <span>Nombre del proyecto <em>(opcional)</em></span>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="se genera a partir de la descripción" disabled={busy} />
        </label>
        <AspectSelect value={aspect} videos={videos} images={images} disabled={busy} onChange={(v) => { setAspect(v); setAspectAuto(false) }} />
        <ModelSelect models={status?.models} value={chosen} onChange={setModel} disabled={busy} />
        <ModelSelect models={status?.efforts} value={chosenEffort} onChange={setEffort} disabled={busy} label="Esfuerzo" aria="Esfuerzo de Claude" />
      </div>
      {aspect === 'manual' && (
        <label className="field manual-aspect">
          <span>Describe el formato <em>(Claude elige la proporción y la resolución)</em></span>
          <input value={aspectText} onChange={(e) => setAspectText(e.target.value)} disabled={busy} autoFocus
            placeholder="p. ej. que se vea en un monitor curvo de 72 pulgadas · pantalla vertical de un kiosko · historia de Instagram" />
        </label>
      )}
      <fieldset className="tools">
        <legend>Herramientas que Claude puede usar</legend>
        {[['images', 'Generar imágenes', imgProv, settings?.catalog?.images], ['tts', 'Generar voz', ttsProv, settings?.catalog?.tts], ['music', 'Generar música', musProv, settings?.catalog?.music]].map(([k, label, prov, cat]) => (
          <label key={k} className={`toggle ${prov === 'none' ? 'is-disabled' : ''}`}>
            <input type="checkbox" checked={!!gen[k] && prov !== 'none'} disabled={busy || prov === 'none'}
              onChange={(e) => setTools({ ...gen, [k]: e.target.checked })} />
            <span className="toggle-ui" aria-hidden="true" />
            <span className="toggle-text"><span>{label}</span>
              <small className="muted">{prov === 'none' ? <>sin proveedor · <a href="#/settings">configurar</a></> : cat?.[prov]?.label}</small></span>
          </label>
        ))}
      </fieldset>
      <div className="form-actions">
        <button className="btn btn-primary btn-lg" type="submit" disabled={!ready}>
          <Send /> {busy ? (progress < 1 ? `Subiendo ${Math.round(progress * 100)}%` : 'Creando…') : 'Crear video'}
        </button>
      </div>
      {busy && <div className="upload-bar"><i style={{ width: `${Math.round(progress * 100)}%` }} /></div>}
      {error && <div className="notice notice-bad">{error}</div>}
      <p className="hint muted">Ctrl + Enter para enviar. Los trabajos se ejecutan de uno en uno porque comparten la GPU.</p>
      {drag && <div className="drop-overlay"><Upload /> Suelta para agregar</div>}
    </form>
  )
}

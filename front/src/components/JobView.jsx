import { useEffect, useRef, useState, useMemo } from 'react'
import { api, openSocket, fmtCost, fmtDur, fmtSize } from '../api.js'
import Timeline, { buildItems } from './Timeline.jsx'
import Results from './Results.jsx'
import Markdown from './Markdown.jsx'
import StatusBadge from './StatusBadge.jsx'
import { Send, Stop, Trash, Film, FileText, List, Pencil, Check, X } from './Icons.jsx'
import ModelSelect, { modelLabel } from './ModelSelect.jsx'

const ACTIVE = ['running', 'queued']

export default function JobView({ id, models, efforts, onDeleted }) {
  const [job, setJob] = useState(null)
  const [events, setEvents] = useState([])
  const [progress, setProgress] = useState('')
  const [tab, setTab] = useState('result')
  const [mtab, setMtab] = useState('feed')   // phone: one panel at a time
  const [text, setText] = useState('')
  const [model, setModel] = useState('')
  const [effort, setEffort] = useState('')
  const [editing, setEditing] = useState(false)
  const [newName, setNewName] = useState('')
  const [error, setError] = useState('')
  const [now, setNow] = useState(Date.now())
  const scroller = useRef(null)
  const stick = useRef(true)
  const lastI = useRef(-1)

  const addEvents = (list) => setEvents((evs) => {
    const fresh = list.filter((e) => e.i > lastI.current)
    if (!fresh.length) return evs
    lastI.current = fresh[fresh.length - 1].i
    return [...evs, ...fresh]
  })
  const reload = () => api.job(id).then((j) => { setJob(j); setProgress(j.progress || '') }).catch((e) => setError(e.message))

  useEffect(() => {
    lastI.current = -1
    setEvents([]); setJob(null)
    reload()
    const close = openSocket(id, (msg) => {
      if (msg.type === 'event') {
        addEvents([msg.event])
        const k = msg.event.kind
        if (k === 'status' || k === 'outputs' || k === 'result') reload()
        if (k === 'tool') setJob((j) => j && { ...j, step: `${msg.event.name}: ${msg.event.summary}` })
      } else if (msg.type === 'progress') setProgress(msg.text)
      else if (msg.type === 'renamed') setJob((j) => j && { ...j, name: msg.name })
    }, () => api.events(id, lastI.current + 1).then(addEvents).catch(() => {}))   // (re)connected: fill the gap
    return close
  }, [id]) // eslint-disable-line

  const running = job && ACTIVE.includes(job.status)
  useEffect(() => {
    if (!running) return
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [running])

  const items = useMemo(() => buildItems(events), [events])
  useEffect(() => {   // follow the live feed unless the user scrolled up
    const el = scroller.current
    if (el && stick.current) el.scrollTop = el.scrollHeight
  }, [items])
  useEffect(() => { if (job?.outputs?.length && job.status === 'done') { setTab('result'); setMtab('result') } }, [job?.status]) // eslint-disable-line

  if (error && !job) return <div className="job-view"><div className="notice notice-bad">{error}</div></div>
  if (!job) return <div className="job-view loading"><span className="spinner" /> Cargando…</div>

  const runs = job.runs || []
  const lastRun = runs[runs.length - 1]
  const started = running ? (events.filter((e) => e.kind === 'status' && e.status === 'running').pop()?.t) : null
  const elapsed = started ? (now / 1000 - started) : null
  const totalMs = runs.reduce((s, r) => s + (r.duration_ms || 0), 0)

  const send = async (e) => {
    e.preventDefault()
    if (!text.trim()) return
    setError('')
    try { await api.message(id, text.trim(), model || job.model, effort || job.effort); setText(''); reload() } catch (err) { setError(err.message) }
  }
  const saveName = async (e) => {
    e?.preventDefault()
    const n = newName.trim()
    if (!n || n === job.name) { setEditing(false); return }
    try { await api.rename(id, n); setJob((j) => ({ ...j, name: n })); setEditing(false) } catch (err) { setError(err.message) }
  }
  const cancel = async () => { try { await api.cancel(id); reload() } catch (err) { setError(err.message) } }
  const remove = async () => {
    if (!window.confirm(`¿Borrar el proyecto "${job.name}" y todos sus archivos?`)) return
    try { await api.remove(id); onDeleted() } catch (err) { setError(err.message) }
  }

  return (
    <div className="job-view">
      <header className="job-head">
        <div className="job-title">
          {editing ? (
            <form className="rename" onSubmit={saveName}>
              <input value={newName} onChange={(e) => setNewName(e.target.value)} autoFocus maxLength={120} aria-label="Nuevo nombre"
                onKeyDown={(e) => e.key === 'Escape' && setEditing(false)} />
              <button className="icon-btn" type="submit" aria-label="Guardar nombre"><Check /></button>
              <button className="icon-btn" type="button" aria-label="Cancelar" onClick={() => setEditing(false)}><X /></button>
            </form>
          ) : (
            <h1>{job.name || job.id}
              <button className="icon-btn rename-btn" aria-label="Renombrar" title="Renombrar (la carpeta del proyecto no cambia)"
                onClick={() => { setNewName(job.name || job.id); setEditing(true) }}><Pencil /></button>
            </h1>
          )}
          <div className="job-meta">
            <StatusBadge status={job.status} />
            <code>projects/{job.id}</code>
            {job.model && <span className="pill">{modelLabel(models, job.model)}{job.effort ? ` · esfuerzo ${modelLabel(efforts, job.effort).toLowerCase()}` : ''}</span>}
            {job.aspect && <span className="pill" title={job.aspect_label || ''}>{
              job.aspect === 'manual' ? `Formato manual${job.format ? ` → ${job.format}` : ''}`
                : /^(del video|de la imagen)/.test(job.aspect_label || '') ? `${job.aspect.replace(':', 'x')} (${job.aspect_label.startsWith('del') ? 'del video' : 'de la imagen'})`
                  : job.aspect}</span>}
            {running && elapsed != null && <span>{fmtDur(elapsed)}</span>}
            {!running && totalMs > 0 && <span>{fmtDur(totalMs / 1000)} de trabajo</span>}
            {job.cost > 0 && <span>{fmtCost(job.cost)}</span>}
          </div>
        </div>
        <div className="job-actions">
          {running && <button className="btn btn-ghost" onClick={cancel}><Stop /> Cancelar</button>}
          {!running && <button className="btn btn-ghost btn-danger" onClick={remove}><Trash /> Borrar</button>}
        </div>
      </header>

      {running && (
        <div className="live-step">
          <span className="spinner" />
          <span className="live-label">{job.status === 'queued' ? 'En cola, esperando a que termine el trabajo anterior…' : job.step || 'Trabajando…'}</span>
        </div>
      )}
      {job.status === 'error' && job.error && <div className="notice notice-bad">{job.error}</div>}
      {job.status === 'interrupted' && <div className="notice notice-warn">{job.error} Escribe abajo “continúa” para retomarlo.</div>}

      <nav className="mtabs" role="tablist" aria-label="Secciones del trabajo">
        {[['feed', 'Proceso'], ['result', `Resultado${job.outputs?.length ? ` (${job.outputs.length})` : ''}`], ['progress', 'Progreso'], ['files', 'Archivos']].map(([k, label]) => (
          <button key={k} role="tab" aria-selected={mtab === k} className={mtab === k ? 'is-active' : ''}
            onClick={() => { setMtab(k); if (k !== 'feed') setTab(k) }}>{label}</button>
        ))}
      </nav>
      <div className="job-grid" data-m={mtab}>
        <section className="panel panel-feed">
          <div className="panel-head"><h2>Proceso</h2><span className="muted">{items.filter((i) => i.type === 'tool').length} pasos</span></div>
          <div className="feed" ref={scroller} onScroll={(e) => {
            const el = e.currentTarget
            stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80
          }}>
            <Timeline items={items} live={running} models={models} efforts={efforts} />
            {running && <div className="typing"><span /><span /><span /></div>}
          </div>
          <form className="composer" onSubmit={send}>
            <textarea value={text} onChange={(e) => setText(e.target.value)} rows={2} disabled={running}
              placeholder={running ? 'Espera a que termine para pedir cambios…' : 'Pide cambios o da más instrucciones (continúa la misma sesión)…'}
              onKeyDown={(e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) send(e) }} />
            <div className="composer-side">
              <ModelSelect compact models={models} value={model || job.model} onChange={setModel} disabled={running} />
              <ModelSelect compact models={efforts} value={effort || job.effort} onChange={setEffort} disabled={running} label="Esfuerzo" aria="Esfuerzo de Claude" />
              <button className="btn btn-primary" disabled={running || !text.trim()} aria-label="Enviar"><Send /></button>
            </div>
          </form>
          {error && <div className="notice notice-bad">{error}</div>}
        </section>

        <section className="panel panel-side">
          <div className="tabs" role="tablist">
            <button role="tab" aria-selected={tab === 'result'} className={tab === 'result' ? 'is-active' : ''} onClick={() => setTab('result')}><Film /> Resultado{job.outputs?.length ? ` (${job.outputs.length})` : ''}</button>
            <button role="tab" aria-selected={tab === 'progress'} className={tab === 'progress' ? 'is-active' : ''} onClick={() => setTab('progress')}><List /> Progreso</button>
            <button role="tab" aria-selected={tab === 'files'} className={tab === 'files' ? 'is-active' : ''} onClick={() => setTab('files')}><FileText /> Archivos</button>
          </div>
          <div className="tab-body">
            {tab === 'result' && <Results id={id} outputs={job.outputs || []} running={running} />}
            {tab === 'progress' && (progress ? <Markdown text={progress} className="progress-md" /> : <p className="muted">Claude aún no escribe PROGRESO.md.</p>)}
            {tab === 'files' && (
              <ul className="file-tree">
                {(job.files || []).map((f) => (
                  <li key={f.name}>
                    <span className="ft-name">{f.dir ? <List /> : f.name.match(/\.(mp4|mov|webm|mkv|mp3|wav|m4a|flac)$/i) ? <Film /> : <FileText />} {f.name}{f.dir ? '/' : ''}</span>
                    {!f.dir && <a className="muted" href={api.fileUrl(id, f.name)} target="_blank" rel="noreferrer">{fmtSize(f.size)}</a>}
                  </li>
                ))}
              </ul>
            )}
          </div>
          <details className="prompt-box">
            <summary>Instrucciones originales</summary>
            <p className="pre">{job.prompt}</p>
            {lastRun && <p className="muted">Última ejecución: {lastRun.started?.replace('T', ' ')} · {lastRun.status}</p>}
          </details>
        </section>
      </div>
    </div>
  )
}

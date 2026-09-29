import { useState } from 'react'
import Markdown from './Markdown.jsx'
import { toolIcon, Chevron, Check, Alert, Bot, User, Film, Spark } from './Icons.jsx'
import { fmtCost, fmtDur, STATUS } from '../api.js'
import { modelLabel } from './ModelSelect.jsx'

const time = (t) => new Date(t * 1000).toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit', second: '2-digit' })

// merge tool calls with their results so each step is one row
export function buildItems(events) {
  const items = [], byId = {}
  let lastOut = ''
  for (const ev of events) {
    if (ev.kind === 'outputs') {   // only when the set of files changes
      const sig = (ev.files || []).map((f) => `${f.path}:${f.size}`).join('|')
      if (sig === lastOut) continue
      const names = (ev.files || []).map((f) => f.path).join('|')
      if (names === lastOut.split('|').map((x) => x.split(':')[0]).join('|')) { lastOut = sig; continue }
      lastOut = sig
    }
    if (ev.kind === 'tool') {
      const it = { ...ev, type: 'tool', result: null }
      byId[ev.id] = it; items.push(it)
    } else if (ev.kind === 'tool_result' && byId[ev.id]) {
      byId[ev.id].result = ev
    } else if (ev.kind === 'status' && !['running', 'queued'].includes(ev.status) && ev.status !== 'done') {
      items.push({ ...ev, type: 'status' })
    } else if (['user', 'text', 'result', 'error', 'system', 'outputs'].includes(ev.kind)) {
      if (ev.kind === 'outputs' && !(ev.files || []).length) continue
      items.push({ ...ev, type: ev.kind })
    }
  }
  return items
}

function ToolRow({ it, live }) {
  const [open, setOpen] = useState(false)
  const pending = !it.result
  const ok = it.result?.ok !== false
  const dur = it.result ? it.result.t - it.t : null
  return (
    <li className={`tl tl-tool ${pending ? (live ? 'is-pending' : 'is-stale') : ok ? 'is-ok' : 'is-bad'}`}>
      <button className="tl-head" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className="tl-icon">{toolIcon(it.name)}</span>
        <span className="tl-tool-name">{it.name}</span>
        <span className="tl-summary" title={it.summary}>{it.summary}</span>
        <span className="tl-meta">
          {pending ? (live ? <span className="spinner" /> : null) : ok ? <Check /> : <Alert />}
          {dur != null && dur >= 1 && <span>{fmtDur(dur)}</span>}
          <Chevron open={open} />
        </span>
      </button>
      {open && (
        <div className="tl-body">
          <pre className="code">{it.input}</pre>
          {it.result && <pre className={`code ${ok ? '' : 'code-bad'}`}>{it.result.text || '(sin salida)'}</pre>}
        </div>
      )}
    </li>
  )
}

export default function Timeline({ items, live, models, efforts }) {
  return (
    <ol className="timeline">
      {items.map((it) => {
        const key = it.i
        switch (it.type) {
          case 'tool': return <ToolRow key={key} it={it} live={live} />
          case 'user': return (
            <li key={key} className="tl tl-user">
              <span className="tl-icon"><User /></span>
              <div className="tl-content"><div className="tl-label">Tú · {time(it.t)}{it.model ? ` · ${modelLabel(models, it.model)}` : ''}{it.effort ? ` · esfuerzo ${modelLabel(efforts, it.effort).toLowerCase()}` : ''}</div><p className="pre">{it.text}</p>
                {it.files?.length > 0 && <div className="tl-files">{it.files.map((f) => <span key={f} className="pill">{f}</span>)}</div>}</div>
            </li>)
          case 'text': return (
            <li key={key} className="tl tl-text">
              <span className="tl-icon"><Bot /></span>
              <div className="tl-content"><div className="tl-label">Claude · {time(it.t)}</div><Markdown text={it.text} /></div>
            </li>)
          case 'system': return <li key={key} className="tl tl-system"><span className="tl-icon"><Spark /></span><span>{it.text}</span><span className="muted">{time(it.t)}</span></li>
          case 'outputs': return (
            <li key={key} className="tl tl-system tl-out"><span className="tl-icon"><Film /></span>
              <span>Archivos en <code>out/</code>: {it.files.map((f) => f.name).join(', ')}</span></li>)
          case 'result': return (
            <li key={key} className={`tl tl-result ${it.ok ? '' : 'is-bad'}`}>
              <span className="tl-icon">{it.ok ? <Check /> : <Alert />}</span>
              <div className="tl-content">
                <div className="tl-label">{it.ok ? 'Paso terminado' : 'Terminó con error'} · {fmtDur(it.duration_ms / 1000)} · {it.turns} turnos · {fmtCost(it.cost)}</div>
              </div>
            </li>)
          case 'error': return <li key={key} className="tl tl-error"><span className="tl-icon"><Alert /></span><pre className="pre">{it.text}</pre></li>
          case 'status': return <li key={key} className="tl tl-system"><span className="tl-icon"><Alert /></span><span>{STATUS[it.status]?.label || it.status}{it.error ? `: ${it.error}` : ''}</span></li>
          default: return null
        }
      })}
    </ol>
  )
}

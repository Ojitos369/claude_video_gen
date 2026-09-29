import { Plus, Film, Gear } from './Icons.jsx'
import StatusBadge from './StatusBadge.jsx'
import { fmtCost } from '../api.js'

const ago = (iso) => {
  if (!iso) return ''
  const s = (Date.now() - new Date(iso).getTime()) / 1000
  if (s < 60) return 'hace un momento'
  if (s < 3600) return `hace ${Math.floor(s / 60)} min`
  if (s < 86400) return `hace ${Math.floor(s / 3600)} h`
  return new Date(iso).toLocaleDateString('es', { day: 'numeric', month: 'short' })
}

export default function Sidebar({ jobs, current, view, onOpen, status }) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <span className="brand-mark"><Film /></span>
        <div>
          <strong>Video Studio</strong>
          <small>Claude · generador de videos</small>
        </div>
      </div>
      <button className={`btn btn-primary new-btn ${view === 'new' ? 'is-active' : ''}`} onClick={() => onOpen(null)}>
        <Plus /> Nuevo video
      </button>
      <div className="side-label">Trabajos</div>
      <nav className="job-list">
        {jobs.length === 0 && <p className="empty-side">Aún no hay trabajos. Crea el primero.</p>}
        {jobs.map((j) => (
          <button key={j.id} className={`job-item ${current === j.id ? 'is-active' : ''}`} onClick={() => onOpen(j.id)}>
            <div className="job-item-top">
              <span className="job-name">{j.name || j.id}</span>
              <StatusBadge status={j.status} small />
            </div>
            <div className="job-item-sub">
              {j.status === 'running' ? <span className="step">{j.step}</span> : <span>{ago(j.updated || j.created)}</span>}
              {j.outputs > 0 && <span className="pill">{j.outputs} archivo{j.outputs > 1 ? 's' : ''}</span>}
              {j.cost > 0 && <span className="muted">{fmtCost(j.cost)}</span>}
            </div>
          </button>
        ))}
      </nav>
      <a className={`side-link ${view === 'settings' ? 'is-active' : ''}`} href="#/settings"><Gear /> Ajustes</a>
      <footer className="env">
        {status?.offline ? <span className="env-bad">Servidor desconectado</span> : status && (
          <>
            <span className={status.claude ? 'env-ok' : 'env-bad'}>{status.claude ? status.claude_version.split(' ')[0] : 'claude no encontrado'}</span>
            <span>{status.model}</span>
            {status.gpu && <span title={status.gpu}>{status.gpu.replace('NVIDIA GeForce ', '')}</span>}
          </>
        )}
      </footer>
    </aside>
  )
}

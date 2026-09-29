import { useEffect, useState, useCallback } from 'react'
import { api, openSocket, settingsApi, applyTheme } from './api.js'
import Sidebar from './components/Sidebar.jsx'
import NewJob from './components/NewJob.jsx'
import JobView from './components/JobView.jsx'
import Settings from './components/Settings.jsx'
import { Menu, Film } from './components/Icons.jsx'

// hash routing: #/ (new video) · #/job/<id> · #/settings
const route = () => {
  if (location.hash === '#/settings') return { view: 'settings' }
  const m = location.hash.match(/^#\/job\/(.+)$/)
  return m ? { view: 'job', id: decodeURIComponent(m[1]) } : { view: 'new' }
}

export default function App() {
  const [jobs, setJobs] = useState([])
  const [r, setR] = useState(route())
  const [status, setStatus] = useState(null)
  const [settings, setSettings] = useState(null)
  const [drawer, setDrawer] = useState(false)

  const refresh = useCallback(() => api.jobs().then(setJobs).catch(() => {}), [])
  const loadSettings = useCallback(() => settingsApi.get().then((s) => { setSettings(s); applyTheme(s.theme) }).catch(() => {}), [])

  useEffect(() => {
    const onHash = () => { setR(route()); setDrawer(false) }
    window.addEventListener('hashchange', onHash)
    refresh(); loadSettings()
    api.status().then(setStatus).catch(() => setStatus({ offline: true }))
    const close = openSocket('all', (msg) => {
      if (msg.type === 'job') setJobs((js) => {
        const i = js.findIndex((j) => j.id === msg.job.id)
        if (i < 0) return [msg.job, ...js]
        const copy = js.slice(); copy[i] = { ...copy[i], ...msg.job }; return copy
      })
    }, refresh)
    return () => { window.removeEventListener('hashchange', onHash); close() }
  }, [refresh, loadSettings])

  const open = (id) => { location.hash = id ? `#/job/${encodeURIComponent(id)}` : '#/' }
  const title = r.view === 'settings' ? 'Ajustes' : r.view === 'job' ? (jobs.find((j) => j.id === r.id)?.name || r.id) : 'Nuevo video'

  return (
    <div className={`app ${drawer ? 'drawer-open' : ''}`}>
      <header className="topbar">
        <button className="icon-btn topbar-menu" aria-label="Abrir menú" onClick={() => setDrawer(true)}><Menu /></button>
        <span className="brand-mark sm"><Film /></span>
        <span className="topbar-title">{title}</span>
      </header>
      <div className="scrim" onClick={() => setDrawer(false)} aria-hidden="true" />
      <Sidebar jobs={jobs} current={r.view === 'job' ? r.id : null} view={r.view} onOpen={(id) => { setDrawer(false); open(id) }} status={status} />
      <main className="main">
        {r.view === 'settings' && <Settings settings={settings} onChange={loadSettings} />}
        {r.view === 'job' && <JobView key={r.id} id={r.id} models={status?.models} efforts={status?.efforts} onDeleted={() => { refresh(); open(null) }} />}
        {r.view === 'new' && <NewJob status={status} settings={settings} onCreated={(job) => { refresh(); open(job.id) }} />}
      </main>
    </div>
  )
}

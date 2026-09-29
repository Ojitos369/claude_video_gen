// Backend calls (same origin: vite proxy in dev, FastAPI in local production)
const json = async (res) => {
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.detail || `Error ${res.status}`)
  return data
}

export const api = {
  status: () => fetch('/api/base/status').then(json),
  jobs: () => fetch('/api/jobs/list').then(json).then((d) => d.jobs),
  job: (id) => fetch(`/api/jobs/detail/${id}`).then(json).then((d) => d.job),
  events: (id, since = 0) => fetch(`/api/jobs/events/${id}?since=${since}`).then(json).then((d) => d.events),
  message: (id, text, model, effort) =>
    fetch(`/api/jobs/message/${id}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text, model, effort }) }).then(json),
  rename: (id, name) =>
    fetch(`/api/jobs/rename/${id}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }) }).then(json),
  cancel: (id) => fetch(`/api/jobs/cancel/${id}`, { method: 'POST' }).then(json),
  remove: (id) => fetch(`/api/jobs/delete/${id}`, { method: 'POST' }).then(json),
  fileUrl: (id, path) => `/api/jobs/file/${id}/${path.split('/').map(encodeURIComponent).join('/')}`,

  // multipart upload with progress (fetch has no upload progress)
  create: ({ prompt, name, model, effort, aspect, aspectText, tools, files }, onProgress) =>
    new Promise((resolve, reject) => {
      const fd = new FormData()
      fd.append('prompt', prompt)
      fd.append('name', name || '')
      if (model) fd.append('model', model)
      if (effort) fd.append('effort', effort)
      if (aspect) fd.append('aspect', aspect)
      if (aspect === 'manual') fd.append('aspect_text', aspectText || '')
      if (tools) fd.append('tools', JSON.stringify(tools))
      files.forEach((f) => fd.append('files', f, f.name))
      const xhr = new XMLHttpRequest()
      xhr.open('POST', '/api/jobs/create')
      xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(e.loaded / e.total)
      xhr.onload = () => {
        let data = {}
        try { data = JSON.parse(xhr.responseText) } catch { /* empty */ }
        xhr.status < 300 ? resolve(data.job) : reject(new Error(data.detail || `Error ${xhr.status}`))
      }
      xhr.onerror = () => reject(new Error('No se pudo conectar con el servidor'))
      xhr.send(fd)
    }),
}

export const settingsApi = {
  get: () => fetch('/api/settings/get').then(json).then((d) => d.settings),
  save: (patch) => fetch('/api/settings/save', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(patch) }).then(json),
  test: (provider) => fetch(`/api/settings/test/${provider}`, { method: 'POST' }).then(json),
  codexLogin: () => fetch('/api/settings/codex_login', { method: 'POST' }).then(json),
  machine: (force) => fetch('/api/settings/machine', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ force }) }).then(json),
}

// theme: stored in settings.local.json (server) and cached in localStorage so the first paint already has it
export function applyTheme(theme) {
  const t = theme === 'light' ? 'light' : 'dark'
  document.documentElement.dataset.theme = t
  try { localStorage.setItem('vs-theme', t) } catch { /* private mode */ }
}

const clientId = Math.random().toString(36).slice(2)

// websocket with automatic reconnection; returns a close function
export function openSocket(channel, onMessage, onOpen) {
  let ws, timer, closed = false
  const connect = () => {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    ws = new WebSocket(`${proto}://${location.host}/api/ws/jobs/${channel}?clientId=${clientId}`)
    ws.onopen = () => onOpen?.()
    ws.onmessage = (e) => { try { onMessage(JSON.parse(e.data)) } catch { /* ignore */ } }
    ws.onclose = () => { if (!closed) timer = setTimeout(connect, 2000) }
  }
  connect()
  const ping = setInterval(() => ws?.readyState === 1 && ws.send('ping'), 25000)
  return () => { closed = true; clearTimeout(timer); clearInterval(ping); ws?.close() }
}

export const fmtSize = (b) => (b == null ? '' : b > 1e9 ? `${(b / 1e9).toFixed(1)} GB` : b > 1e6 ? `${(b / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1e3))} KB`)
export const fmtCost = (c) => (c ? `$${c.toFixed(2)}` : '')
export const fmtDur = (s) => {
  if (s == null || s < 0) return ''
  s = Math.round(s)
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60
  return h ? `${h} h ${m} min` : m ? `${m} min ${r} s` : `${r} s`
}
export const STATUS = {
  queued: { label: 'En cola', tone: 'muted' },
  running: { label: 'Trabajando', tone: 'live' },
  done: { label: 'Terminado', tone: 'ok' },
  error: { label: 'Error', tone: 'bad' },
  cancelled: { label: 'Cancelado', tone: 'muted' },
  interrupted: { label: 'Interrumpido', tone: 'warn' },
}

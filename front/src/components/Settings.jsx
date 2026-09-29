import { useEffect, useMemo, useState } from 'react'
import qrcode from 'qrcode-generator'
import { settingsApi, applyTheme } from '../api.js'
import { Sun, Moon, Key, Mic, Image, Phone, Cpu, Check, Alert } from './Icons.jsx'

// All of this is saved in settings.local.json on the machine running the service (git-ignored). API keys never come back
// to the browser: the page only knows whether a key is stored and its last 4 characters.
const PLATFORMS = [
  { id: 'anthropic', label: 'Anthropic (Claude)', help: 'Opcional. Por defecto Claude usa la sesión de Claude Code; con una API key activa se factura a la API.' },
  { id: 'google', label: 'Google (Gemini)', help: 'Imágenes y voz (TTS) con Gemini. Clave de Google AI Studio.' },
  { id: 'openai', label: 'OpenAI', help: 'Imágenes y voz. Con API key, o imágenes con tu suscripción de ChatGPT (inicio de sesión por Codex CLI).' },
  { id: 'elevenlabs', label: 'ElevenLabs', help: 'Voces (TTS) de alta calidad.' },
]

function Section({ icon, title, children, note }) {
  return (
    <section className="card">
      <header className="card-head"><span className="card-icon">{icon}</span><h2>{title}</h2></header>
      {note && <p className="muted card-note">{note}</p>}
      {children}
    </section>
  )
}

function Toggle({ checked, onChange, label, hint, disabled }) {
  return (
    <label className={`toggle ${disabled ? 'is-disabled' : ''}`}>
      <input type="checkbox" checked={!!checked} onChange={(e) => onChange(e.target.checked)} disabled={disabled} />
      <span className="toggle-ui" aria-hidden="true" />
      <span className="toggle-text"><span>{label}</span>{hint && <small className="muted">{hint}</small>}</span>
    </label>
  )
}

function KeyField({ id, prov, onSaved }) {
  const [val, setVal] = useState('')
  const [msg, setMsg] = useState(null)
  const [busy, setBusy] = useState(false)
  const save = async () => {
    if (!val.trim()) return
    setBusy(true); setMsg(null)
    try { await settingsApi.save({ providers: { [id]: { api_key: val.trim() } } }); setVal(''); await onSaved(); setMsg({ ok: true, text: 'Guardada' }) }
    catch (e) { setMsg({ ok: false, text: e.message }) } finally { setBusy(false) }
  }
  const test = async () => {
    setBusy(true); setMsg(null)
    try { const r = await settingsApi.test(id); setMsg({ ok: r.ok, text: r.detail }) } catch (e) { setMsg({ ok: false, text: e.message }) } finally { setBusy(false) }
  }
  const clear = async () => { await settingsApi.save({ providers: { [id]: { clear_api_key: true } } }); onSaved(); setMsg(null) }
  return (
    <div className="key-field">
      <div className="key-row">
        <input type="password" autoComplete="off" value={val} onChange={(e) => setVal(e.target.value)} disabled={busy}
          placeholder={prov.api_key_set ? `Clave guardada ${prov.api_key_hint} · escribe otra para reemplazarla` : 'Pega tu API key'}
          onKeyDown={(e) => e.key === 'Enter' && save()} aria-label={`API key de ${id}`} />
        <button className="btn" onClick={save} disabled={busy || !val.trim()}>Guardar</button>
      </div>
      <div className="key-actions">
        {prov.api_key_set && <span className="pill pill-ok"><Check /> clave guardada {prov.api_key_hint}</span>}
        {prov.api_key_set && <button className="btn btn-ghost btn-sm" onClick={test} disabled={busy}>Probar</button>}
        {prov.api_key_set && <button className="btn btn-ghost btn-sm btn-danger" onClick={clear} disabled={busy}>Quitar</button>}
        {msg && <span className={msg.ok ? 'ok-text' : 'bad-text'}>{msg.text}</span>}
      </div>
    </div>
  )
}

function ProviderPicker({ section, catalog, value, onSave, keys }) {
  const cat = catalog[value.provider] || {}
  const needsKey = cat.key && !keys[cat.key]
  return (
    <div className="grid-fields">
      <label className="field">
        <span>Proveedor</span>
        <select value={value.provider} onChange={(e) => onSave({ provider: e.target.value, model: '', voice: '' })}>
          {Object.entries(catalog).map(([id, c]) => <option key={id} value={id}>{c.label}</option>)}
        </select>
      </label>
      {value.provider !== 'none' && (
        <label className="field">
          <span>Modelo</span>
          <input list={`${section}-models`} defaultValue={value.model} placeholder={cat.models?.[0] || 'por defecto'}
            onBlur={(e) => e.target.value !== value.model && onSave({ model: e.target.value.trim() })} />
          <datalist id={`${section}-models`}>{(cat.models || []).map((m) => <option key={m} value={m} />)}</datalist>
        </label>
      )}
      {section === 'tts' && value.provider !== 'none' && (
        <>
          <label className="field">
            <span>Voz</span>
            <input list="tts-voices" defaultValue={value.voice} placeholder={cat.voices?.[0] || 'por defecto'}
              onBlur={(e) => e.target.value !== value.voice && onSave({ voice: e.target.value.trim() })} />
            <datalist id="tts-voices">{(cat.voices || []).map((m) => <option key={m} value={m} />)}</datalist>
          </label>
          <label className="field">
            <span>Idioma</span>
            <select value={value.language} onChange={(e) => onSave({ language: e.target.value })}>
              {['es', 'en', 'pt', 'fr', 'it', 'de', 'ja', 'ko', 'zh'].map((l) => <option key={l} value={l}>{l}</option>)}
            </select>
          </label>
        </>
      )}
      {section === 'images' && value.provider !== 'none' && (
        <label className="field">
          <span>Máximo por proyecto</span>
          <input type="number" min="1" max="100" defaultValue={value.max_per_project}
            onBlur={(e) => onSave({ max_per_project: Math.max(1, Math.min(100, +e.target.value || 12)) })} />
        </label>
      )}
      {needsKey && <p className="bad-text full">Este proveedor necesita la API key de {cat.key} (arriba, en Plataformas).</p>}
      {cat.kind === 'open' && <p className="muted full">Se instala y descarga la voz la primera vez que se usa (local, gratis, sin internet después).</p>}
    </div>
  )
}

function Qr({ text }) {
  const svg = useMemo(() => {
    if (!text) return ''
    const q = qrcode(0, 'M'); q.addData(text); q.make()
    return q.createSvgTag({ cellSize: 5, margin: 2, scalable: true })
  }, [text])
  return <div className="qr" dangerouslySetInnerHTML={{ __html: svg }} />
}

export default function Settings({ settings: s, onChange }) {
  const [machineMsg, setMachineMsg] = useState('')
  const [codexMsg, setCodexMsg] = useState('')
  useEffect(() => { if (s) applyTheme(s.theme) }, [s?.theme]) // eslint-disable-line
  if (!s) return <div className="page"><span className="spinner" /> Cargando ajustes…</div>

  const save = async (patch) => { await settingsApi.save(patch); await onChange() }
  const keys = Object.fromEntries(Object.entries(s.providers).map(([k, v]) => [k, v.api_key_set || (k === 'openai' && v.auth === 'subscription' && s.codex?.logged_in)]))
  const local = !!s.access.token

  return (
    <div className="page settings">
      <header className="page-head">
        <h1>Ajustes</h1>
        <p>Se guardan en <code>settings.local.json</code> en el equipo del servicio (fuera de git). Las claves nunca se muestran completas.</p>
      </header>

      <Section icon={s.theme === 'light' ? <Sun /> : <Moon />} title="Apariencia">
        <div className="segmented" role="radiogroup" aria-label="Tema">
          {[['dark', 'Oscuro', <Moon key="m" />], ['light', 'Claro', <Sun key="s" />]].map(([id, label, icon]) => (
            <button key={id} role="radio" aria-checked={s.theme === id} className={s.theme === id ? 'is-active' : ''}
              onClick={() => { applyTheme(id); save({ theme: id }) }}>{icon} {label}</button>
          ))}
        </div>
      </Section>

      <Section icon={<Key />} title="Plataformas" note="Claves de API para las herramientas de generación. Claude Code sigue usando su propia sesión salvo que actives la API key de Anthropic.">
        {PLATFORMS.map((p) => {
          const prov = s.providers[p.id]
          return (
            <div key={p.id} className="platform">
              <div className="platform-head"><strong>{p.label}</strong><small className="muted">{p.help}</small></div>
              {p.id === 'openai' && (
                <div className="segmented sm" role="radiogroup" aria-label="Acceso a OpenAI">
                  {[['api', 'API key'], ['subscription', 'Suscripción ChatGPT']].map(([id, label]) => (
                    <button key={id} role="radio" aria-checked={prov.auth === id} className={prov.auth === id ? 'is-active' : ''}
                      onClick={() => save({ providers: { openai: { auth: id } } })}>{label}</button>
                  ))}
                </div>
              )}
              {p.id === 'openai' && prov.auth === 'subscription' ? (
                <div className="codex">
                  {s.codex?.logged_in
                    ? <span className="pill pill-ok"><Check /> {s.codex.detail}</span>
                    : <span className="pill pill-bad"><Alert /> {s.codex?.installed ? 'Sin sesión de ChatGPT' : 'Codex CLI no instalado'}</span>}
                  {s.codex?.installed && !s.codex.logged_in && (
                    <button className="btn btn-sm" onClick={async () => { try { const r = await settingsApi.codexLogin(); setCodexMsg(r.detail) } catch (e) { setCodexMsg(e.message) } }}>Iniciar sesión</button>
                  )}
                  <button className="btn btn-ghost btn-sm" onClick={onChange}>Actualizar estado</button>
                  <small className="muted full">Usa tu plan de ChatGPT a través de la CLI oficial de Codex (<code>codex login</code>); solo sirve para imágenes.
                    {!s.codex?.installed && <> Instálala con <code>npm i -g @openai/codex</code>.</>}</small>
                  {codexMsg && <small className="ok-text full">{codexMsg}</small>}
                </div>
              ) : <KeyField id={p.id} prov={prov} onSaved={onChange} />}
              {p.id === 'anthropic' && prov.api_key_set && (
                <Toggle checked={prov.use_api_key} onChange={(v) => save({ providers: { anthropic: { use_api_key: v } } })}
                  label="Usar esta API key para Claude" hint="Si está apagado, Claude usa la sesión iniciada en Claude Code." />
              )}
            </div>
          )
        })}
      </Section>

      <Section icon={<Mic />} title="Voz (TTS)" note="Para narraciones o voces en off cuando el video las necesite. Piper y Kokoro son de código abierto y corren en local.">
        <ProviderPicker section="tts" catalog={s.catalog.tts} value={s.tts} keys={keys} onSave={(v) => save({ tts: v })} />
      </Section>

      <Section icon={<Image />} title="Imágenes" note="Para generar fondos, personajes u objetos cuando mejoren el video.">
        <ProviderPicker section="images" catalog={s.catalog.images} value={s.images} keys={keys} onSave={(v) => save({ images: v })} />
      </Section>

      <Section icon={<Image />} title="Herramientas en las generaciones" note="Valores por defecto al crear un video (se pueden cambiar en cada trabajo). Claude solo las usa si ayudan.">
        <Toggle checked={s.generation.images} onChange={(v) => save({ generation: { images: v } })} label="Permitir generar imágenes"
          hint={s.images.provider === 'none' ? 'Configura un proveedor de imágenes para que esté disponible' : s.catalog.images[s.images.provider]?.label} />
        <Toggle checked={s.generation.tts} onChange={(v) => save({ generation: { tts: v } })} label="Permitir generar voz"
          hint={s.tts.provider === 'none' ? 'Configura un proveedor de voz para que esté disponible' : s.catalog.tts[s.tts.provider]?.label} />
      </Section>

      <Section icon={<Phone />} title="Acceso desde el teléfono" note="El servicio escucha en tu red local y pide un token a los demás dispositivos. Úsalo solo en redes de confianza: Claude puede ejecutar comandos en este equipo.">
        {local ? (
          <>
            <Toggle checked={s.access.lan} onChange={(v) => save({ access: { lan: v } })} label="Permitir acceso desde la red local"
              hint="Requiere reiniciar el servicio (run.sh / run.bat) para aplicarse." />
            {s.access.lan && (
              <div className="lan">
                <Qr text={s.access.lan_url} />
                <div className="lan-info">
                  <p>Escanea el código con el teléfono (misma red Wi-Fi) o abre:</p>
                  <code className="lan-url">{s.access.lan_url}</code>
                  <button className="btn btn-ghost btn-sm" onClick={() => save({ access: { regenerate_token: true } })}>Cambiar token</button>
                  <small className="muted">Cambiar el token cierra el acceso de los dispositivos que ya lo tenían.</small>
                </div>
              </div>
            )}
          </>
        ) : <p className="muted">Estas opciones solo se pueden cambiar desde el equipo donde corre el servicio.</p>}
      </Section>

      <Section icon={<Cpu />} title="Equipo del servicio" note="Detectado al iniciar el servicio y guardado en los ajustes; Claude y el motor lo usan para elegir codificador, procesos y resolución.">
        <p className="machine">{s.machine_summary || 'Aún no detectado.'}</p>
        <button className="btn btn-sm" onClick={async () => { const r = await settingsApi.machine(true); setMachineMsg(r.updated ? 'Actualizado' : 'Sin cambios'); onChange() }}>Volver a detectar</button>
        {machineMsg && <span className="ok-text"> {machineMsg}</span>}
      </Section>
    </div>
  )
}

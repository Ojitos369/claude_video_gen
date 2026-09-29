import { useState, useEffect } from 'react'
import { api, fmtSize } from '../api.js'
import { Download, Film, FileText } from './Icons.jsx'

export default function Results({ id, outputs, running }) {
  const videos = outputs.filter((o) => o.video)
  // prefer the final video over previews
  const pick = () => videos.find((v) => !/preview/i.test(v.name)) || videos[videos.length - 1]
  const [sel, setSel] = useState(pick()?.path)
  useEffect(() => { if (!videos.some((v) => v.path === sel)) setSel(pick()?.path) }, [outputs]) // eslint-disable-line

  if (!outputs.length) {
    return (
      <div className="results-empty">
        <Film />
        <p>{running ? 'El video aparecerá aquí en cuanto Claude lo guarde en out/. Las vistas previas también se muestran.' : 'Este trabajo aún no tiene archivos en out/.'}</p>
      </div>
    )
  }
  const current = outputs.find((o) => o.path === sel)
  const v = current ? `${api.fileUrl(id, current.path)}?v=${Math.round(current.mtime)}` : null
  return (
    <div className="results">
      {current?.video && <video key={v} className="player" src={v} controls playsInline preload="metadata" />}
      <ul className="out-list">
        {outputs.map((o) => (
          <li key={o.path} className={o.path === sel ? 'is-active' : ''}>
            <button className="out-name" onClick={() => o.video && setSel(o.path)} disabled={!o.video}>
              {o.video ? <Film /> : <FileText />} <span>{o.name}</span>
              {/preview/i.test(o.name) && <span className="pill">vista previa</span>}
            </button>
            <span className="muted">{fmtSize(o.size)}</span>
            <a className="icon-btn" href={api.fileUrl(id, o.path)} download={o.name} aria-label={`Descargar ${o.name}`}><Download /></a>
          </li>
        ))}
      </ul>
    </div>
  )
}

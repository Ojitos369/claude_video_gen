// Output format picker. video:<file> / image:<file> = proportions of an uploaded file (measured again by the backend);
// manual = free text that Claude interprets ("monitor curvo de 72 pulgadas").
export const PAIRS = [
  { v: { id: '9:16', label: '9:16 vertical', size: '1080x1920' }, h: { id: '16:9', label: '16:9 horizontal', size: '1920x1080' } },
  { v: { id: '3:4', label: '3:4 vertical', size: '1080x1440' }, h: { id: '4:3', label: '4:3 horizontal', size: '1440x1080' } },
  { v: { id: '10:16', label: 'Wallpaper celular 10:16', size: '1200x1920' }, h: { id: '16:10', label: 'Wallpaper PC 16:10', size: '1920x1200' } },
]
const SQUARE = { id: '1:1', label: '1:1 cuadrado', size: '1080x1080' }
const ALL = [...PAIRS.flatMap((p) => [p.v, p.h]), SQUARE]

export const ratioText = (w, h) => {
  const g = (a, b) => (b ? g(b, a % b) : a)
  const d = g(w, h), a = w / d, b = h / d
  return a <= 32 && b <= 32 ? `${a}:${b}` : `${(w / h).toFixed(2)}:1`
}
const short = (n) => (n.length > 22 ? n.slice(0, 20) + '…' : n)

export default function AspectSelect({ value, onChange, videos, images, disabled }) {
  const std = ALL.find((a) => a.id === value)
  const file = [...videos.map((v) => ({ ...v, k: `video:${v.name}` })), ...images.map((v) => ({ ...v, k: `image:${v.name}` }))].find((f) => f.k === value)
  const note = std ? std.size : file ? (file.w ? `${file.w}x${file.h} · ${ratioText(file.w, file.h)}` : 'se mide al subirlo') : value === 'manual' ? 'Claude lo interpreta' : ''
  return (
    <label className="model-select aspect-select">
      <span>Formato</span>
      <select value={value} onChange={(e) => onChange(e.target.value)} disabled={disabled} aria-label="Proporción del video">
        {(videos.length > 0 || images.length > 0) && (
          <optgroup label="De tus archivos">
            {videos.map((v) => <option key={'v' + v.name} value={`video:${v.name}`}>Del video: {short(v.name)}</option>)}
            {images.map((v) => <option key={'i' + v.name} value={`image:${v.name}`}>De la imagen: {short(v.name)}</option>)}
          </optgroup>
        )}
        <optgroup label="Verticales">{PAIRS.map((p) => <option key={p.v.id} value={p.v.id}>{p.v.label}</option>)}</optgroup>
        <optgroup label="Horizontales">{PAIRS.map((p) => <option key={p.h.id} value={p.h.id}>{p.h.label}</option>)}</optgroup>
        <optgroup label="Otros">
          <option value={SQUARE.id}>{SQUARE.label}</option>
          <option value="manual">Manual (descríbelo)…</option>
        </optgroup>
      </select>
      {note && <small className="model-note">{note}</small>}
    </label>
  )
}

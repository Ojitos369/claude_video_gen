// Claude model / effort picker (lists and defaults come from /api/base/status)
export const modelLabel = (models, id) => models?.find((m) => m.id === id)?.label || id

export default function ModelSelect({ models, value, onChange, disabled, compact, label = 'Modelo', aria = 'Modelo de Claude' }) {
  if (!models?.length) return null
  const cur = models.find((m) => m.id === value)
  return (
    <label className={`model-select ${compact ? 'is-compact' : ''}`} title={cur?.note || ''}>
      {!compact && <span>{label}</span>}
      <select value={value} onChange={(e) => onChange(e.target.value)} disabled={disabled} aria-label={aria}>
        {models.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
      </select>
      {!compact && cur?.note && <small className="model-note">{cur.note}</small>}
    </label>
  )
}

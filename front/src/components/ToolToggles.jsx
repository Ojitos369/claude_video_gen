// Generation tools and questions Claude may use in a job (new job form and the job's options panel)
export default function ToolToggles({ settings, value: gen, disabled, onChange }) {
  const imgProv = settings?.images?.provider || 'none', ttsProv = settings?.tts?.provider || 'none', musProv = settings?.music?.provider || 'none'
  return (
    <fieldset className="tools">
      <legend>Herramientas que Claude puede usar</legend>
      {[['images', 'Generar imágenes', imgProv, settings?.catalog?.images], ['tts', 'Generar voz', ttsProv, settings?.catalog?.tts], ['music', 'Generar música', musProv, settings?.catalog?.music], ['models', 'Generar modelos 3D', settings?.blender?.found ? 'blender' : 'none', { blender: { label: 'Blender' } }]].map(([k, label, prov, cat]) => (
        <label key={k} className={`toggle ${prov === 'none' ? 'is-disabled' : ''}`}>
          <input type="checkbox" checked={!!gen[k] && prov !== 'none'} disabled={disabled || prov === 'none'}
            onChange={(e) => onChange({ ...gen, [k]: e.target.checked })} />
          <span className="toggle-ui" aria-hidden="true" />
          <span className="toggle-text"><span>{label}</span>
            <small className="muted">{prov === 'none' ? <>sin proveedor · <a href="#/settings">configurar</a></> : cat?.[prov]?.label}</small></span>
        </label>
      ))}
      {(
        <label className="toggle">
          <input type="checkbox" checked={!!gen.ask} disabled={disabled} onChange={(e) => onChange({ ...gen, ask: e.target.checked })} />
          <span className="toggle-ui" aria-hidden="true" />
          <span className="toggle-text"><span>Hacer preguntas antes de producir</span>
            <small className="muted">{gen.ask ? 'Claude puede pedirte estilo y detalles (opción múltiple o respuesta propia)' : 'Decide solo, sin preguntas'}</small></span>
        </label>
      )}
    </fieldset>
  )
}

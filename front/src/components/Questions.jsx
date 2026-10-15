import { useState } from 'react'
import { Send } from './Icons.jsx'

// Claude's pending questions (preguntas.json): multiple choice, or a custom written answer. Answers go back as a change request.
export default function Questions({ questions, disabled, onSubmit }) {
  const [pick, setPick] = useState({})     // id -> array of chosen options
  const [custom, setCustom] = useState({}) // id -> free text
  const toggle = (q, o) => setPick((p) => {
    const cur = p[q.id] || []
    return { ...p, [q.id]: q.multiple ? (cur.includes(o) ? cur.filter((x) => x !== o) : [...cur, o]) : [o] }
  })
  const answer = (q) => [...(pick[q.id] || []), ...(custom[q.id]?.trim() ? [custom[q.id].trim()] : [])]
  const ready = questions.every((q) => answer(q).length)
  const submit = (e) => {
    e.preventDefault()
    if (ready) onSubmit(questions.map((q) => `- ${q.texto}\n  Respuesta: ${answer(q).join('; ')}`).join('\n'))
  }
  return (
    <form className="questions notice" onSubmit={submit}>
      <strong>Claude necesita unos detalles antes de producir</strong>
      {questions.map((q) => (
        <fieldset key={q.id} className="q">
          <legend>{q.texto}</legend>
          {q.opciones.map((o) => (
            <label key={o} className="q-opt">
              <input type={q.multiple ? 'checkbox' : 'radio'} name={q.id} checked={(pick[q.id] || []).includes(o)} disabled={disabled}
                onChange={() => toggle(q, o)} /> <span>{o}</span>
            </label>
          ))}
          <input className="q-custom" placeholder="Otra respuesta (escríbela)…" value={custom[q.id] || ''} disabled={disabled}
            onChange={(e) => { setCustom({ ...custom, [q.id]: e.target.value }); if (!q.multiple && e.target.value) setPick({ ...pick, [q.id]: [] }) }} />
        </fieldset>
      ))}
      <button className="btn btn-primary" disabled={!ready || disabled}><Send /> Enviar respuestas</button>
    </form>
  )
}

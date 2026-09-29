import { STATUS } from '../api.js'

export default function StatusBadge({ status, small }) {
  const s = STATUS[status] || { label: status, tone: 'muted' }
  return <span className={`badge badge-${s.tone} ${small ? 'badge-sm' : ''}`}><i className="dot" />{s.label}</span>
}

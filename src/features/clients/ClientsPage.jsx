import { useMemo, useState } from 'react'
import Panel from '../../components/Panel.jsx'
import StatusBadge from '../../components/StatusBadge.jsx'
import { formatDate } from '../../utils/date.js'

export default function ClientsPage({ user, clients, trainers, onOpen }) {
  const [query, setQuery] = useState('')
  const [type, setType] = useState('')
  const trainerName = id => trainers.find(trainer => trainer.id === id)?.name ?? '—'
  const visible = useMemo(() => clients.filter(client => {
    if (user.role === 'trainer' && client.trainerId !== user.trainerId) return false
    if (query && !client.name.toLowerCase().includes(query.toLowerCase())) return false
    if (type && client.type !== type) return false
    return true
  }), [clients, query, type, user])

  return (
    <>
      <div className="page-head"><div><span className="eyebrow">Clients</span><h1>All Clients</h1><p>{user.role === 'owner' ? 'All active PT clients' : 'Clients assigned to you'}</p></div></div>
      <Panel>
        <div className="toolbar">
          <input aria-label="Search client" value={query} onChange={event => setQuery(event.target.value)} placeholder="Search client" />
          <select aria-label="Client type" value={type} onChange={event => setType(event.target.value)}><option value="">All types</option><option>Individual</option><option>Couple</option></select>
        </div>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Client</th><th>Type</th><th>Package / Goal</th><th>Assigned Trainer</th><th>Last Trained</th><th>Renewal</th><th></th></tr></thead>
            <tbody>
              {visible.map(client => <tr key={client.id}>
                <td><strong>{client.name}</strong></td><td>{client.type}</td><td>{client.package.total} sessions</td><td>{trainerName(client.trainerId)}</td><td>{formatDate(client.lastTrained)}</td><td><StatusBadge tone={client.package.used >= 10 ? 'amber' : 'neutral'}>{client.renewal}</StatusBadge></td><td><button className="btn small" type="button" onClick={() => onOpen(client.id)}>View</button></td>
              </tr>)}
              {!visible.length && <tr><td colSpan="7" className="empty">No matching clients.</td></tr>}
            </tbody>
          </table>
        </div>
      </Panel>
    </>
  )
}

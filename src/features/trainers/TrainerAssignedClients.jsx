import { useMemo } from 'react'
import usePageState from '../../hooks/usePageState.js'
import usePagination from '../../hooks/usePagination.js'
import PaginationControls from '../../components/PaginationControls.jsx'
import SelectField from '../../components/SelectField.jsx'
import Panel from '../../components/Panel.jsx'
import { clientAssignedToTrainer } from '../../app/clientPackages.js'

export default function TrainerAssignedClients({ trainer, clients, sessions, onOpenClient }) {
  const [assignedQuery, setAssignedQuery] = usePageState('TrainerProfilePage.assignedQuery', '')
  const [assignedType, setAssignedType] = usePageState('TrainerProfilePage.assignedType', '')
  const [assignedFrequency, setAssignedFrequency] = usePageState('TrainerProfilePage.assignedFrequency', '')
  const assignedClients = clients
    .filter(client =>
      clientAssignedToTrainer(client, trainer.id, sessions)
    )
    .sort((a, b) => Number(a.status === 'inactive') - Number(b.status === 'inactive') || (b.startDate ?? '').localeCompare(a.startDate ?? ''))

  const filteredAssignedClients = useMemo(() => {
    const search = assignedQuery.trim().toLowerCase()
    return assignedClients.filter(client => {
      if (search && !client.name.toLowerCase().includes(search) && !client.email.toLowerCase().includes(search)) return false
      if (assignedType && client.type !== assignedType) return false
      if (assignedFrequency && String(client.package?.sessionsPerWeek) !== assignedFrequency) return false
      return true
    })
  }, [assignedClients, assignedFrequency, assignedQuery, assignedType])

  const assignedClientPagination = usePagination(filteredAssignedClients, `${trainer.id}|${assignedQuery}|${assignedType}|${assignedFrequency}`, 'trainer.assignedPage')

  return (
    <Panel>
      <div className="section-head">
        <div><h2>Assigned Clients</h2></div>
      </div>

      <div className="list-controls assigned-client-controls">
        <input
          aria-label="Search assigned clients"
          value={assignedQuery}
          onChange={event => setAssignedQuery(event.target.value)}
          placeholder="Search name or email"
        />
        <SelectField aria-label="Filter assigned clients by type" value={assignedType} onChange={event => setAssignedType(event.target.value)}>
          <option value="">All types</option>
          <option value="Individual">Individual</option>
          <option value="Couple">Couple</option>
        </SelectField>
        <SelectField aria-label="Filter assigned clients by frequency" value={assignedFrequency} onChange={event => setAssignedFrequency(event.target.value)}>
          <option value="">All frequencies</option>
          <option value="1">Once per week</option>
          <option value="2">Twice per week</option>
        </SelectField>
      </div>

      <div className="compact-list" aria-label="Assigned client list">
        <div className="compact-list-head client-compact-grid"><span>Client</span><span>Package</span><span>View</span></div>
        {assignedClientPagination.items.map(client => (
          <div className={`compact-list-row client-compact-grid ${client.status === 'inactive' ? 'inactive-row' : ''}`} key={client.id}>
            <div className="compact-name-wrap"><strong className="compact-primary">{client.name}</strong>{client.status === 'inactive' && <span className="inline-inactive">Client inactive</span>}</div>
            <span className="compact-secondary">{client.package ? `${client.type} · ${client.package.total} sessions · ${client.package.sessionsPerWeek === 2 ? 'Twice' : 'Once'} weekly` : 'No current package'}</span>
            <button type="button" className="secondary-button small compact-view" aria-label={`View ${client.name}`} onClick={() => onOpenClient(client.id)}>View</button>
          </div>
        ))}
        {!filteredAssignedClients.length && <div className="empty">No matching assigned clients.</div>}
      </div>
      <PaginationControls {...assignedClientPagination} onPage={assignedClientPagination.setPage} />
    </Panel>
  )
}

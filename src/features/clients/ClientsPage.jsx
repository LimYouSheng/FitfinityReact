import { useMemo, useState } from 'react'
import Panel from '../../components/Panel.jsx'
import { isActive, visibleClientsForUser } from '../../app/status.js'

export default function ClientsPage({ user, clients, trainers, onOpen }) {
  const [query, setQuery] = useState('')
  const [searchOpen, setSearchOpen] = useState(false)
  const [statusFilter, setStatusFilter] = useState('all')
  const [typeFilter, setTypeFilter] = useState('')
  const [trainerFilter, setTrainerFilter] = useState('')

  const trainerName = id => trainers.find(trainer => trainer.id === id)?.name ?? '—'

  const base = useMemo(
    () => visibleClientsForUser(user, clients),
    [clients, user]
  )

  const trainerOptions = useMemo(() => {
    const ids = [...new Set(base.map(client => client.trainerId).filter(Boolean))]

    return ids
      .map(id => trainers.find(trainer => trainer.id === id))
      .filter(Boolean)
      .sort((a, b) => a.name.localeCompare(b.name))
  }, [base, trainers])

  const suggestions = useMemo(() => {
    const value = query.trim().toLowerCase()
    if (!value) return []

    return base
      .filter(client =>
        client.name.toLowerCase().includes(value) ||
        trainerName(client.trainerId).toLowerCase().includes(value)
      )
      .slice(0, 6)
  }, [base, query, trainers])

  const effectiveStatus = user.role === 'owner' ? statusFilter : 'active'
  const effectiveTrainer = user.role === 'owner' ? trainerFilter : user.trainerId

  const visible = useMemo(() => {
    const value = query.trim().toLowerCase()

    return base.filter(client => {
      if (
        value &&
        !client.name.toLowerCase().includes(value) &&
        !trainerName(client.trainerId).toLowerCase().includes(value)
      ) return false

      if (effectiveStatus === 'active' && !isActive(client)) return false
      if (effectiveStatus === 'inactive' && isActive(client)) return false
      if (typeFilter && client.type !== typeFilter) return false
      if (effectiveTrainer && client.trainerId !== effectiveTrainer) return false

      return true
    })
  }, [base, effectiveStatus, effectiveTrainer, query, typeFilter, trainers])

  return (
    <>
      <div className="page-head compact-page-head">
        <div>
          <span className="eyebrow">Clients</span>
          <h1>All Clients</h1>
        </div>
      </div>

      <Panel>
        <div className="list-controls client-controls">
          <div className="search-suggest-wrap">
            <input
              aria-label="Search client"
              aria-autocomplete="list"
              autoComplete="off"
              value={query}
              onFocus={() => setSearchOpen(true)}
              onBlur={() => window.setTimeout(() => setSearchOpen(false), 120)}
              onChange={event => {
                setQuery(event.target.value)
                setSearchOpen(true)
              }}
              placeholder="Search client or trainer"
            />

            {searchOpen && query.trim() && suggestions.length > 0 && (
              <div className="search-suggestions" role="listbox" aria-label="Client search suggestions">
                {suggestions.map(client => (
                  <button
                    key={client.id}
                    type="button"
                    role="option"
                    onMouseDown={event => event.preventDefault()}
                    onClick={() => {
                      setQuery(client.name)
                      setSearchOpen(false)
                    }}
                  >
                    <strong>{client.name}</strong>
                    <span>{trainerName(client.trainerId)}{!isActive(client) ? ' • Inactive' : ''}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          <select
            aria-label="Filter clients by status"
            value={user.role === 'owner' ? statusFilter : 'active'}
            disabled={user.role !== 'owner'}
            onChange={event => setStatusFilter(event.target.value)}
          >
            {user.role === 'owner' && <option value="all">All status</option>}
            <option value="active">Active</option>
            {user.role === 'owner' && <option value="inactive">Inactive</option>}
          </select>

          <select
            aria-label="Filter clients by type"
            value={typeFilter}
            onChange={event => setTypeFilter(event.target.value)}
          >
            <option value="">All types</option>
            <option value="Individual">Individual</option>
            <option value="Couple">Couple</option>
          </select>

          <select
            aria-label="Filter clients by trainer"
            value={user.role === 'owner' ? trainerFilter : user.trainerId}
            disabled={user.role !== 'owner'}
            onChange={event => setTrainerFilter(event.target.value)}
          >
            {user.role === 'owner'
              ? <option value="">All trainers</option>
              : <option value={user.trainerId}>{trainerName(user.trainerId)}</option>}

            {user.role === 'owner' && trainerOptions.map(trainer => (
              <option key={trainer.id} value={trainer.id}>{trainer.name}</option>
            ))}
          </select>
        </div>

        <div className="compact-list" aria-label="Client list">
          <div className="compact-list-head client-compact-grid">
            <span>Client</span>
            <span>Trainer</span>
            <span>View</span>
          </div>

          {visible.map(client => (
            <div
              className={`compact-list-row client-compact-grid ${isActive(client) ? '' : 'inactive-row'}`.trim()}
              key={client.id}
            >
              <div className="compact-name-wrap">
                <strong className="compact-primary">{client.name}</strong>
                {!isActive(client) && <span className="inline-inactive">Inactive</span>}
              </div>

              <span className="compact-secondary">{trainerName(client.trainerId)}</span>

              <button
                className="btn small compact-view"
                type="button"
                onClick={() => onOpen(client.id)}
                aria-label={`View ${client.name}`}
              >
                View
              </button>
            </div>
          ))}

          {!visible.length && <div className="empty">No matching clients.</div>}
        </div>
      </Panel>
    </>
  )
}

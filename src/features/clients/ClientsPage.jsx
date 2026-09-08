import usePageState from '../../hooks/usePageState.js'
import { useMemo, useState } from 'react'
import Panel from '../../components/Panel.jsx'
import PaginationControls from '../../components/PaginationControls.jsx'
import { isActive, visibleClientsForUser } from '../../app/status.js'
import usePagination from '../../hooks/usePagination.js'

export default function ClientsPage({ user, clients, trainers, onOpen, onAdd }) {
  const [query, setQuery] = usePageState('ClientsPage.query', '')
  const [searchOpen, setSearchOpen] = useState(false)
  const [statusFilter, setStatusFilter] = usePageState('ClientsPage.statusFilter', 'all')
  const [typeFilter, setTypeFilter] = usePageState('ClientsPage.typeFilter', '')
  const [trainerFilter, setTrainerFilter] = usePageState('ClientsPage.trainerFilter', '')

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

  const pagination = usePagination(
    visible,
    `${user.id}|${query}|${effectiveStatus}|${typeFilter}|${effectiveTrainer}`,
  )

  return (
    <>
      <div className="page-head compact-page-head">
        <div>
          <span className="eyebrow">Operations</span>
          <h1>All Clients</h1>
        </div>

        {user.role === 'owner' && (
          <button type="button" className="onboarding-button primary" onClick={onAdd}>
            Add New Client
          </button>
        )}
      </div>

      <Panel>
        <div className={`list-controls client-controls ${user.role === 'trainer' ? 'trainer-client-controls' : ''}`.trim()}>
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

          {user.role === 'owner' && <select
            aria-label="Filter clients by trainer"
            value={trainerFilter}
            onChange={event => setTrainerFilter(event.target.value)}
          >
            <option value="">All trainers</option>
            {trainerOptions.map(trainer => (
              <option key={trainer.id} value={trainer.id}>{trainer.name}</option>
            ))}
          </select>}
        </div>

        <div className="compact-list" aria-label="Client list">
          <div className="compact-list-head client-compact-grid">
            <span>Client</span>
            <span>Trainer</span>
            <span>View</span>
          </div>

          {pagination.items.map(client => (
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

        <PaginationControls {...pagination} onPage={pagination.setPage} />
      </Panel>
    </>
  )
}

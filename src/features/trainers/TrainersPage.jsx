import { useMemo, useState } from 'react'
import Panel from '../../components/Panel.jsx'
import PaginationControls from '../../components/PaginationControls.jsx'
import { isActive, visibleTrainersForOwner } from '../../app/status.js'
import usePagination from '../../hooks/usePagination.js'

export default function TrainersPage({ trainers, onOpen }) {
  const [query, setQuery] = useState('')
  const [searchOpen, setSearchOpen] = useState(false)
  const [statusFilter, setStatusFilter] = useState('all')
  const [typeFilter, setTypeFilter] = useState('')
  const [genderFilter, setGenderFilter] = useState('')

  const base = useMemo(
    () => visibleTrainersForOwner(trainers),
    [trainers]
  )

  const types = useMemo(
    () => [...new Set(base.map(trainer => trainer.trainerType).filter(Boolean))].sort(),
    [base]
  )

  const suggestions = useMemo(() => {
    const value = query.trim().toLowerCase()
    if (!value) return []

    return base
      .filter(trainer =>
        trainer.name.toLowerCase().includes(value) ||
        trainer.trainerType.toLowerCase().includes(value)
      )
      .slice(0, 6)
  }, [base, query])

  const visible = useMemo(() => {
    const value = query.trim().toLowerCase()

    return base.filter(trainer => {
      if (
        value &&
        !trainer.name.toLowerCase().includes(value) &&
        !trainer.trainerType.toLowerCase().includes(value)
      ) return false

      if (statusFilter === 'active' && !isActive(trainer)) return false
      if (statusFilter === 'inactive' && isActive(trainer)) return false
      if (typeFilter && trainer.trainerType !== typeFilter) return false
      if (genderFilter && trainer.gender !== genderFilter) return false

      return true
    })
  }, [base, query, statusFilter, typeFilter, genderFilter])

  const pagination = usePagination(
    visible,
    `${query}|${statusFilter}|${typeFilter}|${genderFilter}`,
  )

  return (
    <>
      <div className="page-head compact-page-head">
        <div>
          <span className="eyebrow">Operations</span>
          <h1>All Trainers</h1>
        </div>
      </div>

      <Panel>
        <div className="list-controls trainer-controls">
          <div className="search-suggest-wrap">
            <input
              aria-label="Search trainer"
              aria-autocomplete="list"
              autoComplete="off"
              value={query}
              onFocus={() => setSearchOpen(true)}
              onBlur={() => window.setTimeout(() => setSearchOpen(false), 120)}
              onChange={event => {
                setQuery(event.target.value)
                setSearchOpen(true)
              }}
              placeholder="Search trainer or type"
            />

            {searchOpen && query.trim() && suggestions.length > 0 && (
              <div className="search-suggestions" role="listbox" aria-label="Trainer search suggestions">
                {suggestions.map(trainer => (
                  <button
                    key={trainer.id}
                    type="button"
                    role="option"
                    onMouseDown={event => event.preventDefault()}
                    onClick={() => {
                      setQuery(trainer.name)
                      setSearchOpen(false)
                    }}
                  >
                    <strong>{trainer.name}</strong>
                    <span>{trainer.trainerType}{!isActive(trainer) ? ' • Inactive' : ''}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          <select
            aria-label="Filter trainers by status"
            value={statusFilter}
            onChange={event => setStatusFilter(event.target.value)}
          >
            <option value="all">All status</option>
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
          </select>

          <select
            aria-label="Filter trainers by type"
            value={typeFilter}
            onChange={event => setTypeFilter(event.target.value)}
          >
            <option value="">All types</option>
            {types.map(type => <option key={type} value={type}>{type}</option>)}
          </select>

          <select
            aria-label="Filter trainers by gender"
            value={genderFilter}
            onChange={event => setGenderFilter(event.target.value)}
          >
            <option value="">All genders</option>
            <option value="Female">Female</option>
            <option value="Male">Male</option>
          </select>
        </div>

        <div className="compact-list" aria-label="Trainer list">
          <div className="compact-list-head trainer-compact-grid">
            <span>Trainer</span>
            <span>Type</span>
            <span>View</span>
          </div>

          {pagination.items.map(trainer => (
            <div
              className={`compact-list-row trainer-compact-grid ${isActive(trainer) ? '' : 'inactive-row'}`.trim()}
              key={trainer.id}
            >
              <div className="compact-name-wrap">
                <strong className="compact-primary">{trainer.name}</strong>
                {!isActive(trainer) && <span className="inline-inactive">Inactive</span>}
              </div>

              <span className="compact-secondary">{trainer.trainerType}</span>

              <button
                type="button"
                className="btn small compact-view"
                onClick={() => onOpen(trainer.id)}
                aria-label={`View ${trainer.name}`}
              >
                View
              </button>
            </div>
          ))}

          {!visible.length && <div className="empty">No matching trainers.</div>}
        </div>

        <PaginationControls {...pagination} onPage={pagination.setPage} />
      </Panel>
    </>
  )
}

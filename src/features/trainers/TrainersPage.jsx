import SelectField from '../../components/SelectField.jsx'
import usePageState from '../../hooks/usePageState.js'
import { useMemo, useState } from 'react'
import Panel from '../../components/Panel.jsx'
import PaginationControls from '../../components/PaginationControls.jsx'
import { isActive, visibleTrainersForOwner } from '../../app/status.js'
import usePagination from '../../hooks/usePagination.js'

export default function TrainersPage({ trainers, onOpen, onAdd }) {
  const [query, setQuery] = usePageState('TrainersPage.query', '')
  const [searchOpen, setSearchOpen] = useState(false)
  const [statusFilter, setStatusFilter] = usePageState('TrainersPage.statusFilter', 'all')
  const [typeFilter, setTypeFilter] = usePageState('TrainersPage.typeFilter', '')
  const [genderFilter, setGenderFilter] = usePageState('TrainersPage.genderFilter', '')

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
      <div className="page-head directory-page-head">
        <div>
          <span className="eyebrow">Operations</span>
          <h1>Trainers</h1>
        </div>
        <button type="button" className="onboarding-button primary" onClick={onAdd}>Add New Trainer</button>
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

          <SelectField
            aria-label="Filter trainers by status"
            value={statusFilter}
            onChange={event => setStatusFilter(event.target.value)}
          >
            <option value="all">All status</option>
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
          </SelectField>

          <SelectField
            aria-label="Filter trainers by type"
            value={typeFilter}
            onChange={event => setTypeFilter(event.target.value)}
          >
            <option value="">All types</option>
            {types.map(type => <option key={type} value={type}>{type}</option>)}
          </SelectField>

          <SelectField
            aria-label="Filter trainers by gender"
            value={genderFilter}
            onChange={event => setGenderFilter(event.target.value)}
          >
            <option value="">All genders</option>
            <option value="Female">Female</option>
            <option value="Male">Male</option>
            <option value="Other">Other</option>
            <option value="Prefer not to say">Prefer not to say</option>
          </SelectField>
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
                className="secondary-button small compact-view"
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

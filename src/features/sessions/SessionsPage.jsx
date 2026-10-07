import { managesOperations } from '../../app/permissions.js'
import SelectField from '../../components/SelectField.jsx'
import usePageState from '../../hooks/usePageState.js'
import { useCallback, useMemo } from 'react'
import Panel from '../../components/Panel.jsx'
import PaginationControls from '../../components/PaginationControls.jsx'
import { isOpenSession, sessionSequence, isSessionHistory, sortSessions, visibleSessionsForUser } from '../../app/sessionRules.js'
import { formatDate, weekday } from '../../utils/date.js'
import usePagination from '../../hooks/usePagination.js'
import DateFilterField from '../../components/DateFilterField.jsx'

export default function SessionsPage({ user, sessions, clients, trainers, today, onOpen }) {
  const [query, setQuery] = usePageState('SessionsPage.query', '')
  const [period, setPeriod] = usePageState('SessionsPage.period', 'upcoming')
  const [statusFilter, setStatusFilter] = usePageState('SessionsPage.statusFilter', '')
  const [fromDate, setFromDate] = usePageState('SessionsPage.fromDate', '')
  const [toDate, setToDate] = usePageState('SessionsPage.toDate', '')

  const clientName = useCallback(id => clients.find(client => client.id === id)?.name ?? 'Unknown client', [clients])
  const trainerName = useCallback(id => trainers.find(trainer => trainer.id === id)?.name ?? 'Unknown trainer', [trainers])

  const visible = useMemo(() => {
    const search = query.trim().toLowerCase()

    return sortSessions(visibleSessionsForUser(user, sessions), today, period).filter(session => {
      const history = isSessionHistory(session, today)
      if (period === 'upcoming' && history) return false
      if (period === 'history' && !history) return false
      if (statusFilter && session.status !== statusFilter) return false
      if (!isOpenSession(session) && fromDate && session.date < fromDate) return false
      if (!isOpenSession(session) && toDate && session.date > toDate) return false

      if (
        search &&
        !clientName(session.clientId).toLowerCase().includes(search) &&
        !trainerName(session.trainerId).toLowerCase().includes(search)
      ) return false

      return true
    })
  }, [clientName, fromDate, period, query, sessions, statusFilter, toDate, trainerName, user, today])

  const pagination = usePagination(
    visible,
    `${user.id}|${query}|${period}|${statusFilter}|${fromDate}|${toDate}`,
  )

  return (
    <>
      <div className="page-head compact-page-head">
        <div>
          <span className="eyebrow">Operations</span>
          <h1>Sessions</h1>
        </div>
      </div>

      <Panel>
        <div className="list-controls session-controls">
          <label className="filter-field session-search-field">
            <span className="filter-label">Search</span>
            <input
              aria-label="Search sessions"
              value={query}
              onChange={event => setQuery(event.target.value)}
              placeholder="Search client or trainer"
            />
          </label>

          <label className="filter-field">
            <span className="filter-label">Period</span>
            <SelectField
              aria-label="Filter sessions by period"
              value={period}
              onChange={event => setPeriod(event.target.value)}
            >
              <option value="all">All periods</option>
              <option value="upcoming">Upcoming</option>
              <option value="history">History</option>
            </SelectField>
          </label>

          <label className="filter-field">
            <span className="filter-label">Status</span>
            <SelectField
              aria-label="Filter sessions by status"
              value={statusFilter}
              onChange={event => setStatusFilter(event.target.value)}
            >
              <option value="">All status</option>
              <option value="not_planned">Not Planned</option>
              <option value="planned">Planned</option>
              <option value="completed">Completed</option>
            </SelectField>
          </label>

          <DateFilterField
            label="From"
            hint="Select start date"
            ariaLabel="Sessions from date"
            value={fromDate}
            max={toDate}
            onChange={setFromDate}
          />

          <DateFilterField
            label="To"
            hint="Select end date"
            ariaLabel="Sessions to date"
            value={toDate}
            min={fromDate}
            onChange={setToDate}
          />
        </div>

        <div className="compact-list session-compact-list" aria-label="Session list">
          <div className="compact-list-head session-compact-grid">
            <span>Date & time</span>
            <span>Client / Trainer</span>
            <span>View</span>
          </div>

          {pagination.items.map(session => (
              <article className={`compact-list-row session-compact-grid session-list-row ${isOpenSession(session) ? 'open-session-row' : ''}`} key={session.id}>
                <div className="session-date-cell">
                  <strong className="compact-primary">{isOpenSession(session) ? 'Date/time not set' : formatDate(session.date)}</strong>
                  <span className="compact-secondary">{isOpenSession(session) ? 'Schedule this open session' : `${weekday(session.date)} · ${session.from}–${session.to}`}</span>
                </div>

                <div className="session-client-cell">
                  <strong className="compact-primary">{clientName(session.clientId)}</strong>
                  {clients.find(client => client.id === session.clientId)?.status === 'inactive' && <span className="inline-inactive">Client inactive</span>}
                  <span className="compact-secondary">
                    {managesOperations(user) ? `Trainer: ${trainerName(session.trainerId)} · ` : ''}
                    {sessionSequence(session)} / {session.packageTotal}
                  </span>
                </div>

                <div className="session-action-cell">
                  <button
                    type="button"
                    className="secondary-button small compact-view session-view-button"
                    aria-label={`View session for ${clientName(session.clientId)} ${isOpenSession(session) ? 'with date/time not set' : `on ${formatDate(session.date)}`}`}
                    onClick={() => onOpen(session.id)}
                  >
                    View
                  </button>
                </div>
              </article>
          ))}

          {!visible.length && <div className="empty">No matching sessions.</div>}
        </div>

        <PaginationControls {...pagination} onPage={pagination.setPage} />
      </Panel>
    </>
  )
}

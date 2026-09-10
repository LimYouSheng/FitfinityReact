import Panel from '../../components/Panel.jsx'
import ModalPortal from '../../components/ModalPortal.jsx'
import StatusBadge from '../../components/StatusBadge.jsx'
import { calendarDays, calendarPeriods, calendarSessions, shiftCalendarDate } from '../../app/calendar.js'
import { sessionStatus } from '../../app/sessionRules.js'
import { formatDate, parseDateOnly, weekday } from '../../utils/date.js'

export default function DashboardPage({ user, sessions, clients, trainers, today, state, onState, onOpenSession, onAddClient, onAddTrainer, renewals, selectedDay, onOpenDay, onCloseDay }) {
  const { mode } = state
  const date = state.date.slice(0, 4) === today.slice(0, 4) ? state.date : today
  const trainerWeek = user.role === 'trainer' && mode === 'week'
  const dates = calendarDays(date, mode)
  const monthStartColumn = mode === 'month' ? (parseDateOnly(dates[0]).getUTCDay() + 6) % 7 + 1 : undefined
  const records = calendarSessions(sessions, dates)
  const dayRecords = selectedDay ? calendarSessions(sessions, [selectedDay]) : []
  const periods = calendarPeriods(date, mode, today)
  const periodValue = mode === 'month' ? `${date.slice(0, 7)}-01` : date
  const rangeLabel = mode === 'month' ? formatDate(periodValue).slice(3) : `${formatDate(dates[0])} – ${formatDate(dates.at(-1))}`
  const change = patch => onState({ ...state, date, ...patch })
  const shifted = amount => shiftCalendarDate(date, mode === 'month' ? amount : amount * 7, mode === 'month' ? 'month' : 'day')
  const allowed = value => value.slice(0, 4) === today.slice(0, 4)
  const move = amount => {
    const next = shifted(amount)
    if (allowed(next)) change({ date: next })
  }
  const entries = value => records.filter(session => session.date === value)
  const trainerName = id => trainers.find(trainer => trainer.id === id)?.name ?? 'Trainer unavailable'
  const dayGroups = user.role === 'owner' ? [...new Set(dayRecords.map(session => session.trainerId))].map(id => ({
    id, name: trainerName(id), sessions: dayRecords.filter(session => session.trainerId === id),
  })) : []
  const event = session => {
    const clientRecord = clients.find(client => client.id === session.clientId)
    const client = clientRecord?.name ?? 'Client unavailable'
    const status = sessionStatus(session.status)
    return <button type="button" className="calendar-event" key={session.id} aria-label={`${session.from}–${session.to}, ${client}, ${status.label}`} onClick={() => onOpenSession(session.id)}>
      <strong>{session.from}–{session.to}</strong>
      <span className="calendar-event-client">{client}{clientRecord?.status === 'inactive' && <small className="inline-inactive">Client inactive</small>}</span>
      <StatusBadge tone={status.tone} className="calendar-event-status">{status.label}</StatusBadge>
      <span aria-hidden="true">›</span>
    </button>
  }
  return (
    <>
      <div className="page-head dashboard-page-head">
        <div>
          <span className="eyebrow">Operations</span>
          <h1>{user.role === 'owner' ? 'Owner Dashboard' : 'Trainer Dashboard'}</h1>
        </div>
        {user.role === 'owner' && (
          <div className="dashboard-quick-actions">
            <button type="button" className="onboarding-button primary" onClick={onAddClient}>Add Client</button>
            <button type="button" className="onboarding-button primary" onClick={onAddTrainer}>Add Trainer</button>
          </div>
        )}
      </div>

      <div className="dashboard-sections">
        {renewals}
        <Panel>
          <div className="section-head calendar-header">
            <h2>Calendar</h2>
            <div className="calendar-modes" aria-label="Calendar view">
              <button type="button" aria-pressed={mode === 'week'} onClick={() => change({ mode: 'week' })}>Weekly</button>
              <button type="button" aria-pressed={mode === 'month'} onClick={() => change({ mode: 'month' })}>Monthly</button>
            </div>
          </div>

          <div className="calendar-toolbar">
            <button type="button" className="secondary-button" aria-label="Previous calendar period" disabled={!allowed(shifted(-1))} onClick={() => move(-1)}>‹</button>
            <select className="calendar-range" aria-label={mode === 'month' ? 'Calendar month' : 'Calendar week'} value={periodValue} onChange={event => change({ date: event.target.value })}>
              {!periods.some(period => period.value === periodValue) && <option hidden value={periodValue}>{rangeLabel}</option>}
              {periods.map(period => <option key={period.value} value={period.value}>{period.label}</option>)}
            </select>
            <button type="button" className="secondary-button" aria-label="Next calendar period" disabled={!allowed(shifted(1))} onClick={() => move(1)}>›</button>
          </div>
          <div className={`calendar-grid calendar-${mode}${trainerWeek ? ' calendar-agenda' : ''}`} aria-label={`${mode === 'week' ? 'Weekly' : 'Monthly'} calendar`}>
            {dates.map((day, index) => {
              const daySessions = entries(day)
              const agendaHeading = <span>{day === today && <span className="calendar-today-label">Today</span>}{weekday(day)}, {formatDate(day)}</span>
              return <section key={day} data-date={day} aria-current={day === today ? 'date' : undefined} style={index === 0 && mode === 'month' ? { gridColumnStart: monthStartColumn } : undefined} className={`calendar-day ${day < today ? 'calendar-past' : ''} ${day === today ? 'calendar-today' : ''}`}>
                {trainerWeek ? <>
                  {daySessions.length > 0 ? <button type="button" className="calendar-agenda-date" aria-label={`Show sessions for ${day}`} aria-haspopup="dialog" aria-current={day === today ? 'date' : undefined} onClick={() => onOpenDay(day)}>
                    {agendaHeading}<span className="calendar-date-action" aria-hidden="true">View day ›</span>
                  </button> : <div className="calendar-agenda-date">{agendaHeading}</div>}
                  <div className="calendar-day-events">{daySessions.map(event)}{!daySessions.length && <p className="empty">No sessions</p>}</div>
                </> : <>
                  <div className="calendar-day-head"><span>{day === today ? 'Today' : weekday(day).slice(0, 3)}</span><time dateTime={day}>{Number(day.slice(-2))}</time></div>
                  {daySessions.length > 0 && <button type="button" className="calendar-date" aria-label={`Show sessions for ${day}`} aria-describedby={`calendar-count-${day} calendar-count-label-${day}`} aria-haspopup="dialog" aria-current={day === today ? 'date' : undefined} onClick={() => onOpenDay(day)}>
                    <strong id={`calendar-count-${day}`}>{daySessions.length}</strong>
                    <span className="calendar-count-label" id={`calendar-count-label-${day}`}>{daySessions.length === 1 ? 'session' : 'sessions'}</span>
                    <small className="calendar-date-action" aria-hidden="true">View day</small>
                  </button>}
                </>}
              </section>
            })}
          </div>
        </Panel>
      </div>
      {selectedDay && <ModalPortal>
        <div className="modal-backdrop" role="presentation" onClick={onCloseDay}>
          <section className="modal-card calendar-day-dialog" role="dialog" aria-modal="true" aria-label="Calendar sessions"
            onClick={event => event.stopPropagation()} onKeyDown={event => { if (event.key === 'Escape') { event.stopPropagation(); onCloseDay() } }}>
            <div className="modal-head">
              <h2>{weekday(selectedDay)}, {formatDate(selectedDay)}</h2>
              <button type="button" className="icon-button" aria-label="Close calendar sessions" onClick={onCloseDay}>×</button>
            </div>
            <div className="modal-body calendar-day-list">
              {user.role === 'owner' ? dayGroups.map(group => <section className="calendar-trainer-group" key={group.id} aria-label={`${group.name} sessions`}>
                <h3>{group.name}</h3>
                {group.sessions.map(event)}
              </section>) : dayRecords.map(event)}
              {!dayRecords.length && <p className="empty">No sessions for this day.</p>}
            </div>
          </section>
        </div>
      </ModalPortal>}
    </>
  )
}

import Panel from '../../components/Panel.jsx'
import ModalPortal from '../../components/ModalPortal.jsx'
import { calendarDays, calendarSessions, shiftCalendarDate } from '../../app/calendar.js'
import { formatDate, weekday } from '../../utils/date.js'

const DAY_PREVIEW_LIMIT = 5

export default function DashboardPage({ user, sessions, clients, trainers, today, state, onState, onOpenSession, onAddClient, onAddTrainer, renewals, selectedDay, onOpenDay, onCloseDay }) {
  const { mode, date } = state
  const dates = calendarDays(date, mode)
  const records = calendarSessions(sessions, dates)
  const dayRecords = selectedDay ? calendarSessions(sessions, [selectedDay]) : []
  const change = patch => onState({ ...state, ...patch })
  const move = amount => {
    const next = shiftCalendarDate(date, mode === 'month' ? amount : amount * 7, mode === 'month' ? 'month' : 'day')
    change({ date: next })
  }
  const entries = value => records.filter(session => session.date === value)
  const event = session => <button type="button" className="calendar-event" key={session.id} onClick={() => onOpenSession(session.id)}>
    <strong>{session.from}–{session.to}</strong>
    <span>{clients.find(client => client.id === session.clientId)?.name ?? 'Client unavailable'}</span>
    {user.role === 'owner' && <small>{trainers.find(trainer => trainer.id === session.trainerId)?.name ?? 'Trainer unavailable'}</small>}
  </button>
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
          <div className="section-head">
            <h2>Calendar</h2>
            <div className="calendar-modes" aria-label="Calendar view">
              <button type="button" aria-pressed={mode === 'week'} onClick={() => change({ mode: 'week' })}>Weekly</button>
              <button type="button" aria-pressed={mode === 'month'} onClick={() => change({ mode: 'month' })}>Monthly</button>
            </div>
          </div>

          <div className="calendar-toolbar">
            <button type="button" className="secondary-button" aria-label="Previous calendar period" onClick={() => move(-1)}>‹</button>
            <strong aria-live="polite">{mode === 'month' ? formatDate(`${date.slice(0, 7)}-01`).slice(3) : `${formatDate(dates[0])} – ${formatDate(dates.at(-1))}`}</strong>
            <button type="button" className="secondary-button" aria-label="Next calendar period" onClick={() => move(1)}>›</button>
            <label>Date<input type="date" aria-label="Calendar date" value={date} onChange={event => { if (event.target.value) change({ date: event.target.value }) }} /></label>
          </div>
          <div className={`calendar-grid calendar-${mode}`} aria-label={`${mode === 'week' ? 'Weekly' : 'Monthly'} calendar`}>
            {dates.map(day => {
              const daySessions = entries(day)
              const remaining = daySessions.length - DAY_PREVIEW_LIMIT
              return <section key={day} className={`calendar-day ${day === today ? 'calendar-today' : ''} ${day.slice(0, 7) !== date.slice(0, 7) ? 'calendar-adjacent' : ''}`}>
                <button type="button" className="calendar-date" aria-label={`Show sessions for ${day}`} aria-haspopup="dialog" aria-current={day === today ? 'date' : undefined} onClick={() => onOpenDay(day)}>
                  <span>{weekday(day).slice(0, 3)}</span><strong>{Number(day.slice(-2))}</strong>
                  <small>{daySessions.length} {daySessions.length === 1 ? 'session' : 'sessions'}</small>
                  <span className="calendar-date-action" aria-hidden="true">View <span>day </span>›</span>
                </button>
                <div className="calendar-day-events">{daySessions.slice(0, DAY_PREVIEW_LIMIT).map(event)}{!daySessions.length && mode === 'week' && <p className="empty">No sessions</p>}</div>
                {remaining > 0 && <button type="button" className="calendar-more" aria-haspopup="dialog" aria-label={`Show ${remaining} more sessions for ${day}`} onClick={() => onOpenDay(day)}>+{remaining} more</button>}
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
              {dayRecords.map(event)}
              {!dayRecords.length && <p className="empty">No sessions for this day.</p>}
            </div>
          </section>
        </div>
      </ModalPortal>}
    </>
  )
}

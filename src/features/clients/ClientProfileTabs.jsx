import { weeklyFrequencyLabel } from '../../app/packages.js'
import Panel from '../../components/Panel.jsx'
import PaginationControls from '../../components/PaginationControls.jsx'
import usePagination from '../../hooks/usePagination.js'
import { formatDate, weekday } from '../../utils/date.js'
import { packageDayProgress } from '../../utils/date.js'
import StrengthProgress from './StrengthProgress.jsx'

function PackageTab({ client, today }) {
  const remaining = Math.max(0, client.package.total - client.package.used)
  const usage = client.package.total ? Math.round((client.package.used / client.package.total) * 100) : 0
  const history = client.packageHistory ?? []
  const pagination = usePagination(history, client.id)
  const elapsedDays = packageDayProgress(client.package.startDate, client.package.validityDays, today)

  return (
    <div className="stack-gap">
      <Panel>
        <div className="section-head"><div><h2>Current Package</h2>{client.package.name && <p>{client.package.name}</p>}</div></div>
        <div className="client-package-grid">
          <div><span>Total sessions</span><strong>{client.package.total}</strong></div>
          <div><span>Completed</span><strong>{client.package.used}</strong></div>
          <div><span>Remaining</span><strong>{remaining}</strong></div>
          <div><span>Frequency</span><strong>{weeklyFrequencyLabel(client.package.sessionsPerWeek, true)}</strong></div>
        </div>
        <div className="client-package-progress" aria-label={`${usage}% package used`}>
          <span style={{ width: `${usage}%` }} />
        </div>
        <p className="helper">Free gym package: <strong>{client.package.freeGym ? 'Included' : 'Not included'}</strong></p>
        <p className="helper">{formatDate(client.package.startDate)} – {formatDate(client.package.endDate)} · {elapsedDays} / {client.package.validityDays} days</p>
      </Panel>

      <Panel>
        <div className="section-head"><h2>Past Packages</h2></div>
        <div className="client-record-list">
          {pagination.items.map(item => (
            <article className="client-record-row" key={item.id}>
              <div><strong>{item.total}-session package</strong><span>{formatDate(item.startDate)} – {formatDate(item.endDate)}</span></div>
              <span>{item.used} / {item.total} used</span>
            </article>
          ))}
          {!history.length && <div className="empty">No past packages.</div>}
        </div>
        <PaginationControls {...pagination} onPage={pagination.setPage} />
      </Panel>
    </div>
  )
}

function SessionsTab({ title, sessions, trainers, emptyCopy, onOpenSession }) {
  const pagination = usePagination(sessions, `${title}|${sessions.length}`)
  const trainerName = id => trainers.find(item => item.id === id)?.name ?? 'Unknown trainer'

  return (
    <Panel>
      <div className="section-head"><h2>{title}</h2></div>
      <div className="client-record-list" aria-label={title}>
        {pagination.items.map(session => (
          <article className="client-record-row" key={session.id}>
            <div>
              <strong>{weekday(session.date)}, {formatDate(session.date)} · {session.from}–{session.to}</strong>
              <span>{trainerName(session.trainerId)} · Session {session.sessionNumber} / {session.packageTotal}</span>
            </div>
            <button type="button" className="btn small" onClick={() => onOpenSession(session.id)}>View</button>
          </article>
        ))}
        {!sessions.length && <div className="empty">{emptyCopy}</div>}
      </div>
      <PaginationControls {...pagination} onPage={pagination.setPage} />
    </Panel>
  )
}

export default function ClientProfileTabs({ tab, client, sessions, trainers, today, onOpenSession }) {
  const clientSessions = sessions.filter(session => session.clientId === client.id)
  const history = clientSessions
    .filter(session => session.status === 'completed' || session.date < today)
    .sort((a, b) => `${b.date}T${b.from}`.localeCompare(`${a.date}T${a.from}`))
  const upcoming = clientSessions
    .filter(session => session.status !== 'completed' && session.date >= today)
    .sort((a, b) => `${a.date}T${a.from}`.localeCompare(`${b.date}T${b.from}`))

  if (tab === 'package') return <PackageTab client={client} today={today} />
  if (tab === 'history') return <SessionsTab title="Session History" sessions={history} trainers={trainers} emptyCopy="No completed sessions." onOpenSession={onOpenSession} />
  if (tab === 'upcoming') return <SessionsTab title="Upcoming Sessions" sessions={upcoming} trainers={trainers} emptyCopy="No upcoming sessions." onOpenSession={onOpenSession} />
  if (tab === 'progress') return <StrengthProgress client={client} />
  return null
}

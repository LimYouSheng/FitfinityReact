import { sessionStatus } from '../../app/sessionRules.js'
import { weeklyFrequencyLabel } from '../../app/packages.js'
import Panel from '../../components/Panel.jsx'
import PaginationControls from '../../components/PaginationControls.jsx'
import usePagination from '../../hooks/usePagination.js'
import usePageState from '../../hooks/usePageState.js'
import { formatDate, formatTimestamp, weekday } from '../../utils/date.js'
import { packageDayProgress } from '../../utils/date.js'
import { useState } from 'react'
import PackageProgress from './PackageProgress.jsx'
import RenewPackageDialog from './RenewPackageDialog.jsx'
import ConfirmDialog from '../../components/ConfirmDialog.jsx'
import StatusBadge from '../../components/StatusBadge.jsx'
import { businessClock } from '../../app/clock.js'
import { deletablePackageSessions, pastClientPackages, packageForRecord } from '../../app/clientPackages.js'

function PackageTab({ client, user, trainers, sessions, packages, policy, today, onRenewPackage, onDeactivatePackage, onDeletePackageSessions, packageCreditTransactions = [] }) {
  const [deletePackage, setDeletePackage] = useState(null)
  const [renewOpen, setRenewOpen] = useState(false)
  const [deactivateOpen, setDeactivateOpen] = useState(null)
  const [deleteUpcoming, setDeleteUpcoming] = useState(false)
  const [deactivating, setDeactivating] = useState(false)
  const [deactivationError, setDeactivationError] = useState('')
  const clock = businessClock(new Date(), policy.timeZone)
  const eligibleCount = purchased => deletablePackageSessions(client, purchased.id, sessions, packageCreditTransactions, clock).length
  const remaining = Math.max(0, client.package.total - client.package.used)
  const usage = client.package.total ? Math.round((client.package.used / client.package.total) * 100) : 0
  const history = pastClientPackages(client)
  const additional = (client.additionalPackages ?? []).filter(item => item.status !== 'inactive')
  const pagination = usePagination(history, client.id, 'client.packageHistoryPage')
  const elapsedDays = packageDayProgress(client.package.startDate, client.package.validityDays, today)

  return (
    <div className="stack-gap">
      {renewOpen && client.status !== 'inactive' && <RenewPackageDialog client={client} trainers={trainers} sessions={sessions} packages={packages} policy={policy} today={today} onSave={onRenewPackage} onClose={() => setRenewOpen(false)} />}
      <Panel>
        <div className="section-head package-section-head"><div><h2>Current Package</h2>{client.package.status !== 'inactive' && client.package.name && <p>{client.package.name}</p>}</div>
          {user.role === 'owner' && client.status !== 'inactive' && <div className="package-actions">
            <button type="button" className="secondary-button" onClick={() => setRenewOpen(true)}>Add Package</button>
            {client.package.status !== 'inactive' && <button type="button" className="secondary-button" onClick={() => { setDeleteUpcoming(false); setDeactivationError(''); setDeactivateOpen(client.package) }}>Deactivate Package</button>}
          </div>}
        </div>
        {client.package.status === 'inactive' ? <p className="empty">No active current package.</p> : <>
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
        </>}
      </Panel>

      {additional.length > 0 && <Panel>
        <div className="section-head"><h2>Additional Packages</h2></div>
        <div className="client-record-list" aria-label="Additional packages">
          {additional.map(item => <article className="client-record-row" key={item.id}>
            <div><strong>{item.name ?? `${item.total} Sessions`}</strong>
              <span>{formatDate(item.startDate)} – {formatDate(item.endDate)}</span>
              <span>{trainers.find(trainer => trainer.id === item.trainerId)?.name ?? 'Unassigned'} · {weeklyFrequencyLabel(item.sessionsPerWeek, true)}</span>
              <span>{item.used} / {item.total} used</span>
            </div>
            {user.role === 'owner' && client.status !== 'inactive' && <button type="button" className="secondary-button" onClick={() => {
              setDeleteUpcoming(false); setDeactivationError(''); setDeactivateOpen(item)
            }}>Deactivate Package</button>}
          </article>)}
        </div>
      </Panel>}
      <Panel>
        <div className="section-head"><h2>Past Packages</h2></div>
        <div className="client-record-list">
          {pagination.items.map(item => (
            <article className="client-record-row" key={item.id}>
              <div><strong>{item.name ?? `${item.total}-session package`}</strong><span>{formatDate(item.startDate)} – {formatDate(item.endDate)}</span>
                {item.status === 'inactive' && <><StatusBadge tone="amber">Inactive</StatusBadge>
                  <span>Deactivated <time dateTime={item.deactivatedAt}>{formatTimestamp(item.deactivatedAt, policy.timeZone)}</time> · {item.deactivatedBy?.name}</span>
                  {(item.sessionDeletionHistory ?? []).map(entry => <span key={entry.at}>
                    {entry.sessionIds.length} upcoming sessions deleted · <time dateTime={entry.at}>{formatTimestamp(entry.at, policy.timeZone)}</time> · {entry.by.name}
                  </span>)}
                  {user.role === 'owner' && <button type="button" className="text-action" disabled={!eligibleCount(item)} onClick={() => { setDeactivationError(''); setDeletePackage(item) }}>Delete Upcoming Sessions ({eligibleCount(item)})</button>}
                </>}
              </div>
              <span>{item.used} / {item.total} used</span>
            </article>
          ))}
          {!history.length && <div className="empty">No past packages.</div>}
        </div>
        <PaginationControls {...pagination} onPage={pagination.setPage} />
      </Panel>
      <ConfirmDialog open={Boolean(deletePackage)} title="Delete Upcoming Package Sessions?" confirmLabel={deactivating ? 'Deleting…' : 'Delete Sessions'} danger
        confirmDisabled={deactivating} onCancel={() => { if (!deactivating) setDeletePackage(null) }} onConfirm={async () => {
          if (deactivating || !deletePackage) return
          setDeactivating(true)
          try { await onDeletePackageSessions({ packageId: deletePackage.id }); setDeletePackage(null) }
          catch (error) { setDeactivationError(error.message || 'Session deletion failed.') }
          finally { setDeactivating(false) }
        }}>
        {deletePackage && <p>Permanently delete {eligibleCount(deletePackage)} unacknowledged upcoming sessions from {deletePackage.name ?? `${deletePackage.total} Sessions`}?</p>}
        {deactivationError && <p role="alert">{deactivationError}</p>}
      </ConfirmDialog>
      <ConfirmDialog open={Boolean(deactivateOpen)} title="Deactivate Package?" confirmLabel={deactivating ? 'Deactivating…' : 'Deactivate Package'} danger
        confirmDisabled={deactivating} onCancel={() => { if (!deactivating) setDeactivateOpen(null) }} onConfirm={async () => {
          if (deactivating || !deactivateOpen) return
          setDeactivating(true)
          try { await onDeactivatePackage({ packageId: deactivateOpen.id, deleteUpcomingSessions: deleteUpcoming }); setDeactivateOpen(null) }
          catch (error) { setDeactivationError(error.message || 'Package deactivation failed.') }
          finally { setDeactivating(false) }
        }}>
        <p>{deactivateOpen?.name ?? `${deactivateOpen?.total} Sessions`} · {formatDate(deactivateOpen?.startDate)} – {formatDate(deactivateOpen?.endDate)}</p>
        <label className="export-summary-option"><input type="checkbox" checked={deleteUpcoming} disabled={deactivating}
          onChange={event => setDeleteUpcoming(event.target.checked)} />Permanently delete unacknowledged upcoming sessions</label>
        {deactivationError && <p role="alert">{deactivationError}</p>}
      </ConfirmDialog>
    </div>
  )
}

function SessionsTab({ title, client, sessions, trainers, emptyCopy, onOpenSession }) {
  const scope = `client.${client.id}.${title}`
  const [fromDate, setFromDate] = usePageState(`${scope}.from`, '')
  const [toDate, setToDate] = usePageState(`${scope}.to`, '')
  const filtered = sessions.filter(session => (!fromDate || session.date >= fromDate) && (!toDate || session.date <= toDate))
  const pagination = usePagination(filtered, `${client.id}|${title}|${fromDate}|${toDate}`, `${scope}.page`)
  const trainerName = id => trainers.find(item => item.id === id)?.name ?? 'Unknown trainer'

  return (
    <Panel>
      <div className="section-head"><h2>{title}</h2></div>
      <div className="session-date-filters" aria-label={`${title} date filters`}>
        <label><span>From</span><input type="date" aria-label={`${title} from`} value={fromDate} max={toDate || undefined} onChange={event => setFromDate(event.target.value)} /></label>
        <label><span>To</span><input type="date" aria-label={`${title} to`} value={toDate} min={fromDate || undefined} onChange={event => setToDate(event.target.value)} /></label>
      </div>
      <div className="client-record-list" aria-label={title}>
        {pagination.items.map(session => (
          <article className="client-record-row" key={session.id}>
            <div>
              <strong>{weekday(session.date)}, {formatDate(session.date)} · {session.from}–{session.to}</strong>
              <span>{trainerName(session.trainerId)} · Session {session.sessionNumber} / {packageForRecord(client, session)?.total ?? '—'}</span>
              <span>{session.status === 'cancelled' ? 'Cancelled' : sessionStatus(session.status).label}{session.acknowledgement?.method === 'late_no_show' ? ' · Late/no-show' : ''}
                {packageForRecord(client, session) && ` · Package started ${formatDate(packageForRecord(client, session).startDate)}`}</span>
            </div>
            <button type="button" className="btn small" onClick={() => onOpenSession(session.id)}>View</button>
          </article>
        ))}
        {!filtered.length && <div className="empty">{fromDate || toDate ? 'No sessions in this date range.' : emptyCopy}</div>}
      </div>
      <PaginationControls {...pagination} onPage={pagination.setPage} />
    </Panel>
  )
}

export default function ClientProfileTabs({ progressPackageId, onOpenProgressPackage, tab, user, client, sessions, trainers, today, onOpenSession, timeZone, onRecordProgressReport, onLoadProgressReportHistory, packages, policy, onRenewPackage, onDeactivatePackage, onDeletePackageSessions, packageCreditTransactions = [] }) {
  const clientSessions = sessions.filter(session => session.clientId === client.id && (user.role === 'owner' || session.trainerId === user.trainerId))
  const history = clientSessions
    .filter(session => session.status === 'completed' || session.date < today)
    .sort((a, b) => `${b.date}T${b.from}`.localeCompare(`${a.date}T${a.from}`))
  const upcoming = clientSessions
    .filter(session => session.status !== 'completed' && session.date >= today)
    .sort((a, b) => `${a.date}T${a.from}`.localeCompare(`${b.date}T${b.from}`))

  if (tab === 'package') return <PackageTab client={client} today={today} user={user} trainers={trainers} sessions={clientSessions} packages={packages} policy={policy} onRenewPackage={onRenewPackage} onDeactivatePackage={onDeactivatePackage} onDeletePackageSessions={onDeletePackageSessions} packageCreditTransactions={packageCreditTransactions} />
  if (tab === 'history') return <SessionsTab title="Session History" client={client} sessions={history} trainers={trainers} emptyCopy="No completed sessions." onOpenSession={onOpenSession} />
  if (tab === 'upcoming') return <SessionsTab title="Upcoming Sessions" client={client} sessions={upcoming} trainers={trainers} emptyCopy="No upcoming sessions." onOpenSession={onOpenSession} />
  if (tab === 'progress') return <PackageProgress packageId={progressPackageId} onOpenPackage={onOpenProgressPackage} client={client} sessions={sessions} user={user} timeZone={timeZone} onRecordAction={onRecordProgressReport} onLoadHistory={onLoadProgressReportHistory} />
  return null
}

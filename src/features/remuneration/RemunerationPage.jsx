import usePageState from '../../hooks/usePageState.js'
import { useRef, useState } from 'react'
import Panel from '../../components/Panel.jsx'
import StatusBadge from '../../components/StatusBadge.jsx'
import PaginationControls from '../../components/PaginationControls.jsx'
import usePagination from '../../hooks/usePagination.js'
import { useActionConfirmation } from '../../components/ActionConfirmationProvider.jsx'
import { useNotifications } from '../../components/NotificationProvider.jsx'
import { formatMoney } from '../../app/remuneration.js'
import { formatDate } from '../../utils/date.js'

const tones = { Approved: 'green', 'Pending approval': 'amber', 'Pending review': 'red', 'In progress': 'blue' }
const cycleLabel = cycle => { return `${formatDate(cycle.start)} – ${formatDate(cycle.end)}` }
function MoneyToggle({ hidden, onClick }) {
  return <button type="button" className="secondary-button remuneration-money-toggle" aria-label={hidden ? 'Show remuneration amounts' : 'Hide remuneration amounts'} aria-pressed={hidden} onClick={onClick}>
    <svg viewBox="0 0 24 24" width="17" height="17" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z" /><circle cx="12" cy="12" r="3" />{hidden && <path d="m3 3 18 18" />}</svg>
    {hidden ? 'Show amounts' : 'Hide amounts'}
  </button>
}
function Totals({ records, money }) {
  const total = key => records.reduce((sum, record) => sum + record[key], 0)
  return <div className="remuneration-totals">
    <div><span>Completed sessions</span><strong>{total('sessions')}</strong></div>
    <div><span>Training hours</span><strong>{(total('minutes') / 60).toFixed(1)}</strong></div>
    <div><span>{records.some(record => record.reviewCount) ? 'Calculated amount so far' : 'Remuneration'}</span><strong>{money(total('amountCents'))}</strong></div>
  </div>
}

function TrainerBreakdown({ record, owner, hidden, money, onApprove, onOpenSession }) {
  const confirm = useActionConfirmation()
  const { notify } = useNotifications()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const operationPending = useRef(false)
  const pagination = usePagination(record.rows, `${record.cycle.key}/${record.trainerId}`, 'remuneration.sessionPage')
  const approved = record.status === 'Approved'

  const approve = async () => {
    if (operationPending.current) return
    if (hidden) {
      notify({ tone: 'info', message: 'Show amounts to review the total before approving.' })
      return
    }
    operationPending.current = true
    setBusy(true); setError('')
    try {
      const accepted = await confirm({
        title: 'Approve trainer remuneration?',
        message: `Approve ${record.sessions} completed sessions for ${record.trainerName}, totalling ${money(record.amountCents)}. This stores the calculated breakdown and notifies the trainer.`,
        confirmLabel: 'Approve Remuneration',
      })
      if (!accepted) return
      await onApprove(record.cycle.key, record.trainerId, record.revision)
    } catch (failure) {
      setError(failure.message || 'Could not approve. Try again.')
    } finally { operationPending.current = false; setBusy(false) }
  }

  return <>
    <div className="remuneration-section-head"><h2>{record.trainerName}</h2><StatusBadge tone={tones[record.status]}>{record.status}</StatusBadge></div>
    <Totals records={[record]} money={money} />
    {record.changed && <p className="validation-copy" role="alert">Session records changed after approval. This page keeps the approved breakdown; the current records have {record.current.sessions} sessions. The changes need a separate owner review.</p>}
    {approved && <p className="muted">Approved {formatDate(record.approvedAt.slice(0, 10))}.</p>}
    {!approved && record.closed && record.reviewCount > 0 && <p className="validation-copy" role="alert">{record.reviewCount} session(s) need attention before approval. Check session completion, dates and the trainer’s preset rates.</p>}
    <div className="compact-list remuneration-session-list" aria-label="Cycle session breakdown">
      <div className="compact-list-head remuneration-session-grid" aria-hidden="true"><span>Client</span><span>Date</span><span>Amount</span><span>View</span></div>
      {pagination.items.map(row => <article className="compact-list-row remuneration-session remuneration-session-grid" key={row.sessionId} data-session-id={row.sessionId}>
        <strong className="remuneration-session-client">{row.clientName}</strong>
        <time className="remuneration-session-date" dateTime={row.date}>{formatDate(row.date)}</time>
        <strong className="remuneration-session-rate">{row.amountCents === null ? '—' : money(row.amountCents)}</strong>
        <button type="button" className="secondary-button compact-view" aria-label={`View Session · ${row.clientName} · ${formatDate(row.date)}`} onClick={() => onOpenSession(row.sessionId)}>View</button>
      </article>)}
      {!record.rows.length && <p className="empty">No sessions in this cycle.</p>}
    </div>
    <PaginationControls {...pagination} onPage={pagination.setPage} />
    {error && <p role="alert" className="validation-copy">{error}</p>}
    {owner && !approved && <div className="remuneration-actions">
      <button className="primary-button" type="button" disabled={busy || !record.closed || !record.sessions || Boolean(record.reviewCount)} onClick={approve}>Approve Remuneration</button>
    </div>}
  </>
}

function PayCycleList({ views, user, money, onNavigate }) {
  const pagination = usePagination(views, user.id, 'remuneration.cyclePage')
  return <Panel>
    <div className="compact-list" aria-label="Pay cycles">
      <div className="compact-list-head remuneration-cycle-grid" aria-hidden="true"><span>Pay cycle</span><span>Completed</span><span>Remuneration</span><span>View</span></div>
      {pagination.items.map(view => <article className="compact-list-row remuneration-cycle-grid" key={view.key} data-cycle-key={view.key}>
        <div className="remuneration-cycle-name"><strong>{cycleLabel(view.cycle)}</strong>{view.isCurrent && <StatusBadge tone="blue">Current</StatusBadge>}</div>
        <span>{view.trainers.reduce((total, record) => total + record.sessions, 0)}</span>
        <span>{money(view.trainers.reduce((total, record) => total + record.amountCents, 0))}</span>
        <button type="button" className="secondary-button compact-view" aria-label={`View pay cycle ${view.key}`} onClick={() => onNavigate(`remuneration/${view.key}`)}>View</button>
      </article>)}
      {!views.length && <p className="empty">No pay cycles available.</p>}
    </div>
    <PaginationControls {...pagination} onPage={pagination.setPage} />
  </Panel>
}

function TrainerList({ view, user, money, onNavigate }) {
  const records = view.trainers
  const pagination = usePagination(records, `${user.id}/${view.key}`, 'remuneration.trainerPage')
  return <>
    <Totals records={records} money={money} />
    <div className="compact-list remuneration-table" role="table" aria-label="Trainer remuneration">
      <div className="compact-list-head remuneration-trainer-grid" role="row"><span role="columnheader">Name</span><span role="columnheader">Sessions</span><span role="columnheader">Remuneration</span><span role="columnheader">Status</span><span role="columnheader">View</span></div>
      {pagination.items.map(record => <div className="compact-list-row remuneration-trainer-grid remuneration-trainer-row" role="row" key={record.trainerId}>
        <strong role="cell">{record.trainerName}</strong><span role="cell" data-label="Sessions">{record.sessions}</span><span role="cell" data-label="Remuneration">{money(record.amountCents)}{record.reviewCount > 0 && <small>Partial</small>}</span><span role="cell" data-label="Status"><StatusBadge tone={tones[record.status]}>{record.status}</StatusBadge>{record.changed && <small>Review changes</small>}</span><span role="cell"><button type="button" className="secondary-button compact-view" aria-label={`View remuneration for ${record.trainerName}`} onClick={() => onNavigate(`remuneration/${view.key}/${record.trainerId}`)}>View</button></span>
      </div>)}
    </div>
    {!records.length && <p className="empty">No trainer remuneration in this cycle.</p>}
    <PaginationControls {...pagination} onPage={pagination.setPage} />
  </>
}

export default function RemunerationPage({ user, views, policy, cycleKey, trainerId, onNavigate, onApprove, onOpenSession }) {
  const [hidden, setHidden] = usePageState('RemunerationPage.hidden', true)
  const money = cents => hidden ? '••••' : formatMoney(cents, policy)
  const owner = user.role === 'owner'
  const view = views.find(view => view.key === cycleKey)
  const selectedId = owner ? trainerId : user.trainerId
  const selected = view?.trainers.find(record => record.trainerId === selectedId)
  const inaccessible = (cycleKey && !view) || (trainerId && !owner && trainerId !== user.trainerId) || (view && selectedId && !selected)
  return <div className="remuneration-page">
    <div className="page-head"><div><span className="eyebrow">Monthly pay cycles</span><h1>Remuneration</h1></div><MoneyToggle hidden={hidden} onClick={() => setHidden(value => !value)} /></div>
    {inaccessible ? <Panel><p>This remuneration record is unavailable for your account.</p><button className="secondary-button" onClick={() => onNavigate('remuneration')}>Back to Remuneration</button></Panel>
      : !cycleKey ? <PayCycleList views={views} user={user} money={money} onNavigate={onNavigate} />
        : <>
          <div className="remuneration-toolbar"><p className="remuneration-cycle-caption">{cycleLabel(view.cycle)}</p>{view.isCurrent && <StatusBadge tone="blue">Current</StatusBadge>}</div>
          <Panel>{selected ? <TrainerBreakdown key={`${view.key}/${selected.trainerId}`} record={selected} owner={owner} hidden={hidden} money={money} onApprove={onApprove} onOpenSession={onOpenSession} />
            : <TrainerList view={view} user={user} money={money} onNavigate={onNavigate} />}</Panel>
        </>}
  </div>
}

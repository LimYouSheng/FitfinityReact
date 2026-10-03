import Panel from '../../components/Panel.jsx'
import DateField from '../../components/DateField.jsx'
import SelectField from '../../components/SelectField.jsx'
import StatusBadge from '../../components/StatusBadge.jsx'
import { hasSessionAcknowledgement } from '../../app/signature.js'
import { formatDate, weekday } from '../../utils/date.js'

export default function SessionOverview({ session, client, trainer, trainers, purchased, clientInactive, packageInactive, status, pendingChanges, isOwner, sessionEditable, activeEditor, setActiveEditor, saving, setDetailsError, schedule, onOpenClient, onOpenTrainer }) {
  const { detailsDraft, setDetailsDraft, requestKind, setRequestKind, setTimeRequestDraft, setTrainerRequestId, timeChangeError, checkTimeRequest, saveDetails } = schedule

  const postponementError = !purchased || purchased.id !== client.package?.id ? 'Postpone is available only for the current package.' : timeChangeError

  return (
    <Panel className={`session-overview-panel ${isOwner ? 'owner' : 'trainer'} ${activeEditor === 'details' || requestKind ? 'editing-section' : ''}`}>
      <div className="section-head">
        <div className={`session-overview-heading ${pendingChanges.length ? 'has-pending-requests' : ''}`}>
          <h2>Session Overview</h2>
          <div className={`session-status-groups ${pendingChanges.length ? 'has-pending' : ''}`}>
            <div className="session-overview-statuses" aria-label="Session status summary">
              <StatusBadge tone={status.tone}>Session · {status.label}</StatusBadge>
              {session.status === 'completed'
                ? <StatusBadge tone={session.whatsappOpenedAt ? 'green' : 'amber'}>WhatsApp · {session.whatsappOpenedAt ? 'Opened' : 'Not opened'}</StatusBadge>
                : <StatusBadge tone={hasSessionAcknowledgement(session) ? 'green' : 'amber'}>{hasSessionAcknowledgement(session) ? 'Acknowledged' : 'Not acknowledged'}</StatusBadge>}
            </div>
            {pendingChanges.length > 0 && <div className="session-pending-statuses" aria-label="Pending session approvals">
              {pendingChanges.map(change => <StatusBadge key={change.kind} tone="amber">{change.label}</StatusBadge>)}
            </div>}
          </div>
        </div>
        <div className="session-detail-actions">
          <button type="button" className="secondary-button small" title={postponementError || undefined} disabled={saving || !sessionEditable || Boolean(activeEditor) || Boolean(requestKind) || Boolean(postponementError) || pendingChanges.length > 0} onClick={schedule.openPostponement}>Postpone</button>
          {isOwner ? (
            activeEditor === 'details' ? (
              <div className="inline-actions">
                <button type="button" className="text-action muted-action" disabled={saving} onClick={() => {
                  setDetailsDraft({ date: session.date, from: session.from, to: session.to, trainerId: session.trainerId })
                  setDetailsError('')
                  setActiveEditor(null)
                }}>Cancel</button>
                <button type="button" className="text-action" disabled={saving} onClick={saveDetails}>{saving ? 'Saving…' : 'Save'}</button>
              </div>
            ) : (
              <button type="button" className="text-action" disabled={!sessionEditable || Boolean(activeEditor)} onClick={() => {
                setDetailsError('')
                setActiveEditor('details')
              }}>Edit</button>
            )
          ) : (
            <>
              <button type="button" className="text-action" disabled={saving || !sessionEditable || Boolean(activeEditor) || Boolean(timeChangeError)} title={timeChangeError || undefined} onClick={() => {
                setDetailsError('')
                if (!checkTimeRequest(null)) return
                setTimeRequestDraft({ date: session.date, from: session.from, to: session.to })
                setRequestKind('time')
              }}>Request Time Change</button>
              <button type="button" className="text-action" disabled={saving || !sessionEditable || Boolean(activeEditor)} onClick={() => {
                setDetailsError('')
                setTrainerRequestId('')
                setRequestKind('trainer')
              }}>Request Trainer Change</button>
            </>
          )}
        </div>
      </div>

      <div className="session-overview-grid">
        <div className="session-overview-item">
          <span className="session-fact-label">Client</span>
          <div className="session-overview-value">
            <strong>{client.name}</strong>
            {clientInactive && <StatusBadge tone="amber">Client inactive</StatusBadge>}
            {activeEditor !== 'details' && <button type="button" className="secondary-button small" aria-label="View Client" onClick={onOpenClient}>View</button>}
          </div>
        </div>

        <div className="session-overview-item">
          <span className="session-fact-label">Trainer</span>
          <div className="session-overview-value">
            {activeEditor === 'details' ? (
              <SelectField aria-label="Session trainer" value={detailsDraft.trainerId} onChange={event => setDetailsDraft(current => ({ ...current, trainerId: event.target.value }))}>
                {trainers.filter(item => item.status !== 'inactive').map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
              </SelectField>
            ) : <strong>{trainer.name}</strong>}
            {activeEditor !== 'details' && <button type="button" className="secondary-button small" aria-label="View Trainer" onClick={onOpenTrainer}>View</button>}
          </div>
        </div>

        <div className="session-overview-item">
          <span className="session-fact-label">Date & time</span>
          {activeEditor === 'details' ? (
            <div className="session-schedule-fields">
              <label>Date<DateField aria-label="Session date"  value={detailsDraft.date} onChange={event => setDetailsDraft(current => ({ ...current, date: event.target.value }))} /></label>
              <label>From<input aria-label="Session start time" type="time" value={detailsDraft.from} onChange={event => setDetailsDraft(current => ({ ...current, from: event.target.value }))} /></label>
              <label>To<input aria-label="Session end time" type="time" value={detailsDraft.to} onChange={event => setDetailsDraft(current => ({ ...current, to: event.target.value }))} /></label>
            </div>
          ) : <strong>{weekday(session.date)}, {formatDate(session.date)} · {session.from}–{session.to}</strong>}
        </div>

        <div className="session-overview-item" aria-label="Session package details">
          <span className="session-fact-label">Package details</span>
          {purchased ? <div className="session-package-summary">
            <strong>{purchased.name ?? `${purchased.total} Sessions`} · Session {session.sessionNumber} / {purchased.total}</strong>
            <span> · <time dateTime={purchased.startDate}>{formatDate(purchased.startDate)}</time> – <time dateTime={purchased.endDate}>{formatDate(purchased.endDate)}</time></span>
          </div> : <strong>Package details unavailable</strong>}
          {packageInactive && <StatusBadge tone="amber">Package inactive</StatusBadge>}
        </div>
      </div>
    </Panel>


  )
}

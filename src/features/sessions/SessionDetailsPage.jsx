import { packageForRecord } from '../../app/clientPackages.js'
import SignaturePad, { SignaturePreview } from '../../components/SignaturePad.jsx'
import { validSignature, hasSessionAcknowledgement } from '../../app/signature.js'
import { useEffect, useState } from 'react'
import ConfirmDialog from '../../components/ConfirmDialog.jsx'
import Panel from '../../components/Panel.jsx'
import StatusBadge from '../../components/StatusBadge.jsx'
import { useActionConfirmation } from '../../components/ActionConfirmationProvider.jsx'
import { useEditGuard } from '../../components/EditGuardProvider.jsx'
import { sessionStatus, pendingSessionChanges, sessionActionError, sessionDurationMinutes } from '../../app/sessionRules.js'
import { businessClock } from '../../app/clock.js'
import { sessionTimeChangeError } from '../../app/scheduleChanges.js'
import { exerciseResultsFor } from '../../app/progress.js'
import { formatDate, formatTimestamp, weekday } from '../../utils/date.js'
import ExercisePlanEditor from './ExercisePlanEditor.jsx'
import { exerciseVideoCaption } from './exerciseVideo.js'
import useReportService from '../../hooks/useReportService.js'
import usePreparedReport from '../../hooks/usePreparedReport.js'
import { reportShareError } from '../../services/reportService.js'

function automaticClientSummary(session, outcome) {
  const items = session.exercisePlan ?? []
  const lines = [
    `Session duration: ${outcome.durationMinutes} minutes`,
    `Exercises completed (${items.length}).`,
  ]

  items.forEach(item => {
    const details = [
      item.weight,
      item.reps && `${item.reps} reps`,
      item.rounds && `${item.rounds} rounds`,
      item.rest && `${item.rest} rest`,
      ...(item.customDetails ?? []).map(detail => typeof detail === 'string' ? detail : detail.value).filter(Boolean),
    ].filter(Boolean).join(' · ')

    lines.push(`- ${item.name}${details ? ` — ${details}` : ''}`)
  })

  return lines.join('\n')
}

export default function SessionDetailsPage({
  policy,
  today = businessClock(new Date(), policy?.timeZone).date,
  user,
  session,
  messages = [],
  client,
  trainer,
  trainers,
  exerciseCatalog,
  onOpenClient,
  onOpenTrainer,
  onSavePlan,
  onLoadVideo,
  onSaveVideo,
  onRemoveVideo,
  onAcknowledge,
  onSaveOutcome,
  onSaveClientSummary,
  onSaveDetails,
  onRequestTimeChange,
  onRequestTrainerChange,
}) {
  const confirmAction = useActionConfirmation()
  const { setActiveEdit } = useEditGuard()
  const fallbackOutcome = {
    durationMinutes: sessionDurationMinutes(session),
    trainerComments: '',
  }
  const outcome = { ...(session.outcome ?? fallbackOutcome), durationMinutes: sessionDurationMinutes(session), exerciseResults: exerciseResultsFor(session) }
  const displayedSummary = session.clientSummary || automaticClientSummary(session, outcome)

  const [activeEditor, setActiveEditor] = useState(null)
  const [outcomeDraft, setOutcomeDraft] = useState(outcome)
  const [summaryDraft, setSummaryDraft] = useState(displayedSummary)
  const [detailsDraft, setDetailsDraft] = useState({
    date: session.date,
    from: session.from,
    to: session.to,
    trainerId: session.trainerId,
  })
  const [requestKind, setRequestKind] = useState(null)
  const [timeRequestDraft, setTimeRequestDraft] = useState({
    date: session.date,
    from: session.from,
    to: session.to,
  })
  const [trainerRequestId, setTrainerRequestId] = useState('')
  const [detailsError, setDetailsError] = useState('')
  const [acknowledgementMethod, setAcknowledgementMethod] = useState(null)
  const [signerName, setSignerName] = useState(client.name)
  const [note, setNote] = useState('')
  const [signature, setSignature] = useState([])
  const [signatureOpen, setSignatureOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [exportOpen, setExportOpen] = useState(false)
  const [shareError, setShareError] = useState('')
  const [selectedVideoIds, setSelectedVideoIds] = useState([])
  const [includeClientSummary, setIncludeClientSummary] = useState(true)

  const editLabel = activeEditor === 'details'
    ? 'Session overview'
    : activeEditor === 'exercise'
      ? 'Exercise plan'
      : activeEditor === 'outcome'
        ? 'Session outcome'
        : activeEditor === 'summary'
          ? 'Client-facing summary'
          : requestKind === 'time'
            ? 'Time-change request'
            : requestKind === 'trainer'
              ? 'Trainer-change request'
              : acknowledgementMethod
                ? 'Session acknowledgement'
                : null

  useEffect(() => {
    setActiveEdit(editLabel)
    return () => setActiveEdit(null)
  }, [editLabel, setActiveEdit])

  useEffect(() => {
    if (!activeEditor) {
      setOutcomeDraft(outcome)
      setSummaryDraft(displayedSummary)
    }
  }, [activeEditor, displayedSummary, session.id, session.outcome, session.from, session.to])

  useEffect(() => {
    setDetailsDraft({
      date: session.date,
      from: session.from,
      to: session.to,
      trainerId: session.trainerId,
    })
    setTimeRequestDraft({ date: session.date, from: session.from, to: session.to })
    setTrainerRequestId('')
    setDetailsError('')
  }, [session.date, session.from, session.id, session.to, session.trainerId])

  useEffect(() => {
    if (client.status !== 'inactive' && packageForRecord(client, session)?.status !== 'inactive') return
    setActiveEditor(null); setRequestKind(null); setAcknowledgementMethod(null); setExportOpen(false)
  }, [client.status, client.package, client.packageHistory, session.packageId])

  const status = sessionStatus(session.status)
  const isOwner = user.role === 'owner'
  const assignedTrainer = user.role === 'trainer' && user.trainerId === session.trainerId
  const clientInactive = client.status === 'inactive'
  const purchased = packageForRecord(client, session)
  const packageInactive = purchased?.status === 'inactive'
  const recordInactive = clientInactive || packageInactive
  const sessionEditable = !recordInactive && !['completed', 'cancelled'].includes(session.status)
  const canEditPlan = (isOwner || assignedTrainer) && sessionEditable
  const canEditNotes = !recordInactive && (isOwner || assignedTrainer)
  const signed = session.acknowledgement?.method === 'signature'
  const canAcknowledge = !recordInactive && (isOwner || assignedTrainer) && !signed
  const acknowledgementHistory = session.acknowledgementHistory?.length ? session.acknowledgementHistory : session.acknowledgement ? [session.acknowledgement] : []
  const replacementTrainers = trainers.filter(item => item.status !== 'inactive' && item.id !== session.trainerId)
  const recordedVideos = (session.exercisePlan ?? []).filter(item => item.videoAttached)
  const selectedVideos = recordedVideos.filter(item => selectedVideoIds.includes(item.id))
  const hasExportSelection = selectedVideos.length > 0 || (includeClientSummary && Boolean(displayedSummary.trim()))
  const reportService = useReportService()
  const report = usePreparedReport(reportService.sessionFile, { client, session, summary: includeClientSummary ? displayedSummary : '', videos: selectedVideos }, exportOpen && hasExportSelection)
  const dateError = sessionActionError(session, today)
  const clock = businessClock(new Date(), policy?.timeZone)
  const timeChangeError = sessionTimeChangeError(session, null, clock)
  const timeRequestError = sessionTimeChangeError(session, timeRequestDraft, clock)
  const checkTimeRequest = next => {
    const error = sessionTimeChangeError(session, next, businessClock(new Date(), policy?.timeZone))
    if (error) setDetailsError(error)
    return !error
  }
  const checkTrainingDate = () => {
    const error = sessionActionError(session, businessClock(new Date(), policy?.timeZone).date)
    if (error) setDetailsError(error)
    return !error
  }
  const validSchedule = draft => Boolean(draft.date && draft.from && draft.to && draft.from < draft.to)

  const openExportSummary = () => {
    if (recordInactive || !checkTrainingDate()) return
    setSelectedVideoIds(recordedVideos.map(item => item.id))
    setIncludeClientSummary(true)
    setShareError('')
    setExportOpen(true)
  }

  const exportSummary = async () => {
    if (saving || !checkTrainingDate() || !hasExportSelection || !report.file) return
    setShareError('')
    setSaving(true)
    try {
      // Already prepared: invoke the device share from the explicit click.
      await reportService.share(report.file)
      setExportOpen(false)
    } catch (error) {
      if (error.name !== 'AbortError') setShareError(reportShareError(error))
    } finally { setSaving(false) }
  }

  const saveDetails = async () => {
    if (!validSchedule(detailsDraft) || !detailsDraft.trainerId) {
      setDetailsError('Choose a valid date, start time, end time and trainer.')
      return
    }

    const confirmed = await confirmAction({
      title: 'Save session details?',
      message: 'This will update the session date, time and assigned trainer.',
      confirmLabel: 'Save Changes',
    })
    if (!confirmed) return

    setSaving(true)
    setDetailsError('')
    try {
      await onSaveDetails(detailsDraft)
      setActiveEditor(null)
    } catch (failure) {
      setDetailsError(failure.message || 'Could not complete this action. Try again.')
    } finally {
      setSaving(false)
    }
  }

  const submitTimeRequest = async () => {
    if (!validSchedule(timeRequestDraft)) {
      setDetailsError('Choose a valid date, start time and end time.')
      return
    }
    if (!checkTimeRequest(timeRequestDraft)) return

    setRequestKind(null)
    const confirmed = await confirmAction({
      title: 'Submit time-change request?',
      message: 'This will either send the proposed date and time to the owner for approval or apply it immediately under trainer autonomy.',
      confirmLabel: 'Submit Request',
    })
    if (!confirmed) {
      setRequestKind('time')
      return
    }
    if (!checkTimeRequest(timeRequestDraft)) {
      setRequestKind('time')
      return
    }

    setSaving(true)
    setDetailsError('')
    try {
      await onRequestTimeChange(timeRequestDraft)
      setRequestKind(null)
    } catch (failure) {
      setRequestKind('time')
      setDetailsError(failure.message || 'Could not complete this action. Try again.')
    } finally {
      setSaving(false)
    }
  }

  const submitTrainerRequest = async () => {
    if (!trainerRequestId) {
      setDetailsError('Choose a replacement trainer.')
      return
    }

    setRequestKind(null)
    const confirmed = await confirmAction({
      title: 'Submit trainer-change request?',
      message: 'This will either ask the owner to approve the selected replacement or apply the change immediately under trainer autonomy.',
      confirmLabel: 'Submit Request',
    })
    if (!confirmed) {
      setRequestKind('trainer')
      return
    }

    setSaving(true)
    setDetailsError('')
    try {
      await onRequestTrainerChange(trainerRequestId)
      setRequestKind(null)
    } catch (failure) {
      setRequestKind('trainer')
      setDetailsError(failure.message || 'Could not complete this action. Try again.')
    } finally {
      setSaving(false)
    }
  }

  const confirmAcknowledgement = async () => {
    if (recordInactive || !checkTrainingDate()) return
    const method = acknowledgementMethod
    if (method === 'signature' && !validSignature(signature)) return
    setAcknowledgementMethod(null)
    const confirmed = await confirmAction({
      title: 'Complete this session?',
      message: method === 'late_no_show'
        ? 'This will record a late/no-show, mark the session Completed and debit one package credit without a client signature.'
        : session.acknowledgement?.method === 'late_no_show'
          ? 'This will permanently save the client signature and record the correction with a timestamp. The original trainer acknowledgement remains in the log. No additional credit will be used.'
          : 'This will permanently save the client signature, complete the session and debit one package credit. The signature cannot be changed or removed. WhatsApp is optional.',
      confirmLabel: 'Complete Session',
      detail: method === 'signature' ? <SignaturePreview strokes={signature} label="Review client signature" /> : null,
    })
    if (!confirmed) {
      setAcknowledgementMethod(method)
      return
    }

    setSaving(true)
    try {
      await onAcknowledge({ method, signerName, note, signature })
      setAcknowledgementMethod(null)
      setNote('')
    } catch (failure) {
      setAcknowledgementMethod(method)
      setDetailsError(failure.message || 'Could not complete this action. Try again.')
    } finally {
      setSaving(false)
    }
  }

  const saveOutcome = async () => {
    const confirmed = await confirmAction({
      title: 'Save session outcome?',
      message: 'This will update the recorded duration and trainer comments for this session.',
      confirmLabel: 'Save Outcome',
    })
    if (!confirmed) return

    setSaving(true)
    try {
      await onSaveOutcome(outcomeDraft)
      setActiveEditor(null)
    } catch (failure) {
      setDetailsError(failure.message || 'Could not complete this action. Try again.')
    } finally {
      setSaving(false)
    }
  }

  const saveSummary = async () => {
    const confirmed = await confirmAction({
      title: 'Save client-facing summary?',
      message: 'This will replace the summary prepared for sharing with the client.',
      confirmLabel: 'Save Summary',
    })
    if (!confirmed) return

    setSaving(true)
    try {
      await onSaveClientSummary(summaryDraft)
      setActiveEditor(null)
    } catch (failure) {
      setDetailsError(failure.message || 'Could not complete this action. Try again.')
    } finally {
      setSaving(false)
    }
  }

  const pendingChanges = pendingSessionChanges(messages, session.id)

  return (
    <>
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
                <select aria-label="Session trainer" value={detailsDraft.trainerId} onChange={event => setDetailsDraft(current => ({ ...current, trainerId: event.target.value }))}>
                  {trainers.filter(item => item.status !== 'inactive').map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
                </select>
              ) : <strong>{trainer.name}</strong>}
              {activeEditor !== 'details' && <button type="button" className="secondary-button small" aria-label="View Trainer" onClick={onOpenTrainer}>View</button>}
            </div>
          </div>

          <div className="session-overview-item">
            <span className="session-fact-label">Date & time</span>
            {activeEditor === 'details' ? (
              <div className="session-schedule-fields">
                <label>Date<input aria-label="Session date" type="date" value={detailsDraft.date} onChange={event => setDetailsDraft(current => ({ ...current, date: event.target.value }))} /></label>
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

      {detailsError && !requestKind && <p className="validation-copy" role="alert">{detailsError}</p>}

      <Panel className={`top-gap exercise-plan-panel ${activeEditor === 'exercise' ? 'editing-section' : ''}`}>
        <ExercisePlanEditor defaults={policy.exerciseDefaults}
          catalog={exerciseCatalog}
          items={session.exercisePlan ?? []}
          sessionId={session.id}
          canEdit={canEditPlan && (!activeEditor || activeEditor === 'exercise')}
          canViewVideo={(isOwner || assignedTrainer) && !activeEditor}
          timeZone={policy.timeZone}
          editing={activeEditor === 'exercise'}
          onBeginEdit={() => setActiveEditor('exercise')}
          onEndEdit={() => setActiveEditor(null)}
          onSave={onSavePlan}
          onLoadVideo={onLoadVideo}
          onSaveVideo={onSaveVideo}
          onRemoveVideo={onRemoveVideo}
        />
      </Panel>

      <Panel className={`top-gap session-outcome-panel ${activeEditor === 'outcome' ? 'editing-section' : ''}`}>
        <div className="section-head">
          <h2>Session Outcome</h2>
          {activeEditor === 'outcome' ? (
            <div className="inline-actions">
              <button type="button" className="text-action muted-action" disabled={saving} onClick={() => setActiveEditor(null)}>Cancel</button>
              <button type="button" className="text-action" disabled={saving} onClick={saveOutcome}>{saving ? 'Saving…' : 'Save'}</button>
            </div>
          ) : canEditNotes && (
            <button type="button" className="text-action" disabled={Boolean(activeEditor)} onClick={() => setActiveEditor('outcome')}>Edit</button>
          )}
        </div>

        {activeEditor === 'outcome' ? (
          <div className="session-outcome-editor">
            <label>
              Duration (minutes)
              <input type="number" readOnly value={sessionDurationMinutes(session)} />
            </label>
            <label>
              Trainer comments
              <textarea rows="3" value={outcomeDraft.trainerComments} onChange={event => setOutcomeDraft(current => ({ ...current, trainerComments: event.target.value }))} />
            </label>
            <div className="recorded-results"><h3>Recorded exercise results</h3>
              {(outcomeDraft.exerciseResults ?? []).map((result, index) => <div className="recorded-result" key={result.id}><strong>{result.name}</strong>{[['loadKg', 'Load (kg)'], ['reps', 'Reps'], ['sets', 'Sets']].map(([field, label]) => <label key={field}>{label}<input aria-label={`${label} for ${result.name}`} type="number" min={field === 'loadKg' ? '0' : '1'} step={field === 'loadKg' ? '0.1' : '1'} value={result[field]} onChange={event => setOutcomeDraft(current => ({ ...current, exerciseResults: current.exerciseResults.map((row, rowIndex) => rowIndex === index ? { ...row, [field]: event.target.value } : row) }))} /></label>)}</div>)}
            </div>
          </div>
        ) : (
          <dl className="session-outcome-list">
            <div><dt>Duration</dt><dd>{outcome.durationMinutes} minutes</dd></div>
            <div><dt>Trainer comments</dt><dd>{outcome.trainerComments || 'No comments yet.'}</dd></div>
            {(session.exerciseResults ?? []).map(result => <div key={result.id}><dt>{result.name}</dt><dd>{result.loadKg} kg · {result.reps} reps · {result.sets} sets</dd></div>)}
          </dl>
        )}
      </Panel>

      <Panel className={`top-gap client-summary-panel ${activeEditor === 'summary' ? 'editing-section' : ''}`}>
        <div className="section-head">
          <h2>Client-Facing Summary</h2>
          {activeEditor === 'summary' ? (
            <div className="inline-actions">
              <button type="button" className="text-action muted-action" disabled={saving} onClick={() => setActiveEditor(null)}>Cancel</button>
              <button type="button" className="text-action" disabled={saving || !summaryDraft.trim()} onClick={saveSummary}>{saving ? 'Saving…' : 'Save'}</button>
            </div>
          ) : canEditNotes && (
            <button type="button" className="text-action" disabled={Boolean(activeEditor)} onClick={() => setActiveEditor('summary')}>Edit</button>
          )}
        </div>

        {activeEditor === 'summary' ? (
          <div className="client-summary-editor">
            <textarea rows="8" value={summaryDraft} onChange={event => setSummaryDraft(event.target.value)} />
          </div>
        ) : (
          <div className="client-summary-copy">{displayedSummary}</div>
        )}

      </Panel>

      <Panel className="top-gap session-acknowledgement-panel">
        <div className="section-head">
          <h2>Acknowledgement</h2>
          {signed && <button type="button" className="secondary-button small" onClick={() => setSignatureOpen(true)}>View Client Signature</button>}
        </div>
        {acknowledgementHistory.length ? <ol className="acknowledgement-history" aria-label="Acknowledgement history">
          {acknowledgementHistory.map((entry, index) => <li key={`${entry.recordedAt}-${index}`}>
            <strong>{entry.method === 'signature' ? index > 0 ? 'Corrected to client signature' : 'Client signature' : 'Trainer acknowledgement · Late / no-show'}</strong>
            {entry.signerName && <span>{entry.signerName}</span>}
            <time dateTime={entry.recordedAt}>{formatTimestamp(entry.recordedAt, policy.timeZone)}</time>
            {entry.recordedBy?.name && <span>Recorded by {entry.recordedBy.name}</span>}
            {entry.note && <p>{entry.note}</p>}
          </li>)}
        </ol> : <p className="empty">Pending acknowledgement</p>}
      </Panel>

      {dateError && <p className="helper">Client signature and WhatsApp are available from {formatDate(session.date)}.</p>}
      <div className={`session-primary-actions ${canAcknowledge ? '' : 'single-action'} ${acknowledgementMethod ? 'editing-section' : ''}`}>
        {canAcknowledge && (
          <button
            type="button"
            className="session-action-button session-acknowledge-button"
            disabled={Boolean(activeEditor || requestKind || dateError || saving)}
            title={dateError ?? undefined}
            onClick={() => { if (checkTrainingDate()) { setSignature([]); setSignerName(client.name); setNote(''); setAcknowledgementMethod('signature') } }}
          >
            {session.acknowledgement ? 'Correct to Client Signature' : 'Client Signature'}
          </button>
        )}

        <button
          type="button"
          className="session-action-button session-export-summary-button"
          disabled={Boolean(recordInactive || activeEditor || requestKind || saving || dateError)}
          title={dateError ?? undefined}
          onClick={openExportSummary}
        >
          Export Summary
        </button>
      </div>

      <ConfirmDialog
        open={exportOpen}
        title="Export Summary"
        confirmLabel={saving ? 'Sharing…' : 'Share PDF'}
        confirmDisabled={saving || Boolean(dateError) || !hasExportSelection || !report.file}
        onCancel={() => { if (!saving) setExportOpen(false) }}
        onConfirm={exportSummary}
      >
        <fieldset className="export-summary-section" disabled={saving}>
        <legend>Selected Videos</legend>
        {recordedVideos.length ? (
          <div className="export-video-list">
            {recordedVideos.map(item => (
              <label className="export-video-option" key={item.id}>
                <input
                  type="checkbox"
                  aria-label={`Include video for ${item.name}`}
                  checked={selectedVideoIds.includes(item.id)}
                  onChange={() => { setShareError(''); setSelectedVideoIds(current => current.includes(item.id)
                    ? current.filter(id => id !== item.id)
                    : [...current, item.id]) }}
                />
                <span>
                  <strong>{item.name}</strong>
                  <small>{exerciseVideoCaption(item)}</small>
                </span>
              </label>
            ))}
          </div>
        ) : (
          <p className="empty">No videos</p>
        )}
        </fieldset>
        <fieldset className="export-summary-section" disabled={saving}>
          <legend>Select Client Facing Summary</legend>
          <label className="export-summary-option">
            <input type="checkbox" aria-label="Include Client-Facing Summary" checked={includeClientSummary}
              onChange={event => { setIncludeClientSummary(event.target.checked); setShareError('') }} />
            <span>Client-Facing Summary</span>
          </label>
          {includeClientSummary && <div className="client-summary-copy">{displayedSummary}</div>}
        </fieldset>
        {report.preparing && <p role="status">Preparing PDF…</p>}
        {report.error && <div role="alert"><p>{report.error}</p><button type="button" className="secondary-button" onClick={report.retry}>Retry PDF</button></div>}
        {shareError && <p role="alert">{shareError}</p>}
        {report.file && <div className="report-file-actions"><button type="button" className="secondary-button" disabled={saving} onClick={() => {
          try { reportService.download(report.file); setShareError('') }
          catch (error) { setShareError(error.message) }
        }}>Download PDF</button></div>}
      </ConfirmDialog>

      <ConfirmDialog open={signatureOpen} title="Client signature" hideConfirm cancelLabel="Close" onCancel={() => setSignatureOpen(false)}>
        {session.acknowledgement?.signature && <SignaturePreview strokes={session.acknowledgement.signature} />}
        <p>{session.acknowledgement?.signerName}</p>
        <p>Signed on <time dateTime={session.acknowledgement?.recordedAt}>{formatTimestamp(session.acknowledgement?.recordedAt, policy.timeZone)}</time></p>
      </ConfirmDialog>

      <ConfirmDialog
        open={Boolean(acknowledgementMethod)}
        title={acknowledgementMethod === 'signature' ? 'Client signature' : 'Trainer late / no-show'}
        confirmLabel={saving ? 'Saving…' : 'Review Completion'}
        confirmDisabled={saving || (acknowledgementMethod === 'signature' && (!signerName.trim() || !validSignature(signature)))}
        onCancel={() => setAcknowledgementMethod(null)}
        onConfirm={confirmAcknowledgement}
      >
        {acknowledgementMethod === 'signature' ? (
          <>
            <label className="acknowledgement-field">
              Client name
              <input aria-label="Client name" value={signerName} onChange={event => setSignerName(event.target.value)} />
            </label>
            <SignaturePad strokes={signature} onChange={setSignature} disabled={saving} />
            {!session.acknowledgement && <button type="button" className="secondary-button acknowledgement-method-switch" onClick={() => setAcknowledgementMethod('late_no_show')}>
              Record late / no-show instead
            </button>}
          </>
        ) : (
          <>
            <p>No client signature is required. This records that the client was over 15 minutes late or did not attend.</p>
            <button type="button" className="secondary-button acknowledgement-method-switch" onClick={() => setAcknowledgementMethod('signature')}>
              Use client signature instead
            </button>
          </>
        )}

        <label className="acknowledgement-field">
          Note (optional)
          <textarea aria-label="Acknowledgement note" rows="3" value={note} onChange={event => setNote(event.target.value)} />
        </label>
      </ConfirmDialog>

      <ConfirmDialog
        open={requestKind === 'time'}
        title="Request Time Change"
        confirmLabel={saving ? 'Submitting…' : 'Review Request'}
        confirmDisabled={saving || !validSchedule(timeRequestDraft) || Boolean(timeRequestError)}
        onCancel={() => {
          setRequestKind(null)
          setDetailsError('')
        }}
        onConfirm={submitTimeRequest}
      >
        <div className="session-request-fields">
          <label>Date<input aria-label="Requested session date" type="date" min={clock.date} value={timeRequestDraft.date} onChange={event => { setDetailsError(''); setTimeRequestDraft(current => ({ ...current, date: event.target.value })) }} /></label>
          <label>From<input aria-label="Requested start time" type="time" min={timeRequestDraft.date === clock.date ? clock.time : undefined} value={timeRequestDraft.from} onChange={event => { setDetailsError(''); setTimeRequestDraft(current => ({ ...current, from: event.target.value })) }} /></label>
          <label>To<input aria-label="Requested end time" type="time" value={timeRequestDraft.to} onChange={event => setTimeRequestDraft(current => ({ ...current, to: event.target.value }))} /></label>
        </div>
        {(detailsError || timeRequestError) && <p className="validation-copy" role="alert">{detailsError || timeRequestError}</p>}
      </ConfirmDialog>

      <ConfirmDialog
        open={requestKind === 'trainer'}
        title="Request Trainer Change"
        confirmLabel={saving ? 'Submitting…' : 'Review Request'}
        confirmDisabled={saving || !trainerRequestId}
        onCancel={() => {
          setRequestKind(null)
          setDetailsError('')
        }}
        onConfirm={submitTrainerRequest}
      >
        <label className="session-request-trainer">
          Replacement trainer
          <select aria-label="Requested replacement trainer" value={trainerRequestId} onChange={event => setTrainerRequestId(event.target.value)}>
            <option value="">Choose trainer</option>
            {replacementTrainers.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        </label>
        {detailsError && <p className="validation-copy" role="alert">{detailsError}</p>}
      </ConfirmDialog>
    </>
  )
}

import SignaturePad, { SignaturePreview } from '../../components/SignaturePad.jsx'
import { validSignature } from '../../app/signature.js'
import { useEffect, useState } from 'react'
import ConfirmDialog from '../../components/ConfirmDialog.jsx'
import Panel from '../../components/Panel.jsx'
import StatusBadge from '../../components/StatusBadge.jsx'
import { useActionConfirmation } from '../../components/ActionConfirmationProvider.jsx'
import { useEditGuard } from '../../components/EditGuardProvider.jsx'
import { sessionStatus, pendingSessionChanges, sessionActionError } from '../../app/sessionRules.js'
import { businessClock } from '../../app/clock.js'
import { exerciseResultsFor } from '../../app/progress.js'
import { formatDate, weekday } from '../../utils/date.js'
import ExercisePlanEditor from './ExercisePlanEditor.jsx'
import { exerciseVideoCaption } from './exerciseVideo.js'
import { sessionSummaryWhatsAppText } from './sessionExport.js'

function durationMinutes(session) {
  const [fromHour, fromMinute] = session.from.split(':').map(Number)
  const [toHour, toMinute] = session.to.split(':').map(Number)
  return Math.max(0, (toHour * 60 + toMinute) - (fromHour * 60 + fromMinute))
}

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

function acknowledgementCopy(acknowledgement) {
  if (!acknowledgement) return 'Pending'
  return acknowledgement.method === 'late_no_show' ? 'Late / no-show' : 'Signed'
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
  onMarkWhatsAppOpened,
  onSaveDetails,
  onRequestTimeChange,
  onRequestTrainerChange,
}) {
  const confirmAction = useActionConfirmation()
  const { setActiveEdit } = useEditGuard()
  const fallbackOutcome = {
    durationMinutes: durationMinutes(session),
    trainerComments: '',
  }
  const outcome = { ...(session.outcome ?? fallbackOutcome), exerciseResults: exerciseResultsFor(session) }
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
  const [signature, setSignature] = useState(session.acknowledgement?.signature ?? [])
  const [signatureOpen, setSignatureOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [exportOpen, setExportOpen] = useState(false)
  const [shareFallback, setShareFallback] = useState('')
  const [selectedVideoIds, setSelectedVideoIds] = useState([])

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
  }, [activeEditor, displayedSummary, session.id, session.outcome])

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

  const status = sessionStatus(session.status)
  const isOwner = user.role === 'owner'
  const assignedTrainer = user.role === 'trainer' && user.trainerId === session.trainerId
  const sessionEditable = session.status !== 'completed'
  const canEditPlan = (isOwner || assignedTrainer) && sessionEditable
  const canEditNotes = isOwner || assignedTrainer
  const canAcknowledge = isOwner || assignedTrainer
  const replacementTrainers = trainers.filter(item => item.status !== 'inactive' && item.id !== session.trainerId)
  const recordedVideos = (session.exercisePlan ?? []).filter(item => item.videoAttached)
  const dateError = sessionActionError(session, today)
  const checkTrainingDate = () => {
    const error = sessionActionError(session, businessClock(new Date(), policy?.timeZone).date)
    if (error) setDetailsError(error)
    return !error
  }
  const phone = (typeof client.phone === 'string'
    ? client.phone
    : `${client.phone.countryCode}${client.phone.number}`
  ).replace(/\D/g, '')

  const validSchedule = draft => Boolean(draft.date && draft.from && draft.to && draft.from < draft.to)

  const openExportSummary = () => {
    if (!checkTrainingDate()) return
    setSelectedVideoIds(recordedVideos.map(item => item.id))
    setExportOpen(true)
  }

  const exportSummary = async () => {
    if (!checkTrainingDate()) return
    const selectedVideos = recordedVideos.filter(item => selectedVideoIds.includes(item.id))
    const text = sessionSummaryWhatsAppText(client, session, displayedSummary, selectedVideos)
    const whatsappUrl = `https://wa.me/${phone}?text=${encodeURIComponent(text)}`

    setShareFallback('')
    let popup
    try { popup = window.open('about:blank', '_blank'); if (popup) { popup.opener = null; popup.location.replace(whatsappUrl) } } catch { popup?.close(); popup = null }
    if (!popup) { setShareFallback(whatsappUrl); return }
    setSaving(true)
    setExportOpen(false)
    try {
      await onMarkWhatsAppOpened()
    } catch (failure) {
      setDetailsError(failure.message || 'Could not complete this action. Try again.')
    } finally {
      setSaving(false)
    }
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
    if (!checkTrainingDate()) return
    const method = acknowledgementMethod
    if (method === 'signature' && !validSignature(signature)) return
    setAcknowledgementMethod(null)
    const confirmed = await confirmAction({
      title: 'Complete this session?',
      message: method === 'late_no_show'
        ? 'This will record a late/no-show, mark the session Completed and debit one package credit without a client signature.'
        : 'This will save the client signature, record the completed exercise loads and debit one package credit. Saved results take priority over planned loads. Updating it later will not debit another credit.',
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
                <StatusBadge tone={session.acknowledgement ? 'green' : 'amber'}>
                  Acknowledgement · {acknowledgementCopy(session.acknowledgement)}
                </StatusBadge>
                <StatusBadge tone={session.whatsappOpenedAt ? 'green' : 'amber'}>
                  WhatsApp · {session.whatsappOpenedAt ? 'Opened' : 'Not opened'}
                </StatusBadge>
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
                <button type="button" className="text-action" disabled={!sessionEditable || Boolean(activeEditor)} onClick={() => {
                  setDetailsError('')
                  setTimeRequestDraft({ date: session.date, from: session.from, to: session.to })
                  setRequestKind('time')
                }}>Request Time Change</button>
                <button type="button" className="text-action" disabled={!sessionEditable || Boolean(activeEditor)} onClick={() => {
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
              {activeEditor !== 'details' && <button type="button" className="text-action" aria-label="View Client" onClick={onOpenClient}>View</button>}
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
              {activeEditor !== 'details' && <button type="button" className="text-action" aria-label="View Trainer" onClick={onOpenTrainer}>View</button>}
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

          <div className="session-overview-item">
            <span className="session-fact-label">Package details</span>
            <strong>{client.type} · Session {session.sessionNumber} / {session.packageTotal}</strong>
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
              <input type="number" min="0" value={outcomeDraft.durationMinutes} onChange={event => setOutcomeDraft(current => ({ ...current, durationMinutes: event.target.value }))} />
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

      {session.acknowledgement?.signature && <button type="button" className="secondary-button" onClick={() => setSignatureOpen(true)}>View Client Signature</button>}

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

      {dateError && <p className="helper">Client signature and WhatsApp are available from {formatDate(session.date)}.</p>}
      <div className={`session-primary-actions ${acknowledgementMethod ? 'editing-section' : ''}`}>
        {canAcknowledge && (
          <button
            type="button"
            className="session-action-button session-acknowledge-button"
            disabled={Boolean(activeEditor || requestKind || dateError)}
            title={dateError ?? undefined}
            onClick={() => { if (checkTrainingDate()) setAcknowledgementMethod(session.acknowledgement?.method ?? 'signature') }}
          >
            {session.acknowledgement ? 'Update Completion' : 'Client Signature'}
          </button>
        )}

        <button
          type="button"
          className="session-action-button session-export-summary-button"
          disabled={Boolean(activeEditor || requestKind || saving || dateError)}
          title={dateError ?? undefined}
          onClick={openExportSummary}
        >
          Export Summary
        </button>
      </div>

      <ConfirmDialog
        open={exportOpen}
        title="Export Summary"
        confirmLabel={saving ? 'Preparing…' : 'Continue to WhatsApp'}
        confirmDisabled={saving || Boolean(dateError)}
        onCancel={() => setExportOpen(false)}
        onConfirm={exportSummary}
      >
        <h3>Video captions</h3>
        {recordedVideos.length ? (
          <div className="export-video-list">
            {recordedVideos.map(item => (
              <label className="export-video-option" key={item.id}>
                <input
                  type="checkbox"
                  checked={selectedVideoIds.includes(item.id)}
                  onChange={() => setSelectedVideoIds(current => current.includes(item.id)
                    ? current.filter(id => id !== item.id)
                    : [...current, item.id])}
                />
                <span>
                  <strong>{item.name}</strong>
                  <small>{exerciseVideoCaption(item)}</small>
                </span>
              </label>
            ))}
          </div>
        ) : (
          <div className="notice">No exercise videos have been recorded or attached. The summary can still be exported.</div>
        )}
        {shareFallback && <p role="alert">The browser blocked the new window. <a href={shareFallback} target="_blank" rel="noreferrer">Open summary in WhatsApp</a></p>}
        <p className="helper">Includes summary text and video captions. Video files are not attached.</p>
      </ConfirmDialog>

      <ConfirmDialog open={signatureOpen} title="Client signature" hideConfirm cancelLabel="Close" onCancel={() => setSignatureOpen(false)}>
        {session.acknowledgement?.signature && <SignaturePreview strokes={session.acknowledgement.signature} />}
        <p>{session.acknowledgement?.signerName}</p>
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
            <button type="button" className="secondary-button acknowledgement-method-switch" onClick={() => setAcknowledgementMethod('late_no_show')}>
              Record late / no-show instead
            </button>
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
        confirmDisabled={saving || !validSchedule(timeRequestDraft)}
        onCancel={() => {
          setRequestKind(null)
          setDetailsError('')
        }}
        onConfirm={submitTimeRequest}
      >
        <div className="session-request-fields">
          <label>Date<input aria-label="Requested session date" type="date" value={timeRequestDraft.date} onChange={event => setTimeRequestDraft(current => ({ ...current, date: event.target.value }))} /></label>
          <label>From<input aria-label="Requested start time" type="time" value={timeRequestDraft.from} onChange={event => setTimeRequestDraft(current => ({ ...current, from: event.target.value }))} /></label>
          <label>To<input aria-label="Requested end time" type="time" value={timeRequestDraft.to} onChange={event => setTimeRequestDraft(current => ({ ...current, to: event.target.value }))} /></label>
        </div>
        {detailsError && <p className="validation-copy" role="alert">{detailsError}</p>}
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

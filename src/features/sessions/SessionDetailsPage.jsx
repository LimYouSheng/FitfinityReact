import { automaticClientSummary } from './sessionSummary.js'
import SessionSummaryExport from './SessionSummaryExport.jsx'
import SessionNotes from './SessionNotes.jsx'
import SessionOverview from './SessionOverview.jsx'
import SessionChangeDialogs from './SessionChangeDialogs.jsx'
import useSessionSchedule from './useSessionSchedule.js'
import { managesOperations } from '../../app/permissions.js'
import { packageForRecord } from '../../app/clientPackages.js'
import SignaturePad, { SignaturePreview } from '../../components/SignaturePad.jsx'
import { validSignature } from '../../app/signature.js'
import { useEffect, useMemo, useState } from 'react'
import ConfirmDialog from '../../components/ConfirmDialog.jsx'
import Panel from '../../components/Panel.jsx'
import { useActionConfirmation } from '../../components/ActionConfirmationProvider.jsx'
import { useEditGuard } from '../../components/EditGuardProvider.jsx'
import { isOpenSession, sessionStatus, pendingSessionChanges, sessionActionError, sessionDurationMinutes } from '../../app/sessionRules.js'
import { businessClock } from '../../app/clock.js'
import { exerciseResultsFor } from '../../app/progress.js'
import { formatDate, formatTimestamp } from '../../utils/date.js'
import ExercisePlanEditor from './ExercisePlanEditor.jsx'

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
  onPreviewPostponement,
  onPostpone,
}) {
  const confirmAction = useActionConfirmation()
  const { setActiveEdit } = useEditGuard()
  const outcome = useMemo(() => ({
    trainerComments: '', ...session.outcome,
    durationMinutes: sessionDurationMinutes(session), exerciseResults: exerciseResultsFor(session),
  }), [session])
  const displayedSummary = session.clientSummary || automaticClientSummary(session, outcome)

  const [activeEditor, setActiveEditor] = useState(null)
  const [detailsError, setDetailsError] = useState('')
  const [acknowledgementMethod, setAcknowledgementMethod] = useState(null)
  const [signerName, setSignerName] = useState(client.name)
  const [note, setNote] = useState('')
  const [signature, setSignature] = useState([])
  const [signatureOpen, setSignatureOpen] = useState(null)
  const [saving, setSaving] = useState(false)
  const acknowledgementReversalId = session.acknowledgementReversals?.at(-1)?.operationId
  useEffect(() => { setSignature([]); setNote(''); setAcknowledgementMethod(null) }, [acknowledgementReversalId])


  const schedule = useSessionSchedule({ session, policy, setActiveEditor, setDetailsError, setSaving,
    onSaveDetails, onRequestTimeChange, onRequestTrainerChange, onPreviewPostponement, onPostpone })
  const { requestKind, setRequestKind } = schedule

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
              : requestKind === 'postpone' ? 'Postpone session' : acknowledgementMethod
                ? 'Session acknowledgement'
                : null

  useEffect(() => {
    setActiveEdit(editLabel)
    return () => setActiveEdit(null)
  }, [editLabel, setActiveEdit])

  useEffect(() => {
    if (client.status !== 'inactive' && packageForRecord(client, session)?.status !== 'inactive') return
    setActiveEditor(null); setRequestKind(null); setAcknowledgementMethod(null)
  }, [client, session, setRequestKind])

  const status = sessionStatus(session.status)
  const isOwner = managesOperations(user)
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
  const dateError = sessionActionError(session, today)
  const checkTrainingDate = () => {
    const error = sessionActionError(session, businessClock(new Date(), policy?.timeZone).date)
    if (error) setDetailsError(error)
    return !error
  }


  const confirmAcknowledgement = async () => {
    if (recordInactive || !checkTrainingDate()) return
    const method = acknowledgementMethod
    if (method === 'signature' && !validSignature(signature)) return
    setAcknowledgementMethod(null)
    const confirmed = await confirmAction({
      title: 'Complete this session?',
      message: method === 'late_no_show'
        ? 'This records a late/no-show, completes the session and debits one package credit. It cannot be undone. You can later correct it to a client signature without another credit deduction.'
        : session.acknowledgement?.method === 'late_no_show'
          ? 'This will permanently save the client signature and record the correction with a timestamp. The original trainer acknowledgement remains in the log. No additional credit will be used.'
          : 'This permanently saves the client signature, completes the session and debits one package credit. It cannot be undone. WhatsApp is optional.',
      confirmLabel: 'Complete Session',
      detail: method === 'signature' ? <SignaturePreview strokes={signature} label="Review client signature" /> : null,
    })
    if (!confirmed) {
      setAcknowledgementMethod(method)
      return
    }

    setSaving(true)
    try {
      await onAcknowledge({ method, signerName, note, signature, ...(acknowledgementReversalId ? { reversalId: acknowledgementReversalId } : {}) })
      setAcknowledgementMethod(null)
      setNote('')
    } catch (failure) {
      setAcknowledgementMethod(method)
      setDetailsError(failure.message || 'Could not complete this action. Try again.')
    } finally {
      setSaving(false)
    }
  }

  const pendingChanges = pendingSessionChanges(messages, session.id)

  return (
    <>
      <SessionOverview session={session} client={client} trainer={trainer} trainers={trainers}
        purchased={purchased} clientInactive={clientInactive} packageInactive={packageInactive}
        status={status} pendingChanges={pendingChanges} isOwner={isOwner} sessionEditable={sessionEditable}
        activeEditor={activeEditor} setActiveEditor={setActiveEditor} saving={saving}
        setDetailsError={setDetailsError} schedule={schedule} onOpenClient={onOpenClient} onOpenTrainer={onOpenTrainer} />

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

      <SessionNotes session={session} outcome={outcome} displayedSummary={displayedSummary}
        activeEditor={activeEditor} setActiveEditor={setActiveEditor} saving={saving} setSaving={setSaving}
        setDetailsError={setDetailsError} canEditNotes={canEditNotes}
        onSaveOutcome={onSaveOutcome} onSaveClientSummary={onSaveClientSummary} />

      <Panel className="top-gap session-acknowledgement-panel">
        <div className="section-head">
          <h2>Acknowledgement</h2>
          {signed && <button type="button" className="secondary-button small" onClick={() => setSignatureOpen(session.acknowledgement)}>View Client Signature</button>}
        </div>
        {acknowledgementHistory.length ? <ol className="acknowledgement-history" aria-label="Acknowledgement history">
          {acknowledgementHistory.map((entry, index) => <li key={`${entry.recordedAt}-${index}`}>
            <strong>{entry.method === 'signature' ? index > 0 ? 'Corrected to client signature' : 'Client signature' : 'Trainer acknowledgement · Late / no-show'}</strong>
            {entry.signerName && <span>{entry.signerName}</span>}
            <time dateTime={entry.recordedAt}>{formatTimestamp(entry.recordedAt, policy.timeZone)}</time>
            {entry.recordedBy?.name && <span>Recorded by {entry.recordedBy.name}</span>}
            {entry.note && <p>{entry.note}</p>}
            {session.acknowledgementReversals?.filter(reversal => reversal.acknowledgement?.recordedAt === entry.recordedAt && reversal.acknowledgement?.method === entry.method).map(reversal => <span key={reversal.operationId}>Reversed · {formatTimestamp(reversal.at, policy.timeZone)}</span>)}
            {entry.method === 'signature' && entry !== session.acknowledgement && session.acknowledgementReversals?.length > 0 && <button type="button" className="text-action" onClick={() => setSignatureOpen(entry)}>View recorded signature</button>}
          </li>)}
        </ol> : <p className="empty">Pending acknowledgement</p>}
      </Panel>

      {dateError && <p className="helper">{isOpenSession(session) ? 'Schedule this open session before completion, acknowledgement or WhatsApp.' : `Client signature and WhatsApp are available from ${formatDate(session.date)}.`}</p>}
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

        <SessionSummaryExport client={client} session={session} displayedSummary={displayedSummary}
          recordInactive={recordInactive} activeEditor={activeEditor} requestKind={requestKind}
          dateError={dateError} checkTrainingDate={checkTrainingDate} saving={saving} setSaving={setSaving} />
      </div>

      <ConfirmDialog open={Boolean(signatureOpen)} title="Client signature" hideConfirm cancelLabel="Close" onCancel={() => setSignatureOpen(null)}>
        {signatureOpen?.signature && <SignaturePreview strokes={signatureOpen.signature} />}
        <p>{signatureOpen?.signerName}</p>
        <p>Signed on <time dateTime={signatureOpen?.recordedAt}>{formatTimestamp(signatureOpen?.recordedAt, policy.timeZone)}</time></p>
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

      <SessionChangeDialogs schedule={schedule} saving={saving} detailsError={detailsError}
        setDetailsError={setDetailsError} replacementTrainers={replacementTrainers} />
    </>
  )
}

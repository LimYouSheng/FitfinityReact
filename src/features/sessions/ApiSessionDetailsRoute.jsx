import { useEffect, useRef, useState } from 'react'
import usePortalData from '../../hooks/usePortalData.js'
import SessionDetailsPage from './SessionDetailsPage.jsx'
import { useEditGuard } from '../../components/EditGuardProvider.jsx'
import ConfirmDialog from '../../components/ConfirmDialog.jsx'
import { managesOperations } from '../../app/permissions.js'
import { packageForRecord } from '../../app/clientPackages.js'

// Versions and booking times may change during a review; authority changes may not
// carry an old editor into the newly scoped record.
const recordScope = ({ session, client, trainer }) => JSON.stringify([session.id, session.clientId, session.trainerId, session.packageId, session.scheduleState, ['completed', 'cancelled'].includes(session.status) ? session.status : 'editable', client.status, trainer.status, packageForRecord(client, session)?.status, packageForRecord(client, session)?.stage, session.acknowledgement?.id])
const scopeDenied = error => [401, 403, 404].includes(error.status) || ['SESSION_CHANGED', 'SESSION_EXPIRED', 'forbidden', 'unauthorized', 'not_found'].includes(error.code)

export default function ApiSessionDetailsRoute({ selectedSession, navigate, openClient, onChangeSaved }) {
  const { snapshot, services, today, refresh } = usePortalData()
  const { user, policy, sessionGeneration, serverAt, data } = snapshot
  const { activeEdit } = useEditGuard()
  const [acknowledgement, setAcknowledgement] = useState(null)
  const [summary, setSummary] = useState(null)
  const [outcome, setOutcome] = useState(null)
  const [video, setVideo] = useState(null)
  const [plan, setPlan] = useState(null)
  const [booking, setBooking] = useState(null), [saved, setSaved] = useState(false)
  const [postponement, setPostponement] = useState(null), [postponementNotice, setPostponementNotice] = useState('')
  const [change, setChange] = useState(null), [changeNotice, setChangeNotice] = useState('')
  const finishing = useRef(false)
  const [state, setState] = useState(null), [attempt, setAttempt] = useState(0)
  const [refreshError, setRefreshError] = useState('')
  const editing = useRef(false)
  useEffect(() => {
    const wasEditing = editing.current
    editing.current = Boolean(activeEdit)
    if (wasEditing && !activeEdit && !saved) setAttempt(n => n + 1)
  }, [activeEdit, saved])
  const lifetime = useRef(null)
  const refreshedDetail = useRef(null)
  useEffect(() => { const token = {}; lifetime.current = token; return () => { if (lifetime.current === token) lifetime.current = null } }, [])
  const [limited, setLimited] = useState(null), [clientBusy, setClientBusy] = useState(false), [clientError, setClientError] = useState('')
  const id = selectedSession.id, version = selectedSession.version
  const calendarClient = data.sessionClients?.find(client => client.id === selectedSession.clientId)
  const assignedClient = data.clients.find(client => client.id === selectedSession.clientId)
  const selectionScope = JSON.stringify([id, sessionGeneration, user.id, user.role, user.trainerId, selectedSession.clientId, selectedSession.trainerId, selectedSession.packageId, selectedSession.scheduleState, ['completed', 'cancelled'].includes(selectedSession.status) ? selectedSession.status : 'editable', assignedClient?.trainerId, assignedClient?.status, calendarClient?.status, calendarClient && packageForRecord(calendarClient, selectedSession)?.status, calendarClient && packageForRecord(calendarClient, selectedSession)?.stage])
  useEffect(() => {
    if (!saved || activeEdit || finishing.current || refreshError) return
    finishing.current = true
    const token = lifetime.current
    // A committed command stays committed even if either subsequent read fails.
    void (async () => {
      try {
        await refresh()
        const value = await services.readSessionDetails({ id })
        if (lifetime.current !== token) return
        refreshedDetail.current = selectionScope
        setState({ id, generation: sessionGeneration, selectionScope, value })
        setSaved(false); setBooking(null); setPostponementNotice(current => current.replace(' Updating details…', ''))
      } catch {
        if (lifetime.current === token) setRefreshError('Saved. The latest details could not be loaded. Retry refreshing; do not repeat the save.')
      } finally { finishing.current = false }
    })()
  }, [saved, activeEdit, refresh, services, id, sessionGeneration, refreshError, selectionScope])
  useEffect(() => {
    if (finishing.current || saved) return
    if (refreshedDetail.current) { const matched = refreshedDetail.current === selectionScope; refreshedDetail.current = null; if (matched) return }
    let current = true
    // Keep same-session drafts mounted while refreshing; identity/generation checks below still hide stale scope.
    services.readSessionDetails({ id }).then(value => {
      if (current) setState(previous => ({ id, generation: sessionGeneration, selectionScope, value: editing.current && previous?.id === id && previous.generation === sessionGeneration && previous.selectionScope === selectionScope && previous.value && recordScope(previous.value) === recordScope(value) ? previous.value : value }))
    }).catch(error => { if (current) setState(previous => ({ id, generation: sessionGeneration, selectionScope, error, value: !scopeDenied(error) && previous?.id === id && previous.generation === sessionGeneration && previous.selectionScope === selectionScope ? previous.value : null })) })
    return () => { current = false }
  }, [id, version, sessionGeneration, serverAt, services, attempt, saved, selectionScope])
  if (!state || state.id !== id || state.generation !== sessionGeneration || state.selectionScope !== selectionScope) return refreshError ? <section role="alert"><p>{refreshError}</p><button type="button" onClick={() => setRefreshError('')}>Retry refreshing</button></section> : <p role="status">{saved ? 'Saved. Updating details…' : 'Loading session…'}</p>
  if (state.error && !state.value) return <section role="alert"><p>{state.error.message}</p><button type="button" onClick={() => setAttempt(n => n + 1)}>Retry session</button></section>
  const { session, client, trainer } = state.value
  const fullClient = data.clients.some(c => c.id === client.id)
  const fullTrainer = data.trainers.some(t => t.id === trainer.id)
  const canLimited = !fullClient && !['completed', 'cancelled'].includes(session.status) && client.status === 'active' && state.value.session.packageId && [client.package, ...client.additionalPackages, ...client.packageHistory].some(p => p?.id === session.packageId && p.status === 'active')
  const openLimited = async () => {
    if (clientBusy) return
    setClientBusy(true); setClientError('')
    try { setLimited(await services.readSessionClient({ id, clientId: client.id })) }
    catch (error) { setClientError(error.message) }
    finally { setClientBusy(false) }
  }
  const canCorrectOutcome = managesOperations(user) || !['completed', 'cancelled'].includes(session.status) || data.clients.some(c => c.id === client.id && c.trainerId === user.trainerId)
  const beginAcknowledgement = async () => {
    const viewed = await services.reviewSessionAcknowledgement({ id, expectedVersion: session.version })
    setAcknowledgement(viewed)
    return viewed.draft
  }
  const saveAcknowledgement = async draft => {
    try {
      const result = await services.sessionService.acknowledge({ sessionId: id, reviewed: acknowledgement.reviewed, acknowledgement: draft })
      onChangeSaved?.(acknowledgement?.uncertain ? 'Original session acknowledgement confirmed.' : 'Session acknowledgement saved.')
      setSaved(true)
      return result
    } catch (error) {
      setAcknowledgement(current => ({ ...current, uncertain: !(error.status >= 400 && error.status < 500) }))
      throw error
    }
  }
  const beginSummary = async () => {
    const viewed = await services.reviewSessionSummary({ id, expectedVersion: session.version })
    setSummary(viewed)
    return viewed.draft
  }
  const saveSummary = async draft => {
    try {
      const result = await services.sessionService.saveClientSummary({ sessionId: id, reviewed: summary.reviewed, summary: draft })
      onChangeSaved?.(summary?.uncertain ? 'Original client summary confirmed.' : 'Client-facing summary saved.')
      setSaved(true)
      return result
    } catch (error) {
      setSummary(current => ({ ...current, uncertain: !(error.status >= 400 && error.status < 500) }))
      throw error
    }
  }
  const beginOutcome = async () => {
    const viewed = await services.reviewSessionOutcome({ id, expectedVersion: session.version })
    setOutcome(viewed)
    return viewed.draft
  }
  const saveOutcome = async draft => {
    try {
      const result = await services.sessionService.saveOutcome({ sessionId: id, reviewed: outcome.reviewed, outcome: draft })
      onChangeSaved?.(outcome?.uncertain ? 'Original session outcome confirmed.' : 'Session outcome saved.')
      setSaved(true)
      return result
    } catch (error) {
      setOutcome(current => ({ ...current, uncertain: !(error.status >= 400 && error.status < 500) }))
      throw error
    }
  }
  const beginPlan = async () => {
    const viewed = await services.reviewSessionPlan({ id, expectedVersion: session.version })
    setPlan(viewed)
    return viewed.draft
  }
  const savePlan = async items => {
    try {
      const result = await services.sessionService.saveExercisePlan({ sessionId: id, reviewed: plan.reviewed, items })
      onChangeSaved?.('Exercise plan saved.')
      setSaved(true)
      return result
    } catch (error) {
      setPlan(current => ({ ...current, uncertain: !(error.status >= 400 && error.status < 500) }))
      throw error
    }
  }
  const previewPreviousPlan = () => services.sessionService.previousPlanFor({ sessionId: id })
  const copyPreviousPlan = async viewed => {
    const result = await services.sessionService.copyPreviousPlan({ sessionId: id, reviewed: viewed.target, copySource: viewed.source })
    onChangeSaved?.('Previous exercise plan copied.')
    setSaved(true)
    return result
  }
  const beginDetails = async () => {
    const current = await services.reviewSessionBooking({ id, expectedVersion: session.version })
    setBooking(current)
    return current.draft
  }
  const saveDetails = async patch => {
    try {
      const result = await services.sessionService.updateDetails({ sessionId: id, reviewed: booking.reviewed, patch })
      setSaved(true)
      return result
    } catch (error) {
      setBooking(current => ({ ...current, draft: patch, uncertain: !(error.status >= 400 && error.status < 500) }))
      throw error
    }
  }
  const previewPostponement = async () => {
    const viewed = await services.sessionService.previewPostponement({ sessionId: id })
    setPostponement(viewed)
    return viewed
  }
  const postpone = async (expected, requestKey) => {
    const result = await services.sessionService.postpone({ sessionId: id, expected, requestKey, reviewed: postponement.reviewed })
    setPostponementNotice(result.outcome === 'requested' ? 'Postponement requested. The booking stays unchanged until approved.' : 'Session postponed. Updating details…')
    setSaved(true)
    return result
  }
  const beginRequest = async kind => {
    const viewed = await services.reviewSessionChange({ id, kind, expectedVersion: session.version })
    setChange(viewed)
    return viewed
  }
  const requestChange = async (kind, patch) => {
    const input = { sessionId: id, reviewed: change.reviewed, ...(kind === 'time' ? { patch } : { replacementTrainerId: patch }) }
    const result = await services.sessionService[kind === 'time' ? 'requestTimeChange' : 'requestTrainerChange'](input)
    const message = result.outcome === 'requested' ? 'Change requested. The booking stays unchanged until approved.' : 'Session change saved.'
    if (onChangeSaved) onChangeSaved(message)
    else setChangeNotice(message)
    setSaved(true)
    return result
  }
  const beginVideo = async exerciseId => {
    const viewed = await services.reviewSessionMedia({ sessionId: id, exerciseId, expectedVersion: session.version })
    setVideo(viewed)
    return viewed.reviewed.media
  }
  const saveVideo = async (exerciseId, file, metadata) => {
    try {
      const result = await services.sessionService.saveVideo({ sessionId: id, exerciseId, file, metadata, reviewed: video.reviewed })
      setSaved(true); return result
    } catch (error) { setVideo(current => ({ ...current, uncertain: !(error.status >= 400 && error.status < 500) })); throw error }
  }
  const removeVideo = async exerciseId => {
    try {
      const result = await services.sessionService.removeVideo({ sessionId: id, exerciseId, reviewed: video.reviewed })
      setSaved(true); return result
    } catch (error) { setVideo(current => ({ ...current, uncertain: !(error.status >= 400 && error.status < 500) })); throw error }
  }
  const recoverVideo = async (exerciseId, resume = false) => {
    const result = await services[resume ? 'resumeSessionMedia' : 'reconcileSessionMedia']({ sessionId: id, exerciseId })
    if (result) setSaved(true)
    return result
  }
  return <><SessionDetailsPage key={recordScope(state.value)} videoWorkflows={Boolean(snapshot.capabilities?.sessionMediaWorkflows && !saved)} videoUncertain={Boolean(video?.uncertain)} onBeginVideo={beginVideo} onLoadVideo={exerciseId => services.sessionService.loadVideo({ sessionId: id, exerciseId })} onSaveVideo={saveVideo} onRemoveVideo={removeVideo} onRecoverVideo={exerciseId => recoverVideo(exerciseId)} onResumeVideo={exerciseId => recoverVideo(exerciseId, true)} summaryExportEnabled={Boolean(snapshot.capabilities?.sessionSummaryWrites && canCorrectOutcome && (managesOperations(user) || session.trainerId === user.trainerId) && !saved)} acknowledgementEditable={Boolean(snapshot.capabilities?.sessionAcknowledgementWrites && canCorrectOutcome && !saved)} acknowledgementUncertain={Boolean(acknowledgement?.uncertain)} onBeginAcknowledgement={beginAcknowledgement} onAcknowledge={saveAcknowledgement} summaryEditable={Boolean(snapshot.capabilities?.sessionSummaryWrites && canCorrectOutcome && !saved)} summaryUncertain={Boolean(summary?.uncertain)} onBeginSummary={beginSummary} onSaveClientSummary={saveSummary} outcomeEditable={Boolean(snapshot.capabilities?.sessionOutcomeWrites && canCorrectOutcome && !saved)} outcomeUncertain={Boolean(outcome?.uncertain)} onBeginOutcome={beginOutcome} onSaveOutcome={saveOutcome} onPreviewPreviousPlan={previewPreviousPlan} onCopyPreviousPlan={copyPreviousPlan} readOnly planEditable={Boolean(snapshot.capabilities?.sessionPlanWrites && !saved)} planUncertain={Boolean(plan?.uncertain)} onBeginPlan={beginPlan} onSavePlan={savePlan} requestEditable={Boolean(snapshot.capabilities?.sessionChangeWrites && !saved)} onBeginRequest={beginRequest} onRequestTimeChange={patch => requestChange('time', patch)} onRequestTrainerChange={id => requestChange('trainer', id)} postponementEditable={Boolean(snapshot.capabilities?.sessionPostponementWrites && !saved)} onPreviewPostponement={previewPostponement} onPostpone={postpone} bookingEditable={Boolean(snapshot.capabilities?.sessionBookingWrites && !saved)} bookingUncertain={Boolean(booking?.uncertain)} onBeginDetails={beginDetails} onSaveDetails={saveDetails} today={today} policy={policy} user={user} session={session} client={client} trainer={trainer}
    trainers={change?.reviewed.trainers ?? booking?.reviewed.trainers ?? data.sessionTrainers ?? data.trainers} messages={data.messages ?? []}
    onOpenClient={fullClient ? () => openClient(client.id) : canLimited && !clientBusy ? openLimited : undefined}
    onOpenTrainer={fullTrainer ? () => navigate(managesOperations(user) ? `trainers/${trainer.id}` : 'my-profile') : undefined} />
    {state.error && <section className="editing-section" role="alert"><p>{state.error.message}</p><button type="button" onClick={() => setAttempt(n => n + 1)}>Retry session</button></section>}
    {saved && !refreshError && <p role="status">Saved. Updating details…</p>}
    {refreshError && <section role="alert"><p>{refreshError}</p><button type="button" onClick={() => setRefreshError('')}>Retry refreshing</button></section>}
    {changeNotice && <p role="status">{changeNotice}</p>}
    {postponementNotice && <p role="status">{postponementNotice}</p>}
    {clientError && <p role="alert">{clientError}</p>}
    <ConfirmDialog open={Boolean(canLimited && limited)} title="Session Client" hideConfirm cancelLabel="Close" onCancel={() => setLimited(null)}>
      {limited && <><p>{limited.name}</p><ul>{limited.person_names.map((name, index) => <li key={index}>{name}</li>)}</ul></>}
    </ConfirmDialog>
  </>
}

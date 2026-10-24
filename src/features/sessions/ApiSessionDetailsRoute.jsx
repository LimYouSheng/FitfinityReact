import { useEffect, useRef, useState } from 'react'
import usePortalData from '../../hooks/usePortalData.js'
import SessionDetailsPage from './SessionDetailsPage.jsx'
import { useEditGuard } from '../../components/EditGuardProvider.jsx'
import ConfirmDialog from '../../components/ConfirmDialog.jsx'
import { managesOperations } from '../../app/permissions.js'

export default function ApiSessionDetailsRoute({ selectedSession, navigate, openClient, onChangeSaved }) {
  const { snapshot, services, today, refresh } = usePortalData()
  const { user, policy, sessionGeneration, serverAt, data } = snapshot
  const { activeEdit } = useEditGuard()
  const [acknowledgement, setAcknowledgement] = useState(null)
  const [summary, setSummary] = useState(null)
  const [outcome, setOutcome] = useState(null)
  const [plan, setPlan] = useState(null)
  const [booking, setBooking] = useState(null), [saved, setSaved] = useState(false)
  const [postponement, setPostponement] = useState(null), [postponementNotice, setPostponementNotice] = useState('')
  const [change, setChange] = useState(null), [changeNotice, setChangeNotice] = useState('')
  const finishing = useRef(false)
  useEffect(() => {
    if (!saved || activeEdit || finishing.current) return
    finishing.current = true
    void refresh().catch(() => null).finally(() => { finishing.current = false; setSaved(false); setBooking(null) })
  }, [saved, activeEdit, refresh])
  const [state, setState] = useState(null), [attempt, setAttempt] = useState(0)
  const [limited, setLimited] = useState(null), [clientBusy, setClientBusy] = useState(false), [clientError, setClientError] = useState('')
  const id = selectedSession.id, version = selectedSession.version
  useEffect(() => {
    let current = true
    // Keep same-session drafts mounted while refreshing; identity/generation checks below still hide stale scope.
    services.readSessionDetails({ id }).then(value => {
      if (current) setState({ id, generation: sessionGeneration, value })
    }).catch(error => { if (current) setState({ id, generation: sessionGeneration, error }) })
    return () => { current = false }
  }, [id, version, sessionGeneration, serverAt, services, attempt])
  if (!state || state.id !== id || state.generation !== sessionGeneration) return <p role="status">Loading session…</p>
  if (state.error) return <section role="alert"><p>{state.error.message}</p><button type="button" onClick={() => setAttempt(n => n + 1)}>Retry session</button></section>
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
    setPostponementNotice(result.outcome === 'requested' ? 'Postponement requested. The booking stays unchanged until approved.' : 'Session postponed.')
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
  return <><SessionDetailsPage acknowledgementEditable={Boolean(snapshot.capabilities?.sessionAcknowledgementWrites && canCorrectOutcome && !saved)} acknowledgementUncertain={Boolean(acknowledgement?.uncertain)} onBeginAcknowledgement={beginAcknowledgement} onAcknowledge={saveAcknowledgement} summaryEditable={Boolean(snapshot.capabilities?.sessionSummaryWrites && canCorrectOutcome && !saved)} summaryUncertain={Boolean(summary?.uncertain)} onBeginSummary={beginSummary} onSaveClientSummary={saveSummary} outcomeEditable={Boolean(snapshot.capabilities?.sessionOutcomeWrites && canCorrectOutcome && !saved)} outcomeUncertain={Boolean(outcome?.uncertain)} onBeginOutcome={beginOutcome} onSaveOutcome={saveOutcome} onPreviewPreviousPlan={previewPreviousPlan} onCopyPreviousPlan={copyPreviousPlan} readOnly planEditable={Boolean(snapshot.capabilities?.sessionPlanWrites && !saved)} planUncertain={Boolean(plan?.uncertain)} onBeginPlan={beginPlan} onSavePlan={savePlan} requestEditable={Boolean(snapshot.capabilities?.sessionChangeWrites && !saved)} onBeginRequest={beginRequest} onRequestTimeChange={patch => requestChange('time', patch)} onRequestTrainerChange={id => requestChange('trainer', id)} postponementEditable={Boolean(snapshot.capabilities?.sessionPostponementWrites && !saved)} onPreviewPostponement={previewPostponement} onPostpone={postpone} bookingEditable={Boolean(snapshot.capabilities?.sessionBookingWrites && !saved)} bookingUncertain={Boolean(booking?.uncertain)} onBeginDetails={beginDetails} onSaveDetails={saveDetails} today={today} policy={policy} user={user} session={session} client={client} trainer={trainer}
    trainers={change?.reviewed.trainers ?? booking?.reviewed.trainers ?? data.sessionTrainers ?? data.trainers} messages={data.messages ?? []}
    onOpenClient={fullClient ? () => openClient(client.id) : canLimited && !clientBusy ? openLimited : undefined}
    onOpenTrainer={fullTrainer ? () => navigate(managesOperations(user) ? `trainers/${trainer.id}` : 'my-profile') : undefined} />
    {changeNotice && <p role="status">{changeNotice}</p>}
    {postponementNotice && <p role="status">{postponementNotice}</p>}
    {clientError && <p role="alert">{clientError}</p>}
    <ConfirmDialog open={Boolean(canLimited && limited)} title="Session Client" hideConfirm cancelLabel="Close" onCancel={() => setLimited(null)}>
      {limited && <><p>{limited.name}</p><ul>{limited.person_names.map((name, index) => <li key={index}>{name}</li>)}</ul></>}
    </ConfirmDialog>
  </>
}

import { useEffect, useRef, useState } from 'react'
import { businessClock } from '../../app/clock.js'
import { sessionScheduleError } from '../../app/sessionRules.js'
import { sessionTimeChangeError } from '../../app/scheduleChanges.js'
import { useActionConfirmation } from '../../components/ActionConfirmationProvider.jsx'
import { createUuid } from '../../utils/uuid.js'

export default function useSessionSchedule({ session, policy, setActiveEditor, setDetailsError, setSaving, onBeginRequest, onBeginDetails, onSaveDetails, onRequestTimeChange, onRequestTrainerChange, onPreviewPostponement, onPostpone }) {
  const confirmAction = useActionConfirmation()
  const [detailsDraft, setDetailsDraft] = useState({
    date: session.date ?? '',
    from: session.from ?? '',
    to: session.to ?? '',
    trainerId: session.trainerId,
  })
  const [requestKind, setRequestKind] = useState(null)
  const [timeRequestDraft, setTimeRequestDraft] = useState({
    date: session.date ?? '',
    from: session.from ?? '',
    to: session.to ?? '',
  })
  const [trainerRequestId, setTrainerRequestId] = useState('')
  const [postponement, setPostponement] = useState(null)
  const requestLock = useRef(false), uncertainRequest = useRef(false)
  const [requestUncertain, setRequestUncertain] = useState(false)
  const postponeLock = useRef(false)
  const postponementKey = useRef(null)
  const mounted = useRef(false)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])

  const openPostponement = async () => {
    if (postponeLock.current) return
    postponeLock.current = true; setSaving(true); setDetailsError('')
    try {
      const preview = await onPreviewPostponement()
      if (!mounted.current) return
      postponementKey.current = preview.requestKey ?? createUuid()
      setPostponement(preview); setRequestKind('postpone')
    } catch (error) { if (mounted.current) setDetailsError(error.message) }
    finally { postponeLock.current = false; if (mounted.current) setSaving(false) }
  }
  const submitPostponement = async () => {
    if (postponeLock.current || !postponement) return
    postponeLock.current = true; setSaving(true); setDetailsError('')
    try {
      await onPostpone(postponement.expected, postponementKey.current)
      if (mounted.current) { setRequestKind(null); setPostponement(null) }
    } catch (error) {
      if (mounted.current) setDetailsError(error.message)
    }
    finally { postponeLock.current = false; if (mounted.current) setSaving(false) }
  }

  useEffect(() => {
    if (requestLock.current || uncertainRequest.current) return
    setDetailsDraft({
      date: session.date ?? '',
      from: session.from ?? '',
      to: session.to ?? '',
      trainerId: session.trainerId,
    })
    setTimeRequestDraft({ date: session.date ?? '', from: session.from ?? '', to: session.to ?? '' })
    setTrainerRequestId('')
    setDetailsError('')
  }, [session.date, session.from, session.id, session.to, session.trainerId, setDetailsError])

  const clock = businessClock(new Date(), policy?.timeZone)
  const timeChangeError = sessionTimeChangeError(session, null, clock)
  const timeRequestError = sessionTimeChangeError(session, timeRequestDraft, clock)
  const checkTimeRequest = next => {
    const error = sessionTimeChangeError(session, next, businessClock(new Date(), policy?.timeZone))
    if (error) setDetailsError(error)
    return !error
  }
  const validSchedule = draft => !sessionScheduleError(draft)

  const beginDetails = async () => {
    setSaving(true); setDetailsError('')
    try {
      const draft = onBeginDetails ? await onBeginDetails() : null
      if (!mounted.current) return
      if (draft) setDetailsDraft(draft)
      setActiveEditor('details')
    } catch (error) { if (mounted.current) setDetailsError(error.message) }
    finally { if (mounted.current) setSaving(false) }
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

  const openRequest = async kind => {
    if (requestLock.current) return
    requestLock.current = true; setSaving(true); setDetailsError('')
    try {
      const viewed = onBeginRequest ? await onBeginRequest(kind) : null
      if (!mounted.current) return
      uncertainRequest.current = Boolean(viewed?.uncertain)
      setRequestUncertain(uncertainRequest.current)
      if (kind === 'time') setTimeRequestDraft(viewed?.draft ?? { date: session.date ?? '', from: session.from ?? '', to: session.to ?? '' })
      else setTrainerRequestId(viewed?.draft.replacementTrainerId ?? '')
      setRequestKind(kind)
    } catch (error) { if (mounted.current) setDetailsError(error.message) }
    finally { requestLock.current = false; if (mounted.current) setSaving(false) }
  }

  const submitRequest = async kind => {
    if (requestLock.current) return
    if (!requestUncertain) {
      if (kind === 'time' && (!validSchedule(timeRequestDraft) || !checkTimeRequest(timeRequestDraft))) {
        if (!validSchedule(timeRequestDraft)) setDetailsError('Choose a valid date, start time and end time.')
        return
      }
      if (kind === 'trainer' && !trainerRequestId) { setDetailsError('Choose a replacement trainer.'); return }
    }
    requestLock.current = true
    try {
      if (!requestUncertain) {
        setRequestKind(null)
        const confirmed = await confirmAction({
          title: kind === 'time' ? 'Submit time-change request?' : 'Submit trainer-change request?',
          message: kind === 'time' ? 'This will either send the proposed date and time to the owner for approval or apply it immediately under trainer autonomy.' : 'This will either ask the owner to approve the selected replacement or apply the change immediately under trainer autonomy.',
          confirmLabel: 'Submit Request',
        })
        if (!mounted.current) return
        if (!confirmed || (kind === 'time' && !checkTimeRequest(timeRequestDraft))) { setRequestKind(kind); return }
      }
      setSaving(true); setDetailsError('')
      try {
        if (kind === 'time') await onRequestTimeChange(timeRequestDraft)
        else await onRequestTrainerChange(trainerRequestId)
        uncertainRequest.current = false
        if (mounted.current) { setRequestUncertain(false); setRequestKind(null) }
      } catch (failure) {
        uncertainRequest.current = Boolean(onBeginRequest) && !(failure.status >= 400 && failure.status < 500)
        if (mounted.current) {
          setRequestUncertain(uncertainRequest.current); setRequestKind(kind)
          setDetailsError(failure.message || 'Could not complete this action. Try again.')
        }
      }
    } finally { requestLock.current = false; if (mounted.current) setSaving(false) }
  }
  const submitTimeRequest = () => submitRequest('time')
  const submitTrainerRequest = () => submitRequest('trainer')

  return { openRequest, requestUncertain, beginDetails, detailsDraft, setDetailsDraft, requestKind, setRequestKind, timeRequestDraft, setTimeRequestDraft, trainerRequestId, setTrainerRequestId, clock, timeChangeError, timeRequestError, checkTimeRequest, validSchedule, saveDetails, submitTimeRequest, submitTrainerRequest, postponement, openPostponement, submitPostponement }
}

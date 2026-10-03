import { useEffect, useRef, useState } from 'react'
import { businessClock } from '../../app/clock.js'
import { sessionScheduleError } from '../../app/sessionRules.js'
import { sessionTimeChangeError } from '../../app/scheduleChanges.js'
import { useActionConfirmation } from '../../components/ActionConfirmationProvider.jsx'
import { createUuid } from '../../utils/uuid.js'

export default function useSessionSchedule({ session, policy, setActiveEditor, setDetailsError, setSaving, onSaveDetails, onRequestTimeChange, onRequestTrainerChange, onPreviewPostponement, onPostpone }) {
  const confirmAction = useActionConfirmation()
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
  const [postponement, setPostponement] = useState(null)
  const [lastSlotDraft, setLastSlotDraft] = useState(null)
  const [editingLastSlot, setEditingLastSlot] = useState(false)
  const postponeLock = useRef(false)
  const postponementKey = useRef(null)
  const mounted = useRef(false)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  const previewSlot = preview => {
    const { date, from, to } = preview.lastSlot ?? preview.changes.at(-1)?.next ?? {}
    return { date, from, to }
  }
  const lastSlotChanged = Boolean(postponement && JSON.stringify(lastSlotDraft) !== JSON.stringify(previewSlot(postponement)))
  const postponementConflicts = postponement?.conflicts ?? []
  const acceptPreview = preview => {
    setPostponement(preview); setLastSlotDraft(previewSlot(preview))
    setEditingLastSlot(Boolean(preview.conflicts?.length))
  }

  const openPostponement = async () => {
    if (postponeLock.current) return
    postponeLock.current = true; setSaving(true); setDetailsError('')
    try {
      const preview = await onPreviewPostponement()
      if (!mounted.current) return
      postponementKey.current = createUuid()
      acceptPreview(preview); setRequestKind('postpone')
    } catch (error) { if (mounted.current) setDetailsError(error.message) }
    finally { postponeLock.current = false; if (mounted.current) setSaving(false) }
  }
  const submitPostponement = async () => {
    if (postponeLock.current || !postponement) return
    postponeLock.current = true; setSaving(true); setDetailsError('')
    try {
      if (lastSlotChanged || postponementConflicts.length) {
        const preview = await onPreviewPostponement(lastSlotDraft)
        if (mounted.current) acceptPreview(preview)
        return
      }
      await onPostpone(postponement.expected, postponementKey.current, postponement.lastSlot)
      if (mounted.current) { setRequestKind(null); setPostponement(null) }
    } catch (error) {
      if (mounted.current) setDetailsError(error.message)
      if (error.code === 'POSTPONEMENT_CONFLICT') {
        try {
          const preview = await onPreviewPostponement(postponement.lastSlot)
          if (mounted.current) acceptPreview(preview)
        } catch (failure) { if (mounted.current) setDetailsError(failure.message) }
      }
    }
    finally { postponeLock.current = false; if (mounted.current) setSaving(false) }
  }

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

  return { detailsDraft, setDetailsDraft, requestKind, setRequestKind, timeRequestDraft, setTimeRequestDraft, trainerRequestId, setTrainerRequestId, clock, timeChangeError, timeRequestError, checkTimeRequest, validSchedule, saveDetails, submitTimeRequest, submitTrainerRequest, postponement, openPostponement, submitPostponement,
    lastSlotDraft, setLastSlotDraft, lastSlotChanged, editingLastSlot, setEditingLastSlot, postponementConflicts }
}

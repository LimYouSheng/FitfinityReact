import { DAYS } from '../../app/constants.js'
import { formatDate, weekday } from '../../utils/date.js'
import { useRef, useState } from 'react'
import { useActionConfirmation } from '../../components/ActionConfirmationProvider.jsx'

export default function RequestReview({ message, trainers, sessions, onResolve, onCancel }) {
  const confirm = useActionConfirmation()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const locked = useRef(false)
  const request = message.request
  const name = id => trainers.find(trainer => trainer.id === id)?.name ?? id
  const stamp = value => value ? `${weekday(value.date)}, ${formatDate(value.date)} · ${value.from}–${value.to}` : 'Session no longer available'
  const isAvailability = request.type === 'trainer_availability'
  const isWeekly = request.type === 'fixed_weekly_schedule'
  const session = sessions.find(item => item.id === request.sessionId)
  const decide = async decision => {
    if (locked.current) return
    locked.current = true
    setBusy(true)
    setError('')
    try {
      const approved = decision === 'approved'
      const cancelled = decision === 'cancelled'
      if (await confirm({ title: cancelled ? 'Cancel this request?' : approved ? 'Approve request?' : 'Reject request?',
        confirmLabel: cancelled ? 'Cancel Request' : approved ? 'Approve Request' : 'Reject Request',
        message: cancelled ? 'Cancel this pending request and notify the owner? Other requests are unchanged.' : approved ? 'Apply the reviewed change and notify the affected trainer(s)?' : 'Reject the proposed change and notify the requesting trainer?' })) {
        if (cancelled) await onCancel(message.requestId ?? message.id)
        else await onResolve(message.id, decision)
      }
    } catch (failure) { setError(failure.message) }
    finally { locked.current = false; setBusy(false) }
  }
  const labels = ['Current at request', 'Requested']
  return (
    <section className="request-review" aria-label="Requested change">
      <h3>{isAvailability ? 'Availability change' : isWeekly ? 'Fixed weekly schedule change' : 'Requested session change'}</h3>
      {!isAvailability && !isWeekly && <p className="request-session-context">{stamp(request.previous ?? session)}</p>}
      <div className="request-comparison">
        {labels.map((label, index) => (
          <section key={label} className={index ? 'request-proposed' : 'request-original'} aria-label={label}>
            <h4>{label}</h4>
            <dl>
              {isAvailability ? DAYS.map(day => (
                <div key={day}>
                  <dt>{day}</dt>
                  <dd>{((index ? request.newAvailability : request.oldAvailability)?.[day] ?? []).map(([from, to]) => `${from}–${to}`).join(', ') || 'Unavailable'}</dd>
                </div>
              )) : isWeekly ? (index ? request.newSlots : request.oldSlots).map(slot => (
                <div key={slot.day}><dt>{slot.day}</dt><dd>{slot.from}–{slot.to}</dd></div>
              )) : request.type === 'session_time' ? (
                <div><dt>Date & time</dt><dd>{stamp(index ? request.next : request.previous)}</dd></div>
              ) : (
                <div><dt>Trainer</dt><dd>{name(index ? request.replacementTrainerId : request.previousTrainerId)}</dd></div>
              )}
            </dl>
          </section>
        ))}
      </div>
      {isAvailability && <p className="request-effect">Availability controls future matching. Existing booked sessions keep their dates and times.</p>}
      {isWeekly && <p className="request-effect">Approval updates future sessions in the current package that still follow the previous weekly times. Completed, cancelled and individually rescheduled sessions remain unchanged.</p>}
      {error && <p role="alert" className="onboarding-error">{error}</p>}
      {message.status === 'pending' && (onResolve || onCancel) && <div className="request-decision-actions">
        {onCancel && <button type="button" className="onboarding-button request-reject" disabled={busy} onClick={() => decide('cancelled')}>Cancel Request</button>}
        {onResolve && <>
          <button type="button" className="onboarding-button request-reject" disabled={busy} onClick={() => decide('rejected')}>Reject Request</button>
          <button type="button" className="onboarding-button request-approve" disabled={busy} onClick={() => decide('approved')}>Approve Request</button>
        </>}
      </div>}
    </section>
  )
}

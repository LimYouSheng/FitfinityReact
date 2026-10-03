import { packageForRecord, requireActiveSessionClient } from './clientPackages.js'
import { businessClock } from './clock.js'
import { hasSessionDebit, sessionScheduleError } from './sessionRules.js'
import { sessionBookingConflict } from './bookingAvailability.js'
import { parseDateOnly, weekday } from '../utils/date.js'

const future = (session, clock) => `${session.date}T${session.from}` > `${clock.date}T${clock.time}`

const interval = ({ date, from, to }) => ({ date, from, to })

/** Move one upcoming session beyond the last booking in the current package. */
export function sessionPostponement(db, sessionId, now = new Date(), ignoredRequestId, lastSlot) {
  const selected = db.sessions.find(item => item.id === sessionId)
  if (!selected) throw new Error('Session not found.')
  const client = requireActiveSessionClient(db.clients.find(item => item.id === selected.clientId), selected)
  const purchased = packageForRecord(client, selected)
  if (!purchased || purchased.id !== client.package?.id) throw new Error('Only a session in the current package can be postponed.')
  const clock = businessClock(now, db.settings.timeZone)
  if (!future(selected, clock) || ['completed', 'cancelled'].includes(selected.status) || selected.acknowledgement || hasSessionDebit(db.packageCreditTransactions ?? [], selected.id)) {
    throw new Error('Only an upcoming, unacknowledged session can be postponed.')
  }
  if (sessionScheduleError(selected)) throw new Error('The session has an invalid date or time.')
  if (!db.trainers.some(item => item.id === selected.trainerId && item.status === 'active')) throw new Error('The assigned trainer is inactive.')
  const slots = purchased.fixedWeeklySchedule ?? client.fixedWeeklySchedule ?? []
  const last = db.sessions.filter(item => item.clientId === client.id && packageForRecord(client, item)?.id === purchased.id && item.status !== 'cancelled')
    .sort((a, b) => `${a.date}T${a.from}|${a.id}`.localeCompare(`${b.date}T${b.from}|${b.id}`)).at(-1)
  if (sessionScheduleError(last)) throw new Error('The last booked session has an invalid date or time.')
  const date = parseDateOnly(last.date)
  date.setUTCDate(date.getUTCDate() + 7)
  const defaultLastSlot = { date: date.toISOString().slice(0, 10), from: last.from, to: last.to }
  const finalSlot = lastSlot ? interval(lastSlot) : defaultLastSlot
  if (sessionScheduleError(finalSlot)) throw new Error('Choose a valid date, start time and end time for this session.')
  if (`${finalSlot.date}T${finalSlot.from}` < `${last.date}T${last.to}`) throw new Error('Choose a slot after the last booked session in this package.')
  const matching = slots.filter(slot => slot.day === weekday(finalSlot.date) && slot.from === finalSlot.from && slot.to === finalSlot.to)
  const changes = [{ sessionId, before: { ...interval(selected), trainerId: selected.trainerId, weeklySlotId: selected.weeklySlotId ?? null },
    next: { ...finalSlot, weeklySlotId: matching.length === 1 ? matching[0].id ?? null : null } }]
  if (db.messages.some(message => message.id !== ignoredRequestId && message.recipientRole === 'owner' && message.status === 'pending' &&
    (message.request?.sessionId === sessionId || message.request?.changes?.some(change => change.sessionId === sessionId) ||
      (message.request?.type === 'fixed_weekly_schedule' && message.request.clientId === client.id)))) {
    throw new Error('Resolve the pending schedule or trainer request before postponing this session.')
  }
  const conflict = sessionBookingConflict(db, selected, finalSlot)
  const subject = conflict?.trainerId === selected.trainerId ? 'trainer' : 'client'
  const conflicts = conflict ? [{ sessionId, subject, message: `The proposed slot conflicts with another session for this ${subject}. Choose another day and time.` }] : []
  const lastBooking = { sessionId: last.id, ...interval(last) }
  const expected = JSON.stringify({ version: 3, packageId: purchased.id, slots, lastBooking, changes })
  return { sessionId, clientId: client.id, packageId: purchased.id, changes, expected, conflicts, lastBooking, lastSlot: finalSlot, defaultLastSlot }
}

export function requirePostponementAvailable(preview) {
  if (preview.conflicts.length) {
    const error = new Error(preview.conflicts[0].message)
    error.code = 'POSTPONEMENT_CONFLICT'
    throw error
  }
}

export function applySessionPostponement(db, sessionId, expected, ignoredRequestId, lastSlot) {
  const preview = sessionPostponement(db, sessionId, new Date(), ignoredRequestId, lastSlot)
  if (preview.expected !== expected) throw new Error('The schedule changed. Review postponement again.')
  requirePostponementAvailable(preview)
  for (const change of preview.changes) Object.assign(db.sessions.find(item => item.id === change.sessionId), change.next, { detailsUpdatedAt: new Date().toISOString() })
  return preview
}

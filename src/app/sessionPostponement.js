import { packageForRecord, requireActiveSessionClient } from './clientPackages.js'
import { businessClock } from './clock.js'
import { hasSessionDebit, sessionScheduleError } from './sessionRules.js'
import { requireSessionSlotAvailable } from './bookingAvailability.js'
import { parseDateOnly, weekday } from '../utils/date.js'

const future = (session, clock) => `${session.date}T${session.from}` > `${clock.date}T${clock.time}`

/** A purchase-local, one-week cascade. Preview and commit use the same calendar. */
export function sessionPostponement(db, sessionId, now = new Date(), ignoredRequestId) {
  const selected = db.sessions.find(item => item.id === sessionId)
  if (!selected) throw new Error('Session not found.')
  const client = requireActiveSessionClient(db.clients.find(item => item.id === selected.clientId), selected)
  const purchased = packageForRecord(client, selected)
  if (!purchased) throw new Error('The session needs a package assignment.')
  const clock = businessClock(now, db.settings.timeZone)
  if (!future(selected, clock) || ['completed', 'cancelled'].includes(selected.status) || selected.acknowledgement || hasSessionDebit(db.packageCreditTransactions ?? [], selected.id)) {
    throw new Error('Only an upcoming, unacknowledged session can be postponed.')
  }
  const slots = purchased.fixedWeeklySchedule ?? (purchased.id === client.package?.id ? client.fixedWeeklySchedule : null)
  if (!slots?.length) throw new Error('This package has no fixed weekly schedule.')
  const changes = db.sessions.filter(item => item.clientId === client.id && packageForRecord(client, item)?.id === purchased.id &&
    `${item.date}T${item.from}` >= `${selected.date}T${selected.from}` && !['completed', 'cancelled'].includes(item.status))
    .sort((a, b) => `${a.date}T${a.from}|${a.id}`.localeCompare(`${b.date}T${b.from}|${b.id}`))
    .map(session => {
      if (session.acknowledgement || hasSessionDebit(db.packageCreditTransactions ?? [], session.id)) throw new Error('An affected session is already acknowledged. Review its schedule separately.')
      if (!db.trainers.some(item => item.id === session.trainerId && item.status === 'active')) throw new Error('An affected trainer is inactive.')
      const matching = slots.filter(slot => slot.day === weekday(session.date) && slot.from === session.from && slot.to === session.to)
      if (matching.length !== 1 || (session.weeklySlotId && matching[0].id && session.weeklySlotId !== matching[0].id)) {
        throw new Error('An affected session was individually rescheduled. Review its fixed weekly slot before postponing.')
      }
      const date = parseDateOnly(session.date)
      date.setUTCDate(date.getUTCDate() + 7)
      const next = { date: date.toISOString().slice(0, 10), from: matching[0].from, to: matching[0].to }
      if (sessionScheduleError(next)) throw new Error('An affected weekly slot is invalid.')
      return { sessionId: session.id, before: { date: session.date, from: session.from, to: session.to, trainerId: session.trainerId }, next }
    })
  const ids = new Set(changes.map(item => item.sessionId))
  if (db.messages.some(message => message.id !== ignoredRequestId && message.recipientRole === 'owner' && message.status === 'pending' &&
    (ids.has(message.request?.sessionId) || (message.request?.type === 'fixed_weekly_schedule' && message.request.clientId === client.id)))) {
    throw new Error('Resolve the pending schedule or trainer request before postponing these sessions.')
  }
  const byId = new Map(changes.map(change => [change.sessionId, change.next]))
  const calendar = { ...db, sessions: db.sessions.map(session => byId.has(session.id) ? { ...session, ...byId.get(session.id) } : session) }
  for (const session of calendar.sessions.filter(item => ids.has(item.id))) requireSessionSlotAvailable(calendar, session)
  const expected = JSON.stringify({ packageId: purchased.id, slots, changes })
  return { sessionId, clientId: client.id, packageId: purchased.id, changes, expected }
}

export function applySessionPostponement(db, sessionId, expected, ignoredRequestId) {
  const preview = sessionPostponement(db, sessionId, new Date(), ignoredRequestId)
  if (preview.expected !== expected) throw new Error('The schedule changed. Review postponement again.')
  for (const change of preview.changes) Object.assign(db.sessions.find(item => item.id === change.sessionId), change.next, { detailsUpdatedAt: new Date().toISOString() })
  return preview
}

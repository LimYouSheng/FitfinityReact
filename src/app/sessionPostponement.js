import { packageForRecord, requireActiveSessionClient } from './clientPackages.js'
import { businessClock } from './clock.js'
import { hasSessionDebit, isOpenSession, sessionScheduleError } from './sessionRules.js'

const interval = ({ date, from, to }) => ({ date, from, to })

/** Release one booking; its existing package session remains explicitly open. */
export function sessionPostponement(db, sessionId, now = new Date(), ignoredRequestId) {
  const selected = db.sessions.find(item => item.id === sessionId)
  if (!selected) throw new Error('Session not found.')
  const client = requireActiveSessionClient(db.clients.find(item => item.id === selected.clientId), selected)
  const purchased = packageForRecord(client, selected)
  if (!purchased || purchased.id !== client.package?.id) throw new Error('Only a session in the current package can be postponed.')
  const clock = businessClock(now, db.settings.timeZone)
  if (isOpenSession(selected) || `${selected.date}T${selected.from}` <= `${clock.date}T${clock.time}` ||
    ['completed', 'cancelled'].includes(selected.status) || selected.acknowledgement || hasSessionDebit(db.packageCreditTransactions ?? [], selected.id)) {
    throw new Error('Only an upcoming, unacknowledged session can be postponed.')
  }
  if (sessionScheduleError(selected)) throw new Error('The session has an invalid date or time.')
  if (!db.trainers.some(item => item.id === selected.trainerId && item.status === 'active')) throw new Error('The assigned trainer is inactive.')
  if (db.messages.some(message => message.id !== ignoredRequestId && message.recipientRole === 'owner' && message.status === 'pending' &&
    (message.request?.sessionId === sessionId || message.request?.changes?.some(change => change.sessionId === sessionId) ||
      (message.request?.type === 'fixed_weekly_schedule' && message.request.clientId === client.id)))) {
    throw new Error('Resolve the pending schedule or trainer request before postponing this session.')
  }
  const changes = [{ sessionId, before: { ...interval(selected), trainerId: selected.trainerId, weeklySlotId: selected.weeklySlotId ?? null },
    next: { scheduleState: 'open', date: null, from: null, to: null, weeklySlotId: null } }]
  const calendar = db.sessions.filter(item => item.clientId === client.id && packageForRecord(client, item)?.id === purchased.id)
    .map(item => ({ id: item.id, ...interval(item), scheduleState: item.scheduleState ?? 'scheduled', sessionNumber: item.sessionNumber, status: item.status }))
    .sort((a, b) => a.id.localeCompare(b.id))
  const expected = JSON.stringify({ version: 4, packageId: purchased.id, calendar, changes })
  return { sessionId, clientId: client.id, packageId: purchased.id, changes, expected }
}

export function applySessionPostponement(db, sessionId, expected, ignoredRequestId) {
  const preview = sessionPostponement(db, sessionId, new Date(), ignoredRequestId)
  if (preview.expected !== expected) throw new Error('The schedule changed. Review postponement again.')
  Object.assign(db.sessions.find(item => item.id === sessionId), preview.changes[0].next, { detailsUpdatedAt: new Date().toISOString() })
  return preview
}

import { managesOperations } from './permissions.js'
import { today as currentDate } from './clock.js'
import { parseDateOnly } from '../utils/date.js'

export function validSessionDate(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false
  const date = parseDateOnly(value)
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value
}

export function sessionScheduleError(session) {
  const validTime = value => typeof value === 'string' && /^([01]\d|2[0-3]):[0-5]\d$/.test(value)
  return validSessionDate(session?.date) && validTime(session.from) && validTime(session.to) && session.from < session.to
    ? null : 'Choose a valid date, start time and end time.'
}
const STATUS = {
  not_planned: { label: 'Not Planned', tone: 'amber' },
  planned: { label: 'Planned', tone: 'blue' },
  completed: { label: 'Completed', tone: 'green' },
}

export function sessionStatus(status) {
  return STATUS[status] ?? { label: 'Not Planned', tone: 'amber' }
}

export function sessionDurationMinutes(session) {
  const minutes = value => /^([01]\d|2[0-3]):[0-5]\d$/.test(value ?? '')
    ? Number(value.slice(0, 2)) * 60 + Number(value.slice(3)) : null
  const start = minutes(session.from), end = minutes(session.to)
  return start !== null && end !== null && end > start ? end - start : 0
}

export function visibleSessionsForUser(user, sessions) {
  if (managesOperations(user)) return [...sessions]
  return sessions.filter(session => session.trainerId === user.trainerId)
}

export const isOpenSession = session => session.scheduleState === 'open'
export const sessionSequence = session => isOpenSession(session) ? 'Open session' : `Session ${session.sessionNumber}`

/** Reorder display positions without moving evidence between identities. */
export function renumberPackageSessions(sessions, clientId, packageId) {
  const members = sessions.filter(item => item.clientId === clientId && item.packageId === packageId)
  for (const session of members.filter(isOpenSession)) session.sessionNumber = null
  members.filter(item => !isOpenSession(item) && !sessionScheduleError(item))
    .sort((a, b) => `${a.date}T${a.from}|${a.id}`.localeCompare(`${b.date}T${b.from}|${b.id}`))
    .forEach((session, index) => { session.sessionNumber = index + 1 })
}

export function isSessionHistory(session, today = currentDate()) {
  if (isOpenSession(session)) return false
  return session.status === 'completed' || session.date < today
}

export function sortSessions(sessions, today = currentDate(), period = 'upcoming') {
  return [...sessions].sort((a, b) => {
    if (isOpenSession(a) || isOpenSession(b)) return isOpenSession(a) && isOpenSession(b)
      ? a.id.localeCompare(b.id) : isOpenSession(a) ? -1 : 1
    const aHistory = isSessionHistory(a, today)
    const bHistory = isSessionHistory(b, today)

    if (period !== 'all' && aHistory !== bHistory) return aHistory ? 1 : -1

    const direction = period === 'all' || aHistory ? -1 : 1
    return direction * `${a.date}T${a.from}`.localeCompare(`${b.date}T${b.from}`)
      || a.id.localeCompare(b.id)
  })
}

export function validateExercisePlan(items) {
  if (!items.length) return 'Add at least one exercise before saving.'
  if (items.some(item => !item.name?.trim())) return 'Every exercise needs a name.'
  return null
}

export function normalizeExercisePlan(items) {
  return items.map((item, index) => ({
    id: item.id || `exercise-${Date.now()}-${index}`,
    name: item.name.trim(),
    weight: item.weight?.trim() ?? '',
    customDetails: (item.customDetails ?? [])
      .map((detail, detailIndex) => ({
        id: detail.id || `detail-${item.id || index}-${detailIndex + 1}`,
        value: (typeof detail === 'string' ? detail : detail.value)?.trim() ?? '',
      }))
      .filter(detail => detail.value),
    reps: item.reps?.trim() ?? '',
    rounds: item.rounds?.trim() ?? '',
    rest: item.rest?.trim() ?? '',
    videoAttached: Boolean(item.videoAttached),
    video: item.videoAttached && item.video ? {
      ...(item.video.id ? { id: item.video.id } : {}),
      name: item.video.name ?? '',
      type: item.video.type ?? '',
      size: Math.max(0, Number(item.video.size) || 0),
      duration: Number.isFinite(item.video.duration) ? Math.max(0, item.video.duration) : null,
      source: item.video.source === 'recorded' ? 'recorded' : 'attached',
      caption: item.video.caption ?? '',
      audioIncluded: typeof item.video.audioIncluded === 'boolean' ? item.video.audioIncluded : null,
      processingStatus: item.video.processingStatus ?? 'deferred',
      attachedAt: item.video.attachedAt ?? '',
      expiresAt: item.video.expiresAt ?? '',
    } : null,
  }))
}

export function hasSessionDebit(transactions, sessionId) {
  return transactions.some(transaction =>
    transaction.sessionId === sessionId && transaction.type === 'session_debit' &&
      !transactions.some(reversal => reversal.type === 'session_reversal' && reversal.debitId === transaction.id)
  )
}

export function sessionActionError(session, today) {
  if (isOpenSession(session)) return 'Schedule this open session before completion or acknowledgement.'
  if (!/^\d{4}-\d{2}-\d{2}$/.test(session.date ?? '') || !/^\d{4}-\d{2}-\d{2}$/.test(today ?? '')) return 'The training date is unavailable.'
  return session.date > today ? 'Available from the training date.' : null
}

/** Owner requests are authoritative; trainer receipt messages never duplicate these badges. */
export function pendingSessionChanges(messages, sessionId) {
  const kinds = new Set(messages.filter(message => message.status === 'pending' && message.request?.sessionId === sessionId)
    .map(message => message.request.type))
  return [['session_time', 'Time change pending'], ['session_trainer', 'Trainer change pending'], ['session_postpone', 'Postponement pending']]
    .filter(([kind]) => kinds.has(kind)).map(([kind, label]) => ({ kind, label }))
}

import { isOpenSession } from './sessionRules.js'
import { businessClock } from './clock.js'
import { requireActiveClient, sessionIsInactive, packageForRecord } from './clientPackages.js'
import { trainerCoversBlock } from './clientOnboarding.js'
import { weekday } from '../utils/date.js'
import { sessionBookingConflict } from './bookingAvailability.js'

const activePurchases = (client, purchaseId = client.package?.id) => [client.package, ...(client.additionalPackages ?? [])].filter(item => item && item.id === purchaseId && item.status !== 'inactive')

export function trainerReassignmentSnapshot(client, sessions, transactions, clock, purchaseId = client.package?.id) {
  const purchases = activePurchases(client, purchaseId)
  if (purchases.length !== 1) throw new Error('Choose an active package before reassigning its Trainer.')
  const purchased = purchases[0]
  const eligible = sessions.filter(session => session.clientId === client.id && packageForRecord(client, session)?.id === purchaseId && !sessionIsInactive(client, session) &&
    !['completed', 'cancelled'].includes(session.status) && !session.acknowledgement && !session.acknowledgementHistory?.length &&
    !transactions.some(transaction => transaction.sessionId === session.id) &&
    (isOpenSession(session) || session.date > clock.date || (session.date === clock.date && session.from > clock.time)))
  return {
    trainerId: purchased.trainerId ?? client.trainerId,
    fixedWeeklySchedule: structuredClone(purchased.fixedWeeklySchedule ?? client.fixedWeeklySchedule ?? []),
    packages: purchases.map(item => ({ id: item.id, trainerId: item.trainerId,
      fixedWeeklySchedule: structuredClone(item.fixedWeeklySchedule ?? []) })).sort((a, b) => a.id.localeCompare(b.id)),
    sessions: eligible.map(({ id, trainerId, date, from, to, scheduleState }) => ({ id, trainerId, date, from, to, ...(scheduleState ? { scheduleState } : {}) })).sort((a, b) => a.id.localeCompare(b.id)),
  }
}

export function trainerReassignmentAvailabilityError(client, trainer, sessions, purchaseId = client.package?.id) {
  const purchases = activePurchases(client, purchaseId)
  if (!purchases.length || !trainer || trainer.status !== 'active' || trainer.id === (purchases[0].trainerId ?? client.trainerId)) return 'Choose a different active trainer.'
  for (const preference of purchases.map(item => item.genderPreference ?? client.genderPreference)) {
    if ((preference === 'Female trainer preferred' && trainer.gender !== 'Female') || (preference === 'Male trainer preferred' && trainer.gender !== 'Male')) return 'The selected trainer does not match the saved trainer preference.'
  }
  const slots = purchases.flatMap(item => item.fixedWeeklySchedule ?? client.fixedWeeklySchedule ?? [])
  const unavailable = slots.find(slot => !trainerCoversBlock(trainer, slot.day, slot.from, slot.to))
  if (unavailable) return `The selected trainer is unavailable for a saved weekly schedule: ${unavailable.day}, ${unavailable.from}–${unavailable.to}.`
  for (const session of sessions) {
    if (!isOpenSession(session) && !trainerCoversBlock(trainer, weekday(session.date), session.from, session.to)) return `The selected trainer is unavailable on ${session.date}, ${session.from}–${session.to}.`
  }
  return ''
}

export function validateTrainerReassignment(db, client, draft) {
  requireActiveClient(client)
  const expected = trainerReassignmentSnapshot(client, db.sessions, db.packageCreditTransactions ?? [], businessClock(new Date(), db.settings.timeZone), draft.purchaseId)
  if (JSON.stringify(expected) !== JSON.stringify(draft.expected)) throw new Error('The client assignment, packages or upcoming sessions changed. Reopen Reassign Trainer to review them.')
  const trainer = db.trainers.find(item => item.id === draft.trainerId)
  const availabilityError = trainerReassignmentAvailabilityError(client, trainer, expected.sessions, draft.purchaseId)
  if (availabilityError) throw new Error(availabilityError)
  const purchases = activePurchases(client, draft.purchaseId)
  const ids = new Set(expected.sessions.map(item => item.id))
  const sessions = db.sessions.filter(item => ids.has(item.id))
  const calendar = { ...db, sessions: db.sessions.map(item => ids.has(item.id) ? { ...item, trainerId: trainer.id } : item) }
  for (const session of sessions) {
    if (sessionBookingConflict(calendar, session, { trainerId: trainer.id })) {
      throw new Error(`The selected trainer has a booking conflict on ${session.date}, ${session.from}–${session.to}.`)
    }
  }
  return { trainer, purchases, sessions }
}

export function applyTrainerReassignment(db, client, draft, staff) {
  if (!/^[a-zA-Z0-9_-]{1,120}$/.test(draft?.requestId ?? '')) throw new Error('A reassignment request ID is required.')
  const previous = (client.trainerAssignmentHistory ?? []).find(item => item.id === draft.requestId)
  const request = JSON.stringify(draft)
  if (previous) {
    if (previous.request !== request) throw new Error('This reassignment request ID has already been used.')
    return
  }
  const { trainer, purchases, sessions } = validateTrainerReassignment(db, client, draft)
  const at = new Date().toISOString(), by = { id: staff.id, name: staff.name }
  const oldTrainerId = purchases[0].trainerId ?? client.trainerId
  const oldTrainer = db.trainers.find(item => item.id === oldTrainerId)
  const entry = { id: draft.requestId, request, at, by,
    from: { id: oldTrainerId, name: oldTrainer?.name ?? 'Unknown trainer' }, to: { id: trainer.id, name: trainer.name },
    packages: purchases.map(item => ({ id: item.id, previousTrainerId: item.trainerId })),
    sessions: sessions.map(item => ({ id: item.id, previousTrainerId: item.trainerId })) }
  const movesDefault = purchases[0].id === client.package?.id
  if (movesDefault) client.trainerId = trainer.id
  for (const purchased of purchases) purchased.trainerId = trainer.id
  for (const session of sessions) {
    session.trainerId = trainer.id
    session.detailsUpdatedAt = at
  }
  client.trainerAssignmentHistory = [...(client.trainerAssignmentHistory ?? []), entry]
  const changed = new Set(sessions.map(item => item.id))
  const requests = new Set(db.messages.filter(message => message.status === 'pending' &&
    (changed.has(message.request?.sessionId) || (movesDefault && message.request?.type === 'fixed_weekly_schedule' && message.request.clientId === client.id))).map(message => message.id))
  for (const message of db.messages) if (requests.has(message.id) || requests.has(message.requestId)) {
    Object.assign(message, { status: 'rejected', decidedAt: at, decidedBy: staff.id, decisionReason: 'Superseded by permanent trainer reassignment.' })
  }
  const recipients = new Set([entry.from.id, trainer.id, ...entry.packages.map(item => item.previousTrainerId), ...entry.sessions.map(item => item.previousTrainerId)])
  const message = { createdAt: at, clientId: client.id, trainerId: trainer.id, kind: 'client_assignment', readBy: {},
    title: `Trainer reassigned: ${client.name}`,
    body: `${entry.from.name} → ${trainer.name} · ${sessions.length} upcoming sessions · ${purchases.length} current/additional packages · ${staff.name}` }
  db.messages.push({ ...message, id: `reassignment-${draft.requestId}-owner`, recipientRole: 'owner' })
  for (const trainerId of recipients) if (trainerId) db.messages.push({ ...message, id: `reassignment-${draft.requestId}-${trainerId}`, recipientTrainerId: trainerId })
}

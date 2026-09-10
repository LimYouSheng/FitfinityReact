import { businessClock } from './clock.js'
import { requireActiveClient, sessionIsInactive } from './clientPackages.js'
import { trainerCoversBlock } from './clientOnboarding.js'
import { weekday } from '../utils/date.js'

const activePurchases = client => [client.package, ...(client.additionalPackages ?? [])].filter(item => item && item.status !== 'inactive')

export function trainerReassignmentSnapshot(client, sessions, transactions, clock) {
  const eligible = sessions.filter(session => session.clientId === client.id && !sessionIsInactive(client, session) &&
    !['completed', 'cancelled'].includes(session.status) && !session.acknowledgement && !session.acknowledgementHistory?.length &&
    !transactions.some(transaction => transaction.sessionId === session.id) &&
    (session.date > clock.date || (session.date === clock.date && session.from > clock.time)))
  return {
    trainerId: client.trainerId,
    fixedWeeklySchedule: structuredClone(client.fixedWeeklySchedule ?? []),
    packages: activePurchases(client).map(item => ({ id: item.id, trainerId: item.trainerId,
      fixedWeeklySchedule: structuredClone(item.fixedWeeklySchedule ?? []) })).sort((a, b) => a.id.localeCompare(b.id)),
    sessions: eligible.map(({ id, trainerId, date, from, to }) => ({ id, trainerId, date, from, to })).sort((a, b) => a.id.localeCompare(b.id)),
  }
}

export function trainerReassignmentAvailabilityError(client, trainer, sessions) {
  if (!trainer || trainer.status !== 'active' || trainer.id === client.trainerId) return 'Choose a different active trainer.'
  const purchases = activePurchases(client)
  for (const preference of [client.genderPreference, ...purchases.map(item => item.genderPreference)]) {
    if ((preference === 'Female trainer preferred' && trainer.gender !== 'Female') || (preference === 'Male trainer preferred' && trainer.gender !== 'Male')) return 'The selected trainer does not match the saved trainer preference.'
  }
  const slots = [...(client.fixedWeeklySchedule ?? []), ...purchases.flatMap(item => item.fixedWeeklySchedule ?? [])]
  const unavailable = slots.find(slot => !trainerCoversBlock(trainer, slot.day, slot.from, slot.to))
  if (unavailable) return `The selected trainer is unavailable for a saved weekly schedule: ${unavailable.day}, ${unavailable.from}–${unavailable.to}.`
  for (const session of sessions) {
    if (!trainerCoversBlock(trainer, weekday(session.date), session.from, session.to)) return `The selected trainer is unavailable on ${session.date}, ${session.from}–${session.to}.`
  }
  return ''
}

export function validateTrainerReassignment(db, client, draft) {
  requireActiveClient(client)
  const expected = trainerReassignmentSnapshot(client, db.sessions, db.packageCreditTransactions ?? [], businessClock(new Date(), db.settings.timeZone))
  if (JSON.stringify(expected) !== JSON.stringify(draft.expected)) throw new Error('The client assignment, packages or upcoming sessions changed. Reopen Reassign Trainer to review them.')
  const trainer = db.trainers.find(item => item.id === draft.trainerId)
  const availabilityError = trainerReassignmentAvailabilityError(client, trainer, expected.sessions)
  if (availabilityError) throw new Error(availabilityError)
  const purchases = activePurchases(client)
  const ids = new Set(expected.sessions.map(item => item.id))
  const sessions = db.sessions.filter(item => ids.has(item.id))
  for (const session of sessions) {
    if (db.sessions.some(other => other.id !== session.id && !sessionIsInactive(db.clients.find(item => item.id === other.clientId), other) &&
      other.status !== 'cancelled' && other.date === session.date && (ids.has(other.id) || other.trainerId === trainer.id) && other.from < session.to && session.from < other.to)) {
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
  const oldTrainer = db.trainers.find(item => item.id === client.trainerId)
  const entry = { id: draft.requestId, request, at, by,
    from: { id: client.trainerId, name: oldTrainer?.name ?? 'Unknown trainer' }, to: { id: trainer.id, name: trainer.name },
    packages: purchases.map(item => ({ id: item.id, previousTrainerId: item.trainerId })),
    sessions: sessions.map(item => ({ id: item.id, previousTrainerId: item.trainerId })) }
  client.trainerId = trainer.id
  for (const purchased of purchases) purchased.trainerId = trainer.id
  for (const session of sessions) {
    session.trainerId = trainer.id
    session.detailsUpdatedAt = at
  }
  client.trainerAssignmentHistory = [...(client.trainerAssignmentHistory ?? []), entry]
  const changed = new Set(sessions.map(item => item.id))
  const requests = new Set(db.messages.filter(message => message.status === 'pending' &&
    (changed.has(message.request?.sessionId) || (message.request?.type === 'fixed_weekly_schedule' && message.request.clientId === client.id))).map(message => message.id))
  for (const message of db.messages) if (requests.has(message.id) || requests.has(message.requestId)) {
    Object.assign(message, { status: 'rejected', decidedAt: at, decidedBy: staff.id, decisionReason: 'Superseded by permanent trainer reassignment.' })
  }
  const recipients = new Set([entry.from.id, trainer.id, ...entry.packages.map(item => item.previousTrainerId), ...entry.sessions.map(item => item.previousTrainerId)])
  const message = { createdAt: at, clientId: client.id, trainerId: trainer.id, kind: 'client_assignment', read: false,
    title: `Trainer reassigned: ${client.name}`,
    body: `${entry.from.name} → ${trainer.name} · ${sessions.length} upcoming sessions · ${purchases.length} current/additional packages · ${staff.name}` }
  db.messages.push({ ...message, id: `reassignment-${draft.requestId}-owner`, recipientRole: 'owner' })
  for (const trainerId of recipients) if (trainerId) db.messages.push({ ...message, id: `reassignment-${draft.requestId}-${trainerId}`, recipientTrainerId: trainerId })
}

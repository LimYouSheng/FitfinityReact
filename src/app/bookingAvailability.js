import { sessionIsInactive } from './clientPackages.js'

/** Completion (including no-show) retains the entire recorded interval. */
export function sessionOccupiesTime(session, clients) {
  return session.status === 'completed' || (session.status !== 'cancelled' &&
    !sessionIsInactive(clients.find(client => client.id === session.clientId), session))
}

export function sessionBookingConflict({ sessions = [], clients = [] }, session, patch = {}) {
  const next = { clientId: session.clientId, date: patch.date ?? session.date,
    from: patch.from ?? session.from, to: patch.to ?? session.to, trainerId: patch.trainerId ?? session.trainerId }
  return sessions.find(other =>
    (!session.id || other.id !== session.id) && other.date === next.date &&
    (other.trainerId === next.trainerId || (next.clientId && other.clientId === next.clientId)) &&
    other.from < next.to && next.from < other.to && sessionOccupiesTime(other, clients)
  )
}

export function requireSessionSlotAvailable(db, session, patch = {}) {
  const conflict = sessionBookingConflict(db, session, patch)
  if (conflict) {
    const subject = conflict.trainerId === (patch.trainerId ?? session.trainerId) ? 'trainer' : 'client'
    const action = subject === 'trainer' ? 'Choose another time or trainer.' : 'Choose another time.'
    throw new Error(`The change conflicts with another session for this ${subject}. ${action}`)
  }
}

/** Include provisional choices so the whole replacement batch must remain bookable. */
export function availableReplacementTrainers(db, session, replacements = {}) {
  const calendar = { ...db, sessions: db.sessions.map(item => replacements[item.id]
    ? { ...item, trainerId: replacements[item.id] } : item) }
  return db.trainers.filter(trainer => trainer.status === 'active' && trainer.id !== session.trainerId &&
    !sessionBookingConflict(calendar, session, { trainerId: trainer.id }))
}

import { clientPackages, packageForRecord, sessionIsInactive } from './clientPackages.js'
import { restoreClientPurchases } from './packageLifecycle.js'
import { sessionBookingConflict } from './bookingAvailability.js'
import { hasSessionDebit, sessionScheduleError } from './sessionRules.js'

/** Review only scheduling evidence; unrelated notes do not invalidate this dialog. */
export function clientReactivationSnapshot(client, sessions, credits = []) {
  return {
    status: client.status,
    packages: clientPackages(client).map(item => ({ id: item.id, status: item.status,
      reason: item.deactivationReason, deactivatedAt: item.deactivatedAt, startDate: item.startDate, endDate: item.endDate }))
      .sort((a, b) => a.id.localeCompare(b.id)),
    sessions: sessions.filter(item => item.clientId === client.id).map(item => ({
      id: item.id, date: item.date, from: item.from, to: item.to, trainerId: item.trainerId,
      packageId: item.packageId, status: item.status, acknowledged: Boolean(item.acknowledgement),
      debited: hasSessionDebit(credits, item.id),
    })).sort((a, b) => a.id.localeCompare(b.id)),
  }
}

/** Evaluate the entire proposed calendar without changing the stored client or sessions. */
export function clientReactivationReview(db, client, dates = {}, at = new Date().toISOString()) {
  if (!dates || typeof dates !== 'object' || Array.isArray(dates)) throw new Error('Session dates must be a named object.')
  const restored = structuredClone(client)
  restored.status = 'active'
  restoreClientPurchases(restored, at, null)
  const retained = db.sessions.filter(item => item.clientId === client.id &&
    !['completed', 'cancelled'].includes(item.status) && !sessionIsInactive(restored, item))
  if (Object.keys(dates).some(id => !retained.some(item => item.id === id))) throw new Error('A rescheduled session is no longer eligible. Reopen reactivation to review it.')
  const calendar = { ...db, clients: db.clients.map(item => item.id === client.id ? restored : item),
    sessions: db.sessions.map(item => Object.hasOwn(dates, item.id) ? { ...item, date: dates[item.id] } : item) }
  const rows = retained.map(original => {
    const session = calendar.sessions.find(item => item.id === original.id)
    const locked = Boolean(original.acknowledgement) || hasSessionDebit(db.packageCreditTransactions ?? [], original.id)
    const purchased = packageForRecord(client, original)
    let error = sessionScheduleError(session)
    if (!error && !db.trainers.some(item => item.id === session.trainerId && item.status === 'active')) error = 'Reactivate the assigned trainer before restoring this session.'
    if (!error && session.date !== original.date && locked) error = 'Acknowledged sessions cannot be rescheduled.'
    if (!error && session.date !== original.date && !purchased) error = 'The original package could not be identified. Review this session before reactivation.'
    const conflict = !error && sessionBookingConflict(calendar, session)
    if (conflict) error = `Conflicts with another session for this ${conflict.trainerId === session.trainerId ? 'trainer' : 'client'} on ${session.date} at ${conflict.from}–${conflict.to}.`
    return { session, original, packageId: purchased?.id, locked, error }
  })
  return { rows, conflicts: rows.filter(row => row.error) }
}

export function applyClientReactivationDates(db, client, { dates = {}, expected } = {}, staff, at) {
  if ((Object.keys(dates ?? {}).length || expected !== undefined) &&
    JSON.stringify(expected) !== JSON.stringify(clientReactivationSnapshot(client, db.sessions, db.packageCreditTransactions))) {
    throw new Error('The client packages or sessions changed. Reopen reactivation to review them.')
  }
  const review = clientReactivationReview(db, client, dates, at)
  if (review.conflicts.length) throw new Error(`Resolve all session conflicts before reactivation. ${review.conflicts[0].error}`)
  for (const { session, original, packageId } of review.rows) {
    if (session.date === original.date) continue
    original.reactivationDateHistory = [...(original.reactivationDateHistory ?? []), {
      fromDate: original.date, toDate: session.date, at, by: { id: staff.id, name: staff.name },
    }]
    Object.assign(original, { date: session.date, packageId, detailsUpdatedAt: at })
  }
}

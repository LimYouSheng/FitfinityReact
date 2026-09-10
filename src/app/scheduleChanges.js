import { packageForRecord, sessionIsInactive } from './clientPackages.js'
import { businessClock } from './clock.js'
import { DAYS, availabilityBlockError, availabilityByDay } from './availability.js'
import { parseDateOnly, weekday } from '../utils/date.js'
import { sessionDurationMinutes } from './sessionRules.js'

export function availabilityBlocks(availability = {}) {
  return DAYS.flatMap(day => (availability[day] ?? []).map(([from, to], index) => ({ id: `${day}-${index}`, days: [day], from, to })))
}

export function validateAvailability(blocks) {
  if (!Array.isArray(blocks)) throw new Error('Availability blocks are required.')
  const accepted = []
  for (const block of blocks) {
    const error = availabilityBlockError(block, accepted, true)
    if (error) throw new Error(error)
    accepted.push(block)
  }
  return availabilityByDay(accepted)
}

export function sameAvailability(a, b) {
  return JSON.stringify(availabilityByDay(availabilityBlocks(a))) === JSON.stringify(availabilityByDay(availabilityBlocks(b)))
}

export function sameSlots(a = [], b = []) {
  const normalized = slots => slots.map(({ day, from, to }) => ({ day, from, to })).sort((x, y) => DAYS.indexOf(x.day) - DAYS.indexOf(y.day))
  return JSON.stringify(normalized(a)) === JSON.stringify(normalized(b))
}

export function requireActiveActor(db, actor) {
  const stored = db.users.find(user => user.id === actor?.id)
  if (!stored || stored.role !== actor.role || (stored.status ?? 'active') !== 'active' || (stored.role === 'trainer' && stored.trainerId !== actor.trainerId)) {
    throw new Error('An active staff identity is required.')
  }
  return stored
}

export const businessNow = businessClock

export function sessionTimeChangeError(session, next, clock) {
  if (['completed', 'cancelled'].includes(session.status)) return 'Completed or cancelled sessions cannot request a time change.'
  const validStart = slot => /^\d{4}-\d{2}-\d{2}$/.test(slot.date ?? '') &&
    /^([01]\d|2[0-3]):[0-5]\d$/.test(slot.from ?? '') &&
    Number.isFinite(parseDateOnly(slot.date).getTime()) && parseDateOnly(slot.date).toISOString().slice(0, 10) === slot.date
  const hasStarted = slot => slot.date < clock.date || (slot.date === clock.date && slot.from <= clock.time)
  if (!validStart(session)) return 'The session date or start time is invalid.'
  if (hasStarted(session)) return 'Time changes are only available before the session starts.'
  if (next && !validStart(next)) return 'Choose a valid requested date and start time.'
  return next && hasStarted(next) ? 'Choose a requested date and start time in the future.' : null
}

export function weeklyScheduleChanges(db, client, nextSlots, now = new Date()) {
  if (!client || client.status !== 'active') throw new Error('The client is no longer active.')
  const trainer = db.trainers.find(item => item.id === client.trainerId)
  if (trainer?.status !== 'active') throw new Error('The assigned trainer is no longer active.')
  if (!Array.isArray(nextSlots) || nextSlots.length !== client.fixedWeeklySchedule.length || !nextSlots.length) throw new Error('Keep the existing weekly training days.')
  const days = new Set()
  for (const slot of nextSlots) {
    const error = availabilityBlockError({ days: [slot.day], from: slot.from, to: slot.to })
    if (error) throw new Error(error)
    if (days.has(slot.day) || !client.fixedWeeklySchedule.some(old => old.day === slot.day)) throw new Error('Keep the existing weekly training days.')
    days.add(slot.day)
  }
  const clock = businessNow(now, db.settings?.timeZone)
  const changes = db.sessions.filter(session => {
    if (session.clientId !== client.id || sessionIsInactive(client, session) || ['completed', 'cancelled'].includes(session.status)) return false
    const purchased = packageForRecord(client, session)
    if ((client.additionalPackages ?? []).some(item => item.id === purchased?.id)) return false
    return session.date > clock.date || (session.date === clock.date && session.from > clock.time)
  }).map(session => {
    // The editor changes times, not booking dates. New bookings carry their slot
    // identity; legacy bookings can use their weekday or the sole weekly slot.
    const identified = session.weeklySlotId && nextSlots.find(item => item.id === session.weeklySlotId)
    const matchingDay = nextSlots.find(item => item.day === weekday(session.date))
    const previousTime = client.fixedWeeklySchedule.filter(item => item.from === session.from && item.to === session.to)
    const matchedPrevious = previousTime.length === 1 && nextSlots.find(item => item.day === previousTime[0].day)
    const slot = identified || matchingDay || (nextSlots.length === 1 ? nextSlots[0] : matchedPrevious)
    if (!slot) throw new Error(`The session on ${session.date} has no matching weekly slot. Review its date before changing the weekly schedule.`)
    return { ...session, from: slot.from, to: slot.to }
  }).filter(session => {
    const previous = db.sessions.find(item => item.id === session.id)
    return session.from !== previous.from || session.to !== previous.to
  })
  if (changes.some(session => session.date === clock.date && session.from <= clock.time)) throw new Error('A new session time would already have passed today.')
  const changedById = new Map(changes.map(session => [session.id, session]))
  const candidate = db.sessions.map(session => changedById.get(session.id) ?? session)
  for (const session of changes) {
    if (candidate.some(other => other.id !== session.id && !['completed', 'cancelled'].includes(other.status) && !sessionIsInactive(db.clients.find(item => item.id === other.clientId), other) && other.date === session.date && (other.trainerId === session.trainerId || other.clientId === session.clientId) && other.from < session.to && session.from < other.to)) {
      throw new Error(`The weekly change conflicts with another session on ${session.date}. Choose another time.`)
    }
  }
  return changes
}

export function applyWeeklySchedule(db, client, slots) {
  const changes = weeklyScheduleChanges(db, client, slots)
  for (const changed of changes) {
    const session = db.sessions.find(item => item.id === changed.id)
    Object.assign(session, { from: changed.from, to: changed.to })
    if (session.outcome) session.outcome.durationMinutes = sessionDurationMinutes(session)
  }
  client.fixedWeeklySchedule = slots.map(slot => ({ ...slot }))
  client.package.fixedWeeklySchedule = structuredClone(client.fixedWeeklySchedule)
  return changes.length
}

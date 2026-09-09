import { businessClock } from './clock.js'
import { DAYS, availabilityBlockError, availabilityByDay } from './availability.js'
import { parseDateOnly, weekday } from '../utils/date.js'

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
  const start = client.package.startDate
  const end = client.package.endDate ?? new Date(parseDateOnly(start).getTime() + (client.package.validityDays - 1) * 86400000).toISOString().slice(0, 10)
  const changes = db.sessions.filter(session => {
    if (session.clientId !== client.id || session.trainerId !== client.trainerId || ['completed', 'cancelled'].includes(session.status)) return false
    if (session.date < start || session.date > end || session.date < clock.date || (session.date === clock.date && session.from <= clock.time)) return false
    return client.fixedWeeklySchedule.some(slot => slot.day === weekday(session.date) && slot.from === session.from && slot.to === session.to)
  }).map(session => {
    const slot = nextSlots.find(item => item.day === weekday(session.date))
    return { ...session, from: slot.from, to: slot.to }
  }).filter(session => {
    const previous = db.sessions.find(item => item.id === session.id)
    return session.from !== previous.from || session.to !== previous.to
  })
  if (changes.some(session => session.date === clock.date && session.from <= clock.time)) throw new Error('A new session time would already have passed today.')
  const changedById = new Map(changes.map(session => [session.id, session]))
  const candidate = db.sessions.map(session => changedById.get(session.id) ?? session)
  for (const session of changes) {
    if (candidate.some(other => other.id !== session.id && !['completed', 'cancelled'].includes(other.status) && other.date === session.date && (other.trainerId === session.trainerId || other.clientId === session.clientId) && other.from < session.to && session.from < other.to)) {
      throw new Error(`The weekly change conflicts with another session on ${session.date}. Choose another time.`)
    }
  }
  return changes
}

export function applyWeeklySchedule(db, client, slots) {
  const changes = weeklyScheduleChanges(db, client, slots)
  for (const changed of changes) Object.assign(db.sessions.find(session => session.id === changed.id), { from: changed.from, to: changed.to })
  client.fixedWeeklySchedule = slots.map(slot => ({ ...slot }))
  return changes.length
}

import { parseDateOnly } from '../utils/date.js'

const iso = date => date.toISOString().slice(0, 10)
export function shiftCalendarDate(value, amount, unit = 'day') {
  const date = parseDateOnly(value)
  if (unit === 'month') { date.setUTCDate(1); date.setUTCMonth(date.getUTCMonth() + amount) }
  else date.setUTCDate(date.getUTCDate() + amount)
  return iso(date)
}

export function calendarDays(date, mode) {
  const start = parseDateOnly(mode === 'month' ? `${date.slice(0, 7)}-01` : date)
  const count = mode === 'month'
    ? new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth() + 1, 0)).getUTCDate()
    : 7
  return Array.from({ length: count }, (_, index) => shiftCalendarDate(iso(start), index))
}

export function calendarSessions(sessions, dates) {
  const days = new Set(dates)
  return sessions.filter(session => days.has(session.date)).sort((a, b) => `${a.date}|${a.from}|${a.id}`.localeCompare(`${b.date}|${b.from}|${b.id}`))
}

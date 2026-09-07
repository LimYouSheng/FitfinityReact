const DATE_FORMAT = new Intl.DateTimeFormat('en-SG', {
  day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC',
})
const WEEKDAY_FORMAT = new Intl.DateTimeFormat('en-SG', {
  weekday: 'long', timeZone: 'UTC',
})

export function parseDateOnly(value) {
  const [year, month, day] = String(value ?? '').split('-').map(Number)
  return new Date(Date.UTC(year, month - 1, day))
}

export function formatDate(value) {
  const date = parseDateOnly(value)
  return Number.isFinite(date.getTime()) ? DATE_FORMAT.format(date) : '—'
}

export function weekday(value) {
  const date = parseDateOnly(value)
  return Number.isFinite(date.getTime()) ? WEEKDAY_FORMAT.format(date) : '—'
}

export function packageDayProgress(startDate, validityDays, today = '2026-08-31') {
  const start = parseDateOnly(startDate)
  const now = parseDateOnly(today)
  const elapsed = Math.floor((now - start) / 86400000) + 1
  return Math.min(validityDays, Math.max(0, elapsed))
}

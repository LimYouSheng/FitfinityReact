const DATE_FORMAT = new Intl.DateTimeFormat('en-SG', {
  day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC',
})
const WEEKDAY_FORMAT = new Intl.DateTimeFormat('en-SG', {
  weekday: 'long', timeZone: 'UTC',
})

export function parseDateOnly(value) {
  const [year, month, day] = value.split('-').map(Number)
  return new Date(Date.UTC(year, month - 1, day))
}

export function formatDate(value) {
  return DATE_FORMAT.format(parseDateOnly(value))
}

export function weekday(value) {
  return WEEKDAY_FORMAT.format(parseDateOnly(value))
}

export function packageDayProgress(startDate, validityDays, today = '2026-08-31') {
  const start = parseDateOnly(startDate)
  const now = parseDateOnly(today)
  const elapsed = Math.floor((now - start) / 86400000) + 1
  return Math.min(validityDays, Math.max(0, elapsed))
}

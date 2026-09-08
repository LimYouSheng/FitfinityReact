// Deliberately unsorted records exercise preview ordering, overflow and role scoping.
export function withBusyCalendar(data) {
  const result = structuredClone(data)
  const template = result.sessions.find(session => session.id === 's1')
  const day = (date, count, trainerId, prefix) => Array.from({ length: count }, (_, index) => ({
    ...template, id: `${prefix}-${index}`, date, trainerId,
    from: `${String(index + 8).padStart(2, '0')}:00`,
    to: `${String(index + 9).padStart(2, '0')}:00`,
  })).reverse()
  result.sessions = [
    ...day('2026-09-02', 8, 't1', 'busy'),
    ...day('2026-09-03', 5, 't1', 'exact'),
    ...day('2026-09-02', 6, 't2', 'other'),
  ]
  return result
}

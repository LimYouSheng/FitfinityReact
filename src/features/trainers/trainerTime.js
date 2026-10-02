export function formatTime(value) {
  const [hour, minute] = value.split(':').map(Number)
  const period = hour >= 12 ? 'pm' : 'am'
  const h = hour % 12 || 12
  return `${h}:${String(minute).padStart(2, '0')}${period}`
}


// Stable UI categories classify adapter records, never message title text.
export const MESSAGE_CATEGORIES = [
  { key: 'all', label: 'All' },
  { key: 'renewals', label: 'Renewals' },
  { key: 'approvals', label: 'Approvals' },
  { key: 'sessions', label: 'Sessions' },
  { key: 'people', label: 'Clients & Trainers' },
  { key: 'remuneration', label: 'Remuneration' },
  { key: 'updates', label: 'Updates' },
]

export function messageCategory(message) {
  if (message.category !== 'all' && MESSAGE_CATEGORIES.some(item => item.key === message.category)) return message.category
  const kind = message.kind ?? ''
  if (kind === 'renewal') return 'renewals'
  if (message.remunerationCycle || kind.startsWith('remuneration')) return 'remuneration'
  if (message.request || message.requestId || kind.endsWith('_request') || kind === 'request_decision') return 'approvals'
  if (message.sessionId || kind === 'session' || kind.startsWith('session_') || kind === 'schedule_update') return 'sessions'
  if (kind.startsWith('client_') || kind.startsWith('trainer_') || kind === 'assignment' || kind === 'availability_update') return 'people'
  return 'updates'
}

function dateKey(value) {
  return String(value ?? '').slice(0, 10)
}

export function filterMessages(messages, { query = '', from = '', to = '', category = 'all' } = {}) {
  const term = query.trim().toLowerCase()

  return messages.filter(message => {
    if (category !== 'all' && messageCategory(message) !== category) return false
    const content = `${message.title ?? ''} ${message.body ?? ''}`.toLowerCase()
    const createdDate = dateKey(message.createdAt)

    if (term && !content.includes(term)) return false
    if (from && createdDate < from) return false
    if (to && createdDate > to) return false
    return true
  })
}

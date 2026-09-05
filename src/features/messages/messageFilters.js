function dateKey(value) {
  return String(value ?? '').slice(0, 10)
}

export function filterMessages(messages, { query = '', from = '', to = '' } = {}) {
  const term = query.trim().toLowerCase()

  return messages.filter(message => {
    const content = `${message.title ?? ''} ${message.body ?? ''}`.toLowerCase()
    const createdDate = dateKey(message.createdAt)

    if (term && !content.includes(term)) return false
    if (from && createdDate < from) return false
    if (to && createdDate > to) return false
    return true
  })
}

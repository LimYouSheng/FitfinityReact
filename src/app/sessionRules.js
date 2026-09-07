const STATUS = {
  not_planned: { label: 'Not Planned', tone: 'amber' },
  planned: { label: 'Planned', tone: 'blue' },
  completed: { label: 'Completed', tone: 'green' },
}

export function sessionStatus(status) {
  return STATUS[status] ?? { label: 'Not Planned', tone: 'amber' }
}

export function visibleSessionsForUser(user, sessions) {
  if (user.role === 'owner') return [...sessions]
  return sessions.filter(session => session.trainerId === user.trainerId)
}

export function isSessionHistory(session, today = '2026-09-02') {
  return session.status === 'completed' || session.date < today
}

export function sortSessions(sessions, today = '2026-09-02') {
  return [...sessions].sort((a, b) => {
    const aHistory = isSessionHistory(a, today)
    const bHistory = isSessionHistory(b, today)

    if (aHistory !== bHistory) return aHistory ? 1 : -1

    const direction = aHistory ? -1 : 1
    return direction * `${a.date}T${a.from}`.localeCompare(`${b.date}T${b.from}`)
  })
}

export function validateExercisePlan(items) {
  if (!items.length) return 'Add at least one exercise before saving.'
  if (items.some(item => !item.name?.trim())) return 'Every exercise needs a name.'
  return null
}

export function normalizeExercisePlan(items) {
  return items.map((item, index) => ({
    id: item.id || `exercise-${Date.now()}-${index}`,
    name: item.name.trim(),
    weight: item.weight?.trim() ?? '',
    customDetails: (item.customDetails ?? [])
      .map((detail, detailIndex) => ({
        id: detail.id || `detail-${item.id || index}-${detailIndex + 1}`,
        value: (typeof detail === 'string' ? detail : detail.value)?.trim() ?? '',
      }))
      .filter(detail => detail.value),
    reps: item.reps?.trim() ?? '',
    rounds: item.rounds?.trim() ?? '',
    rest: item.rest?.trim() ?? '',
    videoAttached: Boolean(item.videoAttached),
    video: item.videoAttached && item.video ? {
      name: item.video.name ?? '',
      type: item.video.type ?? '',
      size: Math.max(0, Number(item.video.size) || 0),
      duration: Math.max(0, Number(item.video.duration) || 0),
      source: item.video.source === 'recorded' ? 'recorded' : 'attached',
      caption: item.video.caption ?? '',
      audioIncluded: false,
      attachedAt: item.video.attachedAt ?? '',
    } : null,
  }))
}

export function hasSessionDebit(transactions, sessionId) {
  return transactions.some(transaction =>
    transaction.sessionId === sessionId && transaction.type === 'session_debit'
  )
}

/** Owner requests are authoritative; trainer receipt messages never duplicate these badges. */
export function pendingSessionChanges(messages, sessionId) {
  const kinds = new Set(messages.filter(message => message.status === 'pending' && message.request?.sessionId === sessionId)
    .map(message => message.request.type))
  return [['session_time', 'Time change pending'], ['session_trainer', 'Trainer change pending']]
    .filter(([kind]) => kinds.has(kind)).map(([kind, label]) => ({ kind, label }))
}

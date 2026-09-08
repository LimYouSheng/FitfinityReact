import { formatDate } from '../../utils/date.js'

export function relatedMessageLinks(
  message,
  { user, clients = [], trainers = [], sessions = [], exercises = [], packages = [], contentEntries = [] },
) {
  if (!message) return []

  const request = message.request ?? {}
  const clientIds = new Set([message.clientId, request.clientId].filter(Boolean))
  const trainerIds = new Set([
    message.trainerId,
    request.trainerId,
    request.previousTrainerId,
    request.replacementTrainerId,
    ...(message.trainerIds ?? []),
  ].filter(Boolean))
  const sessionIds = new Set([message.sessionId, request.sessionId].filter(Boolean))

  const visibleSessions = sessions.filter(session =>
    sessionIds.has(session.id) &&
    (user.role === 'owner' || session.trainerId === user.trainerId)
  )

  for (const session of visibleSessions) {
    clientIds.add(session.clientId)
    trainerIds.add(session.trainerId)
  }

  const links = visibleSessions.map(session => {
    const client = clients.find(item => item.id === session.clientId)
    return {
      type: 'session',
      id: session.id,
      label: `Session · ${client?.name ?? 'Client'} · ${formatDate(session.date)}`,
    }
  })

  clients
    .filter(client =>
      clientIds.has(client.id) &&
      (user.role === 'owner' || client.trainerId === user.trainerId)
    )
    .forEach(client => links.push({ type: 'client', id: client.id, label: `Client · ${client.name}` }))

  trainers
    .filter(trainer =>
      trainerIds.has(trainer.id) &&
      (user.role === 'owner' || trainer.id === user.trainerId)
    )
    .forEach(trainer => links.push({ type: 'trainer', id: trainer.id, label: `Trainer · ${trainer.name}` }))

  if (message.remunerationCycle && message.trainerId &&
      (user.role === 'owner' || message.trainerId === user.trainerId)) {
    links.unshift({ type: 'remuneration', id: `${message.remunerationCycle}/${message.trainerId}`, label: `Remuneration · ${message.remunerationCycle}` })
  }

  if (user.role === 'owner' && message.exerciseId) {
    const exercise = exercises.find(item => item.id === message.exerciseId)
    if (exercise) links.unshift({ type: 'exercise', id: exercise.id, label: `Exercise · ${exercise.name}` })
  }

  if (user.role === 'owner' && message.packageId) {
    const item = packages.find(item => item.id === message.packageId)
    if (item) links.unshift({ type: 'package', id: item.id, label: `Package · ${item.name}` })
  }

  if (user.role === 'owner' && message.contentId) {
    const entry = contentEntries.find(item => item.id === message.contentId)
    if (entry) links.unshift({ type: 'content', id: entry.id, label: `Content · ${entry.title}` })
  }

  return links
}

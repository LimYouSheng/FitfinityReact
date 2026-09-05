import { formatDate } from '../../utils/date.js'

function includesName(content, name) {
  return name && content.includes(name.toLowerCase())
}

export function relatedMessageLinks(
  message,
  { user, clients = [], trainers = [], sessions = [] },
) {
  if (!message) return []

  const content = `${message.title ?? ''} ${message.body ?? ''}`.toLowerCase()
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

  for (const client of clients) {
    if (includesName(content, client.name)) clientIds.add(client.id)
  }

  for (const trainer of trainers) {
    if (includesName(content, trainer.name)) trainerIds.add(trainer.id)
  }

  for (const session of sessions) {
    const client = clients.find(item => item.id === session.clientId)
    if (
      includesName(content, client?.name) &&
      content.includes(session.date) &&
      content.includes(session.from)
    ) {
      sessionIds.add(session.id)
    }
  }

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

  return links
}

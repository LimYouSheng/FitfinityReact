export function isActive(record) {
  return (record?.status ?? 'active') === 'active'
}

export function activeTrainers(trainers) {
  return trainers.filter(isActive)
}

export function activeClients(clients) {
  return clients.filter(isActive)
}

export function sortActiveFirst(records) {
  return [...records].sort((a, b) => {
    const aInactive = isActive(a) ? 0 : 1
    const bInactive = isActive(b) ? 0 : 1

    if (aInactive !== bInactive) return aInactive - bInactive
    return String(a.name ?? '').localeCompare(String(b.name ?? ''))
  })
}

export function trainerSelectableForAvailability(trainer) {
  return isActive(trainer)
}

export function visibleClientsForUser(user, clients) {
  if (user.role === 'owner') return sortActiveFirst(clients)

  return sortActiveFirst(
    clients.filter(client =>
      isActive(client) &&
      client.trainerId === user.trainerId
    )
  )
}

export function visibleTrainersForOwner(trainers) {
  return sortActiveFirst(trainers)
}

export function remainingTrainerSessions(trainerId, sessions) {
  return sessions.filter(session =>
    session.trainerId === trainerId &&
    !['completed', 'cancelled'].includes(session.status)
  )
}

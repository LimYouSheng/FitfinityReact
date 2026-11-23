import { managesOperations } from './permissions.js'
import { clientAssignedToTrainer, sessionIsInactive } from './clientPackages.js'
export function isActive(record) {
  return (record?.status ?? 'active') === 'active'
}

export function activeTrainers(trainers) {
  return trainers.filter(isActive)
}

const compareStatus = (a, b) => Number(!isActive(a)) - Number(!isActive(b))
const compareNames = (a, b) => String(a.name ?? '').localeCompare(String(b.name ?? ''))
const compareClientOrder = (a, b) => compareStatus(a, b)
  || (a.startDate && b.startDate ? b.startDate.localeCompare(a.startDate) : 0)
  || compareNames(a, b)

export function sortActiveFirst(records) {
  return [...records].sort((a, b) => compareStatus(a, b) || compareNames(a, b))
}

export function trainerSelectableForAvailability(trainer) {
  return isActive(trainer)
}

export function visibleClientsForUser(user, clients, sessions = []) {
  const scoped = managesOperations(user) ? clients : clients.filter(client =>
    clientAssignedToTrainer(client, user.trainerId, sessions)
  )
  return [...scoped].sort(compareClientOrder)
}

export function visibleTrainersForOwner(trainers) {
  return sortActiveFirst(trainers)
}

export function remainingTrainerSessions(trainerId, sessions, clients = []) {
  return sessions
    .filter(session =>
      session.trainerId === trainerId &&
      !sessionIsInactive(clients.find(client => client.id === session.clientId), session) &&
      !['completed', 'cancelled'].includes(session.status)
    )
    .sort((a, b) => `${a.date}T${a.from}`.localeCompare(`${b.date}T${b.from}`))
}

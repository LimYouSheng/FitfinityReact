import { clientPackages } from './clientPackages.js'
import { managesOperations } from './permissions.js'

const packageIdFor = client => client.package.id ?? `legacy-package-${client.id}-${client.package.startDate}`

// Future purchases count as renewed immediately; inactive purchases do not.
function hasNextPackage(client, purchased) {
  return Boolean(purchased?.endDate && clientPackages(client).some(next => next.id !== purchased.id &&
    next.status !== 'inactive' && next.startDate > purchased.endDate))
}

export function renewalStatus(message, client) {
  if (message.kind !== 'renewal') return null
  if (message.renewalDismissal) return 'removed'
  if (!client) return 'active'
  const purchased = message.renewal?.clientPackageId
    ? clientPackages(client).find(item => item.id === message.renewal.clientPackageId)
    : client.package
  return hasNextPackage(client, purchased) ? 'renewed' : 'active'
}

export function canDismissRenewal(user, message, client) {
  return message?.kind === 'renewal' && (!message.renewalStatus || message.renewalStatus === 'active') &&
    (managesOperations(user) || (user?.role === 'trainer' && Boolean(user.trainerId) && client?.trainerId === user.trainerId))
}

export function appendRenewalMessage(db, client, createdAt = new Date().toISOString()) {
  const purchased = client.package
  const threshold = db.settings.renewal.remainingSessions
  if (client.status === 'inactive' || purchased?.status === 'inactive' || !purchased || !Number.isInteger(purchased.total) || !Number.isInteger(purchased.used)
    || purchased.total < 1 || purchased.used < 0 || purchased.used > purchased.total
    || !Number.isInteger(threshold) || threshold < 1) return null

  const clientPackageId = packageIdFor(client)
  const existing = db.messages.find(message => message.kind === 'renewal' && message.clientId === client.id
    && message.renewal?.type === 'last_sessions' && message.renewal.clientPackageId === clientPackageId)
  if (existing) return existing
  const remaining = purchased.total - purchased.used
  if (remaining !== threshold || hasNextPackage(client, purchased)) return null

  const message = {
    id: `renewal-${encodeURIComponent(clientPackageId)}`,
    createdAt,
    recipientRole: 'owner',
    ...(client.trainerId ? { recipientTrainerId: client.trainerId, trainerId: client.trainerId } : {}),
    clientId: client.id,
    title: `Renewal follow-up: ${client.name}`,
    body: `${client.name} is approaching package renewal. ${purchased.used}/${purchased.total} sessions used · ${remaining} sessions remaining.`,
    kind: 'renewal',
    renewal: { type: 'last_sessions', clientPackageId, used: purchased.used, total: purchased.total, remaining },
    readBy: {},
  }
  db.messages.push(message)
  return message
}

export function migrateRenewalMessages(db, createdAt = new Date().toISOString()) {
  if (db.renewalMessageVersion === 1) return false
  const previous = (db.messages ?? []).filter(message => message.kind === 'renewal')
  db.messages = (db.messages ?? []).filter(message => message.kind !== 'renewal')
  for (const client of db.clients) {
    if (!client.package) continue
    client.package.id ??= packageIdFor(client)
    const legacy = previous.find(message => message.clientId === client.id)
    const message = appendRenewalMessage(db, client, legacy?.createdAt ?? createdAt)
    if (message && legacy) {
      message.id = legacy.id
      if (legacy.readBy) message.readBy = structuredClone(legacy.readBy)
      else {
        // Leave identity recovery to the message-receipt migration after renewal routing.
        delete message.readBy
        message.read = legacy.read ?? false
        if (legacy.readAt) message.readAt = legacy.readAt
      }
    }
  }
  db.renewalMessageVersion = 1
  return true
}

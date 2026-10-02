import { adminMessageAllowed } from './adminProjection.js'

/** Recipient selectors are additive: renewal notices reach operations and a trainer. */
export function messageVisibleTo(user, message) {
  if (!user?.id || !message || (user.role === 'admin' && !adminMessageAllowed(message))) return false
  return message.recipientUserId === user.id ||
    (Boolean(user.role) && message.recipientRole === user.role) ||
    (user.role === 'admin' && message.recipientRole === 'owner') ||
    (user.role === 'trainer' && Boolean(user.trainerId) && message.recipientTrainerId === user.trainerId)
}

/** UI read state belongs to this viewer; other users' receipts never leave persistence. */
export function messageForUser(message, user) {
  const result = { ...message }
  const receipts = message.readBy ?? {}
  const read = Boolean(user?.id && Object.hasOwn(receipts, user.id))
  delete result.readBy
  delete result.readAt
  result.read = read
  if (read && receipts[user.id].readAt) result.readAt = receipts[user.id].readAt
  return result
}

/** Shared legacy flags have no reader identity. Never attribute them to every recipient. */
export function normalizeMessageReceipts(db) {
  for (const message of db.messages ?? []) {
    if (!Object.hasOwn(message, 'readBy')) {
      message.readBy = {}
      if (message.read && !message.recipientRole && (message.recipientUserId || message.recipientTrainerId)) {
        const recipients = db.users.filter(user => messageVisibleTo(user, message))
        if (recipients.length === 1) message.readBy[recipients[0].id] = message.readAt ? { readAt: message.readAt } : {}
      }
    }
    delete message.read
    delete message.readAt
  }
}

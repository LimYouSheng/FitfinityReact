import { delay, mockDb } from './mockDb.js'
import { messageForUser, messageVisibleTo } from '../app/messageInbox.js'
import { requireActiveActor } from '../app/scheduleChanges.js'
import { PortalContractError } from './portalContracts.js'

async function setRead(id, actor, read) {
  await delay(80)
  const state = mockDb.mutate(db => {
    const staff = requireActiveActor(db, actor)
    const message = db.messages.find(item => item.id === id)
    if (!messageVisibleTo(staff, message)) throw new PortalContractError('FORBIDDEN', 'This message is unavailable.')
    message.readBy ??= {}
    if (read) message.readBy[staff.id] = { readAt: message.readBy[staff.id]?.readAt ?? new Date().toISOString() }
    else delete message.readBy[staff.id]
  })
  return messageForUser(state.messages.find(message => message.id === id), actor)
}

export const messageService = {
  markRead: (id, actor) => setRead(id, actor, true),
  markUnread: (id, actor) => setRead(id, actor, false),
}

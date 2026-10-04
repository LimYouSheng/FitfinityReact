import { delay, mockDb } from './mockDb.js'
import { messageForUser, messageVisibleTo } from '../app/messageInbox.js'
import { requireActiveActor } from '../app/scheduleChanges.js'
import { PortalContractError } from './portalContracts.js'
import { canDismissRenewal, renewalStatus } from '../app/renewals.js'
import { requireMutationActor, mutationVideos, requireUndoReady, reverseSessionMutation } from './sessionMutation.js'
import { loadExerciseVideoBlob } from './exerciseVideoStore.js'
import { flushExerciseVideoDeletions } from './exerciseVideoRetention.js'

function undoTarget(db, id, actor) {
  const message = db.messages.find(item => item.id === id)
  if (!messageVisibleTo(actor, message)) throw new PortalContractError('FORBIDDEN', 'This message is unavailable.')
  const entry = db.sessionMutations?.find(item => item.id === message.mutationId)
  requireUndoReady(db, entry, actor)
  return entry
}

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
  async dismissRenewal(id, actor) {
    await delay(80)
    const state = mockDb.mutate(db => {
      const staff = requireMutationActor(db, actor)
      const message = db.messages.find(item => item.id === id)
      const client = db.clients.find(item => item.id === message?.clientId)
      if (!messageVisibleTo(staff, message) || !canDismissRenewal(staff, message, client)) throw new PortalContractError('FORBIDDEN', 'This renewal follow-up is unavailable.')
      if (message.renewalDismissal || renewalStatus(message, client) === 'renewed') return
      message.renewalDismissal = { at: new Date().toISOString(), by: { id: staff.id, name: staff.name } }
    })
    const message = state.messages.find(item => item.id === id)
    return { ...messageForUser(message, actor), renewalStatus: renewalStatus(message, state.clients.find(item => item.id === message.clientId)) }
  },
  async undo(id, actor) {
    await delay(80)
    const entry = undoTarget(mockDb.read(), id, actor)
    if (entry.status !== 'undone') for (const item of mutationVideos(entry)) {
      if (!await loadExerciseVideoBlob(item.sessionId, item.exerciseId, item.mediaId)) throw new Error('The original video is no longer available. This change cannot be restored.')
    }
    const state = mockDb.mutate(db => reverseSessionMutation(db, undoTarget(db, id, actor), actor))
    await flushExerciseVideoDeletions()
    const saved = state.sessionMutations.find(item => item.id === entry.id)
    return { id: saved.id, status: saved.status, undoneAt: saved.undoneAt }
  },
  markRead: (id, actor) => setRead(id, actor, true),
  markUnread: (id, actor) => setRead(id, actor, false),
}

import { mockDb } from './mockDb.js'
import { requireActiveActor } from '../app/scheduleChanges.js'
import { managesOperations } from '../app/permissions.js'
import { clientPackages, packageForRecord } from '../app/clientPackages.js'
import { sessionOccupiesTime, requireSessionSlotAvailable } from '../app/bookingAvailability.js'
import { businessClock } from '../app/clock.js'
import { cycleForDate, sessionPaySource } from '../app/remuneration.js'
import { exerciseVideoExpired } from '../app/video.js'
import { messageVisibleTo } from '../app/messageInbox.js'
import { createUuid } from '../utils/uuid.js'

const clone = value => structuredClone(value)
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b)
const DAY = 86400000
const actorGuards = new WeakMap()
const id = () => `session-change-${createUuid()}`
const sessionState = session => session && Object.fromEntries(Object.entries(session).filter(([key]) => !['acknowledgementHistory', 'acknowledgementReversals'].includes(key)))
const recordState = record => record && Object.fromEntries(Object.entries(record).filter(([key]) => !['strengthProgress', 'progressBaseline'].includes(key)))
const object = value => value && typeof value === 'object' && !Array.isArray(value)

// Adapter-owned guards cannot be supplied in an operation's input.
export function bindSessionMutationActor(actor, guard) { actorGuards.set(actor, guard) }
export function requireMutationActor(db, actor) { const staff = requireActiveActor(db, actor); actorGuards.get(actor)?.(); return staff }

function differences(before, after, path = []) {
  if (same(before, after)) return []
  if (object(before) && object(after)) return [...new Set([...Object.keys(before), ...Object.keys(after)])]
    .flatMap(key => differences(before[key], after[key], [...path, key]))
  return [{ path, before: before === undefined ? [] : [clone(before)], after: after === undefined ? [] : [clone(after)] }]
}
const get = (record, path) => path.reduce((value, key) => value?.[key], record)
function set(record, path, value) {
  const parent = path.slice(0, -1).reduce((target, key) => target[key] ??= {}, record)
  if (value.length) parent[path.at(-1)] = clone(value[0])
  else delete parent[path.at(-1)]
}
const envelope = value => value === undefined ? [] : [value]
const requestState = message => ({ status: message.status, request: message.request, decidedAt: message.decidedAt, cancelledAt: message.cancelledAt })
const sessionRequest = message => message.request && ['session_time', 'session_trainer', 'session_postpone', 'fixed_weekly_schedule'].includes(message.request.type)
// Older releases journalled completion. Retain that evidence, but never offer
// or execute its inverse, including a no-show-to-signature correction.
const changesAcknowledgement = entry => entry.operation === 'session.acknowledge' || Boolean(entry.debits?.length) ||
  entry.sessions.some(change => !same(change.before?.acknowledgement ?? null, change.after?.acknowledgement ?? null))

/** Journal the domain transaction, including indirect bulk session changes. */
export function mutateSessionRecords(actor, operation, mutator) {
  let before, staff
  return mockDb.mutate(db => {
    before = clone(db)
    mutator(db)
    staff = requireMutationActor(before, actor)
  }, db => {
    if (operation === 'session.acknowledge') return
    const sessions = [...new Set([...before.sessions, ...db.sessions].map(item => item.id))].flatMap(sessionId => {
      const previous = before.sessions.find(item => item.id === sessionId), next = db.sessions.find(item => item.id === sessionId)
      return same(previous, next) ? [] : [{ id: sessionId, position: before.sessions.findIndex(item => item.id === sessionId), before: previous ?? null, after: next ? clone(next) : null }]
    })
    const created = db.messages.filter(message => !before.messages.some(item => item.id === message.id))
    const proposals = created.filter(message => sessionRequest(message) && message.status === 'pending')
    // Status/package changes can freeze sessions without rewriting their rows.
    const lifecycle = ['client.deactivate', 'client.deactivatePackage', 'client.reactivate', 'trainer.reactivate'].includes(operation)
    if (!sessions.length && !proposals.length && !lifecycle) return
    const patches = []
    for (const collection of ['clients', 'trainers', 'users']) {
      for (const recordId of new Set([...before[collection], ...db[collection]].map(item => item.id))) {
        const previous = before[collection].find(item => item.id === recordId), next = db[collection].find(item => item.id === recordId)
        const previousState = recordState(previous), nextState = recordState(next)
        const deltas = differences(previousState, nextState)
        if (deltas.length) patches.push({ collection, id: recordId, deltas })
      }
    }
    if (!sessions.length && !proposals.length && !patches.length) return
    const committedAt = new Date().toISOString(), operationId = id()
    const changedRequests = db.messages.filter(message => {
      const previous = before.messages.find(item => item.id === message.id)
      return previous && sessionRequest(message) && !same(requestState(previous), requestState(message))
    }).map(message => ({ id: message.id, after: requestState(message) }))
    const dependencies = db.sessions.filter(session => !sessions.some(change => change.id === session.id) && patches.some(patch =>
      patch.collection === 'clients' && patch.id === session.clientId || patch.collection === 'trainers' && patch.id === session.trainerId)).map(session => ({ id: session.id, state: sessionState(session) }))
    const entry = { id: operationId, operation, actor: { id: staff.id, name: staff.name, role: staff.role, ...(staff.trainerId ? { trainerId: staff.trainerId } : {}) },
      committedAt, expiresAt: new Date(Date.parse(committedAt) + DAY).toISOString(), sessions, patches,
      requests: changedRequests, proposals: proposals.map(message => ({ id: message.id, after: requestState(message) })), dependencies,
      messageIds: created.map(message => message.id), status: 'available' }
    db.sessionMutations ??= []
    db.sessionMutations.push(entry)
    for (const message of [...created, ...db.messages.filter(item => changedRequests.some(request => request.id === item.id))]) message.mutationId = operationId
    // Ensure the person who performed an autonomous change can reach its Undo.
    if (!created.some(message => messageVisibleTo(staff, message)) && !changedRequests.some(request => messageVisibleTo(staff, db.messages.find(item => item.id === request.id)))) {
      const first = sessions[0]?.after ?? sessions[0]?.before
      const notice = { id: `${operationId}-actor`, mutationId: operationId, recipientUserId: staff.id, recipientRole: 'owner',
        sessionId: first?.id, clientId: first?.clientId, trainerId: first?.trainerId, kind: 'session_update',
        title: created[0]?.title ?? 'Session updated', body: created[0]?.body ?? 'The session record was updated.', createdAt: committedAt, readBy: {} }
      db.messages.push(notice); entry.messageIds.push(notice.id)
    }
  })
}

export function mutationVideos(entry) {
  return entry.sessions.flatMap(change => (change.before?.exercisePlan ?? []).filter(item => item.videoAttached && !change.after?.exercisePlan?.some(next => next.id === item.id && next.videoAttached && same(next.video, item.video))).map(item =>
    ({ sessionId: change.id, exerciseId: item.id, mediaId: item.video?.id, video: item.video })))
}

export function retainedMutationVideos(db, now = new Date()) {
  return (db.sessionMutations ?? []).filter(entry => entry.status === 'available' && Date.parse(entry.expiresAt) > +now)
    .flatMap(mutationVideos).filter(item => !exerciseVideoExpired(item.video, now, db.settings.videoRetentionDays))
}

function requireUndoAuthority(db, entry, actor) {
  const staff = requireMutationActor(db, actor)
  if (managesOperations(staff)) return staff
  if (staff.id !== entry.actor.id || staff.role !== 'trainer' || entry.actor.role !== 'trainer' || !db.trainers.some(item => item.id === staff.trainerId && item.status === 'active')) throw new Error('Only the original trainer or Owner/Admin can undo this change.')
  if (entry.sessions.some(change => (db.sessions.find(item => item.id === change.id)?.trainerId ?? change.after?.trainerId) !== staff.trainerId)) throw new Error('The session is no longer assigned to you.')
  const approval = entry.operation === 'client.saveFixedWeeklySchedule' ? 'fixedWeeklySchedule' : entry.operation === 'session.requestTrainerChange' ? 'trainerReassignment' : ['session.requestTimeChange', 'session.postpone'].includes(entry.operation) ? 'sessionTime' : null
  if (!entry.proposals.length && approval && db.trainers.find(item => item.id === staff.trainerId).approvalNeeded?.[approval] !== false) throw new Error('Owner/Admin approval is now required to reverse this schedule change.')
  return staff
}

export function requireUndoReady(db, entry, actor, now = new Date()) {
  if (!entry) throw new Error('This message has no recoverable session change.')
  requireUndoAuthority(db, entry, actor)
  if (changesAcknowledgement(entry)) throw new Error('Acknowledgements cannot be undone.')
  if (entry.status === 'undone') return
  if (Date.parse(entry.expiresAt) <= +now) throw new Error('Undo expired. Changes can only be undone within 24 hours.')
  for (const change of entry.sessions) {
    const current = db.sessions.find(item => item.id === change.id) ?? null
    if (!same(sessionState(current), sessionState(change.after))) throw new Error('The session changed again. Undo the later change first or review it with the owner.')
    if (db.messages.some(message => message.status === 'pending' && (message.request?.sessionId === change.id || message.request?.type === 'fixed_weekly_schedule' && message.request.clientId === (change.after ?? change.before).clientId) && !entry.proposals.some(proposal => proposal.id === message.id))) throw new Error('A pending request depends on this session. Resolve it before Undo.')
  }
  for (const dependency of entry.dependencies) {
    if (!same(sessionState(db.sessions.find(item => item.id === dependency.id)), dependency.state)) throw new Error('A dependent session changed. Review this change with the owner.')
  }
  for (const patch of entry.patches) for (const delta of patch.deltas) {
    if (!same(envelope(get(recordState(db[patch.collection].find(item => item.id === patch.id)), delta.path)), delta.after)) throw new Error('A related record changed. Review this change with the owner.')
  }
  for (const request of [...entry.proposals, ...entry.requests]) {
    const message = db.messages.find(item => item.id === request.id)
    if (!message || !same(requestState(message), request.after)) throw new Error('This request has already changed. Review its current decision.')
  }
  for (const change of entry.sessions) {
    const session = change.after ?? change.before
    const client = db.clients.find(item => item.id === session.clientId)
    const lifecycle = entry.operation.startsWith('client.') || entry.operation === 'trainer.deactivate'
    if (!lifecycle && (client?.status !== 'active' || packageForRecord(client, session)?.status === 'inactive')) throw new Error('The client or package is inactive. Review it before Undo.')
    const changesPay = !change.before || !change.after || sessionPaySource(change.before) !== sessionPaySource(change.after)
    if (changesPay && (db.remunerationApprovals ?? []).some(record => [change.before, change.after].some(item => item && record.trainerId === item.trainerId && record.cycle.key === cycleForDate(item.date, db.settings.remuneration)))) throw new Error('This change affects approved remuneration. An owner payment adjustment is required.')
  }
  if (mutationVideos(entry).some(item => exerciseVideoExpired(item.video, now, db.settings.videoRetentionDays))) throw new Error('The original media has expired and cannot be restored.')
}

export function mutationForMessage(db, message, actor, now = new Date()) {
  const entry = db.sessionMutations?.find(item => item.id === message.mutationId)
  if (!entry || changesAcknowledgement(entry)) return null
  const result = { id: entry.id, expiresAt: entry.expiresAt, status: entry.status, count: entry.sessions.length,
    ...(entry.operation === 'session.markWhatsAppOpened' ? { notice: 'Undo only corrects this record. It cannot recall a WhatsApp message.' } : {}) }
  if (entry.status === 'undone') return { ...result, undoneAt: entry.undoneAt }
  if (Date.parse(entry.expiresAt) <= +now) return { ...result, status: 'expired' }
  try { requireUndoReady(db, entry, actor, now) } catch (error) { return { ...result, status: 'blocked', reason: error.message } }
  return result
}

/** Apply compensation to the transaction copy; callers persist only on success. */
export function reverseSessionMutation(db, entry, actor) {
  requireUndoReady(db, entry, actor)
  if (entry.status === 'undone') return
  const now = new Date(), at = now.toISOString(), staff = requireMutationActor(db, actor)
  const clock = businessClock(now, db.settings.timeZone)
  const priorClients = clone(db.clients)
  for (const patch of entry.patches) {
    const records = db[patch.collection], index = records.findIndex(item => item.id === patch.id)
    for (const delta of patch.deltas) {
      if (!delta.path.length) {
        if (index >= 0) records.splice(index, 1)
        if (delta.before.length) records.push(clone(delta.before[0]))
      } else set(records[index], delta.path, delta.before)
    }
  }
  for (const change of entry.sessions) {
    const index = db.sessions.findIndex(item => item.id === change.id), current = db.sessions[index]
    if (change.before && change.after && ['date', 'from', 'to', 'trainerId'].some(key => change.before[key] !== change.after[key]) &&
      [change.before, change.after].some(item => `${item.date}T${item.from}` <= `${clock.date}T${clock.time}`)) throw new Error('A session has already started. Review its schedule with the owner.')
    if (index >= 0) db.sessions.splice(index, 1)
    if (change.before) {
      const restored = clone(change.before)
      if (current?.acknowledgementHistory?.length) restored.acknowledgementHistory = clone(current.acknowledgementHistory)
      if (current?.acknowledgementReversals?.length) restored.acknowledgementReversals = clone(current.acknowledgementReversals)
      db.sessions.splice(Math.max(0, change.position), 0, restored)
    }
  }
  // Keep historical evidence even when the current status/assignment is reversed.
  const mergeHistory = (earlier = [], later = []) => [...earlier, ...later.filter(item => !earlier.some(old => same(old, item)))]
  for (const client of db.clients) {
    const prior = priorClients.find(item => item.id === client.id)
    if (!prior) continue
    if (prior.trainerAssignmentHistory?.length) client.trainerAssignmentHistory = clone(prior.trainerAssignmentHistory)
    if (prior.trainerId !== client.trainerId) {
      const trainer = trainerId => ({ id: trainerId, name: db.trainers.find(item => item.id === trainerId)?.name ?? trainerId })
      client.trainerAssignmentHistory = [...(client.trainerAssignmentHistory ?? []), { id: `undo-${entry.id}`, at, by: { id: staff.id, name: staff.name },
        from: trainer(prior.trainerId), to: trainer(client.trainerId), packages: [], sessions: [], reversalOf: entry.id }]
    }
    for (const purchased of clientPackages(client)) {
      const previous = clientPackages(prior).find(item => item.id === purchased.id)
      if (!previous) continue
      if (previous.statusHistory?.length) purchased.statusHistory = mergeHistory(purchased.statusHistory, previous.statusHistory)
      if (previous.sessionDeletionHistory?.length) purchased.sessionDeletionHistory = mergeHistory(purchased.sessionDeletionHistory, previous.sessionDeletionHistory)
      if (previous.status !== purchased.status) purchased.statusHistory = [...(purchased.statusHistory ?? []), { status: purchased.status ?? 'active', reason: 'undo', at, by: { id: staff.id, name: staff.name }, reversalOf: entry.id }]
    }
  }
  const affectedIds = new Set([...entry.sessions.map(item => item.id), ...entry.dependencies.map(item => item.id)])
  for (const session of db.sessions.filter(item => affectedIds.has(item.id) && sessionOccupiesTime(item, db.clients))) {
    if (!db.trainers.some(item => item.id === session.trainerId && item.status === 'active') && session.status !== 'completed') throw new Error('The original trainer is inactive.')
    requireSessionSlotAvailable(db, session)
  }
  for (const request of entry.proposals) for (const message of db.messages.filter(item => item.id === request.id || item.requestId === request.id)) Object.assign(message, { status: 'cancelled', cancelledAt: at, cancelledBy: { id: staff.id, name: staff.name }, reversedBy: entry.id })
  for (const request of entry.requests) for (const message of db.messages.filter(item => item.id === request.id || item.requestId === request.id)) Object.assign(message, { status: 'reversed', reversedAt: at, reversedBy: entry.id })
  Object.assign(entry, { status: 'undone', undoneAt: at, undoneBy: staff.id })
  for (const message of db.messages.filter(item => entry.messageIds.includes(item.id))) message.reversedAt = at
  const first = entry.sessions[0]?.before ?? entry.sessions[0]?.after
  db.messages.push({ id: `undo-${entry.id}`, recipientRole: 'owner', recipientUserId: entry.actor.id, ...(first?.trainerId ? { recipientTrainerId: first.trainerId } : {}),
    sessionId: first?.id, clientId: first?.clientId, kind: 'session_undo', title: 'Session change undone',
    body: `${staff.name} undid ${entry.sessions.length ? `${entry.sessions.length} session change${entry.sessions.length === 1 ? '' : 's'}` : 'the pending request'}. Original history is retained.`, createdAt: at, readBy: {}, reversedMutationId: entry.id })
}

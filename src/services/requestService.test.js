import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { mockDb } from './mockDb.js'
import { sessionService } from './sessionService.js'
import { requestService } from './requestService.js'
import { clientService } from './clientService.js'
import { trainerService } from './trainerService.js'
import { mockPortalAdapter } from './mockPortalAdapter.js'
import { MOCK_SESSION_KEY } from './authService.js'
import { pendingSessionChanges } from '../app/sessionRules.js'
let owner, actor, session
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-09-02T04:00:00Z'))
  mockDb.reset()
  mockDb.mutate(db => { db.sessions.find(item => item.id === 's1').date = '2026-09-02' })
  mockDb.mutate(db => {
    owner = db.users.find(item => item.role === 'owner')
    session = db.sessions.find(item => item.id === 's1')
    actor = db.users.find(item => item.trainerId === session.trainerId)
    db.trainers.find(item => item.id === session.trainerId).approvalNeeded = { sessionTime: true, trainerReassignment: true }
  })
})
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks() })
async function pending(type = 'time') {
  if (type === 'time') await sessionService.requestTimeChange(session.id, actor, { date: '2026-12-01', from: '10:00', to: '11:00' })
  else await sessionService.requestTrainerChange(session.id, actor, mockDb.read().trainers.find(item => item.status === 'active' && item.id !== actor.trainerId).id)
  return mockDb.read().messages.findLast(item => item.request?.sessionId === session.id)
}
it('approves time atomically and updates the exact receipt with an unread routed decision', async () => {
  const request = await pending()
  expect(mockDb.read().sessions.find(item => item.id === session.id)).toEqual(session)
  await requestService.resolve(request.id, 'approved', owner)
  const db = mockDb.read()
  expect(db.sessions.find(item => item.id === session.id)).toMatchObject(request.request.next)
  expect(db.messages.filter(item => item.requestId === request.id)).toHaveLength(2)
  expect(db.messages.filter(item => item.requestId === request.id).every(item => item.status === 'approved')).toBe(true)
  expect(db.messages.find(item => item.kind === 'request_decision')).toMatchObject({ read: false, sessionId: session.id, recipientTrainerId: actor.trainerId })
})
it('rejects without changing session or credits', async () => {
  const request = await pending(); const before = mockDb.read()
  await requestService.resolve(request.id, 'rejected', owner)
  expect(mockDb.read().sessions).toEqual(before.sessions)
  expect(mockDb.read().packageCreditTransactions).toEqual(before.packageCreditTransactions)
})
it('requires stored active owner identity', async () => {
  const request = await pending(); const before = mockDb.read()
  for (const invalid of [actor, {id: actor.id, role:'owner'}, {id:'missing', role:'owner'}]) await expect(requestService.resolve(request.id, 'approved', invalid)).rejects.toThrow('active owner')
  expect(mockDb.read()).toEqual(before)
})
it('cannot decide twice or emit duplicate messages', async () => {
  const request = await pending(); await requestService.resolve(request.id, 'approved', owner)
  const before = mockDb.read()
  await expect(requestService.resolve(request.id, 'rejected', owner)).rejects.toThrow('already')
  expect(mockDb.read()).toEqual(before)
})
it('rejects stale approval but still allows rejection', async () => {
  const request = await pending()
  mockDb.mutate(db => { db.sessions.find(item => item.id === session.id).from = '07:00' })
  const before = mockDb.read()
  await expect(requestService.resolve(request.id, 'approved', owner)).rejects.toThrow('changed')
  expect(mockDb.read()).toEqual(before)
  await requestService.resolve(request.id, 'rejected', owner)
  for (const proposedPassesFirst of [false, true]) {
    mockDb.reset()
  mockDb.mutate(db => { db.sessions.find(item => item.id === 's1').date = '2026-09-02' })
    vi.setSystemTime(new Date('2026-09-02T04:00:00Z'))
    await sessionService.requestTimeChange(session.id, actor, proposedPassesFirst
      ? { date: '2026-09-02', from: '13:00', to: '14:00' }
      : { date: '2026-12-01', from: '10:00', to: '11:00' })
    const timedRequest = mockDb.read().messages.findLast(item => item.request?.sessionId === session.id)
    vi.setSystemTime(new Date(proposedPassesFirst ? '2026-09-02T05:00:00Z' : '2026-09-02T10:00:00Z'))
    const unchanged = mockDb.read()
    await expect(requestService.resolve(timedRequest.id, 'approved', owner)).rejects.toThrow(proposedPassesFirst ? 'in the future' : 'before the session starts')
    expect(mockDb.read()).toEqual(unchanged)
    await requestService.resolve(timedRequest.id, 'rejected', owner)
    expect(mockDb.read().sessions).toEqual(unchanged.sessions)
  }
})
it('blocks completed sessions without mutation', async () => {
  const request = await pending()
  mockDb.mutate(db => { db.sessions.find(item => item.id === session.id).status = 'completed' })
  const before = mockDb.read()
  await expect(requestService.resolve(request.id, 'approved', owner)).rejects.toThrow('eligible')
  expect(mockDb.read()).toEqual(before)
})
it('approves trainer reassignment and notifies both trainers', async () => {
  const request = await pending('trainer')
  await requestService.resolve(request.id, 'approved', owner)
  const db = mockDb.read()
  expect(db.sessions.find(item => item.id === session.id).trainerId).toBe(request.request.replacementTrainerId)
  expect(db.messages.filter(item => item.kind === 'request_decision')).toHaveLength(2)
})
it('blocks inactive replacement trainers', async () => {
  const request = await pending('trainer')
  mockDb.mutate(db => { db.trainers.find(item => item.id === request.request.replacementTrainerId).status = 'inactive' })
  const before = mockDb.read()
  await expect(requestService.resolve(request.id, 'approved', owner)).rejects.toThrow('replacement')
  expect(mockDb.read()).toEqual(before)
})
it('rolls back a time change if it conflicts with another session', async () => {
  const request = await pending()
  mockDb.mutate(db => { db.sessions.push({ ...session, id:'conflict', ...request.request.next }) })
  const before = mockDb.read()
  await expect(requestService.resolve(request.id, 'approved', owner)).rejects.toThrow('conflicts')
  expect(mockDb.read()).toEqual(before)
})

async function cancellationRequest(type) {
  if (type === 'session_time') return pending()
  if (type === 'session_trainer') return pending('trainer')
  if (type === 'trainer_availability') {
    await trainerService.saveAvailability(actor.trainerId, [{ days: ['Monday'], from: '09:00', to: '12:00' }], actor)
  } else {
    mockDb.mutate(db => { db.sessions = db.sessions.filter(item => item.clientId === session.clientId) })
    const client = mockDb.read().clients.find(item => item.id === session.clientId)
    await clientService.saveFixedWeeklySchedule(client.id, client.fixedWeeklySchedule.map(slot => ({ ...slot, from: '19:00', to: '20:00' })), actor)
  }
  return mockDb.read().messages.findLast(item => item.request?.type === type)
}

it.each(['session_time', 'session_trainer', 'fixed_weekly_schedule', 'trainer_availability'])('cancels an owned %s request and its receipts atomically with actor/time, notices and unchanged domain records', async type => {
  const request = await cancellationRequest(type), before = mockDb.read()
  const cancelled = await requestService.cancel(request.id, actor)
  const after = mockDb.read(), cancellation = { status: 'cancelled', cancelledAt: '2026-09-02T04:00:00.000Z', cancelledBy: { id: actor.id, name: actor.name, trainerId: actor.trainerId } }
  expect(cancelled).toMatchObject(cancellation)
  expect(cancelled.request).toEqual(request.request)
  expect(after.messages.filter(item => item.requestId === request.id)).toHaveLength(3)
  for (const linked of after.messages.filter(item => item.id === request.id || item.requestId === request.id)) expect(linked).toMatchObject(cancellation)
  expect(after.messages.filter(item => item.id.startsWith(`cancellation-${request.id}-`))).toEqual(expect.arrayContaining([
    expect.objectContaining({ recipientRole: 'owner', read: false }),
    expect.objectContaining({ recipientTrainerId: actor.trainerId, read: false }),
  ]))
  expect({ ...after, messages: before.messages }).toEqual(before)
  expect(mockDb.reload().messages.find(item => item.id === request.id)).toEqual(cancelled)
  await expect(requestService.resolve(request.id, 'approved', owner)).rejects.toThrow('already')
  expect(mockDb.read()).toEqual(after)
})

it('cancels just one duplicate request and keeps the session pending until the remaining request is cancelled', async () => {
  const first = await pending(), second = await pending()
  await requestService.cancel(first.id, actor)
  expect(mockDb.read().messages.find(item => item.id === second.id).status).toBe('pending')
  expect(pendingSessionChanges(mockDb.read().messages, session.id)).toEqual([{ kind: 'session_time', label: 'Time change pending' }])
  await requestService.cancel(second.id, actor)
  expect(pendingSessionChanges(mockDb.read().messages, session.id)).toEqual([])
})

it('rejects owner, other trainer, forged and inactive cancellation identities without writes', async () => {
  const request = await pending(), before = mockDb.read()
  const other = before.users.find(item => item.role === 'trainer' && item.trainerId !== actor.trainerId)
  for (const invalid of [owner, other, { ...actor, id: 'unknown' }, { ...actor, trainerId: other.trainerId }, { ...other, trainerId: actor.trainerId }]) {
    await expect(requestService.cancel(request.id, invalid)).rejects.toThrow()
    expect(mockDb.read()).toEqual(before)
  }
  for (const collection of ['users', 'trainers']) {
    mockDb.write(before)
    mockDb.mutate(db => { db[collection].find(item => item.id === (collection === 'users' ? actor.id : actor.trainerId)).status = 'inactive' })
    const inactive = mockDb.read()
    await expect(requestService.cancel(request.id, actor)).rejects.toThrow()
    expect(mockDb.read()).toEqual(inactive)
  }
})

it.each(['approved', 'rejected'])('does not cancel a request already %s by the owner', async decision => {
  const request = await pending()
  await requestService.resolve(request.id, decision, owner)
  const before = mockDb.read()
  await expect(requestService.cancel(request.id, actor)).rejects.toThrow('no longer pending')
  expect(mockDb.read()).toEqual(before)
})

it('retries cancellation without writes, duplicate notices or a new timestamp', async () => {
  const request = await pending()
  const saved = await requestService.cancel(request.id, actor), before = mockDb.read()
  vi.setSystemTime(new Date('2026-09-02T04:05:00Z'))
  const write = vi.spyOn(Storage.prototype, 'setItem')
  expect(await requestService.cancel(request.id, actor)).toEqual(saved)
  expect(write).not.toHaveBeenCalled()
  expect(mockDb.read()).toEqual(before)
})

it('rolls back a failed cancellation save and allows a complete retry', async () => {
  const request = await pending(), before = mockDb.read()
  vi.spyOn(Storage.prototype, 'setItem').mockImplementationOnce(() => { throw new Error('Storage full') })
  await expect(requestService.cancel(request.id, actor)).rejects.toThrow('Storage full')
  expect(mockDb.read()).toEqual(before)
  await requestService.cancel(request.id, actor)
  expect(mockDb.read().messages.filter(item => item.id.startsWith(`cancellation-${request.id}-`))).toHaveLength(2)
})

it('allows withdrawing a stale proposal without applying it and rejects missing or nonrequest IDs', async () => {
  const request = await pending()
  mockDb.mutate(db => { db.sessions.find(item => item.id === session.id).from = '07:00' })
  const before = mockDb.read()
  for (const id of ['missing', before.messages.find(item => item.requestId === request.id).id]) {
    await expect(requestService.cancel(id, actor)).rejects.toThrow('unavailable')
    expect(mockDb.read()).toEqual(before)
  }
  await requestService.cancel(request.id, actor)
  expect(mockDb.read().sessions).toEqual(before.sessions)
})

it('projects the requesting trainer proposal into legacy receipts and derives cancellation identity from the authenticated adapter', async () => {
  const request = await pending()
  const receipt = mockDb.read().messages.find(item => item.requestId === request.id)
  const signIn = user => localStorage.setItem(MOCK_SESSION_KEY, JSON.stringify({ userId: user.id, expiresAt: Date.now() + 3600000 }))
  signIn(actor)
  const loaded = await mockPortalAdapter.load()
  expect(loaded.data.messages.find(item => item.id === receipt.id).request).toEqual(request.request)
  expect(mockDb.read().messages.find(item => item.id === receipt.id).request).toBeUndefined()
  const other = mockDb.read().users.find(item => item.role === 'trainer' && item.trainerId !== actor.trainerId)
  signIn(other)
  expect((await mockPortalAdapter.load()).data.messages.find(item => item.id === receipt.id).request).toBeUndefined()
  const before = mockDb.read()
  await expect(mockPortalAdapter.invoke('requestService', 'cancel', [request.id, actor])).rejects.toThrow('unavailable')
  expect(mockDb.read()).toEqual(before)
  signIn(actor)
  const saved = await mockPortalAdapter.invoke('requestService', 'cancel', [request.id, owner])
  expect(saved.cancelledBy.id).toBe(actor.id)
  await expect(mockPortalAdapter.invoke('requestService', 'resolve', [request.id, 'approved', owner])).rejects.toThrow('owner')
})

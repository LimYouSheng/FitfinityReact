import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { mockDb } from './mockDb.js'
import { sessionService } from './sessionService.js'
import { requestService } from './requestService.js'
let owner, actor, session
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-09-02T04:00:00Z'))
  mockDb.reset()
  mockDb.mutate(db => {
    owner = db.users.find(item => item.role === 'owner')
    session = db.sessions.find(item => item.id === 's1')
    actor = db.users.find(item => item.trainerId === session.trainerId)
    db.trainers.find(item => item.id === session.trainerId).approvalNeeded = { sessionTime: true, trainerReassignment: true }
  })
})
afterEach(() => vi.useRealTimers())
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

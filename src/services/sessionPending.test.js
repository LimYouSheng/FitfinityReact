import { beforeEach, expect, it } from 'vitest'
import { pendingSessionChanges } from '../app/sessionRules.js'
import { mockDb } from './mockDb.js'
import { sessionService } from './sessionService.js'
import { requestService } from './requestService.js'

beforeEach(() => mockDb.reset())
it('deduplicates pending request types and ignores receipts, unrelated sessions and completed decisions', () => {
  const request = { status: 'pending', request: { type: 'session_time', sessionId: 's1' } }
  expect(pendingSessionChanges([request, request, { ...request, status: 'approved' },
    { status: 'pending', requestId: 'receipt', sessionId: 's1' },
    { status: 'pending', request: { type: 'session_trainer', sessionId: 's2' } }], 's1'))
    .toEqual([{ kind: 'session_time', label: 'Time change pending' }])
})
it('shows both outstanding changes and clears each badge after its corresponding decision', async () => {
  let actor, owner
  mockDb.mutate(db => {
    const session = db.sessions.find(item => item.id === 's1')
    actor = db.users.find(user => user.trainerId === session.trainerId)
    owner = db.users.find(user => user.role === 'owner')
    db.trainers.find(item => item.id === actor.trainerId).approvalNeeded = { sessionTime: true, trainerReassignment: true }
  })
  await sessionService.requestTimeChange('s1', actor, { date: '2026-12-01', from: '10:00', to: '11:00' })
  const replacement = mockDb.read().trainers.find(item => item.status === 'active' && item.id !== actor.trainerId)
  await sessionService.requestTrainerChange('s1', actor, replacement.id)
  let db = mockDb.read()
  expect(pendingSessionChanges(db.messages, 's1').map(item => item.kind)).toEqual(['session_time', 'session_trainer'])
  await requestService.resolve(db.messages.findLast(item => item.request?.type === 'session_trainer').id, 'rejected', owner)
  db = mockDb.read()
  expect(pendingSessionChanges(db.messages, 's1').map(item => item.kind)).toEqual(['session_time'])
  await requestService.resolve(db.messages.findLast(item => item.request?.type === 'session_time').id, 'approved', owner)
  expect(pendingSessionChanges(mockDb.read().messages, 's1')).toEqual([])
})

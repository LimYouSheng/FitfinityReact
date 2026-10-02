import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { AUTH_CONTRACTS, PORTAL_CONTRACTS, portalRequest } from './portalContracts.js'
import { createPortalServices } from './portalService.js'
import { mockPortalAdapter } from './mockPortalAdapter.js'
import { mockPortalOperations } from './mockPortalOperations.js'
import { createApiPortalAdapter } from './apiPortalAdapter.js'
import { mockDb } from './mockDb.js'
import { payFixture } from '../test/fixtures/remuneration.js'
import { messageForUser } from '../app/messageInbox.js'
import { MOCK_SESSION_KEY } from './authService.js'

const signIn = userId => localStorage.setItem(MOCK_SESSION_KEY, JSON.stringify({ userId, expiresAt: Date.now() + 3600000 }))
const request = (service, operation, input = {}) => ({ service, operation, input })
beforeEach(() => { localStorage.clear(); mockDb.reset(); signIn('u-owner') })
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers() })

it('keeps every declared operation implemented and documents its resolved value', () => {
  const services = createPortalServices(mockPortalAdapter)
  expect(Object.keys(mockPortalOperations)).toEqual(Object.keys(PORTAL_CONTRACTS))
  for (const [service, operations] of Object.entries(PORTAL_CONTRACTS)) {
    expect(Object.keys(services[service])).toEqual(Object.keys(operations))
    expect(Object.keys(mockPortalOperations[service])).toEqual(Object.keys(operations))
    for (const contract of Object.values(operations)) {
      expect(contract.result).toEqual(expect.any(String))
      expect(contract.result.length).toBeGreaterThan(0)
      expect(Object.keys(contract.fields).some(key => /actor|context|user/i.test(key))).toBe(false)
    }
  }
  expect(Object.keys(services.auth)).toEqual(Object.keys(AUTH_CONTRACTS))
})

it('rejects positional, inherited and unknown dispatch before changing data', async () => {
  const before = mockDb.read()
  for (const bad of [null, [], 'clientService', { ...request('clientService', 'getAll'), context: { actor: before.users[0] } }]) {
    await expect(mockPortalAdapter.invoke(bad)).rejects.toMatchObject({ code: 'INVALID_REQUEST' })
  }
  for (const [service, operation] of [['__proto__', 'getAll'], ['constructor', 'constructor'], ['clientService', 'toString'], ['clientService', 'missing'], [['clientService'], 'getAll']]) {
    await expect(mockPortalAdapter.invoke(request(service, operation))).rejects.toMatchObject({ code: 'OPERATION_UNAVAILABLE' })
  }
  expect(mockDb.read()).toEqual(before)
})

it('rejects malformed named inputs and unknown fields before invoking a domain mutation', async () => {
  const before = mockDb.read()
  for (const input of [null, [], { id: 'c1' }, { id: 7, patch: {} }, { id: 'c1', patch: [] }, { id: 'c1', patch: {}, unexpected: true }]) {
    await expect(mockPortalAdapter.invoke(request('clientService', 'update', input))).rejects.toMatchObject({ code: 'INVALID_REQUEST' })
  }
  const inherited = Object.create({ id: 'c1', patch: { name: 'Forged' } })
  await expect(mockPortalAdapter.invoke(request('clientService', 'update', inherited))).rejects.toMatchObject({ code: 'INVALID_REQUEST' })
  expect(mockDb.read()).toEqual(before)
})

it('rejects caller-supplied identity and records the authenticated trainer on a successful acknowledgement', async () => {
  signIn('u-marcus')
  const before = mockDb.read(), actor = before.users.find(user => user.role === 'owner')
  const input = { sessionId: 's1', acknowledgement: { method: 'late_no_show' } }
  for (const forged of [{ ...input, actor }, { ...input, context: { actor } }, { ...input, user: actor }]) {
    await expect(mockPortalAdapter.invoke(request('sessionService', 'acknowledge', forged))).rejects.toMatchObject({ code: 'INVALID_REQUEST' })
  }
  expect(mockDb.read()).toEqual(before)
  const result = await createPortalServices(mockPortalAdapter).sessionService.acknowledge(input)
  expect(result.session.acknowledgement.recordedBy).toMatchObject({ id: 'u-marcus', role: 'trainer' })
})

it('preserves assignment checks for named requests without mutating protected records', async () => {
  signIn('u-marcus')
  const before = mockDb.read()
  const other = before.sessions.find(session => session.trainerId !== 't1')
  await expect(mockPortalAdapter.invoke(request('sessionService', 'saveOutcome', { sessionId: other.id, outcome: { trainerComments: 'Forbidden' } }))).rejects.toMatchObject({ code: 'FORBIDDEN' })
  await expect(mockPortalAdapter.invoke(request('trainerService', 'update', { id: 't2', patch: { qualifications: 'Forbidden' } }))).rejects.toMatchObject({ code: 'FORBIDDEN' })
  await expect(mockPortalAdapter.invoke(request('clientService', 'renewPackage', { id: 'c1', draft: {} }))).rejects.toMatchObject({ code: 'FORBIDDEN' })
  expect(mockDb.read()).toEqual(before)
})

it('refuses every unavailable API domain operation before authentication or network access', async () => {
  const fetchImpl = vi.fn(() => { throw new Error('Unexpected network access') })
  const adapter = createApiPortalAdapter({ baseUrl: 'https://api.example.test', fetchImpl })
  for (const [service, operations] of Object.entries(PORTAL_CONTRACTS)) {
    for (const [operation, contract] of Object.entries(operations)) if (!contract.api) {
      await expect(adapter.invoke(request(service, operation))).rejects.toMatchObject({ code: 'OPERATION_UNAVAILABLE' })
    }
  }
  expect(fetchImpl).not.toHaveBeenCalled()
})

it('validates supported API requests before sending a staff creation or sign-in request', async () => {
  const fetchImpl = vi.fn(() => { throw new Error('Unexpected network access') })
  const adapter = createApiPortalAdapter({ baseUrl: 'https://api.example.test', fetchImpl })
  await expect(adapter.invoke(request('staffService', 'createAdmin', { body: {} }))).rejects.toMatchObject({ code: 'INVALID_REQUEST' })
  await expect(adapter.session({ operation: 'signIn', input: { identifier: 'owner@example.test', password: 'private', role: 'owner' } })).rejects.toMatchObject({ code: 'INVALID_REQUEST' })
  expect(fetchImpl).not.toHaveBeenCalled()
})

it('allows only explicit account operations and refuses unsupported demo challenges', async () => {
  const before = localStorage.getItem(MOCK_SESSION_KEY)
  for (const operation of ['current', 'requireCurrent', 'constructor', 'toString', 'challenge', 'forgotPassword', 'resetPassword']) {
    await expect(mockPortalAdapter.session({ operation, input: {} })).rejects.toMatchObject({ code: 'OPERATION_UNAVAILABLE' })
  }
  expect(localStorage.getItem(MOCK_SESSION_KEY)).toBe(before)
  await createPortalServices(mockPortalAdapter).auth.switchDemoIdentity({ userId: 'u-marcus' })
  expect(JSON.parse(localStorage.getItem(MOCK_SESSION_KEY)).userId).toBe('u-marcus')
})

it('requires one named challenge answer and never sends ambiguous or empty answers', async () => {
  const fetchImpl = vi.fn(() => { throw new Error('Unexpected network access') })
  const adapter = createApiPortalAdapter({ baseUrl: 'https://api.example.test', fetchImpl })
  for (const input of [{}, { code: '123456', newPassword: 'private' }, { code: 123456 }]) {
    await expect(adapter.session({ operation: 'challenge', input })).rejects.toMatchObject({ code: 'INVALID_REQUEST' })
  }
  expect(fetchImpl).not.toHaveBeenCalled()
})

it('validates envelope shapes without copying attachments or replacing domain draft validation', () => {
  const file = new Blob(['video'], { type: 'video/mp4' })
  const input = { sessionId: 's1', exerciseId: 'exercise-s1-1', file, metadata: {} }
  expect(portalRequest(request('sessionService', 'saveVideo', input), 'mock').input.file).toBe(file)
  expect(portalRequest(request('clientService', 'create', { draft: {} }), 'mock').input).toEqual({ draft: {} })
})

it('returns only the decided request record after persisting an owner decision', async () => {
  mockDb.mutate(db => db.messages.push({ id: 'contract-request', title: 'Availability', recipientRole: 'owner', status: 'pending', request: { type: 'trainer_availability', trainerId: 't1' } }))
  const result = await createPortalServices(mockPortalAdapter).requestService.resolve({ id: 'contract-request', decision: 'rejected' })
  expect(result).toMatchObject({ id: 'contract-request', status: 'rejected', decidedBy: 'u-owner' })
  expect(result).not.toHaveProperty('users')
  expect(result).not.toHaveProperty('clients')
  expect(messageForUser(mockDb.read().messages.find(message => message.id === result.id), { id: 'u-owner' })).toEqual(result)
})

it('returns the approved remuneration record without exposing the entire database', async () => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-09-16T01:00:00Z'))
  mockDb.write(payFixture()); signIn('owner')
  const services = createPortalServices(mockPortalAdapter)
  const detail = await services.remunerationService.detail({ cycle: '2026-09', trainerId: 't1' })
  const operation = services.remunerationService.approve({ cycle: '2026-09', trainerId: 't1', revision: detail.revision })
  await vi.runAllTimersAsync()
  const result = await operation
  expect(result).toMatchObject({ trainerId: 't1', status: 'Approved', approvedBy: 'owner', amountCents: 8000 })
  expect(result).not.toHaveProperty('users')
  expect(result).not.toHaveProperty('clients')
  expect(mockDb.read().remunerationApprovals).toContainEqual(result)
})

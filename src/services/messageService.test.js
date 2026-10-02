import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { mockDb } from './mockDb.js'
import { MOCK_SESSION_KEY } from './authService.js'
import { mockPortalAdapter } from './mockPortalAdapter.js'
import { createPortalServices } from './portalService.js'
import { messageService } from './messageService.js'
import { messageForUser, messageVisibleTo } from '../app/messageInbox.js'
import { orderMessages } from '../features/messages/messageOrdering.js'

const services = createPortalServices(mockPortalAdapter)
const signIn = id => localStorage.setItem(MOCK_SESSION_KEY, JSON.stringify({ userId: id, expiresAt: Date.now() + 3600000 }))
const stored = () => mockDb.read().messages.find(message => message.id === 'shared')
const actor = id => mockDb.read().users.find(user => user.id === id)
const view = id => messageForUser(stored(), actor(id))
const invoke = (id, operation, messageId = 'shared') => {
  signIn(id)
  return services.messageService[operation]({ id: messageId })
}

beforeEach(() => {
  localStorage.clear()
  mockDb.reset()
  mockDb.mutate(db => {
    db.users.push({ id: 'admin-a', role: 'admin', name: 'Admin A' }, { id: 'admin-b', role: 'admin', name: 'Admin B' })
    db.messages = [{ id: 'shared', recipientRole: 'owner', recipientTrainerId: 't1', kind: 'renewal', title: 'Shared renewal', createdAt: '2026-09-01T00:00:00Z', readBy: {} }]
  })
  signIn('u-owner')
})
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers() })

it('an Owner reading a shared notice leaves Admins and the assigned trainer unread', async () => {
  expect(await invoke('u-owner', 'markRead')).toMatchObject({ read: true, readAt: expect.any(String) })
  for (const id of ['admin-a', 'admin-b', 'u-marcus']) expect(view(id).read).toBe(false)
  expect(Object.keys(stored().readBy)).toEqual(['u-owner'])
})

it('a trainer reading a shared notice leaves operations unread and cannot receive other receipts', async () => {
  await invoke('u-owner', 'markRead')
  const result = await invoke('u-marcus', 'markRead')
  expect(result).toMatchObject({ read: true, id: 'shared' })
  expect(result).not.toHaveProperty('readBy')
  expect(view('admin-a').read).toBe(false)
  expect(view('u-owner').read).toBe(true)
})

it('Admin receipts are keyed by user rather than shared by role', async () => {
  await invoke('admin-a', 'markRead')
  expect(view('admin-a').read).toBe(true)
  expect(view('admin-b').read).toBe(false)
  expect(view('u-owner').read).toBe(false)
})

it('marking unread removes only the caller receipt and preserves message content and decisions', async () => {
  mockDb.mutate(db => { db.messages[0].status = 'approved' })
  for (const id of ['u-owner', 'admin-a', 'u-marcus']) await invoke(id, 'markRead')
  const before = stored()
  const result = await invoke('admin-a', 'markUnread')
  expect(result).toMatchObject({ read: false, status: 'approved', title: 'Shared renewal' })
  expect(result).not.toHaveProperty('readAt')
  expect(stored()).toEqual({ ...before, readBy: { 'u-owner': before.readBy['u-owner'], 'u-marcus': before.readBy['u-marcus'] } })
  mockDb.reload()
  expect(view('admin-a').read).toBe(false)
})

it('reload and identity switching return personal read state without disclosing receipt maps', async () => {
  await invoke('u-owner', 'markRead')
  for (const [id, read] of [['u-owner', true], ['admin-a', false], ['u-marcus', false]]) {
    signIn(id)
    const snapshot = await mockPortalAdapter.load()
    expect(snapshot.data.messages.find(message => message.id === 'shared')).toMatchObject({ read })
    expect(JSON.stringify(snapshot.data.messages)).not.toContain('readBy')
  }
})

it('retains the first read timestamp until that user marks unread and opens again', async () => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-09-26T01:00:00Z'))
  const first = await invoke('u-owner', 'markRead')
  vi.setSystemTime(new Date('2026-09-26T01:01:00Z'))
  expect((await invoke('u-owner', 'markRead')).readAt).toBe(first.readAt)
  await invoke('u-owner', 'markUnread')
  expect((await invoke('u-owner', 'markRead')).readAt).toBe('2026-09-26T01:01:00.000Z')
})

it('overlapping writes by two recipients retain both receipts', async () => {
  await Promise.all([invoke('u-owner', 'markRead'), invoke('u-marcus', 'markRead')])
  expect(Object.keys(stored().readBy).sort()).toEqual(['u-marcus', 'u-owner'])
})

it.each([
  ['u-marcus', { recipientRole: 'owner' }],
  ['u-marcus', { recipientTrainerId: 't2' }],
  ['u-owner', { recipientTrainerId: 't2' }],
  ['admin-a', { recipientRole: 'owner', kind: 'trainer_rates' }],
])('rejects both read operations outside %s inbox without changing storage', async (id, routing) => {
  mockDb.mutate(db => { db.messages = [{ id: 'private', title: 'Private', ...routing, readBy: {} }] })
  const before = mockDb.read()
  for (const operation of ['markRead', 'markUnread']) await expect(invoke(id, operation, 'private')).rejects.toMatchObject({ code: 'FORBIDDEN' })
  expect(mockDb.read()).toEqual(before)
})

it('rejects missing messages, unauthenticated sessions and supplied actor fields', async () => {
  const before = mockDb.read()
  await expect(invoke('u-owner', 'markRead', 'missing')).rejects.toMatchObject({ code: 'FORBIDDEN' })
  await expect(services.messageService.markRead({ id: 'shared', userId: 'admin-a' })).rejects.toMatchObject({ code: 'INVALID_REQUEST' })
  localStorage.removeItem(MOCK_SESSION_KEY)
  await expect(services.messageService.markUnread({ id: 'shared' })).rejects.toMatchObject({ code: 'SESSION_EXPIRED' })
  expect(mockDb.read()).toEqual(before)
})

it('domain writes require a stored active actor and recheck recipient access after the delay', async () => {
  const trainer = actor('u-marcus')
  for (const invalid of [undefined, { ...trainer, role: 'owner' }, { id: 'missing', role: 'owner' }]) {
    await expect(messageService.markRead('shared', invalid)).rejects.toThrow('active staff')
  }
  const pending = invoke('u-marcus', 'markRead')
  mockDb.mutate(db => { db.messages[0].recipientTrainerId = 't2' })
  await expect(pending).rejects.toMatchObject({ code: 'FORBIDDEN' })
  mockDb.mutate(db => { db.users.find(user => user.id === 'u-owner').status = 'inactive' })
  await expect(messageService.markUnread('shared', { id: 'u-owner', role: 'owner' })).rejects.toThrow('active staff')
  expect(stored().readBy).toEqual({})
})

it('a request decision is shared while each recipient read state remains independent', async () => {
  mockDb.mutate(db => {
    db.messages[0] = { ...db.messages[0], kind: 'availability_request', status: 'pending', request: { type: 'trainer_availability', trainerId: 't1' } }
  })
  await invoke('admin-a', 'markRead')
  signIn('u-owner')
  const result = await services.requestService.resolve({ id: 'shared', decision: 'rejected' })
  expect(result).toMatchObject({ status: 'rejected', read: false })
  expect(result).not.toHaveProperty('readBy')
  expect(view('admin-a')).toMatchObject({ status: 'rejected', read: true })
  expect(view('u-marcus')).toMatchObject({ status: 'rejected', read: false })
  expect(mockDb.read().messages.find(message => message.kind === 'request_decision').readBy).toEqual({})
})

it('migrates only attributable legacy reads, keeps existing receipts and never resets twice', () => {
  const db = mockDb.read()
  db.messages = [
    { id: 'shared', recipientRole: 'owner', recipientTrainerId: 't1', read: true, readAt: '2026-09-01T00:00:00Z' },
    { id: 'direct', recipientUserId: 'u-marcus', read: true, readAt: '2026-09-01T01:00:00Z' },
    { id: 'trainer', recipientTrainerId: 't1', read: true },
    { id: 'existing', recipientRole: 'owner', read: true, readBy: { 'admin-a': { readAt: '2026-09-01T02:00:00Z' } } },
  ]
  localStorage.setItem('fitfinity-m2-demo-db-v4', JSON.stringify(db))
  const migrated = mockDb.reload()
  expect(migrated.messages.map(message => message.readBy)).toEqual([{}, { 'u-marcus': { readAt: '2026-09-01T01:00:00Z' } }, { 'u-marcus': {} }, { 'admin-a': { readAt: '2026-09-01T02:00:00Z' } }])
  for (const message of migrated.messages) {
    expect(message).not.toHaveProperty('read')
    expect(message).not.toHaveProperty('readAt')
  }
  expect(mockDb.reload()).toEqual(migrated)
})

it('failed storage publishes no receipt and can be retried', async () => {
  const before = mockDb.read()
  const write = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Storage full') })
  await expect(services.messageService.markRead({ id: 'shared' })).rejects.toThrow('Storage full')
  expect(mockDb.read()).toEqual(before)
  write.mockRestore()
  expect(await services.messageService.markRead({ id: 'shared' })).toMatchObject({ read: true })
})

it('one recipient reading cannot change another recipient message ordering', async () => {
  mockDb.mutate(db => { db.messages.push({ id: 'newer', recipientRole: 'owner', createdAt: '2026-09-02T00:00:00Z', readBy: {} }) })
  const ordered = id => orderMessages(mockDb.read().messages.map(message => messageForUser(message, actor(id)))).map(message => message.id)
  const before = ordered('admin-a')
  await invoke('u-owner', 'markRead')
  expect(ordered('admin-a')).toEqual(before)
})

it('the shared inbox rule includes additive recipients and excludes financial messages for Admin', () => {
  for (const id of ['u-owner', 'admin-a', 'admin-b', 'u-marcus']) expect(messageVisibleTo(actor(id), stored())).toBe(true)
  expect(messageVisibleTo({ id: 'other', role: 'trainer', trainerId: 't2' }, stored())).toBe(false)
  expect(messageVisibleTo(actor('admin-a'), { recipientRole: 'admin', kind: 'trainer_rates' })).toBe(false)
  expect(messageVisibleTo({ id: 'incomplete', role: 'trainer' }, { id: 'unaddressed' })).toBe(false)
})

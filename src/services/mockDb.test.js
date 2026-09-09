import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { mockDb } from './mockDb.js'

const KEY = 'fitfinity-m2-demo-db-v4'
beforeEach(() => mockDb.reset())
afterEach(() => vi.restoreAllMocks())

it('rejects failed mutations, writes and resets without changing memory or stored data, then retries once', () => {
  for (const operation of ['mutate', 'write', 'reset']) {
    mockDb.mutate(db => { db.testRevision = 1 })
    const before = mockDb.read(), stored = localStorage.getItem(KEY)
    const save = () => operation === 'mutate' ? mockDb.mutate(db => { db.testRevision += 1 })
      : operation === 'write' ? mockDb.write({ ...before, testRevision: 2 }) : mockDb.reset()
    const error = new Error('Storage full. Try again.')
    const fail = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw error })
    expect(save).toThrow(error)
    expect(mockDb.read()).toEqual(before)
    expect(localStorage.getItem(KEY)).toBe(stored)
    fail.mockRestore()
    const saved = save()
    expect(mockDb.read()).toEqual(saved)
    expect(JSON.parse(localStorage.getItem(KEY))).toEqual(saved)
    if (operation !== 'reset') expect(saved.testRevision).toBe(2)
    else expect(saved.testRevision).toBeUndefined()
  }
})

it('leaves the current state untouched when a mutation or serialization fails', () => {
  const before = mockDb.read(), stored = localStorage.getItem(KEY)
  expect(() => mockDb.mutate(db => { db.clients.length = 0; throw new Error('Invalid change') })).toThrow('Invalid change')
  expect(() => mockDb.mutate(db => { db.circular = db })).toThrow()
  expect(mockDb.read()).toEqual(before)
  expect(localStorage.getItem(KEY)).toBe(stored)
})

it('preserves explicit WhatsApp nulls and zero counts across reloads and migrates only absent legacy fields', () => {
  const legacyTime = '2026-08-20T12:00:00Z'
  mockDb.mutate(db => {
    db.sessions = [
      { id: 'empty', whatsappOpenedAt: null, whatsappOpenCount: 0 },
      { id: 'current', whatsappOpenedAt: null, whatsappOpenCount: 0, whatsappSentAt: legacyTime, whatsappSendCount: 2 },
      { id: 'legacy', whatsappSentAt: legacyTime, whatsappSendCount: 2 },
      { id: 'absent' },
    ]
  })
  const stored = mockDb.read().sessions
  const expected = stored.map(session => session.id === 'legacy' ? { ...session, whatsappOpenedAt: legacyTime, whatsappOpenCount: 2 } : session)
  expect(mockDb.reload().sessions).toEqual(expected)
  mockDb.mutate(db => { db.unrelatedUpdate = true })
  expect(mockDb.reload().sessions).toEqual(expected)
  expect(JSON.parse(localStorage.getItem(KEY)).sessions).toEqual(expected)
})

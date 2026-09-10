import { createElement } from 'react'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { appendRenewalMessage } from '../app/renewals.js'
import { seed } from '../data/seed.js'
import { MessageInbox } from '../features/messages/MessagesPage.jsx'
import { signatureFixture } from '../test/fixtures/signature.js'
import { mockDb } from './mockDb.js'
import { sessionService } from './sessionService.js'
import { clientService } from './clientService.js'
import { packageService } from './packageService.js'

const acknowledgementActor = () => mockDb.read().users.find(user => user.role === 'owner')

const KEY = 'fitfinity-m2-demo-db-v4'
const signature = { method: 'signature', signerName: 'Amanda Lim', signature: signatureFixture }
const renewals = (db, clientId = 'c1') => db.messages.filter(message => message.kind === 'renewal' && message.clientId === clientId)
const amanda = db => db.clients.find(client => client.id === 'c1')
function prepare(used = 9, total = 12) {
  return mockDb.mutate(db => {
    Object.assign(amanda(db).package, { id: 'amanda-current-package', used, total })
    db.messages = db.messages.filter(message => message.kind !== 'renewal' || message.clientId !== 'c1')
    for (const id of ['s1', 's2']) Object.assign(db.sessions.find(session => session.id === id), { date: '2026-09-01', packageId: amanda(db).package.id })
  })
}

beforeEach(() => {
  localStorage.clear()
  mockDb.reset()
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-09-08T04:00:00Z'))
})
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  vi.useRealTimers()
  history.replaceState({}, '', '/')
})

describe('last-session renewal updates', () => {
  it('creates one reminder exactly at 10/12, 22/24 and 34/36, with no four-session reminder at 32/36', () => {
    expect(seed.messages.filter(message => message.kind === 'renewal')).toHaveLength(1)
    for (const [used, total] of [[10, 12], [22, 24], [34, 36]]) {
      const db = prepare(used, total), client = amanda(db)
      const reminder = appendRenewalMessage(db, client)
      expect(reminder).toMatchObject({
        kind: 'renewal', clientId: 'c1', title: 'Renewal follow-up: Amanda Lim',
        renewal: { type: 'last_sessions', clientPackageId: client.package.id, used, total, remaining: 2 },
      })
      expect(reminder.body).toContain('approaching package renewal')
      expect(reminder.body).toContain(`${used}/${total} sessions used · 2 sessions remaining.`)
      expect(appendRenewalMessage(db, client)).toEqual(reminder)
      expect(renewals(db)).toEqual([reminder])
    }
    const db = prepare(32, 36)
    expect(appendRenewalMessage(db, amanda(db))).toBeNull()
    expect(renewals(db)).toEqual([])
  })

  it('uses configured policy for custom and newly created packages and rejects inactive or invalid balances', async () => {
    for (const [total, threshold] of [[18, 2], [365, 2], [36, 4]]) {
      const db = prepare(total - threshold, total)
      db.settings.renewal = { remainingSessions: threshold }
      const reminder = appendRenewalMessage(db, amanda(db))
      expect(reminder.renewal).toMatchObject({ used: total - threshold, total, remaining: threshold })
    }
    const owner = mockDb.read().users.find(user => user.role === 'owner')
    const purchasedIds = []
    for (const total of [1, 2]) {
      const definition = await packageService.save({ draft: { name: `Small ${total} package`, total: String(total) } }, owner)
      const created = await clientService.create({
        type: 'Individual', people: [{ name: `Small ${total} client` }], startDate: '2026-09-07', trainerId: 't1',
        sessionsPerWeek: 1, packageId: definition.id, packageVersion: definition.version,
        clientPreferences: [{ days: ['Monday'], from: '18:00', to: '19:00' }],
        fixedWeeklySchedule: [{ day: 'Monday', from: '18:00', to: '19:00' }],
      })
      expect(created.package.id).toEqual(expect.any(String))
      purchasedIds.push(created.package.id)
      const messages = renewals(mockDb.read(), created.id)
      expect(messages).toHaveLength(total === 2 ? 1 : 0)
      if (total === 2) expect(messages[0].renewal).toMatchObject({ clientPackageId: created.package.id, used: 0, total: 2, remaining: 2 })
    }
    expect(new Set(purchasedIds).size).toBe(2)
    for (const patch of [
      { status: 'inactive' },
      { package: { id: 'invalid', total: 12.5, used: 10.5 } },
      { package: { id: 'invalid', total: '12', used: 10 } },
      { package: { id: 'invalid', total: 1, used: -1 } },
      { package: null },
    ]) {
      const db = prepare(10)
      Object.assign(amanda(db), patch)
      expect(appendRenewalMessage(db, amanda(db))).toBeNull()
      expect(renewals(db)).toEqual([])
    }
  })

  it('creates the reminder atomically with the first signature or no-show debit and never duplicates it on conversion', async () => {
    for (const first of [signature, { method: 'late_no_show' }]) {
      mockDb.reset()
      prepare()
      await sessionService.acknowledge('s1', first, acknowledgementActor())
      const reminder = renewals(mockDb.read())[0]
      expect(reminder.renewal).toMatchObject({ used: 10, total: 12, remaining: 2 })
      await sessionService.acknowledge('s1', first, acknowledgementActor())
      if (first.method === 'late_no_show') await sessionService.acknowledge('s1', signature, acknowledgementActor())
      await sessionService.acknowledge('s1', signature, acknowledgementActor())
      await expect(sessionService.acknowledge('s1', { method: 'late_no_show' }, acknowledgementActor())).rejects.toThrow()
      const db = mockDb.reload()
      expect(amanda(db).package.used).toBe(10)
      expect(db.packageCreditTransactions.filter(transaction => transaction.sessionId === 's1')).toHaveLength(1)
      expect(renewals(db)).toEqual([reminder])
    }
  })

  it('does not create early, expiry or exhausted-package reminders and retains the original at one or zero sessions', async () => {
    for (const used of [8, 10, 11]) {
      mockDb.reset()
      prepare(used)
      await sessionService.acknowledge('s1', { method: 'late_no_show' }, acknowledgementActor())
      expect(renewals(mockDb.read())).toEqual([])
    }
    mockDb.reset()
    prepare()
    await sessionService.acknowledge('s1', signature, acknowledgementActor())
    const original = renewals(mockDb.read())[0]
    await sessionService.acknowledge('s2', { method: 'late_no_show' }, acknowledgementActor())
    expect(amanda(mockDb.read()).package.used).toBe(11)
    expect(renewals(mockDb.read())).toEqual([original])
    mockDb.mutate(db => {
      const source = db.sessions.find(session => session.id === 's2')
      db.sessions.push({ ...source, id: 'last-package-session', status: 'not_planned', acknowledgement: null })
    })
    await sessionService.acknowledge('last-package-session', { method: 'late_no_show' }, acknowledgementActor())
    expect(amanda(mockDb.read()).package.used).toBe(12)
    expect(renewals(mockDb.reload())).toEqual([original])
    const expired = prepare(4)
    amanda(expired).package.endDate = '2026-08-01'
    expect(appendRenewalMessage(expired, amanda(expired))).toBeNull()
  })

  it('rolls back the credit, completion and renewal together on persistence failure, then permits one retry', async () => {
    const before = prepare()
    const storage = vi.spyOn(Storage.prototype, 'setItem').mockImplementationOnce(() => { throw new Error('Storage full') })
    await expect(sessionService.acknowledge('s1', signature, acknowledgementActor())).rejects.toThrow('Storage full')
    expect(mockDb.read()).toEqual(before)
    expect(JSON.parse(localStorage.getItem(KEY))).toEqual(before)
    storage.mockRestore()
    await sessionService.acknowledge('s1', signature, acknowledgementActor())
    await sessionService.acknowledge('s1', signature, acknowledgementActor())
    expect(amanda(mockDb.reload()).package.used).toBe(10)
    expect(renewals(mockDb.read())).toHaveLength(1)
    expect(mockDb.read().packageCreditTransactions.filter(transaction => transaction.sessionId === 's1')).toHaveLength(1)
  })

  it('defers migration until loading, recovers from storage failure and preserves legacy read state and package identities', async () => {
    const legacy = structuredClone(seed)
    delete legacy.renewalMessageVersion
    for (const client of legacy.clients) {
      delete client.package.id
      client.package.used = 0
    }
    amanda(legacy).package.used = 10
    legacy.clients.find(client => client.id === 'c3').package.used = 10
    legacy.clients.find(client => client.id === 'c2').package.used = 23
    Object.assign(legacy.clients.find(client => client.id === 'c4'), { status: 'inactive', package: { total: 12, used: 10 } })
    const preserved = { id: 'old-read-reminder', kind: 'renewal', clientId: 'c3', title: 'Last sessions', createdAt: '2026-09-01T04:00:00Z', read: true, readAt: '2026-09-02T05:00:00Z' }
    const ordinary = { id: 'ordinary-session', kind: 'session', title: 'Session updated', read: false }
    legacy.messages = [
      preserved,
      { ...preserved, id: 'duplicate-reminder', read: false },
      { ...preserved, id: 'one-session-left', clientId: 'c2' },
      { ...preserved, id: 'inactive-reminder', clientId: 'c4' },
      { ...preserved, id: 'expiry-reminder', clientId: 'c5' },
      ordinary,
    ]
    const before = mockDb.read()
    const storedLegacy = JSON.stringify(legacy)
    localStorage.setItem(KEY, storedLegacy)
    const storage = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Migration storage unavailable') })
    let isolated
    vi.resetModules()
    try {
      isolated = (await import('./mockDb.js')).mockDb
      expect(storage).not.toHaveBeenCalled()
      expect(() => isolated.reload()).toThrow('Migration storage unavailable')
      expect(() => mockDb.reload()).toThrow('Migration storage unavailable')
      expect(mockDb.read()).toEqual(before)
      expect(localStorage.getItem(KEY)).toBe(storedLegacy)
    } finally {
      storage.mockRestore()
      vi.resetModules()
    }
    const persistence = vi.spyOn(Storage.prototype, 'setItem')
    const migrated = isolated.reload()
    expect(migrated.renewalMessageVersion).toBe(1)
    expect(migrated.messages.filter(message => message.kind === 'renewal')).toHaveLength(2)
    expect(renewals(migrated, 'c3')[0]).toMatchObject({
      id: preserved.id, read: true, readAt: preserved.readAt, createdAt: preserved.createdAt,
      title: 'Renewal follow-up: Nadia Koh', renewal: { type: 'last_sessions', used: 10, total: 12 },
    })
    expect(renewals(migrated)).toHaveLength(1)
    expect(migrated.messages).toContainEqual(ordinary)
    expect(migrated.clients.every(client => typeof client.package.id === 'string' && client.package.id.length > 0)).toBe(true)
    expect(new Set(migrated.clients.map(client => client.package.id)).size).toBe(migrated.clients.length)
    expect(JSON.parse(localStorage.getItem(KEY))).toEqual(migrated)
    expect(isolated.reload()).toEqual(migrated)
    expect(mockDb.reload()).toEqual(migrated)
    expect(persistence).toHaveBeenCalledExactlyOnceWith(KEY, JSON.stringify(migrated))
  })

  it('deduplicates by the client package identity while allowing a separate reminder for a replacement package', () => {
    const db = prepare(10), client = amanda(db)
    const first = appendRenewalMessage(db, client)
    client.package = { ...client.package, id: 'amanda-replacement-package' }
    const second = appendRenewalMessage(db, client)
    expect(second.id).not.toBe(first.id)
    expect(second.renewal.clientPackageId).toBe(client.package.id)
    expect(first.renewal.clientPackageId).toBe('amanda-current-package')
    expect(appendRenewalMessage(db, client)).toEqual(second)
    expect(renewals(db)).toEqual([first, second])
    mockDb.write(db)
    expect(renewals(mockDb.reload())).toEqual([first, second])
  })

  it('shows the same reminder to the owner and assigned trainer and hides it from an unrelated trainer', () => {
    vi.stubGlobal('matchMedia', () => ({ matches: true, addEventListener() {}, removeEventListener() {} }))
    const db = prepare(10), reminder = appendRenewalMessage(db, amanda(db))
    expect(reminder).toMatchObject({ recipientRole: 'owner', recipientTrainerId: 't1' })
    for (const [userId, count] of [['u-owner', 1], ['u-marcus', 1], ['u-aisha', 0]]) {
      const user = db.users.find(user => user.id === userId)
      expect(user).toBeTruthy()
      render(createElement(MessageInbox, { embedded: true, category: 'renewals', user, messages: [reminder] }))
      expect(screen.getByLabelText('Renewal messages').querySelectorAll('article')).toHaveLength(count)
      if (count) expect(screen.getByRole('button', { name: 'Open Renewal follow-up: Amanda Lim' })).toBeVisible()
      else expect(screen.getByText('No renewal messages.')).toBeVisible()
      cleanup()
    }
  })
})

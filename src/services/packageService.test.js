import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { mockDb } from './mockDb.js'
import { packageService } from './packageService.js'
import { clientService } from './clientService.js'
import { selectedPackage } from '../app/packages.js'
import { DEFAULT_PACKAGES } from '../data/mockPackages.js'
import { relatedMessageLinks } from '../features/messages/messageLinks.js'

const KEY = 'fitfinity-m2-demo-db-v4'
const owner = () => mockDb.read().users.find(user => user.role === 'owner')
const save = (draft, options = {}) => packageService.save({ draft, ...options }, owner())
const clientDraft = (definition, frequency) => ({
  type: 'Individual', people: [{ name: 'Package client' }], startDate: '2026-09-07',
  trainerId: 't1', sessionsPerWeek: frequency, packageId: definition.id, packageVersion: definition.version,
  clientPreferences: [{ days: ['Monday', 'Wednesday', 'Friday'], from: '18:00', to: '19:00' }],
  fixedWeeklySchedule: ['Monday', 'Wednesday', 'Friday'].slice(0, frequency).map(day => ({ day, from: '18:00', to: '19:00' })),
})
beforeEach(() => mockDb.reset())
afterEach(() => vi.restoreAllMocks())

it('preloads 12/90, 24/180 and 36/270 packages and upgrades old mock data without resetting it', async () => {
  expect(mockDb.read().packages.map(({ total, validityDays }) => [total, validityDays])).toEqual([[12, 90], [24, 180], [36, 270]])
  const old = mockDb.read(); delete old.packages; old.clients[0].name = 'Keep this client'
  localStorage.setItem(KEY, JSON.stringify(old))
  vi.resetModules()
  const reloaded = (await import('./mockDb.js')).mockDb.read()
  expect(reloaded.packages).toEqual(DEFAULT_PACKAGES)
  expect(reloaded.clients).toEqual(old.clients)
  expect(reloaded.sessions).toEqual(old.sessions)
  expect(JSON.parse(localStorage.getItem(KEY))).toEqual(old)
})

it('saves rules derived from session count and emits an unread owner-only package link', async () => {
  const result = await save({ name: '  Strength package  ', total: 36, validityDays: 1, freeGym: false })
  expect(result).toMatchObject({ name: 'Strength package', total: 36, validityDays: 270, status: 'active', version: 1 })
  expect(result).not.toHaveProperty('sessionsPerWeek')
  const db = mockDb.read(), message = db.messages.at(-1)
  expect(message).toMatchObject({ packageId: result.id, read: false, recipientRole: 'owner' })
  expect(relatedMessageLinks(message, { user: owner(), packages: db.packages })).toEqual([{ type: 'package', id: result.id, label: 'Package · Strength package' }])
  expect(relatedMessageLinks(message, { user: { role: 'trainer' }, packages: db.packages })).toEqual([])
})

it('requires an active stored owner and rejects forged identities without mutation', async () => {
  const before = mockDb.read(), trainer = before.users.find(user => user.role === 'trainer')
  for (const actor of [undefined, trainer, { ...trainer, role: 'owner' }, { id: 'unknown', role: 'owner' }]) {
    await expect(packageService.save({ draft: { name: 'Invalid actor', total: 12 } }, actor)).rejects.toThrow()
  }
  expect(mockDb.read()).toEqual(before)
  const actor = owner()
  mockDb.mutate(db => { db.users.find(user => user.id === actor.id).status = 'inactive' })
  const disabled = mockDb.read()
  await expect(packageService.save({ draft: { name: 'Inactive owner', total: 12 } }, actor)).rejects.toThrow()
  expect(mockDb.read()).toEqual(disabled)
})

it('rejects invalid counts, duplicate names, stale updates and deactivated selections', async () => {
  const before = mockDb.read()
  for (const draft of [{ name: '', total: 12 }, { name: 'Invalid count', total: 18 }, { name: '12 SESSIONS', total: 24 }]) {
    await expect(save(draft)).rejects.toThrow()
  }
  expect(mockDb.read()).toEqual(before)
  const item = before.packages[0]
  const inactive = await save({ ...item, status: 'inactive' }, { id: item.id, expectedVersion: item.version })
  expect(() => selectedPackage(mockDb.read(), { packageId: item.id })).toThrow('active PT package')
  await expect(save({ ...item, name: 'Stale' }, { id: item.id, expectedVersion: item.version })).rejects.toThrow('changed')
  const active = await save({ ...inactive, status: 'active' }, { id: item.id, expectedVersion: inactive.version })
  expect(() => selectedPackage(mockDb.read(), { packageId: item.id, packageVersion: item.version })).toThrow('changed')
  expect(selectedPackage(mockDb.read(), { packageId: item.id, packageVersion: active.version })).toEqual(active)
})

it('creates every session independently of cadence and grants free gym from twice weekly upwards', async () => {
  for (const definition of DEFAULT_PACKAGES) {
    for (const frequency of [1, 2, 3]) {
      const client = await clientService.create(clientDraft(definition, frequency))
      expect(client.package).toMatchObject({ total: definition.total, validityDays: definition.validityDays,
        durationWeeks: Math.ceil(definition.total / frequency), sessionsPerWeek: frequency, freeGym: frequency >= 2,
        templateId: definition.id, templateVersion: definition.version })
      const sessions = mockDb.read().sessions.filter(session => session.clientId === client.id)
      expect(sessions).toHaveLength(definition.total)
      expect(sessions.every(session => session.date <= client.package.endDate && session.date >= client.package.startDate)).toBe(true)
    }
  }
})

it('preserves purchased package snapshots and sessions when a definition is edited or deactivated', async () => {
  const item = DEFAULT_PACKAGES[1]
  const client = await clientService.create(clientDraft(item, 1))
  const before = mockDb.read()
  await save({ name: 'Updated definition', total: 36, status: 'inactive' }, { id: item.id, expectedVersion: item.version })
  const after = mockDb.read()
  expect(after.clients).toEqual(before.clients)
  expect(after.sessions).toEqual(before.sessions)
  expect(after.clients.find(value => value.id === client.id).package).toMatchObject({ name: item.name, total: 24, validityDays: 180 })
  await expect(clientService.create(clientDraft(item, 1))).rejects.toThrow('active PT package')
  expect(mockDb.read()).toEqual(after)
})

it('rolls back package records and messages on storage failure and permits one retry', async () => {
  const before = mockDb.read(), stored = localStorage.getItem(KEY)
  const failure = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Storage unavailable') })
  await expect(save({ name: 'Retry package', total: 24 })).rejects.toThrow('Storage unavailable')
  expect(mockDb.read()).toEqual(before)
  expect(localStorage.getItem(KEY)).toBe(stored)
  failure.mockRestore()
  await save({ name: 'Retry package', total: 24 })
  expect(mockDb.read().packages).toHaveLength(before.packages.length + 1)
  expect(mockDb.read().messages).toHaveLength(before.messages.length + 1)
})

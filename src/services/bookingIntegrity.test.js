import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { mockDb } from './mockDb.js'
import { MOCK_SESSION_KEY } from './authService.js'
import { mockPortalAdapter } from './mockPortalAdapter.js'
import { createPortalServices } from './portalService.js'
import { trainerService } from './trainerService.js'
import { matchTrainers } from '../app/clientOnboarding.js'
import { availableReplacementTrainers } from '../app/bookingAvailability.js'

const api = createPortalServices(mockPortalAdapter)
const approvals = { availability: false, sessionTime: false, trainerReassignment: false, fixedWeeklySchedule: false }
const owner = () => mockDb.read().users.find(user => user.role === 'owner')
const actor = id => mockDb.read().users.find(user => user.id === id)
const signIn = id => localStorage.setItem(MOCK_SESSION_KEY, JSON.stringify({ userId: id, expiresAt: Date.now() + 3600000 }))
const draft = (name, trainerId = 't1') => ({
  type: 'Individual', people: [{ name, email: `${name.replaceAll(' ', '-')}@example.test`, birthday: '1990-01-02', gender: 'Female',
    phone: { countryCode: '+65', number: '91234567' }, emergencyContact: { name: 'Contact', relationship: 'Spouse', countryCode: '+65', number: '98765432' } }],
  packageId: 'package-12', packageVersion: 1, startDate: '2027-06-07', sessionsPerWeek: 1, trainerId,
  genderPreference: 'No gender preference', clientPreferences: [{ id: 'preference', days: ['Monday'], from: '18:00', to: '19:00' }],
  fixedWeeklySchedule: [{ id: 'weekly', day: 'Monday', from: '18:00', to: '19:00' }],
})
const create = (name, trainerId) => api.clientService.create({ draft: draft(name, trainerId) })
const unchanged = before => { expect(mockDb.read()).toEqual(before); expect(mockDb.reload()).toEqual(before) }
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2027-06-07T01:30:00Z'))
  localStorage.clear()
  mockDb.reset('2027-06-07')
  mockDb.mutate(db => {
    db.clients = []; db.sessions = []; db.messages = []; db.packageCreditTransactions = []
    db.users.push({ id: 'audit-admin', role: 'admin', status: 'active', name: 'Admin' })
  })
  signIn(owner().id)
})
afterEach(() => { vi.useRealTimers(); localStorage.clear() })

it.each([
  ['approvalNeeded', approvals], ['availability', {}], ['status', 'inactive'],
  ['id', 'another-trainer'], ['role', 'owner'], ['unexpected', true],
])('rejects a trainer generic edit containing %s and rolls back ordinary fields too', async (key, value) => {
  signIn('u-marcus')
  const before = mockDb.read()
  await expect(api.trainerService.update({ id: 't1', patch: { qualifications: 'Changed', [key]: value } })).rejects.toThrow('Unsupported trainer profile field')
  unchanged(before)
})
it.each(['u-owner', 'audit-admin'])('%s must use the dedicated approval action and can still save legitimate edits', async id => {
  signIn(id)
  const before = mockDb.read()
  await expect(api.trainerService.update({ id: 't1', patch: { approvalNeeded: approvals } })).rejects.toThrow('Unsupported')
  unchanged(before)
  await api.trainerService.updateAutonomy({ id: 't1', approvalNeeded: approvals })
  await api.trainerService.update({ id: 't1', patch: { qualifications: 'First aid' } })
  expect(mockDb.read().trainers.find(t => t.id === 't1')).toMatchObject({ approvalNeeded: approvals, qualifications: 'First aid', rates: before.trainers[0].rates })
})
it('rejects trainer, forged and missing approval actors even when the adapter is bypassed', async () => {
  const trainer = actor('u-marcus'), before = mockDb.read()
  for (const value of [trainer, { ...trainer, role: 'owner' }, undefined]) {
    await expect(trainerService.updateAutonomy('t1', approvals, value)).rejects.toThrow()
    unchanged(before)
  }
  signIn(trainer.id)
  await expect(api.trainerService.updateAutonomy({ id: 't1', approvalNeeded: approvals })).rejects.toMatchObject({ code: 'FORBIDDEN' })
})
it('rejects partial or malformed approval controls without changing the trainer', async () => {
  const before = mockDb.read()
  for (const value of [{ sessionTime: false }, { ...approvals, availability: 'false' }, { ...approvals, other: true }]) {
    await expect(api.trainerService.updateAutonomy({ id: 't1', approvalNeeded: value })).rejects.toThrow('all four')
    unchanged(before)
  }
})
it('rechecks stored identity inside generic and dedicated trainer mutations', async () => {
  for (const operation of ['update', 'updateAutonomy']) {
    signIn('u-owner')
    const pending = api.trainerService[operation]({ id: 't1', ...(operation === 'update' ? { patch: { qualifications: 'Changed' } } : { approvalNeeded: approvals }) })
    mockDb.mutate(db => { db.users.find(user => user.id === 'u-owner').status = 'inactive' })
    const before = mockDb.read()
    await expect(pending).rejects.toThrow('active staff')
    unchanged(before)
    mockDb.mutate(db => { db.users.find(user => user.id === 'u-owner').status = 'active' })
  }
})
it('allows a trainer own ordinary edits but rejects direct name or other-trainer writes', async () => {
  const trainer = actor('u-marcus')
  signIn(trainer.id)
  await api.trainerService.update({ id: 't1', patch: { qualifications: 'First aid' } })
  const before = mockDb.read()
  await expect(trainerService.update('t2', { qualifications: 'Changed' }, trainer)).rejects.toThrow('assigned trainer')
  await expect(trainerService.update('t1', { name: 'Changed' }, trainer)).rejects.toThrow('name changes')
  unchanged(before)
})

it.each(['not_planned', 'planned', 'completed', 'completed-inactive'])('client creation rejects an overlapping %s booking after matching', async status => {
  const first = await create('First')
  const proposed = draft('Second')
  mockDb.mutate(db => {
    for (const session of db.sessions) session.status = status.startsWith('completed') ? 'completed' : status
    if (status.endsWith('inactive')) db.clients.find(client => client.id === first.id).package.status = 'inactive'
  })
  const before = mockDb.read()
  await expect(api.clientService.create({ draft: proposed })).rejects.toThrow('conflicts')
  unchanged(before)
  const matches = matchTrainers(before.trainers, proposed.clientPreferences, proposed.genderPreference,
    { ...proposed, definition: before.packages[0], clients: before.clients, sessions: before.sessions })
  expect(matches.some(result => result.trainer.id === 't1')).toBe(false)
})
it('client creation rechecks the last generated date and partial time overlaps atomically', async () => {
  await create('First', 't2')
  mockDb.mutate(db => {
    db.sessions = [db.sessions.at(-1)]
    Object.assign(db.sessions[0], { trainerId: 't1', from: '18:45', to: '19:45' })
  })
  const before = mockDb.read()
  await expect(create('Second')).rejects.toThrow('conflicts')
  unchanged(before)
})
it('allows adjacent bookings, cancelled bookings and unfinished bookings in inactive packages', async () => {
  await create('First')
  const adjacent = draft('Adjacent'); adjacent.fixedWeeklySchedule[0].from = '19:00'; adjacent.fixedWeeklySchedule[0].to = '20:00'
  adjacent.clientPreferences[0].from = '19:00'; adjacent.clientPreferences[0].to = '20:00'
  await api.clientService.create({ draft: adjacent })
  mockDb.mutate(db => { for (const session of db.sessions) session.status = 'cancelled' })
  const second = await create('After cancellation')
  mockDb.mutate(db => { db.clients.find(client => client.id === second.id).package.status = 'inactive' })
  await expect(create('After deactivation')).resolves.toHaveProperty('id')
})
it('serializes two competing client creations so only one occupies the slot', async () => {
  const results = await Promise.allSettled([create('First'), create('Second')])
  expect(results.filter(result => result.status === 'fulfilled')).toHaveLength(1)
  expect(results.find(result => result.status === 'rejected').reason.message).toContain('conflicts')
  expect(mockDb.read().clients).toHaveLength(1)
  expect(mockDb.read().sessions).toHaveLength(12)
})

it('never lets schedule patch fields replace the client identity used for collision checks', async () => {
  await create('Client')
  mockDb.mutate(db => {
    const session = db.sessions[0]
    db.sessions = [session, { ...session, id: 'other-client-slot', trainerId: 't2', from: '19:30', to: '20:30' }]
  })
  const before = mockDb.read(), session = before.sessions[0]
  await expect(api.sessionService.updateDetails({ sessionId: session.id,
    patch: { date: session.date, from: '19:00', to: '20:00', trainerId: 't1', clientId: 'forged-client' } })).rejects.toThrow('this client')
  unchanged(before)
})

it.each(['planned', 'completed-inactive'])('deactivation rejects an occupied %s replacement without partial writes', async status => {
  await create('Departing', 't1'); const replacement = await create('Occupied', 't2')
  mockDb.mutate(db => {
    for (const session of db.sessions.filter(s => s.trainerId === 't2')) session.status = status.startsWith('completed') ? 'completed' : status
    if (status.endsWith('inactive')) db.clients.find(c => c.id === replacement.id).status = 'inactive'
  })
  const before = mockDb.read(), departing = before.sessions.filter(s => s.trainerId === 't1')
  expect(availableReplacementTrainers(before, departing[0]).map(t => t.id)).not.toContain('t2')
  await expect(api.trainerService.deactivate({ id: 't1', replacements: Object.fromEntries(departing.map(s => [s.id, 't2'])) })).rejects.toThrow('conflicts')
  unchanged(before)
})
it('checks proposed replacements against each other and permits a free trainer outside declared hours', async () => {
  await create('Departing', 't1'); await create('Second', 't2')
  mockDb.mutate(db => {
    // Model legacy conflicting assignments: each must be resolved before deactivation.
    for (const session of db.sessions) session.trainerId = 't1'
    db.trainers.find(t => t.id === 't3').availability = {}
  })
  const before = mockDb.read(), allToTwo = Object.fromEntries(before.sessions.map(s => [s.id, 't2']))
  await expect(api.trainerService.deactivate({ id: 't1', replacements: allToTwo })).rejects.toThrow('conflicts')
  unchanged(before)
  const separate = Object.fromEntries(before.sessions.map(s => [s.id, s.clientId === before.clients[0].id ? 't2' : 't3']))
  await api.trainerService.deactivate({ id: 't1', replacements: separate })
  expect(mockDb.read().trainers.find(t => t.id === 't1').status).toBe('inactive')
  expect(mockDb.read().sessions.map(s => s.trainerId)).toEqual(before.sessions.map(s => separate[s.id]))
})

it.each(['signature', 'late_no_show'])('weekly changes retain the full interval of an early %s completion', async method => {
  const client = await create('Upcoming'); await create('Completed', 't2')
  mockDb.mutate(db => {
    db.sessions = [db.sessions.find(s => s.clientId === client.id), db.sessions.find(s => s.clientId !== client.id)]
    Object.assign(db.sessions[1], { trainerId: 't1', from: '09:00', to: '10:00', status: 'completed', acknowledgement: { method } })
  })
  const before = mockDb.read()
  await expect(api.clientService.saveFixedWeeklySchedule({ id: client.id, slots: [{ ...client.fixedWeeklySchedule[0], from: '09:45', to: '10:45' }] })).rejects.toThrow('conflicts')
  unchanged(before)
})
it('weekly approval rechecks completed history in an inactive package after submission', async () => {
  const client = await create('Upcoming'); const other = await create('Other', 't2')
  signIn('u-marcus')
  const slots = [{ ...client.fixedWeeklySchedule[0], from: '09:45', to: '10:45' }]
  await api.clientService.saveFixedWeeklySchedule({ id: client.id, slots })
  const request = mockDb.read().messages.find(message => message.request?.type === 'fixed_weekly_schedule')
  mockDb.mutate(db => {
    Object.assign(db.sessions.find(s => s.clientId === other.id), { trainerId: 't1', from: '09:00', to: '10:00', status: 'completed' })
    db.clients.find(c => c.id === other.id).package.status = 'inactive'
  })
  signIn(owner().id)
  const before = mockDb.read()
  await expect(api.requestService.resolve({ id: request.id, decision: 'approved' })).rejects.toThrow('conflicts')
  unchanged(before)
})

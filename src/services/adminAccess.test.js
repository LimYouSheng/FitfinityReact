import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { mockDb } from './mockDb.js'
import { MOCK_SESSION_KEY } from './authService.js'
import { mockPortalAdapter } from './mockPortalAdapter.js'
import { staffService } from './staffService.js'
import { createApiPortalAdapter } from './apiPortalAdapter.js'
import { directorySnapshot } from './apiDirectory.js'
import { directoryData } from '../test/directory.js'
import { jsonResponse, sessionInfo, csrfToken } from '../test/api.js'
import { mockPolicy } from '../data/mockPolicy.js'
import { createTrainerDraft } from '../app/trainerOnboarding.js'
import { trainerService } from './trainerService.js'
import { clientService } from './clientService.js'

const body = { name: 'Operations Staff', email: 'admin@example.test', phone_country_code: '+65', phone_number: '91234567', birthday: '1990-01-02', gender: 'Female' }
const owner = () => mockDb.read().users.find(row => row.role === 'owner')
const signIn = id => localStorage.setItem(MOCK_SESSION_KEY, JSON.stringify({ userId: id, expiresAt: Date.now() + 3600000 }))
const create = () => staffService.createAdmin(body, crypto.randomUUID(), owner())
beforeEach(() => { localStorage.clear(); mockDb.reset(); signIn(owner().id) })
afterEach(() => { vi.unstubAllGlobals() })

it.each([
  ['renewPackage', actor => clientService.renewPackage('c1', {}, actor), 'Only the owner or Admin can add packages.'],
  ['deactivatePackage', actor => clientService.deactivatePackage('c1', {}, actor), 'Only the owner or Admin can deactivate packages.'],
  ['deletePackageSessions', actor => clientService.deletePackageSessions('c1', {}, actor), 'Only the owner or Admin can delete package sessions.'],
  ['reassignTrainer', actor => clientService.reassignTrainer('c1', {}, actor), 'Only the owner or Admin can permanently reassign trainers.'],
  ['saveAssessment', actor => clientService.saveAssessment('c1', {}, actor), 'Assessment recording is available to the owner or Admin.'],
  ['progressReportHistory', actor => clientService.progressReportHistory('c1', actor), 'Report history is available to the owner or Admin.'],
  ['deactivate', actor => clientService.deactivate('c1', actor), 'Only the owner or Admin can deactivate clients.'],
  ['reactivate', actor => clientService.reactivate('c1', actor), 'Only the owner or Admin can reactivate clients.'],
])('names both operational roles when %s rejects a trainer, including forged role claims', async (_operation, invoke, message) => {
  const before = mockDb.read(), trainer = before.users.find(row => row.role === 'trainer')
  for (const [actor, expected] of [[trainer, message], [{ ...trainer, role: 'owner' }, 'An active staff identity is required.'], [{ ...trainer, role: 'admin' }, 'An active staff identity is required.']]) {
    await expect(invoke(actor)).rejects.toThrow(expected)
    expect(mockDb.read()).toEqual(before)
  }
})

it.each(['owner', 'admin'])('attributes client deactivation to the stored %s identity', async role => {
  const actor = role === 'owner' ? owner() : await create()
  signIn(actor.id)
  const before = mockDb.read(), client = before.clients.find(row => row.id === 'c1')
  const result = await mockPortalAdapter.invoke({ service: 'clientService', operation: 'deactivate', input: { id: client.id } })
  expect(result.status).toBe('inactive')
  expect(result.deactivatedBy).toEqual({ id: actor.id, name: actor.name })
  const after = mockDb.reload()
  const notices = after.messages.filter(row => !before.messages.some(previous => previous.id === row.id))
  expect(notices).toHaveLength(2)
  expect(notices.find(row => row.recipientTrainerId === client.trainerId)).toMatchObject({
    clientId: client.id, kind: 'client_status', readBy: {},
    body: `${client.name} has been deactivated by ${actor.name} and is available in your client list for viewing only.`,
  })
  expect(notices.find(row => row.recipientRole === 'owner')).toMatchObject({ clientId: client.id, kind: 'client_status', readBy: {} })
  expect(after.sessions).toEqual(before.sessions)
})

it('creates one Admin with personal details, no trainer record, and no email claim in demo mode', async () => {
  const before = mockDb.read(), key = crypto.randomUUID()
  const created = await staffService.createAdmin(body, key, owner())
  expect(created).toMatchObject({ role: 'admin', invitation: 'demo' })
  expect(mockDb.read().users.find(row => row.id === created.id)).toMatchObject({ phone: { countryCode: '+65', number: '91234567' }, birthday: body.birthday, gender: body.gender })
  expect(mockDb.read().trainers).toEqual(before.trainers)
  expect(await staffService.createAdmin(body, key, owner())).toEqual(created)
  expect(mockDb.read().users).toHaveLength(before.users.length + 1)
  await expect(staffService.createAdmin({ ...body, name: 'Changed' }, key, owner())).rejects.toThrow('original account details')
})
it('persists exactly one demo Admin and reuses its receipt on HTTP without randomUUID', async () => {
  const browserCrypto = globalThis.crypto, key = browserCrypto.randomUUID(), before = mockDb.read()
  vi.stubGlobal('crypto', { getRandomValues: browserCrypto.getRandomValues.bind(browserCrypto) })
  const created = await staffService.createAdmin(body, key, owner())
  expect(created.id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/)
  expect(await staffService.createAdmin(body, key, owner())).toEqual(created)
  expect(mockDb.read().users).toHaveLength(before.users.length + 1)
  expect(mockDb.read().staffInvitations).toHaveLength(1)
  expect(created.invitation).toBe('demo')
})
it('rejects duplicate emails, untrusted Owner claims and protected input fields', async () => {
  const trainer = mockDb.read().users.find(row => row.role === 'trainer')
  await expect(staffService.createAdmin(body, crypto.randomUUID(), { ...trainer, role: 'owner' })).rejects.toThrow()
  await expect(staffService.createAdmin({ ...body, role: 'owner' }, crypto.randomUUID(), owner())).rejects.toThrow()
  await create()
  await expect(staffService.createAdmin({ ...body, email: ' ADMIN@EXAMPLE.TEST ' }, crypto.randomUUID(), owner())).rejects.toThrow('already belongs')
})
it('removes rates, pay policy, remuneration records and financial notifications from Admin snapshots', async () => {
  const created = await create()
  mockDb.mutate(db => {
    db.remunerationApprovals = [{ amountCents: 87654321, sentinel: 'PAY_SECRET' }]
    db.messages.push({ id: 'private-pay', recipientRole: 'owner', remunerationCycle: '2026-09', body: 'PAY_SECRET', read: false }, { id: 'private-rate', recipientRole: 'owner', kind: 'trainer_rates', body: 'RATE_SECRET', read: false })
  })
  signIn(created.id)
  const snapshot = await mockPortalAdapter.load()
  expect(snapshot.user.role).toBe('admin')
  expect(snapshot.data.clients.length).toBeGreaterThan(0)
  expect(snapshot.data.trainers.length).toBeGreaterThan(0)
  expect(JSON.stringify(snapshot)).not.toMatch(/PAY_SECRET|RATE_SECRET|"rates"|"trainerRates"|"amountCents"|"remuneration/)
  await expect(mockPortalAdapter.invoke({ service: 'remunerationService', operation: 'list', input: {} })).rejects.toThrow('restricted')
  await expect(mockPortalAdapter.invoke({ service: 'remunerationService', operation: 'approve', input: { cycle: '2026-01', trainerId: 't1', revision: 'revision' } })).rejects.toThrow('restricted')
  await expect(mockPortalAdapter.invoke({ service: 'staffService', operation: 'createAdmin', input: { body, requestKey: crypto.randomUUID() } })).rejects.toThrow('Only the owner')
  await expect(mockPortalAdapter.invoke({ service: 'trainerService', operation: 'update', input: { id: 't1', patch: { rates: { peak: 1, offPeak: 1 } } } })).rejects.toThrow('restricted')
  for (const [method, input] of [['getAll', {}], ['getActive', {}], ['getById', { id: 't1' }]]) {
    expect(JSON.stringify(await mockPortalAdapter.invoke({ service: 'trainerService', operation: method, input }))).not.toContain('"rates"')
  }
  await expect(mockPortalAdapter.invoke({ service: 'messageService', operation: 'markRead', input: { id: 'private-pay' } })).rejects.toThrow('unavailable')
})
it('allows an Admin to change ordinary trainer information while preserving hidden rates', async () => {
  const created = await create(), before = mockDb.read().trainers[0]
  signIn(created.id)
  const result = await mockPortalAdapter.invoke({ service: 'trainerService', operation: 'update', input: { id: before.id, patch: { qualifications: 'Updated certification' } } })
  expect(result.qualifications).toBe('Updated certification')
  expect(result).not.toHaveProperty('rates')
  expect(mockDb.read().trainers[0].rates).toEqual(before.rates)
})
it('allows Admin trainer onboarding with Owner-configured defaults without receiving or choosing rates', async () => {
  const created = await create()
  signIn(created.id)
  const draft = { ...createTrainerDraft(mockPolicy, { includeRates: false }), name: 'New Coach', email: 'new-coach@example.test', phone: { countryCode: '+65', number: '91234567' }, birthday: '1990-01-02', gender: 'Female', trainerType: 'Personal', availabilityBlocks: [{ id: 'slot', days: ['Sunday'], from: '10:00', to: '12:00' }] }
  const before = mockDb.read()
  await expect(mockPortalAdapter.invoke({ service: 'trainerService', operation: 'create', input: { draft: { ...draft, rates: { peak: 0, offPeak: 0 } } } })).rejects.toThrow('restricted')
  expect(mockDb.read()).toEqual(before)
  const result = await mockPortalAdapter.invoke({ service: 'trainerService', operation: 'create', input: { draft } })
  expect(result).not.toHaveProperty('rates')
  expect(mockDb.read().trainers.find(row => row.id === result.id).rates).toEqual(mockPolicy.trainerRates)
})
it('requires an active stored Owner for rate writes even when the adapter is bypassed or an actor is forged', async () => {
  const created = await create(), db = mockDb.read(), admin = db.users.find(row => row.id === created.id)
  const patch = { rates: { peak: 91, offPeak: 62 } }
  for (const actor of [undefined, admin, { ...admin, role: 'owner' }, db.users.find(row => row.role === 'trainer')]) {
    await expect(trainerService.update('t1', patch, actor)).rejects.toThrow()
    expect(mockDb.read()).toEqual(db)
  }
  signIn(created.id)
  await expect(mockPortalAdapter.invoke({ service: 'trainerService', operation: 'update', input: { id: 't1', patch } })).rejects.toThrow('restricted')
  await trainerService.update('t1', patch, owner())
  expect(mockDb.read().trainers.find(row => row.id === 't1').rates).toEqual(patch.rates)
  const disabled = owner()
  mockDb.mutate(state => { state.users.find(row => row.id === disabled.id).status = 'inactive' })
  await expect(trainerService.update('t1', { rates: { peak: 0, offPeak: 0 } }, disabled)).rejects.toThrow()
  expect(mockDb.read().trainers.find(row => row.id === 't1').rates).toEqual(patch.rates)
})
it('uses cookie authentication, CSRF and an unchanged idempotency key for actual Admin creation', async () => {
  const key = crypto.randomUUID(), response = { id: crypto.randomUUID(), name: body.name, email: body.email, role: 'admin', invitation: 'sent' }
  const fetchImpl = vi.fn(async url => jsonResponse(url.endsWith('/me') ? sessionInfo() : response))
  const adapter = createApiPortalAdapter({ baseUrl: 'https://api.example', fetchImpl })
  expect(await adapter.invoke({ service: 'staffService', operation: 'createAdmin', input: { body, requestKey: key } })).toEqual(response)
  const [url, request] = fetchImpl.mock.calls[1]
  expect(url).toBe('https://api.example/api/staff/admins')
  expect(request.headers).toMatchObject({ 'X-CSRF-Token': csrfToken, 'Idempotency-Key': key })
  expect(request.credentials).toBe('include')
  expect(JSON.parse(request.body)).toEqual(body)
})
it('does not send a privileged creation request when the live identity is Admin', async () => {
  const fetchImpl = vi.fn(async () => jsonResponse({ ...sessionInfo(), user: { ...sessionInfo().user, role: 'admin' } }))
  const adapter = createApiPortalAdapter({ baseUrl: 'https://api.example', fetchImpl })
  await expect(adapter.invoke({ service: 'staffService', operation: 'createAdmin', input: { body, requestKey: crypto.randomUUID() } })).rejects.toMatchObject({ code: 'forbidden' })
  expect(fetchImpl).toHaveBeenCalledTimes(1)
})
it('accepts a rate-free Admin directory but fails closed if the server sends rate fields', () => {
  const raw = directoryData(), user = { ...sessionInfo().user, role: 'admin' }
  expect(() => directorySnapshot(raw, user)).toThrow('could not be verified')
  delete raw.trainers[0].peak_rate_cents; delete raw.trainers[0].off_peak_rate_cents
  const result = directorySnapshot(raw, user)
  expect(result.data.trainers[0]).not.toHaveProperty('rates')
  expect(result.data.packages).toHaveLength(1)
})

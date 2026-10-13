import { expect, it, vi } from 'vitest'
import { createApiPortalAdapter } from './apiPortalAdapter.js'
import { createConfiguredPortalServices } from './defaultPortalServices.js'
import { failure, jsonResponse, sessionInfo } from '../test/api.js'
import { directoryId as id } from '../test/directory.js'

const review = () => ({ id: id(20), version: 8, name: 'Client One', trainerId: id(1), genderPreference: 'No gender preference', expected: 'a'.repeat(64), minimumStartDate: '2027-06-07',
  package: { id: id(21), version: 2, templateId: id(4), total: 12, validityDays: 90, sessionsPerWeek: 1, startDate: '2027-03-01', endDate: '2027-05-29' },
  fixedWeeklySchedule: [{ id: id(22), day: 'Monday', from: '10:00', to: '11:00' }], clientPreferences: [{ days: ['Monday'], from: '09:00', to: '12:00' }] })
const draft = () => ({ requestId: id(30), renewalExpected: 'a'.repeat(64), expectedVersion: 8, packageId: id(4), packageVersion: 2, startDate: '2027-06-07', sessionsPerWeek: 1,
  genderPreference: 'No gender preference', clientPreferences: [{ id: 'local-block', days: ['Monday'], from: '09:00', to: '12:00' }], trainerId: id(1), trainerVersion: 3,
  fixedWeeklySchedule: [{ id: id(22), day: 'Monday', from: '10:00', to: '11:00' }], packageName: 'Display only' })
const saved = { id: id(20), version: 9, purchaseId: id(31) }
const request = (value = draft()) => ({ service: 'clientService', operation: 'renewPackage', input: { id: id(20), draft: value } })

it('reads authoritative renewal defaults through the initiating session', async () => {
  const fetch = vi.fn(async url => jsonResponse(url.endsWith('/me') ? sessionInfo() : review()))
  const services = createConfiguredPortalServices({ mode: 'api', fetchImpl: fetch }).forSession(0)
  expect(await services.reviewClientRenewal({ id: id(20), expectedVersion: 8 })).toEqual(review())
  expect(fetch.mock.calls.every(([, o]) => o.method === 'GET')).toBe(true)
})

it.each([
  { version: 9 }, { fixedWeeklySchedule: [] }, { healthNotes: 'Unrequested information' },
])('rejects stale or unverifiable renewal defaults: %j', async patch => {
  const fetch = vi.fn(async url => jsonResponse(url.endsWith('/me') ? sessionInfo() : { ...review(), ...patch }))
  const adapter = createApiPortalAdapter({ fetchImpl: fetch })
  await expect(adapter.reviewClientRenewal({ id: id(20), expectedVersion: 8 })).rejects.toBeTruthy()
})

it('preserves exact saved intervals in matching without trusting display identities', async () => {
  const matches = [{ trainerId: id(1), trainerVersion: 3, matches: 1, total: 1, schedule: [{ day: 'Monday', from: '10:00', to: '11:00' }] }]
  const fetch = vi.fn(async url => jsonResponse(url.endsWith('/me') ? sessionInfo() : { matches }))
  const adapter = createApiPortalAdapter({ fetchImpl: fetch })
  expect(await adapter.previewClientRenewalMatches({ id: id(20), draft: draft() })).toEqual(matches)
  const [, options] = fetch.mock.calls.find(([url]) => url.endsWith('/renewal-matches'))
  const body = JSON.parse(options.body)
  expect(body.expected).toBe('a'.repeat(64))
  expect(body.fixedWeeklySchedule).toEqual(matches[0].schedule)
  expect(body).not.toHaveProperty('expectedVersion')
  expect(body).not.toHaveProperty('packageName')
  expect(body).not.toHaveProperty('clientId')
})

it('uses the stable wizard request ID and strips local metadata from the atomic command', async () => {
  const fetch = vi.fn(async url => jsonResponse(url.endsWith('/me') ? sessionInfo() : saved))
  const adapter = createApiPortalAdapter({ fetchImpl: fetch })
  expect(await adapter.invoke(request())).toEqual(saved)
  expect(await adapter.invoke(request())).toEqual(saved)
  const calls = fetch.mock.calls.filter(([, o]) => o.method === 'POST')
  expect(calls).toHaveLength(2)
  expect(calls.map(([, o]) => o.headers['Idempotency-Key'])).toEqual([id(30), id(30)])
  const body = JSON.parse(calls[0][1].body)
  expect(body.expected).toBe('a'.repeat(64))
  expect(body.trainerVersion).toBe(3)
  expect(body.fixedWeeklySchedule[0]).not.toHaveProperty('id')
  expect(body).not.toHaveProperty('requestId')
  expect(body).not.toHaveProperty('packageName')
  expect(body).not.toHaveProperty('actor')
})

it('reconciles a committed uncertain save without another POST', async () => {
  const fetch = vi.fn(async (url, options) => {
    if (url.endsWith('/me')) return jsonResponse(sessionInfo())
    if (options.method === 'POST') throw new Error('response lost')
    return jsonResponse(saved)
  })
  const adapter = createApiPortalAdapter({ fetchImpl: fetch })
  await expect(adapter.invoke(request())).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  expect(await adapter.invoke(request())).toEqual(saved)
  expect(fetch.mock.calls.filter(([, o]) => o.method === 'POST')).toHaveLength(1)
  expect(fetch.mock.calls.some(([url]) => url.endsWith(`/client-renewals/${id(30)}`))).toBe(true)
})

it('keeps an absent receipt uncertain until an explicit retry with the same request ID', async () => {
  let writes = 0
  const fetch = vi.fn(async (url, options) => {
    if (url.endsWith('/me')) return jsonResponse(sessionInfo())
    if (options.method === 'GET') return failure('not_found', 404)
    if (++writes === 1) throw new Error('request lost')
    return jsonResponse(saved)
  })
  const adapter = createApiPortalAdapter({ fetchImpl: fetch })
  await expect(adapter.invoke(request())).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  expect(await adapter.invoke(request())).toEqual(saved)
  expect(fetch.mock.calls.filter(([, o]) => o.method === 'POST').map(([, o]) => o.headers['Idempotency-Key'])).toEqual([id(30), id(30)])
})

it('blocks replacing an uncertain draft or opening another renewal preview', async () => {
  const fetch = vi.fn(async url => { if (url.endsWith('/me')) return jsonResponse(sessionInfo()); throw new Error('offline') })
  const adapter = createApiPortalAdapter({ fetchImpl: fetch })
  await expect(adapter.invoke(request())).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  await expect(adapter.invoke(request({ ...draft(), startDate: '2027-06-14' }))).rejects.toMatchObject({ code: 'SAVE_UNCERTAIN' })
  await expect(adapter.previewClientRenewalMatches({ id: id(20), draft: draft() })).rejects.toMatchObject({ code: 'SAVE_UNCERTAIN' })
  await expect(adapter.reviewClientRenewal({ id: id(20), expectedVersion: 8 })).rejects.toMatchObject({ code: 'SAVE_UNCERTAIN' })
  expect(fetch.mock.calls.filter(([, o]) => o.method === 'POST')).toHaveLength(1)
})

it('rejects mismatched receipt identity and keeps the original command for checking', async () => {
  let malformed = true
  const fetch = vi.fn(async url => jsonResponse(url.endsWith('/me') ? sessionInfo() : malformed ? { ...saved, id: id(99) } : saved))
  const adapter = createApiPortalAdapter({ fetchImpl: fetch })
  await expect(adapter.invoke(request())).rejects.toMatchObject({ code: 'API_RESPONSE' })
  malformed = false
  expect(await adapter.invoke(request())).toEqual(saved)
  expect(fetch.mock.calls.filter(([, o]) => o.method === 'POST')).toHaveLength(1)
})

it('refuses trainer renewal reads and saves before any domain request', async () => {
  const fetch = vi.fn(async () => jsonResponse({ ...sessionInfo(), user: { ...sessionInfo().user, role: 'trainer', trainerId: id(1) } }))
  const adapter = createApiPortalAdapter({ fetchImpl: fetch })
  await expect(adapter.reviewClientRenewal({ id: id(20), expectedVersion: 8 })).rejects.toMatchObject({ code: 'forbidden' })
  await expect(adapter.invoke(request())).rejects.toMatchObject({ code: 'forbidden' })
  expect(fetch.mock.calls.every(([url]) => url.endsWith('/me'))).toBe(true)
})

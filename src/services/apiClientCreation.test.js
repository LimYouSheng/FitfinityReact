import { expect, it, vi } from 'vitest'
import { createApiPortalAdapter } from './apiPortalAdapter.js'
import { createPortalServices } from './portalService.js'
import { createConfiguredPortalServices } from './defaultPortalServices.js'
import { failure, jsonResponse, sessionInfo } from '../test/api.js'
import { directoryId } from '../test/directory.js'

const draft = () => ({ type: 'Individual', packageId: directoryId(4), packageVersion: 2, packageName: 'Reviewed PT', startDate: '2027-06-07', sessionsPerWeek: 1,
  genderPreference: 'No gender preference', clientPreferences: [{ id: 'local-block', days: ['Monday'], from: '18:00', to: '19:00' }],
  trainerId: directoryId(1), trainerVersion: 3, fixedWeeklySchedule: [{ id: 'local-slot', day: 'Monday', from: '18:00', to: '19:00' }], remarks: '',
  people: [{ name: 'New Client', email: 'new@example.test', phone: { countryCode: '+65', number: '91234567' }, birthday: '1990-01-01', gender: 'Other',
    emergencyContact: { name: 'Contact', relationship: 'Friend', countryCode: '+65', number: '91234568' }, healthNotes: 'General note', assessments: {} }],
})
const created = { id: directoryId(20), version: 2, purchaseId: directoryId(21) }
const request = value => ({ service: 'clientService', operation: 'create', input: { draft: value } })

it('sends reviewed creation with no display-only values or caller identities', async () => {
  const fetch = vi.fn(async url => jsonResponse(url.endsWith('/me') ? sessionInfo() : created))
  const adapter = createApiPortalAdapter({ fetchImpl: fetch })
  expect(await adapter.invoke(request(draft()))).toEqual(created)
  const [, options] = fetch.mock.calls.find(([url]) => url.endsWith('/api/clients'))
  const body = JSON.parse(options.body)
  expect(body.packageVersion).toBe(2)
  expect(body.trainerVersion).toBe(3)
  expect(body.people[0].healthNotes).toBe('General note')
  expect(body.clientPreferences[0]).not.toHaveProperty('id')
  expect(body.fixedWeeklySchedule[0]).not.toHaveProperty('id')
  expect(body).not.toHaveProperty('packageName')
  expect(body).not.toHaveProperty('actor')
  expect(options.headers['Idempotency-Key']).toMatch(/^[0-9a-f-]{36}$/)
})

it('recovers uncertain creation by receipt and rejects changed drafts', async () => {
  let writes = 0
  const fetch = vi.fn(async (url, options) => {
    if (url.endsWith('/me')) return jsonResponse(sessionInfo())
    if (options.method === 'POST') { writes++; throw new Error('offline') }
    return jsonResponse(created)
  })
  const adapter = createApiPortalAdapter({ fetchImpl: fetch })
  await expect(adapter.invoke(request(draft()))).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  await expect(adapter.invoke(request({ ...draft(), remarks: 'changed' }))).rejects.toMatchObject({ code: 'SAVE_UNCERTAIN' })
  expect(await adapter.invoke(request(draft()))).toEqual(created)
  expect(writes).toBe(1)
})

it('explicit retry after absent receipt preserves the original request key', async () => {
  let writes = 0
  const fetch = vi.fn(async (url, options) => {
    if (url.endsWith('/me')) return jsonResponse(sessionInfo())
    if (options.method === 'GET') return failure('not_found', 404)
    if (++writes === 1) throw new Error('offline')
    return jsonResponse(created)
  })
  const adapter = createApiPortalAdapter({ fetchImpl: fetch })
  await expect(adapter.invoke(request(draft()))).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  expect(await adapter.invoke(request(draft()))).toEqual(created)
  const writesMade = fetch.mock.calls.filter(([, o]) => o.method === 'POST')
  expect(writesMade).toHaveLength(2)
  expect(writesMade[0][1].headers['Idempotency-Key']).toBe(writesMade[1][1].headers['Idempotency-Key'])
})

it('binds matching reads to the initiating login and validates complete schedules', async () => {
  const matches = [{ trainerId: directoryId(1), trainerVersion: 3, matches: 1, total: 1, schedule: [{ day: 'Monday', from: '18:00', to: '19:00' }] }]
  const fetch = vi.fn(async url => jsonResponse(url.endsWith('/me') ? sessionInfo() : { matches }))
  const services = createConfiguredPortalServices({ mode: 'api', fetchImpl: fetch }).forSession(0)
  expect(await services.previewClientMatches(draft())).toEqual(matches)
  matches[0].schedule = []
  await expect(services.previewClientMatches(draft())).rejects.toMatchObject({ code: 'API_RESPONSE' })
  expect(fetch.mock.calls.find(([url]) => url.endsWith('/matches'))[1].headers['Idempotency-Key']).toBeTruthy()
})

it('denies Trainer creation and matching before either domain request', async () => {
  const fetch = vi.fn(async () => jsonResponse({ ...sessionInfo(), user: { ...sessionInfo().user, role: 'trainer', trainerId: directoryId(1) } }))
  const adapter = createApiPortalAdapter({ fetchImpl: fetch })
  await expect(adapter.invoke(request(draft()))).rejects.toMatchObject({ code: 'forbidden' })
  await expect(adapter.previewClientMatches(draft())).rejects.toMatchObject({ code: 'forbidden' })
  expect(fetch.mock.calls.every(([url]) => url.endsWith('/me'))).toBe(true)
})

it('refuses malformed creation inputs before transport', async () => {
  const fetch = vi.fn(), adapter = createApiPortalAdapter({ fetchImpl: fetch })
  await expect(adapter.invoke(request({}))).rejects.toMatchObject({ code: 'INVALID_REQUEST' })
  expect(fetch).not.toHaveBeenCalled()
})

it('old matching closures stop when preflight discovers a replacement role', async () => {
  let replaced = false
  const fetch = vi.fn(async url => jsonResponse(url.endsWith('/me')
    ? { ...sessionInfo(), user: { ...sessionInfo().user, role: replaced ? 'admin' : 'owner' } }
    : { matches: [] }))
  const services = createPortalServices(createApiPortalAdapter({ fetchImpl: fetch })).forSession(0)
  expect(await services.previewClientMatches(draft())).toEqual([])
  replaced = true
  await expect(services.previewClientMatches(draft())).rejects.toMatchObject({ code: 'SESSION_CHANGED' })
  expect(fetch.mock.calls.filter(([url]) => url.endsWith('/matches'))).toHaveLength(1)
})

it('rejects malformed saved IDs and retains the uncertain operation for reconciliation', async () => {
  const fetch = vi.fn(async url => jsonResponse(url.endsWith('/me') ? sessionInfo() : { ...created, id: 'invented' }))
  const adapter = createApiPortalAdapter({ fetchImpl: fetch })
  await expect(adapter.invoke(request(draft()))).rejects.toMatchObject({ code: 'API_RESPONSE' })
  await expect(adapter.invoke(request({ ...draft(), remarks: 'new' }))).rejects.toMatchObject({ code: 'SAVE_UNCERTAIN' })
})

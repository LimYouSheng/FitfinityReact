import { expect, it, vi } from 'vitest'
import { createApiPortalAdapter } from './apiPortalAdapter.js'
import { authPolicy, csrfToken, failure, jsonResponse, sessionInfo } from '../test/api.js'
import { directoryData, directoryId } from '../test/directory.js'

const person = { name: 'Updated Client', email: 'updated@example.test', birthday: '1990-01-01', gender: 'Female', phone: { countryCode: '+65', number: '91234568' }, emergencyContact: { name: 'Contact', relationship: 'Friend', countryCode: '+65', number: '91234569' }, healthNotes: '', assessments: {} }
const input = { id: directoryId(7), reviewed: { expectedVersion: 2, people: [{ id: directoryId(3), expectedVersion: 1 }] }, patch: { people: [person], remarks: 'Updated', genderPreference: 'Female trainer preferred' } }
const result = { id: input.id, version: 3, people: [{ id: directoryId(3), version: 2 }] }
const request = (value = input) => ({ service: 'clientService', operation: 'update', input: value })
const make = fetchImpl => createApiPortalAdapter({ baseUrl: 'https://api.example', fetchImpl })

it.each(['owner', 'admin'])('sends only reviewed personal fields as %s with bound CSRF', async role => {
  const fetch = vi.fn(async (_url, options) => jsonResponse(options.method === 'POST' ? result : { ...sessionInfo(), user: { ...sessionInfo().user, role } }))
  expect(await make(fetch).invoke(request())).toEqual(result)
  const [url, options] = fetch.mock.calls.find(([, options]) => options.method === 'POST')
  expect(url).toBe(`https://api.example/api/clients/${input.id}/personal-details`)
  const body = JSON.parse(options.body)
  expect(body.expectedVersion).toBe(2)
  expect(body.people[0]).toMatchObject({ id: directoryId(3), expectedVersion: 1, name: 'Updated Client' })
  expect(body.people[0]).not.toHaveProperty('healthNotes')
  expect(body.people[0]).not.toHaveProperty('assessments')
  expect(options.headers['X-CSRF-Token']).toBe(csrfToken)
  expect(options.headers['Idempotency-Key']).toMatch(/^[0-9a-f-]{36}$/)
})
it('reconciles lost personal-edit responses without replaying mutations', async () => {
  const fetch = vi.fn(async (url, options) => {
    if (options.method === 'POST') throw new Error('Response lost')
    return jsonResponse(url.includes('client-detail-saves') ? result : sessionInfo())
  })
  const adapter = make(fetch)
  await expect(adapter.invoke(request())).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  expect(await adapter.invoke(request())).toEqual(result)
  expect(fetch.mock.calls.filter(([, options]) => options.method === 'POST')).toHaveLength(1)
})
it('blocks changed pending drafts and retries identical content only after an absent receipt', async () => {
  let posts = 0
  const fetch = vi.fn(async (url, options) => {
    if (url.includes('client-detail-saves')) return failure('not_found', 404)
    if (options.method === 'POST') { if (++posts === 1) throw new Error('Not received'); return jsonResponse(result) }
    return jsonResponse(sessionInfo())
  })
  const adapter = make(fetch)
  await expect(adapter.invoke(request())).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  await expect(adapter.invoke(request({ ...input, patch: { ...input.patch, remarks: 'Changed' } }))).rejects.toMatchObject({ code: 'SAVE_UNCERTAIN' })
  await adapter.invoke(request())
  const writes = fetch.mock.calls.filter(([, options]) => options.method === 'POST').map(([, options]) => options)
  expect(writes[0].body).toBe(writes[1].body)
  expect(writes[0].headers['Idempotency-Key']).toBe(writes[1].headers['Idempotency-Key'])
})
it('rejects forged result identities while retaining the original recovery key', async () => {
  const fetch = vi.fn(async (url, options) => jsonResponse(options.method === 'POST' ? { ...result, people: [{ id: directoryId(90), version: 2 }] } : url.includes('client-detail-saves') ? result : sessionInfo()))
  const adapter = make(fetch)
  await expect(adapter.invoke(request())).rejects.toMatchObject({ code: 'API_RESPONSE' })
  expect(await adapter.invoke(request())).toEqual(result)
})
it('denies Trainer writes and rejects health or incomplete-version contact requests', async () => {
  const fetch = vi.fn(async () => jsonResponse({ ...sessionInfo(), user: { ...sessionInfo().user, role: 'trainer', trainerId: directoryId(1) } }))
  const adapter = make(fetch)
  await expect(adapter.invoke(request())).rejects.toMatchObject({ code: 'forbidden' })
  await expect(adapter.invoke(request({ ...input, reviewed: {} }))).rejects.toMatchObject({ code: 'INVALID_REQUEST' })
  await expect(adapter.invoke(request({ ...input, patch: { ...input.patch, healthNotes: 'secret' } }))).rejects.toMatchObject({ code: 'OPERATION_UNAVAILABLE' })
  expect(fetch.mock.calls.every(([, options]) => options.method === 'GET')).toBe(true)
})
it('requires explicit server capability before enabling personal edits', async () => {
  const directory = directoryData()
  const adapter = make(vi.fn(async url => jsonResponse(url.endsWith('/auth/policy') ? authPolicy : url.endsWith('/api/directory') ? directory : sessionInfo())))
  expect((await adapter.load()).capabilities.clientPersonalWrites).toBe(false)
  directory.clientPersonalWrites = true
  expect((await adapter.load()).capabilities.clientPersonalWrites).toBe(true)
  directory.clientPersonalWrites = 'true'
  await expect(adapter.load()).rejects.toMatchObject({ code: 'API_RESPONSE' })
})

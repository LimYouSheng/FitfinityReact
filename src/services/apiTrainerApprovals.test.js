import { expect, it, vi } from 'vitest'
import { createApiPortalAdapter } from './apiPortalAdapter.js'
import { authPolicy, csrfToken, failure, jsonResponse, sessionInfo } from '../test/api.js'
import { directoryData, directoryId } from '../test/directory.js'

const controls = { availability: false, sessionTime: true, trainerReassignment: false, fixedWeeklySchedule: true }
const input = { id: directoryId(1), expectedVersion: 1, approvalNeeded: controls }
const result = { id: input.id, version: 2, approvalNeeded: controls }
const request = (value = input) => ({ service: 'trainerService', operation: 'updateAutonomy', input: value })
const make = fetchImpl => createApiPortalAdapter({ baseUrl: 'https://api.example', fetchImpl })

it.each(['owner', 'admin'])('saves exact reviewed approval controls as %s with CSRF and a retry key', async role => {
  const fetch = vi.fn(async (_url, options) => jsonResponse(options.method === 'POST' ? result : { ...sessionInfo(), user: { ...sessionInfo().user, role } }))
  expect(await make(fetch).invoke(request())).toEqual(result)
  const [url, options] = fetch.mock.calls.find(([, options]) => options.method === 'POST')
  expect(url).toBe(`https://api.example/api/trainers/${input.id}/approvals`)
  expect(JSON.parse(options.body)).toEqual({ expectedVersion: 1, approvalNeeded: controls })
  expect(options.headers['X-CSRF-Token']).toBe(csrfToken)
  expect(options.headers['Idempotency-Key']).toMatch(/^[0-9a-f-]{36}$/)
})
it('reconciles an interrupted commit without replay and blocks changed pending values', async () => {
  const fetch = vi.fn(async (url, options) => {
    if (options.method === 'POST') throw new Error('Response lost')
    return jsonResponse(url.includes('trainer-approval-saves') ? result : sessionInfo())
  })
  const adapter = make(fetch)
  await expect(adapter.invoke(request())).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  await expect(adapter.invoke(request({ ...input, approvalNeeded: { ...controls, sessionTime: false } }))).rejects.toMatchObject({ code: 'SAVE_UNCERTAIN' })
  expect(await adapter.invoke(request())).toEqual(result)
  expect(fetch.mock.calls.filter(([, options]) => options.method === 'POST')).toHaveLength(1)
})
it('reuses the exact key and body only after a serialized absent receipt', async () => {
  let posts = 0
  const fetch = vi.fn(async (url, options) => {
    if (url.includes('trainer-approval-saves')) return failure('not_found', 404)
    if (options.method === 'POST') { if (++posts === 1) throw new Error('Not received'); return jsonResponse(result) }
    return jsonResponse(sessionInfo())
  })
  const adapter = make(fetch)
  await expect(adapter.invoke(request())).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  await adapter.invoke(request())
  const writes = fetch.mock.calls.filter(([, options]) => options.method === 'POST').map(([, options]) => options)
  expect(writes[0].body).toBe(writes[1].body)
  expect(writes[0].headers['Idempotency-Key']).toBe(writes[1].headers['Idempotency-Key'])
})
it('rejects rates or malformed response evidence and preserves reconciliation', async () => {
  const fetch = vi.fn(async (url, options) => jsonResponse(options.method === 'POST' ? { ...result, rates: {} } : url.includes('trainer-approval-saves') ? result : sessionInfo()))
  const adapter = make(fetch)
  await expect(adapter.invoke(request())).rejects.toMatchObject({ code: 'API_RESPONSE' })
  expect(await adapter.invoke(request())).toEqual(result)
  expect(fetch.mock.calls.filter(([, options]) => options.method === 'POST')).toHaveLength(1)
})
it('denies Trainer writes and does not adopt a changed session for an old action', async () => {
  let user = { ...sessionInfo().user, role: 'trainer', trainerId: input.id }
  const fetch = vi.fn(async () => jsonResponse({ ...sessionInfo(), user }))
  const adapter = make(fetch)
  await expect(adapter.invoke(request())).rejects.toMatchObject({ code: 'forbidden' })
  user = { ...sessionInfo().user, id: directoryId(90) }
  await expect(adapter.invoke(request(), { expectedGeneration: 0 })).rejects.toMatchObject({ code: 'SESSION_CHANGED' })
  expect(fetch.mock.calls.every(([, options]) => options.method === 'GET')).toBe(true)
})
it('enables only the advertised controls and rejects invalid capability types', async () => {
  const directory = directoryData()
  const adapter = make(vi.fn(async url => jsonResponse(url.endsWith('/auth/policy') ? authPolicy : url.endsWith('/api/directory') ? directory : sessionInfo())))
  expect((await adapter.load()).capabilities.trainerApprovalWrites).toBe(false)
  directory.trainerApprovalWrites = true
  expect((await adapter.load()).capabilities.trainerApprovalWrites).toBe(true)
  directory.trainerApprovalWrites = 'true'
  await expect(adapter.load()).rejects.toMatchObject({ code: 'API_RESPONSE' })
})

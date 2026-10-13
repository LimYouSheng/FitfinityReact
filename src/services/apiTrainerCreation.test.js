import { expect, it, vi } from 'vitest'
import { createApiPortalAdapter } from './apiPortalAdapter.js'
import { failure, jsonResponse, sessionInfo } from '../test/api.js'
import { directoryId } from '../test/directory.js'

const draft = () => ({ requestId: directoryId(40), name: 'New Trainer', email: 'trainer@example.test', phone: { countryCode: '+65', number: '91234567' }, birthday: '1990-01-01', gender: 'Other', trainerType: 'Personal Trainer', qualifications: 'Qualified', publicProfile: 'Visible', rates: { peak: '80.25', offPeak: '55' }, availabilityBlocks: [{ days: ['Monday'], from: '18:00', to: '19:00' }], approvalNeeded: { availability: true, sessionTime: true, trainerReassignment: true, fixedWeeklySchedule: true } })
const created = { id: directoryId(41), invitation: 'sent' }
const request = (value = draft()) => ({ service: 'trainerService', operation: 'create', input: { draft: value } })

it('sends exact cents, reviewed controls and a stable request identity', async () => {
  const fetch = vi.fn(async url => jsonResponse(url.endsWith('/me') ? sessionInfo() : created))
  const adapter = createApiPortalAdapter({ fetchImpl: fetch })
  expect(await adapter.invoke(request())).toEqual(created)
  const [, options] = fetch.mock.calls.find(([url]) => url.endsWith('/api/staff/trainers'))
  expect(options.headers['Idempotency-Key']).toBe(draft().requestId)
  expect(JSON.parse(options.body)).toMatchObject({ rates: { peak: 8025, offPeak: 5500 }, slots: [{ weekday: 0, startsAt: '18:00', endsAt: '19:00' }] })
  expect(JSON.parse(options.body)).not.toHaveProperty('requestId')
})

it.each(['sent', 'unknown'])('recovers a %s receipt without resending the invitation', async invitation => {
  const fetch = vi.fn(async (url, options) => {
    if (url.endsWith('/me')) return jsonResponse(sessionInfo())
    if (options.method === 'POST') throw new Error('offline')
    return jsonResponse({ ...created, invitation })
  })
  const adapter = createApiPortalAdapter({ fetchImpl: fetch })
  await expect(adapter.invoke(request())).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  await expect(adapter.invoke(request({ ...draft(), name: 'Changed' }))).rejects.toMatchObject({ code: 'SAVE_UNCERTAIN' })
  expect(await adapter.invoke(request())).toEqual({ ...created, invitation })
  expect(fetch.mock.calls.filter(([, o]) => o.method === 'POST')).toHaveLength(1)
})

it.each(['pending', 'sending'])('resumes %s only on an explicit identical retry', async invitation => {
  let writes = 0
  const fetch = vi.fn(async (url, options) => {
    if (url.endsWith('/me')) return jsonResponse(sessionInfo())
    if (options.method === 'GET') return jsonResponse({ ...created, invitation })
    return ++writes === 1 ? failure('INVITATION_BUSY', 409) : jsonResponse(created)
  })
  const adapter = createApiPortalAdapter({ fetchImpl: fetch })
  await expect(adapter.invoke(request())).rejects.toMatchObject({ code: 'SAVE_UNCERTAIN' })
  expect(writes).toBe(1)
  expect(await adapter.invoke(request())).toEqual(created)
  const posts = fetch.mock.calls.filter(([, o]) => o.method === 'POST')
  expect(posts).toHaveLength(2)
  expect(posts[0][1].body).toBe(posts[1][1].body)
  expect(posts[0][1].headers['Idempotency-Key']).toBe(posts[1][1].headers['Idempotency-Key'])
})

it('does not transmit financial fields for an Admin draft', async () => {
  const value = draft(); delete value.rates
  const fetch = vi.fn(async url => jsonResponse(url.endsWith('/me') ? { ...sessionInfo(), user: { ...sessionInfo().user, role: 'admin' } } : created))
  await createApiPortalAdapter({ fetchImpl: fetch }).invoke(request(value))
  expect(JSON.parse(fetch.mock.calls.find(([, o]) => o.method === 'POST')[1].body)).not.toHaveProperty('rates')
})

it('retains an uncertain request after malformed receipt evidence', async () => {
  const fetch = vi.fn(async url => jsonResponse(url.endsWith('/me') ? sessionInfo() : { ...created, rates: { peak: 8000 } }))
  const adapter = createApiPortalAdapter({ fetchImpl: fetch })
  await expect(adapter.invoke(request())).rejects.toMatchObject({ code: 'API_RESPONSE' })
  await expect(adapter.invoke(request({ ...draft(), email: 'changed@example.test' }))).rejects.toMatchObject({ code: 'SAVE_UNCERTAIN' })
})

it('rejects incomplete input and null rates before transport', async () => {
  const fetch = vi.fn(), adapter = createApiPortalAdapter({ fetchImpl: fetch })
  for (const value of [{}, { ...draft(), rates: null }]) await expect(adapter.invoke(request(value))).rejects.toMatchObject({ code: 'INVALID_REQUEST' })
  expect(fetch).not.toHaveBeenCalled()
})

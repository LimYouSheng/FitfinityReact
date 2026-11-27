import { expect, it, vi } from 'vitest'
import { createApiPortalAdapter } from './apiPortalAdapter.js'
import { jsonResponse, sessionInfo, staff } from '../test/api.js'

const details = { name: 'Updated Owner', email: staff.email, phone_country_code: '+65', phone_number: '91234567', birthday: '1990-01-02', gender: 'Other' }
const input = { id: staff.id, expectedVersion: 1, details }
const saved = { id: staff.id, version: 2, ...details }
const command = { service: 'ownerService', operation: 'saveProfile', input }

it('recovers a lost Owner save from its receipt without a second write', async () => {
  const fetch = vi.fn(async (url, options) => {
    if (url.endsWith('/me')) return jsonResponse(sessionInfo())
    if (options.method === 'POST') throw new Error('response lost')
    return jsonResponse(saved)
  })
  const adapter = createApiPortalAdapter({ baseUrl: 'https://api.example', fetchImpl: fetch })
  await expect(adapter.invoke(command)).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  await expect(adapter.invoke({ ...command, input: { ...input, details: { ...details, name: 'Different' } } })).rejects.toMatchObject({ code: 'SAVE_UNCERTAIN' })
  expect(await adapter.invoke(command)).toEqual(saved)
  expect(fetch.mock.calls.filter(([, options]) => options.method === 'POST')).toHaveLength(1)
  expect(fetch.mock.calls.some(([url]) => url.includes('/api/owner-profile/saves/'))).toBe(true)
})

it('rejects a profile read for a different identity', async () => {
  const fetch = vi.fn(async url => jsonResponse(url.endsWith('/me') ? sessionInfo() : { ...saved, id: '00000000-0000-4000-8000-000000000002' }))
  const adapter = createApiPortalAdapter({ baseUrl: 'https://api.example', fetchImpl: fetch })
  await expect(adapter.invoke({ service: 'ownerService', operation: 'getProfile', input: {} })).rejects.toMatchObject({ code: 'API_RESPONSE' })
})

it('reserves the Owner email without sending a code or changing identity', async () => {
  const change = { id: '00000000-0000-4000-8000-000000000003', email: 'new-owner@example.test', state: 'requested', signedOut: false }
  const fetch = vi.fn(async url => jsonResponse(url.endsWith('/me') ? sessionInfo() : change))
  const adapter = createApiPortalAdapter({ baseUrl: 'https://api.example', fetchImpl: fetch })
  expect(await adapter.session({ operation: 'requestOwnerEmailChange', input: { email: change.email, expectedVersion: 1 } })).toEqual(change)
  expect(fetch.mock.calls.some(([url]) => url.endsWith('/api/owner-profile/email-change'))).toBe(true)
  expect(fetch.mock.calls.some(([url]) => url.endsWith('/send'))).toBe(false)
})

import { expect, it, vi } from 'vitest'
import { createApiPortalAdapter } from './apiPortalAdapter.js'
import { jsonResponse, sessionInfo } from '../test/api.js'
import { directoryId } from '../test/directory.js'

const input = { id: directoryId(1), expectedVersion: 2, patch: { name: 'Changed', birthday: '', phone: { countryCode: '+60', number: '' } } }
const update = input => ({ service: 'trainerService', operation: 'update', input })

it('sends only reviewed profile fields and preserves cleared contacts', async () => {
  const fetch = vi.fn(async url => jsonResponse(url.endsWith('/me') ? sessionInfo() : { id: input.id, version: 3 }))
  const adapter = createApiPortalAdapter({ fetchImpl: fetch })
  await adapter.invoke(update(input))
  const [, options] = fetch.mock.calls.find(([url]) => url.endsWith('/personal-details'))
  expect(JSON.parse(options.body)).toEqual({ expectedVersion: 2, patch: { name: 'Changed', birthday: null, phone: { countryCode: '+60', number: '' } } })
  expect(options.headers['Idempotency-Key']).toMatch(/^[0-9a-f-]{36}$/)
})

it('recovers a lost profile response by receipt without rewriting the record', async () => {
  let writes = 0
  const fetch = vi.fn(async (url, options) => {
    if (url.endsWith('/me')) return jsonResponse(sessionInfo())
    if (options.method === 'POST') { writes++; throw new Error('offline') }
    return jsonResponse({ id: input.id, version: 3 })
  })
  const adapter = createApiPortalAdapter({ fetchImpl: fetch })
  await expect(adapter.invoke(update(input))).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  await expect(adapter.invoke(update({ ...input, patch: { name: 'Other' } }))).rejects.toMatchObject({ code: 'SAVE_UNCERTAIN' })
  expect(await adapter.invoke(update(input))).toEqual({ id: input.id, version: 3 })
  expect(writes).toBe(1)
})

it.each([{ status: 'inactive' }, { name: 'Changed', email: 'unverified@example.test' }, { role: 'owner' }])('rejects mixed or protected profile fields before HTTP: %j', async patch => {
  const fetch = vi.fn()
  const adapter = createApiPortalAdapter({ fetchImpl: fetch })
  await expect(adapter.invoke(update({ ...input, patch }))).rejects.toMatchObject({ code: 'OPERATION_UNAVAILABLE' })
  expect(fetch).not.toHaveBeenCalled()
})

it('rejects a profile receipt with an unrelated ID or version', async () => {
  const fetch = vi.fn(async url => jsonResponse(url.endsWith('/me') ? sessionInfo() : { id: input.id, version: 2 }))
  const adapter = createApiPortalAdapter({ fetchImpl: fetch })
  await expect(adapter.invoke(update(input))).rejects.toMatchObject({ code: 'API_RESPONSE' })
})

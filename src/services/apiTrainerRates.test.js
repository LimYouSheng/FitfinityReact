import { expect, it, vi } from 'vitest'
import { createApiPortalAdapter } from './apiPortalAdapter.js'
import { jsonResponse, sessionInfo } from '../test/api.js'
import { directoryId } from '../test/directory.js'

const id = directoryId(1)
const input = { id, expectedVersion: 2, patch: { rates: { peak: 65.43, offPeak: 43.21 } } }
const result = { id, version: 3 }
const request = (value = input) => ({ service: 'trainerService', operation: 'update', input: value })
const make = fetchImpl => createApiPortalAdapter({ baseUrl: 'https://api.example', fetchImpl })

it('saves exact integer cents under Owner authority without profile fields', async () => {
  const fetch = vi.fn(async (_url, options) => jsonResponse(options.method === 'POST' ? result : sessionInfo()))
  expect(await make(fetch).invoke(request())).toEqual(result)
  const [url, options] = fetch.mock.calls.find(([, options]) => options.method === 'POST')
  expect(url).toBe(`https://api.example/api/trainers/${id}/rates`)
  expect(JSON.parse(options.body)).toEqual({ expectedVersion: 2, rates: { peak: 6543, offPeak: 4321 } })
})
it.each(['admin', 'trainer'])('denies %s before a rate mutation', async role => {
  const fetch = vi.fn(async () => jsonResponse({ ...sessionInfo(), user: { ...sessionInfo().user, role } }))
  await expect(make(fetch).invoke(request())).rejects.toMatchObject({ code: 'forbidden' })
  expect(fetch.mock.calls.every(([, options]) => options.method === 'GET')).toBe(true)
})
it.each([-1, 1.234, Infinity, 9007199254740992])('rejects inaccurate or invalid rate %s before HTTP', async peak => {
  const fetch = vi.fn()
  await expect(make(fetch).invoke(request({ ...input, patch: { rates: { peak, offPeak: 0 } } }))).rejects.toMatchObject({ code: 'INVALID_REQUEST' })
  expect(fetch).not.toHaveBeenCalled()
})
it('reconciles uncertain rate writes before replay and rejects another pending value', async () => {
  const fetch = vi.fn(async (url, options) => {
    if (options.method === 'POST') throw new Error('Lost response')
    return jsonResponse(url.includes('trainer-rate-saves') ? result : sessionInfo())
  })
  const adapter = make(fetch)
  await expect(adapter.invoke(request())).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  await expect(adapter.invoke(request({ ...input, patch: { rates: { peak: 1, offPeak: 2 } } }))).rejects.toMatchObject({ code: 'SAVE_UNCERTAIN' })
  expect(await adapter.invoke(request())).toEqual(result)
  expect(fetch.mock.calls.filter(([, options]) => options.method === 'POST')).toHaveLength(1)
})
it('keeps lifecycle and mixed rate/profile writes unavailable and requires the reviewed version', async () => {
  const fetch = vi.fn()
  const adapter = make(fetch)
  await expect(adapter.invoke(request({ ...input, patch: { status: 'inactive' } }))).rejects.toMatchObject({ code: 'OPERATION_UNAVAILABLE' })
  await expect(adapter.invoke(request({ ...input, patch: { ...input.patch, name: 'Changed' } }))).rejects.toMatchObject({ code: 'OPERATION_UNAVAILABLE' })
  await expect(adapter.invoke(request({ ...input, expectedVersion: undefined }))).rejects.toMatchObject({ code: 'INVALID_REQUEST' })
  expect(fetch).not.toHaveBeenCalled()
})

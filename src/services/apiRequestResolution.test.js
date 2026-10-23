import { expect, it, vi } from 'vitest'
import { createApiPortalAdapter } from './apiPortalAdapter.js'
import { createPortalServices } from './portalService.js'
import { authPolicy, jsonResponse, sessionInfo } from '../test/api.js'
import { messageCommands, resolutionState } from './apiMessages.js'
import { ApiError } from './apiClient.js'
import { directoryId } from '../test/directory.js'

const input = { id: directoryId(90), expectedVersion: 1, decision: 'approved' }
const result = { id: input.id, version: 2, status: 'approved', at: '2026-10-23T05:00:00Z', by: { id: directoryId(1), name: 'Owner' } }
const session = role => async () => ({ sessionGeneration: 1, user: { id: directoryId(1), role } })
it.each(['owner', 'admin'])('%s submits a reviewed decision and validates the receipt', async role => {
  const http = { post: vi.fn().mockResolvedValue(result) }
  expect(await messageCommands(http, session(role)).resolve(input, 1)).toEqual(result)
  expect(http.post).toHaveBeenCalledWith(`/api/requests/${input.id}/resolve`, { expectedVersion: 1, decision: 'approved' }, expect.objectContaining({ csrf: true, expectedGeneration: 1 }))
})
it('Trainer cannot send a decision even if a button is forged', async () => {
  const http = { post: vi.fn() }
  await expect(messageCommands(http, session('trainer')).resolve(input, 1)).rejects.toMatchObject({ status: 403 })
  expect(http.post).not.toHaveBeenCalled()
})
it('unknown outcomes forbid a changed decision and reconcile the original without another write', async () => {
  const http = { post: vi.fn().mockRejectedValue(new ApiError('NETWORK_ERROR', 'offline')), get: vi.fn().mockResolvedValue(result) }
  const commands = messageCommands(http, session('owner'))
  await expect(commands.resolve(input, 1)).rejects.toThrow('offline')
  await expect(commands.resolve({ ...input, decision: 'rejected' }, 1)).rejects.toMatchObject({ code: 'SAVE_UNCERTAIN' })
  expect(await commands.resolve(input, 1)).toEqual(result)
  expect(http.post).toHaveBeenCalledTimes(1)
  expect(http.get.mock.calls[0][0]).toMatch(/^\/api\/request-resolutions\//)
})
it('a definitive stale rejection releases the attempt for an explicit rejection', async () => {
  const http = { post: vi.fn().mockRejectedValueOnce(new ApiError('state_conflict', 'stale', 409)).mockResolvedValue({ ...result, status: 'rejected' }) }
  const commands = messageCommands(http, session('owner'))
  await expect(commands.resolve(input, 1)).rejects.toMatchObject({ status: 409 })
  expect(await commands.resolve({ ...input, decision: 'rejected' }, 1)).toMatchObject({ status: 'rejected' })
})
it.each([{ status: 'cancelled' }, { version: 0 }, { by: { id: directoryId(1), name: '' } }, { at: 'invalid' }])('rejects unverified decision receipts %j', patch => {
  expect(() => resolutionState({ ...result, ...patch })).toThrow()
})
it('rejects an otherwise valid receipt belonging to another decision', async () => {
  const http = { post: vi.fn().mockResolvedValue({ ...result, status: 'rejected' }) }
  await expect(messageCommands(http, session('owner')).resolve(input, 1)).rejects.toMatchObject({ code: 'API_RESPONSE' })
})

it('dispatches the named portal operation through the real API adapter boundary', async () => {
  const fetch = vi.fn(async url => {
    if (url.endsWith('/auth/policy')) return jsonResponse(authPolicy)
    if (url.endsWith('/me')) return jsonResponse(sessionInfo())
    return jsonResponse(result)
  })
  const services = createPortalServices(createApiPortalAdapter({ fetchImpl: fetch }))
  expect(await services.requestService.resolve(input)).toEqual(result)
  expect(fetch.mock.calls.some(([url, options]) => url.endsWith(`/api/requests/${input.id}/resolve`) && options.method === 'POST')).toBe(true)
})

it('snapshot recovery retains the exact unconfirmed decision without automatically resubmitting it', async () => {
  const http = { post: vi.fn().mockRejectedValue(new ApiError('NETWORK_ERROR', 'offline')), get: vi.fn(async path => {
    if (path.startsWith('/api/request-resolutions/')) throw new ApiError('not_found', 'missing', 404)
    return []
  }) }
  const commands = messageCommands(http, session('owner'))
  await expect(commands.resolve(input, 1)).rejects.toThrow('offline')
  expect((await commands.read(1)).resolutionPending).toEqual(input)
  expect(http.post).toHaveBeenCalledTimes(1)
})
it('snapshot recovery clears an already committed decision using its receipt only', async () => {
  const http = { post: vi.fn().mockRejectedValue(new ApiError('NETWORK_ERROR', 'offline')), get: vi.fn(async path => path.startsWith('/api/request-resolutions/') ? result : []) }
  const commands = messageCommands(http, session('owner'))
  await expect(commands.resolve(input, 1)).rejects.toThrow('offline')
  expect((await commands.read(1)).resolutionPending).toBeNull()
  expect(http.post).toHaveBeenCalledTimes(1)
})

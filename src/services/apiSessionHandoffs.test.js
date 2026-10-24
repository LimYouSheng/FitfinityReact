import { expect, it, vi } from 'vitest'
import { sessionHandoffCommands } from './apiSessionHandoffs.js'
import { ApiError } from './apiClient.js'
import { createConfiguredPortalServices } from './defaultPortalServices.js'
import { jsonResponse, sessionInfo } from '../test/api.js'
import { directoryId as id } from '../test/directory.js'
const review = () => ({ sessionId: id(1), version: 4, expected: 'a'.repeat(64), whatsappOpenedAt: null, whatsappOpenCount: 0 })
const saved = () => ({ sessionId: id(1), version: 5, whatsappOpenedAt: '2026-10-24T10:00:00Z', whatsappOpenCount: 1 })
const actor = async () => ({ user: { role: 'owner' }, sessionGeneration: 0 })
it.each(['owner', 'admin', 'trainer'])('configured %s records a legacy opening using stored review and CSRF', async role => {
  const fetch = vi.fn(async url => jsonResponse(url.endsWith('/me') ? { ...sessionInfo(), user: { ...sessionInfo().user, role, ...(role === 'trainer' ? { trainerId: id(9) } : {}) } } : url.endsWith('handoff-review') ? review() : saved()))
  const services = createConfiguredPortalServices({ mode: 'api', fetchImpl: fetch }).forSession(0)
  expect(await services.sessionService.markWhatsAppOpened({ sessionId: id(1) })).toEqual(saved())
  const [, options] = fetch.mock.calls.find(([, value]) => value.method === 'POST')
  expect(JSON.parse(options.body)).toEqual({ expected: review().expected })
  expect(options.headers['Idempotency-Key']).toMatch(/^[0-9a-f-]{36}$/)
  expect(options.headers['X-CSRF-Token']).toBeTruthy()
})
it('recovers a lost opening without recording another or accepting another session', async () => {
  const http = { post: vi.fn(async () => { throw new ApiError('NETWORK_ERROR', 'Lost') }), get: vi.fn(async path => path.endsWith('handoff-review') ? review() : saved()) }
  const service = sessionHandoffCommands(http, actor)
  await expect(service.mark({ sessionId: id(1) }, 0)).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  await expect(service.mark({ sessionId: id(2) }, 0)).rejects.toMatchObject({ code: 'SAVE_UNCERTAIN' })
  expect(await service.mark({ sessionId: id(1) }, 0)).toEqual(saved())
  expect(http.post).toHaveBeenCalledTimes(1)
})
it('rejects foreign reviews and counter or timestamp corruption', async () => {
  let viewed = { ...review(), sessionId: id(2) }
  let result = { ...saved(), whatsappOpenCount: 2 }
  const service = sessionHandoffCommands({ get: async path => path.endsWith('handoff-review') ? viewed : result, post: async () => result }, actor)
  await expect(service.mark({ sessionId: id(1) }, 0)).rejects.toMatchObject({ code: 'API_RESPONSE' })
  viewed = review()
  await expect(service.mark({ sessionId: id(1) }, 0)).rejects.toMatchObject({ code: 'API_RESPONSE' })
  result = { ...saved(), whatsappOpenedAt: 2026 }
  await expect(service.mark({ sessionId: id(1) }, 0)).rejects.toMatchObject({ code: 'API_RESPONSE' })
})

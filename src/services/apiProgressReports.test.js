import { expect, it, vi } from 'vitest'
import { progressReportCommands } from './apiProgressReports.js'
import { ApiError } from './apiClient.js'
import { createConfiguredPortalServices } from './defaultPortalServices.js'
import { jsonResponse, sessionInfo } from '../test/api.js'
import { directoryId as id } from '../test/directory.js'
const result = () => ({ id: id(8), clientId: id(1), packageId: id(2), kind: 'pdf_export', at: '2026-10-24T08:00:00Z', by: { id: id(9), name: 'Trainer' } })
const input = () => ({ id: id(1), action: { id: `report-${id(8)}`, packageId: id(2), kind: 'pdf_export' } })
const actor = async () => ({ user: { role: 'owner' }, sessionGeneration: 0 })
it.each(['owner', 'admin', 'trainer'])('configured %s records a report without invoking a device action', async role => {
  const fetch = vi.fn(async url => jsonResponse(url.endsWith('/me') ? { ...sessionInfo(), user: { ...sessionInfo().user, role, ...(role === 'trainer' ? { trainerId: id(9) } : {}) } } : result()))
  const services = createConfiguredPortalServices({ mode: 'api', fetchImpl: fetch }).forSession(0)
  expect(await services.clientService.recordProgressReportAction(input())).toEqual({ ...result(), id: `report-${id(8)}` })
  const [, options] = fetch.mock.calls.find(([, options]) => options.method === 'POST')
  expect(options.headers['Idempotency-Key']).toBe(id(8))
  expect(JSON.parse(options.body)).toEqual({ purchaseId: id(2), kind: 'pdf_export' })
})
it('recovers one original audit after a lost response and rejects changed intent', async () => {
  const http = { post: vi.fn(async () => { throw new ApiError('NETWORK_ERROR', 'Lost') }), get: vi.fn(async () => result()) }
  const service = progressReportCommands(http, actor)
  await expect(service.record(input(), 0)).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  await expect(service.record({ ...input(), action: { ...input().action, kind: 'pdf_share_opened' } }, 0)).rejects.toMatchObject({ code: 'SAVE_UNCERTAIN' })
  expect((await service.record(input(), 0)).id).toBe(`report-${id(8)}`)
  expect(http.post).toHaveBeenCalledTimes(1)
})
it('history rejects foreign purchases, duplicate records and Trainer access', async () => {
  let rows = [{ ...result(), packageId: id(3) }]
  const service = progressReportCommands({ get: async () => rows }, actor)
  await expect(service.record({ ...input(), action: { ...input().action, id: 123 } }, 0)).rejects.toMatchObject({ code: 'INVALID_REQUEST' })
  await expect(service.history({ id: id(1), packageId: id(2) }, 0)).rejects.toMatchObject({ code: 'API_RESPONSE' })
  rows = [result(), result()]
  await expect(service.history({ id: id(1) }, 0)).rejects.toMatchObject({ code: 'API_RESPONSE' })
  const trainer = progressReportCommands({ get: vi.fn() }, async () => ({ user: { role: 'trainer' }, sessionGeneration: 0 }))
  await expect(trainer.history({ id: id(1) }, 0)).rejects.toMatchObject({ status: 403 })
})

import { expect, it, vi } from 'vitest'
import { createApiPortalAdapter } from './apiPortalAdapter.js'
import { createPortalServices } from './portalService.js'
import { directoryData, directoryId } from '../test/directory.js'
import { reactivationReview } from '../test/clientLifecycleApi.js'
import { authPolicy, failure, jsonResponse, sessionInfo } from '../test/api.js'

const reviewed = { ...reactivationReview(), packageId: directoryData().clients[0].purchases[0].id }
const input = { id: reviewed.id, options: { packageId: reviewed.packageId, reviewed, dates: {} } }
const result = { id: reviewed.id, version: reviewed.version + 1, packageId: reviewed.packageId, status: 'active' }
const reviewInput = { id: reviewed.id, packageId: reviewed.packageId, expectedVersion: reviewed.version }
function transport(handler, role = 'owner') {
  return vi.fn(async (url, options) => {
    if (url.endsWith('/auth/policy')) return jsonResponse(authPolicy)
    if (url.endsWith('/me')) { const session = sessionInfo(); session.user.role = role; return jsonResponse(session) }
    if (url.endsWith('/api/directory')) return jsonResponse({ ...directoryData(), packageReactivationWrites: true, personalMessages: true })
    if (url.endsWith('/api/messages')) return jsonResponse({ messages: [], requestCancellationWrites: false, renewalDismissalWrites: false })
    return handler(url, options)
  })
}
const servicesFor = fetch => createPortalServices(createApiPortalAdapter({ fetchImpl: fetch }))
it('routes review, date preview and save to exactly one purchase', async () => {
  const fetch = transport((url, options) => jsonResponse(url.endsWith('/reactivation') && options.method === 'POST' ? result : reviewed))
  const services = servicesFor(fetch)
  expect((await services.previewPackageReactivation(reviewInput)).reviewed).toEqual(reviewed)
  expect(await services.previewPackageReactivationDates({ id: input.id, ...input.options })).toEqual(reviewed)
  expect(await services.clientService.reactivatePackage(input)).toEqual(result)
  const attempts = fetch.mock.calls.filter(([url]) => url.includes('/api/clients/'))
  expect(attempts.every(([url]) => url.includes(`/packages/${reviewed.packageId}/`))).toBe(true)
  expect(JSON.parse(attempts.at(-1)[1].body)).toEqual({ expected: reviewed.expected, dates: {} })
})
it('retains an absent receipt and retries the identical original purchase and body', async () => {
  let first = true
  const fetch = transport((url, options) => {
    if (url.includes('/package-reactivations/')) return failure('not_found', 404)
    if (options.method === 'POST' && first) { first = false; throw new Error('offline') }
    return jsonResponse(result)
  })
  const services = servicesFor(fetch)
  await expect(services.clientService.reactivatePackage(input)).rejects.toThrow()
  expect((await services.previewPackageReactivation(reviewInput)).uncertain).toBe(true)
  await expect(services.previewPackageReactivation({ ...reviewInput, packageId: directoryId(99) })).rejects.toMatchObject({ code: 'SAVE_UNCERTAIN' })
  await expect(services.previewPackageReactivationDates({ id: input.id, ...input.options })).rejects.toMatchObject({ code: 'SAVE_UNCERTAIN' })
  expect(await services.clientService.reactivatePackage(input)).toEqual(result)
  const attempts = fetch.mock.calls.filter(([, o]) => o.method === 'POST').map(([, o]) => o)
  expect(attempts).toHaveLength(2)
  expect(attempts[0].body).toBe(attempts[1].body)
  expect(attempts[0].headers['Idempotency-Key']).toBe(attempts[1].headers['Idempotency-Key'])
})
it('reconciles a committed interrupted save without resubmission', async () => {
  const fetch = transport((url, options) => {
    if (options.method === 'POST') throw new Error('lost response')
    if (url.includes('/package-reactivations/')) return jsonResponse(result)
    return jsonResponse(reviewed)
  })
  const services = servicesFor(fetch)
  await expect(services.clientService.reactivatePackage(input)).rejects.toThrow()
  expect(await services.clientService.reactivatePackage(input)).toEqual(result)
  expect(fetch.mock.calls.filter(([, o]) => o.method === 'POST')).toHaveLength(1)
})
it.each(['other-purchase', 'foreign-row', 'two-purchases', 'malformed-rows'])('rejects misleading purchase review: %s', async kind => {
  const bad = structuredClone(reviewed)
  if (kind === 'other-purchase') bad.packageId = directoryId(99)
  if (kind === 'foreign-row') bad.rows[0].purchaseId = directoryId(99)
  if (kind === 'two-purchases') bad.purchaseIds.push(directoryId(99))
  if (kind === 'malformed-rows') bad.rows = {}
  await expect(servicesFor(transport(() => jsonResponse(bad))).previewPackageReactivation(reviewInput)).rejects.toMatchObject({ code: 'API_RESPONSE' })
})
it('rejects a mismatched purchase command and Trainer authority before POST', async () => {
  const fetch = transport(() => jsonResponse(result), 'trainer')
  await expect(servicesFor(fetch).clientService.reactivatePackage(input)).rejects.toMatchObject({ code: 'forbidden' })
  await expect(servicesFor(fetch).clientService.reactivatePackage({ ...input, options: { ...input.options, packageId: directoryId(99) } })).rejects.toMatchObject({ code: 'INVALID_REQUEST' })
  expect(fetch.mock.calls.some(([, o]) => o.method === 'POST')).toBe(false)
})
it('does not accept a receipt for another purchase as confirmed success', async () => {
  const services = servicesFor(transport(() => jsonResponse({ ...result, packageId: directoryId(99) })))
  await expect(services.clientService.reactivatePackage(input)).rejects.toMatchObject({ code: 'API_RESPONSE' })
  expect((await services.previewPackageReactivation(reviewInput)).uncertain).toBe(true)
})

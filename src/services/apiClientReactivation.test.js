import { expect, it, vi } from 'vitest'
import { createApiPortalAdapter } from './apiPortalAdapter.js'
import { createPortalServices } from './portalService.js'
import { directoryData, directoryId } from '../test/directory.js'
import { reactivationReview } from '../test/clientLifecycleApi.js'
import { authPolicy, failure, jsonResponse, sessionInfo } from '../test/api.js'

const reviewed = reactivationReview(), input = { id: reviewed.id, reviewed, dates: {} }
const result = { id: reviewed.id, version: reviewed.version + 1, status: 'active' }
function transport(handler, role = 'owner') {
  return vi.fn(async (url, options) => {
    if (url.endsWith('/auth/policy')) return jsonResponse(authPolicy)
    if (url.endsWith('/me')) { const session = sessionInfo(); session.user.role = role; return jsonResponse(session) }
    if (url.endsWith('/api/directory')) return jsonResponse({ ...directoryData(), clientReactivationWrites: true })
    return handler(url, options)
  })
}
const servicesFor = fetch => createPortalServices(createApiPortalAdapter({ fetchImpl: fetch }))

it('reviews and validates the exact proposed retained calendar through configured helpers', async () => {
  const moved = { ...reviewed, rows: reviewed.rows.map(r => ({ ...r, date: '2026-09-08' })) }
  const fetch = transport((_url, options) => jsonResponse(options.method === 'POST' ? moved : reviewed))
  const services = servicesFor(fetch)
  expect(await services.previewClientReactivation({ id: reviewed.id, expectedVersion: reviewed.version })).toEqual({ reviewed, dates: {}, uncertain: false })
  expect(await services.previewClientReactivationDates({ ...input, dates: { [reviewed.rows[0].id]: '2026-09-08' } })).toEqual(moved)
  expect(JSON.parse(fetch.mock.calls.find(([, o]) => o.method === 'POST')[1].body)).toEqual({ expected: reviewed.expected, dates: { [reviewed.rows[0].id]: '2026-09-08' } })
})
it('posts only reviewed evidence and date changes', async () => {
  const fetch = transport(() => jsonResponse(result))
  expect(await servicesFor(fetch).clientService.reactivate(input)).toEqual(result)
  expect(JSON.parse(fetch.mock.calls.find(([, o]) => o.method === 'POST')[1].body)).toEqual({ expected: reviewed.expected, dates: {} })
})
it('reconciles a committed interrupted save during refresh without another POST', async () => {
  let writes = 0
  const services = servicesFor(transport((_url, options) => { if (options.method === 'POST') { writes++; throw new Error('offline') } return jsonResponse(result) }))
  await expect(services.clientService.reactivate(input)).rejects.toThrow()
  const snapshot = await services.load()
  expect(snapshot.clientReactivationPending).toBeNull()
  expect(snapshot.capabilities.clientReactivationWrites).toBe(true)
  expect(writes).toBe(1)
})
it('retains original dates and key across a missing receipt and refuses replacement intent', async () => {
  let writes = 0
  const fetch = transport((_url, options) => { if (options.method === 'POST') { if (++writes === 1) throw new Error('offline'); return jsonResponse(result) } return failure('not_found', 404) })
  const services = servicesFor(fetch)
  await expect(services.clientService.reactivate(input)).rejects.toThrow()
  expect((await services.load()).clientReactivationPending).toEqual(input)
  expect(await services.previewClientReactivation({ id: input.id, expectedVersion: 99 })).toEqual({ reviewed, dates: {}, uncertain: true })
  await expect(services.previewClientReactivationDates(input)).rejects.toMatchObject({ code: 'SAVE_UNCERTAIN' })
  await expect(services.previewClientReactivation({ id: directoryId(99), expectedVersion: 1 })).rejects.toMatchObject({ code: 'SAVE_UNCERTAIN' })
  expect(await services.clientService.reactivate(input)).toEqual(result)
  const attempts = fetch.mock.calls.filter(([, o]) => o.method === 'POST').map(([, o]) => o)
  expect(attempts[0].body).toBe(attempts[1].body)
  expect(attempts[0].headers['Idempotency-Key']).toBe(attempts[1].headers['Idempotency-Key'])
})
it.each(['bad-date', 'changed-time', 'missing-row'])('rejects a misleading preview: %s', async mutation => {
  const bad = structuredClone(reviewed)
  if (mutation === 'bad-date') bad.rows[0].date = '2026-09-10'
  if (mutation === 'changed-time') bad.rows[0].endsAt = '12:00'
  if (mutation === 'missing-row') bad.rows = []
  await expect(servicesFor(transport(() => jsonResponse(bad))).previewClientReactivationDates(input)).rejects.toMatchObject({ code: 'API_RESPONSE' })
})
it('rejects a changed client before opening confirmation', async () => {
  await expect(servicesFor(transport(() => jsonResponse({ ...reviewed, version: 99 }))).previewClientReactivation({ id: input.id, expectedVersion: reviewed.version })).rejects.toMatchObject({ code: 'VERSION_CONFLICT' })
})
it('rejects Trainer commands and exposes no reactivation capability', async () => {
  const fetch = transport(() => jsonResponse(result), 'trainer')
  await expect(servicesFor(fetch).clientService.reactivate(input)).rejects.toMatchObject({ code: 'forbidden' })
  expect(fetch.mock.calls.some(([, o]) => o.method === 'POST')).toBe(false)
})
it('rejects unreviewed input before contacting transport', async () => {
  const fetch = vi.fn()
  await expect(servicesFor(fetch).clientService.reactivate({ id: input.id })).rejects.toMatchObject({ code: 'INVALID_REQUEST' })
  expect(fetch).not.toHaveBeenCalled()
})

const openReview = () => ({ ...reviewed, rows: reviewed.rows.map(row => ({ ...row, scheduleState: 'open', originalDate: null, date: null, startsAt: null, endsAt: null })) })
it('retains open-session identity without fabricated dates in review and save', async () => {
  const open = openReview()
  const fetch = transport((_url, options) => jsonResponse(options.method === 'POST' ? result : open))
  const services = servicesFor(fetch)
  expect((await services.previewClientReactivation({ id: open.id, expectedVersion: open.version })).reviewed).toEqual(open)
  expect(await services.clientService.reactivate({ id: open.id, reviewed: open, dates: {} })).toEqual(result)
  expect(JSON.parse(fetch.mock.calls.find(([, o]) => o.method === 'POST')[1].body).dates).toEqual({})
})
it('rejects date changes to an open session before transport', async () => {
  const fetch = vi.fn(), open = openReview()
  await expect(servicesFor(fetch).clientService.reactivate({ id: open.id, reviewed: open, dates: { [open.rows[0].id]: '2026-09-08' } })).rejects.toMatchObject({ code: 'INVALID_REQUEST' })
  expect(fetch).not.toHaveBeenCalled()
})
it.each(['invented-date', 'incomplete-booking', 'unknown-state'])('rejects malformed scheduling evidence: %s', async mutation => {
  const bad = openReview()
  if (mutation === 'invented-date') bad.rows[0].date = '2026-09-08'
  if (mutation === 'incomplete-booking') bad.rows[0].scheduleState = 'booked'
  if (mutation === 'unknown-state') bad.rows[0].scheduleState = 'unknown'
  await expect(servicesFor(transport(() => jsonResponse(bad))).previewClientReactivation({ id: bad.id, expectedVersion: bad.version })).rejects.toMatchObject({ code: 'API_RESPONSE' })
})

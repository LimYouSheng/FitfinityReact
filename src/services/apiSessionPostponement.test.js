import { expect, it, vi } from 'vitest'
import { createConfiguredPortalServices } from './defaultPortalServices.js'
import { directoryId as id } from '../test/directory.js'
import { jsonResponse, sessionInfo, failure } from '../test/api.js'
const reviewed = outcome => ({ id: id(1), version: 2, expected: 'a'.repeat(64), outcome, session: { id: id(1), version: 2, sessionNumber: 1, scheduleState: 'booked', date: '2026-10-24', startsAt: '10:00', endsAt: '11:00', trainerId: id(2), slotId: id(3) } })
const saved = outcome => ({ outcome, session: outcome === 'requested' ? reviewed(outcome).session : { ...reviewed(outcome).session, version: 3, scheduleState: 'open', date: null, startsAt: null, endsAt: null, slotId: null, sessionNumber: null }, requestId: outcome === 'requested' ? id(4) : null, messageId: id(5), changedPositions: outcome === 'requested' ? 0 : 1 })
const input = outcome => ({ sessionId: id(1), expected: 'a'.repeat(64), requestKey: id(6), reviewed: reviewed(outcome) })

it.each(['applied', 'requested'])('keeps the %s postponement outcome and original booking evidence through configured services', async outcome => {
  const fetch = vi.fn(async (url, options) => jsonResponse(url.endsWith('/me') ? sessionInfo() : options.method === 'GET' ? reviewed(outcome) : saved(outcome)))
  const services = createConfiguredPortalServices({ mode: 'api', fetchImpl: fetch }).forSession(0)
  const preview = await services.sessionService.previewPostponement({ sessionId: id(1) })
  expect(preview.outcome).toBe(outcome)
  expect(preview.changes[0].next).toEqual({ scheduleState: 'open', date: null, from: null, to: null, weeklySlotId: null })
  expect(await services.sessionService.postpone(input(outcome))).toEqual(saved(outcome))
  const write = fetch.mock.calls.find(([, options]) => options.method === 'POST')
  expect(JSON.parse(write[1].body)).toEqual({ expected: 'a'.repeat(64) })
  expect(write[1].headers['Idempotency-Key']).toBe(id(6))
})

it('reopens an uncertain postponement with the same key and reconciles without another write', async () => {
  let writes = 0
  const fetch = vi.fn(async (url, options) => {
    if (url.endsWith('/me')) return jsonResponse(sessionInfo())
    if (options.method === 'POST') { writes += 1; throw new Error('lost response') }
    return jsonResponse(saved('applied'))
  })
  const services = createConfiguredPortalServices({ mode: 'api', fetchImpl: fetch }).forSession(0)
  await expect(services.sessionService.postpone(input('applied'))).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  const preview = await services.sessionService.previewPostponement({ sessionId: id(1) })
  expect(preview).toMatchObject({ requestKey: id(6), uncertain: true, reviewed: reviewed('applied') })
  expect(await services.sessionService.postpone(input('applied'))).toEqual(saved('applied'))
  expect(writes).toBe(1)
})

it('does not claim a supervised proposal changed the booking', async () => {
  const services = createConfiguredPortalServices({ mode: 'api', fetchImpl: async url => jsonResponse(url.endsWith('/me') ? sessionInfo() : { ...saved('applied'), outcome: 'requested', requestId: id(4) }) }).forSession(0)
  await expect(services.sessionService.postpone(input('requested'))).rejects.toMatchObject({ code: 'API_RESPONSE' })
})

it('keeps definitive stale-review errors while permitting a newly reviewed request', async () => {
  const fetch = vi.fn(async (url, options) => url.endsWith('/me') ? jsonResponse(sessionInfo()) : options.method === 'POST' ? failure('state_conflict', 409) : jsonResponse(reviewed('applied')))
  const services = createConfiguredPortalServices({ mode: 'api', fetchImpl: fetch }).forSession(0)
  await expect(services.sessionService.postpone(input('applied'))).rejects.toMatchObject({ status: 409 })
  expect((await services.sessionService.previewPostponement({ sessionId: id(1) })).uncertain).toBe(false)
})

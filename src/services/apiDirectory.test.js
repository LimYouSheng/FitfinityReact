import { expect, it, vi } from 'vitest'
import { directorySnapshot } from './apiDirectory.js'
import { createApiPortalAdapter } from './apiPortalAdapter.js'
import { authPolicy, failure, jsonResponse, sessionInfo, staff } from '../test/api.js'
import { directoryData, directoryId } from '../test/directory.js'

const directoryDates = [
  ['business date', (raw, value) => { raw.businessDate = value }, result => result.businessDate],
  ['client birthday', (raw, value) => { raw.clients[0].people[0].birthday = value }, result => result.data.clients[0].people[0].birthday],
  ['trainer birthday', (raw, value) => { raw.trainers[0].birthday = value }, result => result.data.trainers[0].birthday],
  ['purchase start', (raw, value) => { raw.clients[0].purchases[0].start_date = value }, result => result.data.clients[0].package.startDate],
  ['purchase end', (raw, value) => { raw.clients[0].purchases[0].end_date = value }, result => result.data.clients[0].package.endDate],
]

it.each(directoryDates)('rejects impossible or malformed %s with the directory response error', (_label, setDate) => {
  for (const value of ['2026-02-31', '2026-04-31', '2026-02-29', '1900-02-29', '2100-02-29', '2026-13-01', '2026-00-10', '2026-01-00', '2026-01-32', '2026-2-01', '2026-02-01T00:00:00Z', ' 2026-02-01', '', null, undefined, 20260201]) {
    const raw = directoryData(); setDate(raw, value)
    expect(() => directorySnapshot(raw, staff)).toThrow(expect.objectContaining({ code: 'API_RESPONSE', message: 'The staff directory could not be verified. Please reload.' }))
  }
})

it.each(directoryDates)('preserves real calendar dates and leap days in %s', (_label, setDate, getDate) => {
  for (const value of ['2000-02-29', '2024-02-29', '2026-02-28', '2026-04-30', '2026-12-31']) {
    const raw = directoryData(); setDate(raw, value)
    expect(getDate(directorySnapshot(raw, staff))).toBe(value)
  }
})

it('preserves purchased terms, credit counts and server date independently of the changed template', () => {
  const result = directorySnapshot(directoryData(), staff)
  expect(result.data.clients[0].package).toMatchObject({ name: 'Purchased Twelve', total: 12, used: 3, templateVersion: 1, freeGym: false })
  expect(result.data.packages[0]).toMatchObject({ total: 24, version: 1, revision: 2 })
  expect(result.data.clients[0].fixedWeeklySchedule[0]).toMatchObject({ day: 'Monday', from: '10:00', to: '11:00' })
  expect(result.data.trainers[0].approvalNeeded).toEqual({ availability: true, sessionTime: true, trainerReassignment: true, fixedWeeklySchedule: true })
  expect(result.businessDate).toBe('2026-09-22')
  expect(result.data).not.toHaveProperty('sessions')
})
it('represents no current purchase explicitly while retaining queued and archived purchases', () => {
  const raw = directoryData(), original = raw.clients[0].purchases[0]
  raw.clients[0].purchases = [{ ...original, stage: 'archived' }, { ...original, id: directoryId(20), stage: 'queued', used: 0 }]
  const client = directorySnapshot(raw, staff).data.clients[0]
  expect(client.package).toBe(null)
  expect(client.fixedWeeklySchedule).toEqual([])
  expect(client.packageHistory[0].used).toBe(3)
  expect(client.additionalPackages[0].used).toBe(0)
})
it('retains both individual identities for a couple without synthesizing missing people', () => {
  const raw = directoryData()
  raw.clients[0].kind = 'couple'
  expect(() => directorySnapshot(raw, staff)).toThrow('could not be verified')
  raw.clients[0].people.push({ ...raw.clients[0].people[0], id: directoryId(21), position: 2, name: 'Second Person' })
  expect(directorySnapshot(raw, staff).data.clients[0].people.map(p => p.name)).toEqual(['API Client', 'Second Person'])
})
it('rejects mixed viewers, unsupported schema, partial records and invalid credit evidence', () => {
  for (const mutate of [raw => { raw.viewerId = directoryId(99) }, raw => { raw.schemaVersion = 2 }, raw => { delete raw.clients }, raw => { delete raw.clients[0].people[0].email }, raw => { raw.clients[0].purchases[0].used = 13 }, raw => { raw.clients.push(raw.clients[0]) }]) {
    const raw = directoryData(); mutate(raw)
    expect(() => directorySnapshot(raw, staff)).toThrow('could not be verified')
  }
})
it('enforces the returned trainer relationship and excludes other staff profiles', () => {
  const user = { ...staff, role: 'trainer', trainerId: directoryId(1) }, raw = directoryData()
  raw.packages = []
  expect(directorySnapshot(raw, user).data.clients).toHaveLength(1)
  raw.clients[0].trainer_id = directoryId(22)
  expect(() => directorySnapshot(raw, user)).toThrow('could not be verified')
})
it('reads through the real transport and rejects every unimplemented write without sending it', async () => {
  const fetchImpl = vi.fn(async url => jsonResponse(url.endsWith('/me') ? sessionInfo() : directoryData()))
  const adapter = createApiPortalAdapter({ fetchImpl })
  expect((await adapter.invoke({ service: 'clientService', operation: 'getById', input: { id: directoryId(7) } })).name).toBe('API Client')
  const count = fetchImpl.mock.calls.length
  await expect(adapter.invoke({ service: 'clientService', operation: 'update', input: { id: directoryId(7), patch: { role: 'owner' } } })).rejects.toMatchObject({ code: 'OPERATION_UNAVAILABLE' })
  expect(fetchImpl).toHaveBeenCalledTimes(count)
})
it('fails visibly on a directory outage instead of returning an empty business snapshot', async () => {
  const fetchImpl = vi.fn(async url => url.endsWith('/api/directory') ? failure('service_unavailable', 503) : jsonResponse(url.endsWith('/auth/policy') ? authPolicy : sessionInfo()))
  await expect(createApiPortalAdapter({ fetchImpl }).load()).rejects.toMatchObject({ code: 'service_unavailable' })
})

it('rejects non-boolean public visibility values at the API boundary', () => {
  for (const value of ['Visible', 'Hidden', 'true', 1, 0, null, undefined]) {
    const raw = directoryData(); raw.trainers[0].public_profile = value
    expect(() => directorySnapshot(raw, staff)).toThrow(expect.objectContaining({ code: 'API_RESPONSE' }))
  }
})

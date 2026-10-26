import { expect, it, vi } from 'vitest'
import { createApiPortalAdapter } from './apiPortalAdapter.js'
import { failure, jsonResponse, sessionInfo } from '../test/api.js'
import { directoryId } from '../test/directory.js'

const id = directoryId(7), personId = directoryId(3)
const approvals = { availability: true, sessionTime: true, trainerReassignment: false, fixedWeeklySchedule: false }
const rows = [
  ['notes', 'Notes', 'clientService', 'update', { id, reviewed: { expectedVersion: 1 }, patch: { remarks: 'Original notes' } }, { id, version: 2 }],
  ['clientDetails', 'Client Information', 'clientService', 'update', { id, reviewed: { expectedVersion: 1, people: [{ id: personId, expectedVersion: 1 }] }, patch: { people: [{ name: 'Original Person', email: '', birthday: '1990-01-01', gender: 'Other', phone: {}, emergencyContact: {} }], remarks: '', genderPreference: '' } }, { id, version: 2, people: [{ id: personId, version: 2 }] }],
  ['trainerDetails', 'Trainer Information', 'trainerService', 'update', { id, expectedVersion: 1, patch: { name: 'Original Trainer' } }, { id, version: 2 }],
  ['trainerRates', 'Trainer Rates', 'trainerService', 'update', { id, expectedVersion: 1, patch: { rates: { peak: 65.43, offPeak: 43.21 } } }, { id, version: 2 }],
  ['trainerApprovals', 'Approval Settings', 'trainerService', 'updateAutonomy', { id, expectedVersion: 1, approvalNeeded: approvals }, { id, version: 2, approvalNeeded: approvals }],
  ['packages', 'Package Setup', 'packageService', 'save', { id, expectedVersion: 1, draft: { name: 'Original Package', total: 12, status: 'active' } }, { id, version: 2, name: 'Original Package', status: 'active', revision: 2, total_sessions: 12, validity_days: 90 }],
]

for (const committed of [true, false]) it.each(rows)('%s recovery retains exact transformed intent after Cancel (committed: '+committed+')', async (kind, label, service, operation, input, saved) => {
  let first = true
  const fetch = vi.fn(async (url, options) => {
    if (options.method === 'POST') {
      if (first) { first = false; throw new Error('Interrupted transmission') }
      return jsonResponse(saved)
    }
    if (!url.includes('saves/')) return jsonResponse(sessionInfo())
    return committed ? jsonResponse(saved) : failure('not_found', 404)
  })
  const adapter = createApiPortalAdapter({ baseUrl: 'https://api.example', fetchImpl: fetch })
  await expect(adapter.invoke({ service, operation, input })).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  expect(await adapter.recoverProfileSaves({})).toEqual({ pending: [{ kind, label }], recovered: false })
  expect(fetch.mock.calls.filter(([url]) => url.includes('saves/'))).toHaveLength(0)
  const recovered = await adapter.recoverProfileSaves({ kind })
  expect(recovered).toEqual({ recovered: committed, pending: committed ? [] : [{ kind, label }] })
  expect(fetch.mock.calls.filter(([, options]) => options.method === 'POST')).toHaveLength(1)
  if (!committed) {
    expect(await adapter.resumeProfileSave({ kind })).toMatchObject({ id, version: 2 })
    const writes = fetch.mock.calls.filter(([, options]) => options.method === 'POST')
    expect(writes).toHaveLength(2)
    expect(writes[1]).toEqual(writes[0])
  }
  expect(await adapter.recoverProfileSaves({})).toEqual({ pending: [], recovered: false })
})

it('rejects unknown recovery kinds without any request', async () => {
  const fetch = vi.fn()
  const adapter = createApiPortalAdapter({ fetchImpl: fetch })
  await expect(adapter.resumeProfileSave({ kind: '__proto__' })).rejects.toMatchObject({ code: 'INVALID_REQUEST' })
  expect(fetch).not.toHaveBeenCalled()
})

it('does not expose or resume an old-login intent through a new generation', async () => {
  const fetch = vi.fn(async (_url, options) => {
    if (options.method === 'POST') throw new Error('Lost response')
    return jsonResponse(sessionInfo())
  })
  const adapter = createApiPortalAdapter({ fetchImpl: fetch })
  const [, , service, operation, input] = rows[0]
  await expect(adapter.invoke({ service, operation, input })).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  const before = fetch.mock.calls.length
  expect(await adapter.recoverProfileSaves({}, { expectedGeneration: 999 })).toEqual({ pending: [], recovered: false })
  expect(await adapter.resumeProfileSave({ kind: 'notes' }, { expectedGeneration: 999 })).toBeNull()
  expect(fetch).toHaveBeenCalledTimes(before)
})

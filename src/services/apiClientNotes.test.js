import { expect, it, vi } from 'vitest'
import { createApiPortalAdapter } from './apiPortalAdapter.js'
import { withClientNotes } from './apiClientNotes.js'
import { jsonResponse, sessionInfo, failure } from '../test/api.js'
import { directoryId } from '../test/directory.js'

const id = directoryId(7)
const input = { id, reviewed: { expectedVersion: 2 }, patch: { healthNotes: 'General limitation' } }
const result = { id, version: 3 }
const request = (value = input) => ({ service: 'clientService', operation: 'update', input: value })
const make = fetchImpl => createApiPortalAdapter({ baseUrl: 'https://api.example', fetchImpl })

it.each(['owner', 'admin', 'trainer'])('allows %s general-note requests without sending assessment fields', async role => {
  const fetch = vi.fn(async (_url, options) => jsonResponse(options.method === 'POST' ? result : { ...sessionInfo(), user: { ...sessionInfo().user, role } }))
  expect(await make(fetch).invoke(request())).toEqual(result)
  const [url, options] = fetch.mock.calls.find(([, value]) => value.method === 'POST')
  expect(url).toBe(`https://api.example/api/clients/${id}/notes`)
  expect(JSON.parse(options.body)).toEqual({ expectedVersion: 2, patch: input.patch })
})
it('reconciles an uncertain note save before retry and blocks changed drafts', async () => {
  const fetch = vi.fn(async (url, options) => {
    if (options.method === 'POST') throw new Error('Lost response')
    return jsonResponse(url.includes('client-note-saves') ? result : sessionInfo())
  })
  const adapter = make(fetch)
  await expect(adapter.invoke(request())).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  await expect(adapter.invoke(request({ ...input, patch: { healthNotes: 'Changed' } }))).rejects.toMatchObject({ code: 'SAVE_UNCERTAIN' })
  expect(await adapter.invoke(request())).toEqual(result)
  expect(fetch.mock.calls.filter(([, options]) => options.method === 'POST')).toHaveLength(1)
})
it('propagates server assignment rejection without pretending to save', async () => {
  const fetch = vi.fn(async (_url, options) => options.method === 'POST' ? failure('not_found', 404) : jsonResponse(sessionInfo()))
  await expect(make(fetch).invoke(request())).rejects.toMatchObject({ code: 'not_found' })
})
it('rejects missing review and forbidden assessment fields before any mutation', async () => {
  const fetch = vi.fn()
  const adapter = make(fetch)
  await expect(adapter.invoke(request({ ...input, reviewed: {} }))).rejects.toMatchObject({ code: 'INVALID_REQUEST' })
  await expect(adapter.invoke(request({ ...input, patch: { ...input.patch, assessments: {} } }))).rejects.toMatchObject({ code: 'OPERATION_UNAVAILABLE' })
  expect(fetch).not.toHaveBeenCalled()
})
it('requires matching client/person versions and rejects assessment data in note projections', () => {
  const client = { id, version: 2, people: [{ id: directoryId(3), version: 1 }] }
  const notes = { id, version: 2, remarks: '', healthNotes: '', people: [{ ...client.people[0], healthNotes: '' }] }
  expect(withClientNotes(client, notes)).toMatchObject({ notesAvailable: true, healthNotes: '' })
  expect(() => withClientNotes(client, { ...notes, version: 3 })).toThrow()
  expect(() => withClientNotes(client, { ...notes, people: [{ ...notes.people[0], version: 2 }] })).toThrow()
  expect(() => withClientNotes(client, { ...notes, assessments: {} })).toThrow()
})

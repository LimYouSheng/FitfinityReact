import { expect, it, vi } from 'vitest'
import { createApiPortalAdapter } from './apiPortalAdapter.js'
import { createPortalServices } from './portalService.js'
import { contentRecord } from './apiContent.js'
import { contentDraft, contentState } from '../test/contentApi.js'
import { failure, jsonResponse, sessionInfo } from '../test/api.js'

it('normalizes staff content and sends its reviewed version without caller identity', async () => {
  const fetch = vi.fn(async url => jsonResponse(url.endsWith('/me') ? sessionInfo() : contentState({ version: 2 })))
  const services = createPortalServices(createApiPortalAdapter({ fetchImpl: fetch }))
  const saved = await services.contentService.save({ id: contentState().id, expectedVersion: 1, draft: { ...contentDraft, body: ' Staff content. ' } })
  expect(saved).toMatchObject({ version: 2, createdAt: contentState().created_at, body: contentDraft.body })
  const [, options] = fetch.mock.calls.find(([, options]) => options.method === 'POST')
  expect(JSON.parse(options.body)).toEqual({ id: saved.id, expectedVersion: 1, draft: contentDraft })
})

it('reconciles an interrupted committed save on read without another POST', async () => {
  let writes = 0
  const fetch = vi.fn(async (url, options) => {
    if (url.endsWith('/me')) return jsonResponse(sessionInfo())
    if (options.method === 'POST') { writes++; throw new Error('offline') }
    return jsonResponse(url.includes('/content-saves/') ? contentState() : [contentState()])
  })
  const services = createPortalServices(createApiPortalAdapter({ fetchImpl: fetch }))
  await expect(services.contentService.save({ draft: contentDraft })).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  const result = await services.readContent()
  expect(result.entries).toHaveLength(1)
  expect(result.pending).toBeNull()
  expect(writes).toBe(1)
})

it('retains the original missing receipt and explicitly retries its identical key/body', async () => {
  let writes = 0
  const fetch = vi.fn(async (url, options) => {
    if (url.endsWith('/me')) return jsonResponse(sessionInfo())
    if (options.method === 'POST') { if (++writes === 1) throw new Error('offline'); return jsonResponse(contentState()) }
    return url.includes('/content-saves/') ? failure('not_found', 404) : jsonResponse([])
  })
  const services = createPortalServices(createApiPortalAdapter({ fetchImpl: fetch }))
  await expect(services.contentService.save({ draft: contentDraft })).rejects.toThrow()
  const { pending } = await services.readContent()
  expect(writes).toBe(1)
  await expect(services.contentService.save({ draft: { ...contentDraft, title: 'Replacement' } })).rejects.toMatchObject({ code: 'SAVE_UNCERTAIN' })
  await services.contentService.save(pending)
  const posts = fetch.mock.calls.filter(([, options]) => options.method === 'POST').map(([, options]) => options)
  expect(posts).toHaveLength(2)
  expect(posts[1].body).toBe(posts[0].body)
  expect(posts[1].headers['Idempotency-Key']).toBe(posts[0].headers['Idempotency-Key'])
})

it.each([{ version: 0 }, { body: 123 }, { status: 'published' }, { extra: 'unknown' }, { updated_at: '1900-01-01' }])('rejects malformed content records: %j', patch => {
  expect(() => contentRecord(contentState(patch))).toThrow()
})

it('rejects duplicate collection identity/key and mismatched save receipts', async () => {
  const fetch = vi.fn(async (url, options) => jsonResponse(url.endsWith('/me') ? sessionInfo() : options.method === 'POST' ? contentState({ title: 'Wrong' }) : [contentState(), contentState()]))
  const services = createPortalServices(createApiPortalAdapter({ fetchImpl: fetch }))
  await expect(services.readContent()).rejects.toMatchObject({ code: 'API_RESPONSE' })
  await expect(services.contentService.save({ draft: contentDraft })).rejects.toMatchObject({ code: 'API_RESPONSE' })
})

it('rejects Trainer reads and writes before content access', async () => {
  const fetch = vi.fn(async () => jsonResponse({ ...sessionInfo(), user: { ...sessionInfo().user, role: 'trainer', trainerId: contentState().id } }))
  const services = createPortalServices(createApiPortalAdapter({ fetchImpl: fetch }))
  await expect(services.readContent()).rejects.toMatchObject({ status: 403 })
  await expect(services.contentService.save({ draft: contentDraft })).rejects.toMatchObject({ status: 403 })
  expect(fetch.mock.calls.every(([url]) => url.endsWith('/me'))).toBe(true)
})

it('rejects a read from an old rendered login generation', async () => {
  const fetch = vi.fn(async () => jsonResponse(sessionInfo()))
  const services = createPortalServices(createApiPortalAdapter({ fetchImpl: fetch })).forSession(999)
  await expect(services.readContent()).rejects.toMatchObject({ code: 'SESSION_CHANGED' })
  expect(fetch).not.toHaveBeenCalled()
})

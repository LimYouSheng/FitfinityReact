import { webcrypto } from 'node:crypto'
import { Blob, File, Buffer } from 'node:buffer'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { ApiError } from './apiClient.js'
import { exerciseLibraryCommands } from './apiExerciseLibrary.js'
import { fileDigest, getLibraryMedia } from './apiLibraryMedia.js'
import { directoryId as id } from '../test/directory.js'
import { directoryData } from '../test/directory.js'
import { authPolicy, jsonResponse, sessionInfo } from '../test/api.js'
import { personalNotice } from '../test/messageApi.js'
import { createApiPortalAdapter } from './apiPortalAdapter.js'

beforeEach(() => { vi.stubGlobal('crypto', webcrypto); vi.stubGlobal('Blob', Blob); vi.stubGlobal('File', File) })
afterEach(() => vi.unstubAllGlobals())
const signed = `https://storage.example.test/private?X-Amz-Signature=${'a'.repeat(64)}`
const input = () => ({ draft: { name: 'Original exercise', category: 'Core', description: '', status: 'active' }, mediaFile: new File(['original'], 'reference.png', { type: 'image/png' }) })
const saved = () => ({ id: id(1), version: 1, name: 'Original exercise', category: 'Core', description: '', status: 'active', createdAt: '2026-10-24T10:00:00Z', updatedAt: '2026-10-24T10:00:00Z', media: { id: id(2), name: 'reference.png', type: 'image/png', size: 8 } })
const actor = async () => ({ user: { role: 'owner' }, sessionGeneration: 0 })

it('keeps the library and inbox together in the authenticated snapshot', async () => {
  const fetch = async url => {
    if (url.endsWith('/auth/policy')) return jsonResponse(authPolicy)
    if (url.endsWith('/me')) return jsonResponse(sessionInfo())
    if (url.endsWith('/api/directory')) return jsonResponse({ ...directoryData(), personalMessages: true, exerciseLibraryWorkflows: true })
    if (url.endsWith('/api/exercise-library')) return jsonResponse({ items: [saved()], categories: ['Core'] })
    return jsonResponse([personalNotice()])
  }
  const result = await createApiPortalAdapter({ fetchImpl: fetch }).load()
  expect(result.data.exerciseLibrary).toEqual([saved()])
  expect(result.data.messages).toEqual([personalNotice()])
  expect(result.policy.exerciseCategories).toEqual(['Core'])
  expect(result.capabilities.exerciseLibraryWorkflows).toBe(true)
})

it('recovers a lost commit without sending another file or accepting changed intent', async () => {
  let key, result = null
  const original = input(), hash = await fileDigest(original.mediaFile)
  const http = { generation: () => 0,
    get: vi.fn(async () => ({ key, state: result ? 'completed' : 'pending', result, uploadUntil: '2026-10-24T10:05:00Z' })),
    post: vi.fn(async (path, _body, options) => {
      key = options.idempotencyKey
      if (path.endsWith('/upload')) return { url: signed, headers: { 'Content-Type': 'image/png', 'If-None-Match': '*', 'x-amz-checksum-sha256': Buffer.from(hash, 'hex').toString('base64') } }
      if (path.endsWith('/commit')) { result = saved(); throw new ApiError('NETWORK_ERROR', 'Lost commit response') }
      return { key, state: 'pending', result: null, uploadUntil: '2026-10-24T10:05:00Z' }
    }) }
  const fetch = vi.fn(async () => new Response('', { status: 200 }))
  const service = exerciseLibraryCommands(http, actor, fetch)
  await expect(service.save(original, 0)).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  await expect(service.save({ ...original, draft: { ...original.draft, name: 'Changed' } }, 0)).rejects.toMatchObject({ code: 'SAVE_UNCERTAIN' })
  expect(await service.recover(0)).toEqual(saved())
  expect(fetch).toHaveBeenCalledTimes(1)
  expect(fetch.mock.calls[0][1]).toMatchObject({ credentials: 'omit', redirect: 'error', referrerPolicy: 'no-referrer' })
  expect(Object.keys(fetch.mock.calls[0][1].headers).sort()).toEqual(['Content-Type', 'If-None-Match', 'x-amz-checksum-sha256'])
  expect(http.post.mock.calls.filter(([path]) => path.endsWith('/commit'))).toHaveLength(1)
})

it('stops before sending bytes if the login changes after the upload lease', async () => {
  let generation = 0
  const original = input(), hash = await fileDigest(original.mediaFile)
  const http = { generation: () => generation, post: async path => {
    if (path.endsWith('/upload')) {
      generation++
      return { url: signed, headers: { 'Content-Type': 'image/png', 'If-None-Match': '*', 'x-amz-checksum-sha256': Buffer.from(hash, 'hex').toString('base64') } }
    }
    return {}
  } }
  const fetch = vi.fn()
  const service = exerciseLibraryCommands(http, actor, fetch)
  await expect(service.save(original, 0)).rejects.toMatchObject({ code: 'SESSION_CHANGED' })
  expect(fetch).not.toHaveBeenCalled()
})

it('denies Trainer saves before any upload or API mutation', async () => {
  const http = { generation: () => 0, post: vi.fn() }, fetch = vi.fn()
  const service = exerciseLibraryCommands(http, async () => ({ user: { role: 'trainer' }, sessionGeneration: 0 }), fetch)
  await expect(service.save(input(), 0)).rejects.toMatchObject({ status: 403 })
  expect(http.post).not.toHaveBeenCalled(); expect(fetch).not.toHaveBeenCalled()
})

it('rejects changed download bytes before offering playback', async () => {
  const file = input().mediaFile
  const http = { get: vi.fn(async () => ({ url: signed, sha256: await fileDigest(file), size: 8, type: 'image/png', version: 1 })) }
  const fetch = vi.fn(async () => new Response('tampered', { headers: { 'Content-Type': 'image/png', 'Content-Length': '8' } }))
  await expect(getLibraryMedia(http, fetch, id(2), 0, () => {})).rejects.toMatchObject({ code: 'MEDIA_RESPONSE' })
  expect(http.get).toHaveBeenCalledTimes(1)
})

it('rechecks current authority after exact bytes arrive and denies revoked playback', async () => {
  const file = input().mediaFile
  const http = { get: vi.fn(async path => {
    if (path.includes('/check?')) throw new ApiError('not_found', 'Attachment removed', 404)
    return { url: signed, sha256: await fileDigest(file), size: 8, type: 'image/png', version: 1 }
  }) }
  const fetch = vi.fn(async () => new Response('original', { headers: { 'Content-Type': 'image/png', 'Content-Length': '8' } }))
  await expect(getLibraryMedia(http, fetch, id(2), 0, () => {})).rejects.toMatchObject({ status: 404 })
  expect(http.get.mock.calls[1][0]).toContain('/check?version=1')
})

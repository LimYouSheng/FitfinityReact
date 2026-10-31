import { webcrypto } from 'node:crypto'
import { Blob, File, Buffer } from 'node:buffer'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { ApiError } from './apiClient.js'
import { sessionMediaCommands } from './apiSessionMedia.js'
import { fileDigest, getLibraryMedia } from './apiLibraryMedia.js'
import { directoryId as id } from '../test/directory.js'

beforeEach(() => { vi.stubGlobal('crypto', webcrypto); vi.stubGlobal('Blob', Blob); vi.stubGlobal('File', File) })
afterEach(() => vi.unstubAllGlobals())
const actor = async () => ({ user: { role: 'trainer' }, sessionGeneration: 0 })
const target = () => ({ sessionId: id(1), exerciseId: id(2) })
const reviewed = () => ({ ...target(), version: 3, expected: 'a'.repeat(64), media: null })
const input = () => ({ ...target(), reviewed: reviewed(), file: new File(['recording'], 'training.webm', { type: 'video/webm' }), metadata: { name: 'training.webm' } })
const saved = () => ({ ...target(), version: 4, savedAt: '2026-10-24T10:00:00Z', media: { id: id(3), name: 'training.webm', type: 'video/webm', size: 9, attachedAt: '2026-10-24T10:00:00Z', expiresAt: '2026-10-31T10:00:00Z' } })
const signed = `https://storage.example.test/private?X-Amz-Signature=${'a'.repeat(64)}`

it('rejects a stale recording review before reserving any upload', async () => {
  const http = { generation: () => 0, get: vi.fn(async () => reviewed()), post: vi.fn() }
  await expect(sessionMediaCommands(http, actor).review({ ...target(), expectedVersion: 2 }, 0)).rejects.toMatchObject({ code: 'VERSION_CONFLICT' })
  expect(http.post).not.toHaveBeenCalled()
})

it('recovers a lost recording commit without repeating the upload or write', async () => {
  let key, result = null
  const request = input(), checksum = Buffer.from(await fileDigest(request.file), 'hex').toString('base64')
  const http = { generation: () => 0,
    get: vi.fn(async () => ({ key, state: result ? 'completed' : 'pending', result, uploadUntil: '2026-10-24T10:05:00Z' })),
    post: vi.fn(async (path, _body, options) => {
      key = options.idempotencyKey
      if (path.endsWith('/upload')) return { url: signed, headers: { 'Content-Type': 'video/webm', 'If-None-Match': '*', 'x-amz-checksum-sha256': checksum } }
      if (path.endsWith('/commit')) { result = saved(); throw new ApiError('NETWORK_ERROR', 'Lost response') }
      return {}
    }) }
  const fetch = vi.fn(async () => new Response('', { status: 200 }))
  const service = sessionMediaCommands(http, actor, fetch)
  await expect(service.save(request, 0)).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  await expect(service.save({ ...request, file: new File(['different'], 'changed.webm', { type: 'video/webm' }) }, 0)).rejects.toMatchObject({ code: 'SAVE_UNCERTAIN' })
  expect(await service.recover(target(), 0)).toEqual(saved())
  expect(fetch).toHaveBeenCalledTimes(1)
  expect(http.post.mock.calls.filter(([path]) => path.endsWith('/commit'))).toHaveLength(1)
  expect(fetch.mock.calls[0][1]).toMatchObject({ credentials: 'omit', redirect: 'error', cache: 'no-store' })
})

it('keeps an uncertain removal tied to its original recording and never uploads bytes', async () => {
  let key
  const http = { generation: () => 0,
    get: vi.fn(async () => ({ key, state: 'pending', result: null, uploadUntil: '2026-10-24T10:05:00Z' })),
    post: vi.fn(async (_path, _body, options) => { key = options.idempotencyKey; throw new ApiError('NETWORK_ERROR', 'Lost request') }) }
  const fetch = vi.fn(), service = sessionMediaCommands(http, actor, fetch)
  await expect(service.save({ ...target(), reviewed: reviewed() }, 0, true)).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  await expect(service.review({ ...target(), exerciseId: id(9), expectedVersion: 3 }, 0)).rejects.toMatchObject({ code: 'SAVE_UNCERTAIN' })
  expect(await service.recover(target(), 0)).toBeNull()
  expect(http.post).toHaveBeenCalledTimes(1); expect(fetch).not.toHaveBeenCalled()
})

it('refuses oversized files before issuing an intent or uploading bytes', async () => {
  const http = { generation: () => 0, post: vi.fn() }, fetch = vi.fn()
  await expect(sessionMediaCommands(http, actor, fetch).save({ ...input(), file: new Blob([new Uint8Array(10 * 1024 * 1024 + 1)], { type: 'video/webm' }) }, 0)).rejects.toMatchObject({ code: 'INVALID_REQUEST' })
  expect(http.post).not.toHaveBeenCalled(); expect(fetch).not.toHaveBeenCalled()
})

it('allows an absent session recording without weakening library response validation', async () => {
  const http = { generation: () => 0, get: vi.fn(async () => null) }, fetch = vi.fn()
  expect(await sessionMediaCommands(http, actor, fetch).load(target(), 0)).toBeNull()
  await expect(getLibraryMedia(http, fetch, id(3), 0, () => {})).rejects.toMatchObject({ code: 'MEDIA_RESPONSE' })
  expect(fetch).not.toHaveBeenCalled()
})

it('denies playback when the server revokes scope after the verified bytes arrive', async () => {
  const file = input().file
  const http = { generation: () => 0, get: vi.fn(async path => {
    if (path.includes('/check?')) throw new ApiError('not_found', 'Unavailable', 404)
    return { url: signed, sha256: await fileDigest(file), size: file.size, type: file.type, version: 2 }
  }) }
  const fetch = vi.fn(async () => new Response('recording', { headers: { 'Content-Type': file.type, 'Content-Length': String(file.size) } }))
  await expect(sessionMediaCommands(http, actor, fetch).load(target(), 0)).rejects.toMatchObject({ status: 404 })
  expect(http.get).toHaveBeenCalledTimes(2)
})

it('normalizes MediaRecorder codec parameters while signing and retaining the exact bytes', async () => {
  const request = { ...input(), file: new File(['recording'], 'training.webm', { type: 'video/webm;codecs=vp8' }) }
  const checksum = Buffer.from(await fileDigest(request.file), 'hex').toString('base64')
  const http = { generation: () => 0, post: vi.fn(async path => {
    if (path.endsWith('/upload')) return { url: signed, headers: { 'Content-Type': 'video/webm', 'If-None-Match': '*', 'x-amz-checksum-sha256': checksum } }
    return path.endsWith('/commit') ? saved() : {}
  }) }
  const fetch = vi.fn(async () => new Response('', { status: 200 }))
  expect(await sessionMediaCommands(http, actor, fetch).save(request, 0)).toEqual(saved())
  expect(http.post.mock.calls[0][1].upload.type).toBe('video/webm')
  expect(fetch.mock.calls[0][1].body.type).toBe('video/webm')
  expect(await fetch.mock.calls[0][1].body.text()).toBe('recording')
})

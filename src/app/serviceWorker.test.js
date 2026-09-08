// @vitest-environment node
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { describe, expect, it, vi } from 'vitest'

const origin = 'https://staff.example.test'
const resourcesFor = base => [base, `${base}assets/app-build.js`, `${base}assets/app-build.css`, `${base}icons/icon-192.png`]
const prefixFor = base => `fitfinity-react-shell-${encodeURIComponent(base)}-`

function worker(base) {
  const handlers = {}
  const cache = { addAll: vi.fn().mockResolvedValue(undefined), match: vi.fn().mockResolvedValue(undefined), put: vi.fn() }
  const caches = { open: vi.fn().mockResolvedValue(cache), keys: vi.fn().mockResolvedValue([]), delete: vi.fn().mockResolvedValue(true) }
  const self = { location: { origin }, addEventListener: (name, callback) => { handlers[name] = callback }, clients: { claim: vi.fn().mockResolvedValue(undefined) }, skipWaiting: vi.fn() }
  const fetch = vi.fn().mockResolvedValue(new Response('network response'))
  const source = readFileSync(new URL('../../public/sw.js', import.meta.url), 'utf8')
    .replace("'__BASE_PATH__'", JSON.stringify(base))
    .replace('__BUILD_REVISION__', 'test-release')
    .replace('/* __PRECACHE__ */ []', JSON.stringify(resourcesFor(base)))
  class BrowserRequest extends Request {
    constructor(input, options) { super(new URL(input, origin), options) }
  }
  runInNewContext(source, { self, caches, fetch, URL, Request: BrowserRequest })
  const lifecycle = name => {
    let pending
    handlers[name]({ waitUntil: promise => { pending = promise } })
    return pending
  }
  const request = (pathname, options = {}) => {
    const event = { request: { url: new URL(pathname, origin).href, method: 'GET', mode: 'cors', headers: new Headers(), ...options }, respondWith: vi.fn() }
    handlers.fetch(event)
    return event
  }
  return { cache, caches, self, fetch, lifecycle, request }
}

describe.each(['/', '/FitfinityReact/'])('production service-worker boundaries at %s', base => {
  const resources = resourcesFor(base)
  const prefix = prefixFor(base), revision = `${prefix}test-release`
  it('prepares the entire release with fresh requests without interrupting active windows', async () => {
    const w = worker(base)
    await w.lifecycle('install')
    expect(w.caches.open).toHaveBeenCalledWith(revision)
    const requests = w.cache.addAll.mock.calls[0][0]
    expect(requests.map(item => new URL(item.url).pathname)).toEqual(resources)
    expect(requests.every(item => item.cache === 'reload')).toBe(true)
    expect(w.self.skipWaiting).not.toHaveBeenCalled()
    expect(w.self.clients.claim).not.toHaveBeenCalled()
  })

  it('rejects a failed installation without deleting or claiming the active release', async () => {
    const w = worker(base)
    w.cache.addAll.mockRejectedValue(new Error('Failed static asset'))
    await expect(w.lifecycle('install')).rejects.toThrow('Failed static asset')
    expect(w.caches.delete).not.toHaveBeenCalled()
    expect(w.self.clients.claim).not.toHaveBeenCalled()
  })

  it('cleans only older owned caches before claiming clients on activation', async () => {
    const w = worker(base)
    w.caches.keys.mockResolvedValue([revision, `${prefix}old-release`, `${prefixFor('/another-app/')}old-release`, 'fitfinity-react-shell-legacy', 'fitfinity-member-cache', 'other-app-cache'])
    await w.lifecycle('activate')
    expect(w.caches.delete.mock.calls).toEqual([[`${prefix}old-release`]])
    expect(w.self.clients.claim).toHaveBeenCalledTimes(1)
    expect(w.caches.delete.mock.invocationCallOrder[0]).toBeLessThan(w.self.clients.claim.mock.invocationCallOrder[0])
  })

  it('pins root navigation to matching cached HTML while a newer release is on the network', async () => {
    const w = worker(base)
    const current = new Response('current release')
    w.cache.match.mockResolvedValue(current)
    const event = w.request(base, { mode: 'navigate' })
    const response = await event.respondWith.mock.calls[0][0]
    expect(await response.text()).toBe('current release')
    expect(w.cache.match).toHaveBeenCalledWith(base)
    expect(w.fetch).not.toHaveBeenCalled()
  })

  it('leaves API, auth, uploaded media, external, POST, query and range requests to the network', () => {
    const w = worker(base)
    const examples = [
      [`${base}api/clients`], [`${base}auth/callback`, { mode: 'navigate' }], [`${base}private/video.mp4`],
      ['/another-app/', { mode: 'navigate' }], ['/another-app/assets/app-build.js'],
      ['https://media.example.test/video.mp4'], [`${base}assets/app-build.js`, { method: 'POST' }],
      [`${base}?code=secret`, { mode: 'navigate' }], [`${base}assets/app-build.js?token=secret`],
      [`${base}assets/app-build.js`, { headers: new Headers({ range: 'bytes=0-10' }) }],
    ]
    for (const [url, options] of examples) expect(w.request(url, options).respondWith).not.toHaveBeenCalled()
    expect(w.caches.open).not.toHaveBeenCalled()
  })

  it('serves the precached build bundle without a network dependency', async () => {
    const w = worker(base)
    w.cache.match.mockResolvedValue(new Response('offline bundle'))
    const event = w.request(`${base}assets/app-build.js`)
    expect(await (await event.respondWith.mock.calls[0][0]).text()).toBe('offline bundle')
    expect(w.fetch).not.toHaveBeenCalled()
  })

  it('falls back to the network for an evicted asset without caching an error response', async () => {
    const w = worker(base)
    w.fetch.mockResolvedValue(new Response('unavailable', { status: 503 }))
    const event = w.request(`${base}assets/app-build.js`)
    expect((await event.respondWith.mock.calls[0][0]).status).toBe(503)
    expect(w.fetch).toHaveBeenCalledWith(event.request)
    expect(w.cache.put).not.toHaveBeenCalled()
  })
})

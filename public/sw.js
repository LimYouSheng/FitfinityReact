const BASE = '__BASE_PATH__'
const CACHE_PREFIX = `fitfinity-react-shell-${encodeURIComponent(BASE)}-`
const CACHE = `${CACHE_PREFIX}__BUILD_REVISION__`
const CORE = /* __PRECACHE__ */ []

self.addEventListener('install', event => {
  // Bypass the HTTP cache so a new revision cannot precache an older index/manifest.
  event.waitUntil(caches.open(CACHE).then(cache =>
    cache.addAll(CORE.map(url => new Request(url, { cache: 'reload' })))
  ))
  // Updates wait until all existing tabs/windows close; never interrupt an open edit.
})

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys
        .filter(key => key.startsWith(CACHE_PREFIX) && key !== CACHE)
        .map(key => caches.delete(key))))
      .then(() => self.clients.claim())
  )
})

self.addEventListener('fetch', event => {
  const request = event.request
  const url = new URL(request.url)
  if (request.method !== 'GET' || url.origin !== self.location.origin) return
  if (request.headers.has('range')) return

  // Only this deployment's document and build assets belong to this worker.
  const shellNavigation = request.mode === 'navigate' && [BASE, `${BASE}index.html`].includes(url.pathname) && !url.search
  const shellAsset = !url.search && CORE.includes(url.pathname) && url.pathname !== BASE
  if (!shellNavigation && !shellAsset) return

  event.respondWith(caches.open(CACHE).then(async cache => {
    // Keep HTML and bundles on one release, even while a newer worker is waiting.
    const cached = await cache.match(shellNavigation ? BASE : request)
    return cached || fetch(request)
  }))
  // No runtime cache: API responses, credentials and uploaded media never enter this cache.
})

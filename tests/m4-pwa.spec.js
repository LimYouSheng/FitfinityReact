import { createServer } from 'node:http'
import { readFile } from 'node:fs/promises'
import { resolve, extname } from 'node:path'
import { expect, test as base } from './fixtures.js'

const prefixFor = base => `fitfinity-react-shell-${encodeURIComponent(base)}-`
const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.png': 'image/png', '.jpg': 'image/jpeg', '.webmanifest': 'application/manifest+json' }
const test = base.extend({
  mountBase: ['/', { option: true }],
  // Each test gets a separate origin so update/failure fixtures never alter the shared preview.
  release: async ({ mountBase }, use) => {
    const directory = resolve(mountBase === '/' ? 'dist' : 'dist-pages')
    const originalWorker = await readFile(resolve(directory, 'sw.js'), 'utf8')
    const revision = originalWorker.match(/CACHE_PREFIX\}([^`]+)`/)[1]
    const state = { version: 1, failIcon: false, unavailable: false }
    const server = createServer(async (request, response) => {
      // Cut the transport: no document, asset or API response can reach the browser.
      if (state.unavailable) { response.destroy(); return }
      try {
        const pathname = new URL(request.url, 'http://localhost').pathname
        if (!pathname.startsWith(mountBase)) { response.writeHead(404).end('Outside app'); return }
        const path = pathname.slice(mountBase.length)
        response.setHeader('Cache-Control', 'no-store')
        if (state.failIcon && path === 'icons/icon-192.png') {
          response.writeHead(503).end('Temporary failure')
          return
        }
        if (path === 'api/pwa-probe' || path === 'private/member-media') {
          response.setHeader('Content-Type', 'application/json')
          response.end('{"private":true}')
          return
        }
        if (path === 'sw.js') {
          response.setHeader('Content-Type', 'text/javascript')
          response.end(state.version === 1 ? originalWorker : originalWorker.replace(revision, `${revision}-next`))
          return
        }
        const file = resolve(directory, path === '' ? 'index.html' : path)
        if (!file.startsWith(`${directory}/`)) { response.writeHead(404).end(); return }
        response.setHeader('Content-Type', mime[extname(file)] ?? 'application/octet-stream')
        response.end(await readFile(file))
      } catch { response.writeHead(404).end('Not found') }
    })
    await new Promise(resolveListening => server.listen(0, '127.0.0.1', resolveListening))
    try {
      const origin = `http://127.0.0.1:${server.address().port}`
      const prefix = prefixFor(mountBase)
      await use({ origin, base: mountBase, url: `${origin}${mountBase}`, state, cache: `${prefix}${revision}`, nextCache: `${prefix}${revision}-next` })
    } finally {
      server.closeAllConnections()
      await new Promise(resolveClosed => server.close(resolveClosed))
    }
  },
})

async function controlled(page, release) {
  await page.goto(`${release.url}#/dashboard`)
  await expect(page.getByRole('heading', { name: 'Owner Dashboard', exact: true })).toBeVisible()
  await page.evaluate(async () => { await navigator.serviceWorker.ready })
  await expect.poll(() => page.evaluate(() => Boolean(navigator.serviceWorker.controller))).toBe(true)
}

async function cacheKeys(page, name) {
  return page.evaluate(async key => {
    const cache = await caches.open(key)
    const requests = await cache.keys()
    return requests.map(request => new URL(request.url).pathname).sort()
  }, name)
}

async function networkUnavailable(page, release) {
  return page.evaluate(async base => {
    try {
      await fetch(`${base}api/pwa-probe`, { cache: 'no-store' })
      return false
    } catch { return true }
  }, release.base)
}

async function disconnect(page, context, release, browserName) {
  release.state.unavailable = true
  // All projects lose access to the real origin. Chromium also exercises Playwright's
  // offline switch. The Mac WebKit run errors inside reload with that switch enabled;
  // its fresh-document/cache check uses the transport outage instead. Physical-device
  // airplane-mode acceptance remains required; this does not emulate an OS install.
  if (browserName === 'chromium') await context.setOffline(true)
  expect(await networkUnavailable(page, release)).toBe(true)
}

for (const mountBase of ['/', '/FitfinityReact/']) {
  test.describe(`PWA at ${mountBase}`, () => {
    test.use({ mountBase })

    test('M4 complete shell reopens offline and excludes private responses from cache', async ({ page, context, release, browserName }) => {
      await controlled(page, release)
      const keys = await cacheKeys(page, release.cache)
      expect(keys).toContain(release.base)
      expect(keys).toContain(`${release.base}manifest.webmanifest`)
      expect(keys).toContain(`${release.base}icons/icon-192.png`)
      expect(keys.some(path => /\/assets\/index-.*\.js$/.test(path))).toBe(true)
      expect(keys.some(path => /\/assets\/index-.*\.css$/.test(path))).toBe(true)
      const manifest = await page.evaluate(async base => (await fetch(`${base}manifest.webmanifest`)).json(), release.base)
      expect(manifest).toMatchObject({ start_url: './#/dashboard', scope: './', display: 'standalone' })
      expect(new URL(manifest.start_url, `${release.url}manifest.webmanifest`).href).toBe(`${release.url}#/dashboard`)
      expect(await page.evaluate(async () => (await navigator.serviceWorker.ready).scope)).toBe(release.url)
      const logo = page.getByRole('img', { name: 'Fitfinity', exact: true })
      await expect(logo).toHaveAttribute('src', `${release.base}assets/images/fitfinity-logo.jpg`)
      await expect.poll(() => logo.evaluate(image => image.complete && image.naturalWidth > 0)).toBe(true)
      expect(keys.every(path => path.startsWith(release.base))).toBe(true)
      await page.evaluate(async base => {
        await fetch(`${base}api/pwa-probe`)
        await fetch(`${base}private/member-media`)
        localStorage.setItem('m4-preserved-record', 'retained')
      }, release.base)
      expect(await cacheKeys(page, release.cache)).toEqual(keys)
      await disconnect(page, context, release, browserName)
      await page.close()
      const reopened = await context.newPage()
      // A new tab forces a document load, unlike changing only the current page's hash.
      // This detail route has never been visited and has no in-app history: Back uses
      // the client's list fallback, rather than returning to the earlier Dashboard.
      const navigation = await reopened.goto(`${release.url}#/clients/c1`)
      expect(navigation).not.toBeNull()
      expect(navigation.ok()).toBe(true)
      await expect(reopened.getByRole('heading', { name: 'Amanda Lim', exact: true })).toBeVisible()
      expect(await reopened.evaluate(() => Boolean(navigator.serviceWorker.controller))).toBe(true)
      expect(await networkUnavailable(reopened, release)).toBe(true)
      await expect(reopened.locator('.topbar')).toHaveCSS('position', 'sticky')
      await reopened.getByRole('button', { name: 'Back', exact: true }).click()
      await expect(reopened.getByRole('heading', { name: 'All Clients', exact: true })).toBeVisible()
      expect(await reopened.evaluate(() => localStorage.getItem('m4-preserved-record'))).toBe('retained')
      expect(await cacheKeys(reopened, release.cache)).toEqual(keys)
      await reopened.close()
    })

    test('M4 an update waits through an open edit and cleans only old shell caches after all tabs close', async ({ page, context, release }) => {
      await controlled(page, release)
      const second = await context.newPage()
      await controlled(second, release)
      await page.evaluate(async () => {
        await caches.open('unrelated-feature-cache')
        await caches.open('fitfinity-react-shell-%2Fanother-app%2F-old')
        localStorage.setItem('m4-preserved-record', 'retained')
        location.hash = '#/clients/c1'
      })
      const information = page.locator('.panel').filter({ has: page.getByRole('heading', { name: 'General Information', exact: true }) })
      await information.getByRole('button', { name: 'Edit', exact: true }).click()
      await expect(information.getByRole('button', { name: 'Save', exact: true })).toBeVisible()
      release.state.version = 2
      await page.evaluate(async () => { await (await navigator.serviceWorker.ready).update() })
      await expect.poll(() => page.evaluate(async () => Boolean((await navigator.serviceWorker.getRegistration()).waiting))).toBe(true)
      await expect(information.getByRole('button', { name: 'Save', exact: true })).toBeVisible()
      expect(await page.evaluate(() => caches.keys())).toEqual(expect.arrayContaining([release.cache, release.nextCache, 'unrelated-feature-cache']))
      await information.getByRole('button', { name: 'Cancel', exact: true }).click()
      await page.close()
      expect(await second.evaluate(async () => Boolean((await navigator.serviceWorker.getRegistration()).waiting))).toBe(true)
      await second.close()
      const reopened = await context.newPage()
      await controlled(reopened, release)
      await expect.poll(() => reopened.evaluate(() => caches.keys())).toEqual(expect.arrayContaining([release.nextCache, 'unrelated-feature-cache', 'fitfinity-react-shell-%2Fanother-app%2F-old']))
      await expect.poll(() => reopened.evaluate(() => caches.keys())).not.toContain(release.cache)
      expect(await reopened.evaluate(() => localStorage.getItem('m4-preserved-record'))).toBe('retained')
      await reopened.close()
    })

    test('M4 a failed update keeps the working release and can retry successfully', async ({ page, context, release, browserName }) => {
      await controlled(page, release)
      release.state.version = 2
      release.state.failIcon = true
      const outcome = await page.evaluate(async () => {
        const registration = await navigator.serviceWorker.ready
        const changed = new Promise(resolveState => {
          registration.addEventListener('updatefound', () => {
            const worker = registration.installing
            worker.addEventListener('statechange', () => {
              if (['redundant', 'installed'].includes(worker.state)) resolveState(worker.state)
            })
          }, { once: true })
        })
        await registration.update()
        return changed
      })
      expect(outcome).toBe('redundant')
      expect(await page.evaluate(async () => Boolean((await navigator.serviceWorker.getRegistration()).waiting))).toBe(false)
      expect(await cacheKeys(page, release.cache)).toContain(release.base)
      await disconnect(page, context, release, browserName)
      const navigation = await page.reload()
      expect(navigation).not.toBeNull()
      expect(navigation.ok()).toBe(true)
      await expect(page.getByRole('heading', { name: 'Owner Dashboard', exact: true })).toBeVisible()
      expect(await page.evaluate(() => Boolean(navigator.serviceWorker.controller))).toBe(true)
      expect(await networkUnavailable(page, release)).toBe(true)
      await expect(page.locator('.topbar')).toHaveCSS('position', 'sticky')
      release.state.failIcon = false
      release.state.unavailable = false
      if (browserName === 'chromium') await context.setOffline(false)
      expect(await networkUnavailable(page, release)).toBe(false)
      await page.evaluate(async () => { await (await navigator.serviceWorker.ready).update() })
      await expect.poll(() => page.evaluate(async () => Boolean((await navigator.serviceWorker.getRegistration()).waiting))).toBe(true)
      expect(await cacheKeys(page, release.nextCache)).toContain(`${release.base}icons/icon-192.png`)
    })

  })
}

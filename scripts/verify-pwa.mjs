import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { readFileSync, readdirSync } from 'node:fs'
import { resolve, join } from 'node:path'
import { pathToFileURL } from 'node:url'

export function verifyPwaBuild(directory, base) {
  assert.match(base, /^\/(?:[A-Za-z0-9_.-]+\/)*$/, 'Expected an absolute app directory path')
  assert.ok(!base.split('/').some(part => part === '.' || part === '..'), 'App directory cannot contain traversal segments')
  const root = resolve(directory)
  const filesIn = (folder, prefix = '') => readdirSync(folder, { withFileTypes: true }).flatMap(entry => entry.isDirectory()
    ? filesIn(join(folder, entry.name), `${prefix}${entry.name}/`) : [`${prefix}${entry.name}`])
  const files = filesIn(root).filter(file => file !== 'sw.js' && !file.endsWith('.map')).sort()
  const template = readFileSync(new URL('../public/sw.js', import.meta.url), 'utf8')
  const digest = createHash('sha256').update(base).update('\0').update(template)
  for (const file of files) digest.update(file).update('\0').update(readFileSync(join(root, file)))
  const revision = digest.digest('hex').slice(0, 20)
  const resources = files.map(file => file === 'index.html' ? base : `${base}${file}`)
  const expected = template.replace("'__BASE_PATH__'", JSON.stringify(base)).replace('__BUILD_REVISION__', revision)
    .replace('/* __PRECACHE__ */ []', JSON.stringify(resources))
  assert.equal(readFileSync(join(root, 'sw.js'), 'utf8'), expected, 'Worker revision or precache differs from the published files')

  const origin = 'https://deployment.example.test'
  const manifestURL = `${origin}${base}manifest.webmanifest`
  const manifest = JSON.parse(readFileSync(join(root, 'manifest.webmanifest'), 'utf8'))
  for (const key of ['id', 'scope']) assert.equal(new URL(manifest[key], manifestURL).href, `${origin}${base}`, `Manifest ${key} escapes the app directory`)
  assert.equal(new URL(manifest.start_url, manifestURL).href, `${origin}${base}#/dashboard`)
  assert.equal(manifest.display, 'standalone')
  const checkAsset = value => {
    const url = new URL(value, `${origin}${base}`)
    assert.equal(url.origin, origin, `Unexpected external build asset: ${value}`)
    assert.ok(url.pathname.startsWith(base), `Asset escapes app directory: ${value}`)
    assert.ok(files.includes(url.pathname.slice(base.length)), `Missing build asset: ${value}`)
  }
  for (const icon of manifest.icons) checkAsset(new URL(icon.src, manifestURL).href)
  const html = readFileSync(join(root, 'index.html'), 'utf8')
  assert.ok(!html.includes('%BASE_URL%'), 'Unexpanded HTML base URL')
  for (const [, value] of html.matchAll(/(?:src|href)="([^"]+)"/g)) checkAsset(value)
  const javascript = files.filter(file => file.endsWith('.js')).map(file => readFileSync(join(root, file), 'utf8')).join('\n')
  assert.ok(javascript.includes(`${base}sw.js`), 'Worker registration does not use the deployment directory')
  assert.ok(javascript.includes(`${base}assets/images/fitfinity-logo.jpg`), 'Logo does not use the deployment directory')
  return { base, revision, resources }
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const result = verifyPwaBuild(process.argv[2] || 'dist', process.argv[3] || '/')
  console.log(`PWA verified: ${result.base}; ${result.resources.length} resources; revision ${result.revision}`)
}

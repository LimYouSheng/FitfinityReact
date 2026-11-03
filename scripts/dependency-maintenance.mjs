import fs from 'node:fs'
import path from 'node:path'
import { pathToFileURL } from 'node:url'
import { createHash } from 'node:crypto'
import semver from 'semver'
import { parse as yaml } from 'yaml'
import { parse as toml } from 'smol-toml'

const fail = message => { throw new Error(`Dependency maintenance: ${message}`) }
const normalize = name => name.toLowerCase().replace(/[-_.]+/g, '-')
const quoted = value => `\`${value}\``
const row = values => `| ${values.join(' | ')} |`

// Parse the generated, hash-locked format; duplicate pins must not hide drift.
export function pythonLock(text) {
  const result = {}
  for (const match of text.matchAll(/^([\w.-]+)==([^\s\\]+)/gm)) {
    const name = normalize(match[1])
    if (Object.hasOwn(result, name)) fail(`duplicate Python pin: ${name}`)
    result[name] = match[2]
  }
  if (!Object.keys(result).length) fail('empty Python lock')
  return result
}

export function readDependencies(root = process.cwd()) {
  const read = name => fs.readFileSync(path.join(root, name), 'utf8')
  const workflows = Object.fromEntries(fs.readdirSync(path.join(root, '.github/workflows')).filter(name => /\.ya?ml$/.test(name)).sort().map(name => [`.github/workflows/${name}`, read(`.github/workflows/${name}`)]))
  const inputs = ['package.json', 'package-lock.json', '.nvmrc', '.github/dependabot.yml', 'backend/app/main.py', 'backend/pyproject.toml', 'backend/requirements.lock', 'backend/requirements-test.lock', 'backend/Dockerfile', 'backend/compose.yaml', 'backend/compose.browser.yaml', 'backend/infrastructure/test-foundation.json', 'scripts/prepare-browser-apt.py', ...Object.keys(workflows)]
  return {
    manifest: JSON.parse(read('package.json')), lock: JSON.parse(read('package-lock.json')),
    python: toml(read('backend/pyproject.toml')).project,
    runtime: pythonLock(read('backend/requirements.lock')), test: pythonLock(read('backend/requirements-test.lock')),
    workflows, node: read('.nvmrc').trim(), compose: yaml(read('backend/compose.yaml')),
    docker: read('backend/Dockerfile'), foundation: JSON.parse(read('backend/infrastructure/test-foundation.json')),
    browsers: JSON.parse(read('node_modules/playwright-core/browsers.json')),
    browserVersion: JSON.parse(read('node_modules/playwright-core/package.json')).version,
    document: read('docs/versions.md'), inputs: Object.fromEntries(inputs.map(name => [name, read(name)])),
  }
}

function pythonPins(declarations) {
  return declarations.map(value => {
    const match = /^([\w.-]+)(?:\[[\w,.-]+\])?==([^\s;]+)$/.exec(value)
    if (!match) fail(`Python direct dependencies must be exact reviewed pins: ${value}`)
    return [normalize(match[1]), match[2]]
  })
}

// Validate independent sources before rendering; refresh must never bless mismatches.
export function validateDependencies(state, nodeVersion = process.versions.node) {
  const { manifest, lock, python, runtime, test, workflows } = state
  if (!semver.validRange(manifest.engines?.node) || !semver.satisfies(nodeVersion, manifest.engines.node)) fail(`Node ${nodeVersion} does not satisfy ${manifest.engines?.node}`)
  if (!/^\d+$/.test(state.node) || !semver.subset(manifest.engines.node, `${state.node}.x`)) fail('Node engine range must stay within the selected .nvmrc major')
  for (const scope of ['dependencies', 'devDependencies']) {
    if (JSON.stringify(Object.entries(manifest[scope] ?? {}).sort()) !== JSON.stringify(Object.entries(lock.packages[''][scope] ?? {}).sort())) fail(`manifest/lock ${scope} mismatch`)
    for (const [name, constraint] of Object.entries(manifest[scope] ?? {})) {
      if (!semver.satisfies(lock.packages[`node_modules/${name}`]?.version ?? '', constraint)) fail(`direct npm pin mismatch: ${name}`)
    }
  }
  if (JSON.stringify(manifest.engines) !== JSON.stringify(lock.packages[''].engines)) fail('manifest/lock Node engines mismatch')
  for (const [name, entry] of Object.entries(lock.packages)) {
    if (entry.engines?.node && !semver.satisfies(nodeVersion, entry.engines.node)) fail(`Node ${nodeVersion} is incompatible with ${name}: ${entry.engines.node}`)
  }
  if (lock.packages['node_modules/react'].version !== lock.packages['node_modules/react-dom'].version) fail('React and react-dom versions differ')
  for (const [name, version] of pythonPins(python.dependencies)) if (runtime[name] !== version) fail(`Python manifest/runtime mismatch: ${name}`)
  for (const [name, version] of pythonPins(python['optional-dependencies'].test)) if (test[name] !== version) fail(`Python manifest/test mismatch: ${name}`)
  for (const [name, version] of Object.entries(runtime)) if (test[name] !== version) fail(`Python runtime/test mismatch: ${name}`)
  const actions = new Map()
  let nodeSteps = 0
  for (const [file, contents] of Object.entries(workflows)) {
    for (const job of Object.values(yaml(contents).jobs ?? {})) for (const step of job.steps ?? []) {
      if (!step.uses || step.uses.startsWith('./')) continue
      const [name, pin] = step.uses.split('@')
      if (!/^[0-9a-f]{40}$/.test(pin ?? '')) fail(`Action must use a full SHA: ${file}: ${name}`)
      if (actions.has(name) && actions.get(name) !== pin) fail(`conflicting Action pins: ${name}`)
      actions.set(name, pin)
      if (name === 'actions/setup-node') {
        nodeSteps++
        if (step.with?.['node-version-file'] !== '.nvmrc' || step.with?.['node-version'] != null) fail(`Node selection must use .nvmrc: ${file}`)
      }
    }
  }
  if (!nodeSteps) fail('missing Node workflow selection')
  const postgres = Object.values(state.compose.services).map(service => service.image).filter(value => value?.startsWith('postgres:'))
  if (!postgres.length || new Set(postgres).size !== 1) fail('Compose PostgreSQL images disagree')
  if (state.browserVersion !== lock.packages['node_modules/playwright-core'].version) fail('installed Playwright metadata does not match lock; run npm ci')
  const override = manifest.overrides?.minimatch
  if (override && (!semver.valid(override) || semver.lt(override, '11.0.1'))) fail('minimatch override must be an exact patched version')
  for (const [name, entry] of Object.entries(lock.packages).filter(([name]) => name.endsWith('node_modules/minimatch'))) {
    if (semver.lt(entry.version, '11.0.1') || (override && entry.version !== override)) fail(`minimatch override/lock drift: ${name}`)
  }
}

function replaceTable(document, header, rows) {
  const start = document.indexOf(header + '\n')
  if (start < 0) fail(`missing inventory table: ${header}`)
  const end = document.indexOf('\n\n', start)
  if (end < 0) fail(`unterminated inventory table: ${header}`)
  return document.slice(0, start) + [header, row(header.split('|').slice(1, -1).map(() => '---')), ...rows].join('\n') + document.slice(end)
}

// Preserve explanatory prose and headings; regenerate only source-owned inventory tables.
export function renderInventory(state) {
  let document = state.document
  const runtimeRow = (name, value) => {
    const prefix = `| ${name} | `
    const line = document.split('\n').find(line => line.startsWith(prefix))
    if (!line) fail(`missing runtime inventory row: ${name}`)
    document = document.replace(line, row([name, value, line.split('|').slice(3, -1).join('|').trim()]))
  }
  const base = /^FROM (python:([^\s]+)) AS application$/m.exec(state.docker)
  const adapter = /COPY --from=([^\s]+) \/lambda-adapter/.exec(state.docker)
  if (!base || !adapter) fail('review changed Docker image structure before refreshing')
  runtimeRow('Frontend application', state.manifest.version)
  runtimeRow('Backend application', state.python.version)
  const apiVersion = /version="([^"]+)"/.exec(state.inputs['backend/app/main.py'])
  if (!apiVersion) fail('review changed API version declaration before refreshing')
  runtimeRow('FastAPI application/OpenAPI metadata', apiVersion[1])
  const floors = [...state.docker.matchAll(/dpkg-query[^\n]+?' ([\w-]+)\)" ge '([^']+)'/g)]
  if (floors.length !== 2) fail('review changed Docker security floors before refreshing')
  runtimeRow('Perl/OpenSSL build floors', floors.map(match => quoted(`${match[1]} >=${match[2]}`)).join('; '))
  runtimeRow('Node.js', `${state.node} selected by .nvmrc; supported ${state.manifest.engines.node}`)
  runtimeRow('Python', `${base[2].split('-')[0]}; supported range ${state.python['requires-python']}`)
  runtimeRow('Backend base image', quoted(base[1]))
  runtimeRow('Lambda Web Adapter', quoted(adapter[1]))
  const images = Object.values(state.compose.services).map(service => service.image).filter(Boolean)
  runtimeRow('Local/test PostgreSQL', quoted(images.find(image => image.startsWith('postgres:'))))
  runtimeRow('Isolated S3-compatible test storage', quoted(images.find(image => image.startsWith('ghcr.io/rustfs/rustfs:')) ?? fail('missing test storage image')))
  runtimeRow('RDS engine configuration', `PostgreSQL ${state.foundation.Resources.Database.Properties.EngineVersion}`)
  const browsers = state.browsers.browsers
  document = document.replace(/playwright-core@[^`]+/, `playwright-core@${state.browserVersion}`)
  document = replaceTable(document, '| Engine/tool | Browser version | Playwright revision | Scope / platform override |', browsers.map(entry => {
    const scope = ['chromium', 'chromium-headless-shell', 'webkit'].includes(entry.name) ? 'CI browser engine' : entry.name === 'ffmpeg' ? 'Playwright recording helper' : 'Available in package; not selected by current CI'
    const overrides = Object.entries(entry.revisionOverrides ?? {}).map(([platform, revision]) => `${platform}: revision ${revision}`)
    return row([entry.name, entry.browserVersion ?? 'Not provided by package', entry.revision, [scope, ...overrides].join('; ')])
  }))
  const packages = Object.entries(state.lock.packages).filter(([name]) => name)
  document = replaceTable(document, '| Package | Manifest constraint | Locked version | Scope |', ['dependencies', 'devDependencies'].flatMap(scope => Object.entries(state.manifest[scope]).map(([name, constraint]) => row([quoted(name), quoted(constraint), quoted(state.lock.packages[`node_modules/${name}`].version), scope === 'dependencies' ? 'application' : 'development/build/test']))))
  document = replaceTable(document, '| Package | Locked version | Lock scope | Lock path |', packages.map(([name, entry]) => row([quoted(name.split('node_modules/').at(-1)), quoted(entry.version), [entry.dev ? 'development' : 'application', ...(entry.optional ? ['optional'] : [])].join(', '), quoted(name)])))
  document = document.replace(/\*\*\d+ locked entries\*\*, not \d+ packages/, `**${packages.length} locked entries**, not ${packages.length} packages`)
  const direct = new Set(pythonPins([...state.python.dependencies, ...state.python['optional-dependencies'].test]).map(([name]) => name))
  document = replaceTable(document, '| Distribution | Runtime lock | Test lock | Declaration |', [...new Set([...Object.keys(state.runtime), ...Object.keys(state.test)])].sort().map(name => row([quoted(name), state.runtime[name] ?? '—', state.test[name] ?? '—', direct.has(name) ? 'direct' : 'transitive'])))
  document = document.replace(/\[Runtime lock\]\(\.\.\/backend\/requirements.lock\): \*\*\d+ packages\*\*/, `[Runtime lock](../backend/requirements.lock): **${Object.keys(state.runtime).length} packages**`).replace(/\[Test lock\]\(\.\.\/backend\/requirements-test.lock\): \*\*\d+ packages\*\*/, `[Test lock](../backend/requirements-test.lock): **${Object.keys(state.test).length} packages**`)
  const actions = new Map()
  for (const [file, contents] of Object.entries(state.workflows)) for (const match of contents.matchAll(/uses:\s+([^\s@]+)@([a-f0-9]{40})(?:[^\S\n]+#([^\n]+))?/g)) {
    const key = `${match[1]}@${match[2]}`
    const entry = actions.get(key) ?? { name: match[1], pin: match[2], label: match[3]?.trim() ?? 'No tag label; use SHA', files: new Set() }
    entry.files.add(file); actions.set(key, entry)
  }
  document = replaceTable(document, '| Action | Pinned commit | Workflow label | Used in |', [...actions.values()].sort((a, b) => a.name.localeCompare(b.name)).map(entry => row([quoted(entry.name), quoted(entry.pin), entry.label, [...entry.files].map(file => `[${path.basename(file)}](../${file})`).join(', ')])))
  document = replaceTable(document, '| Input | SHA256 |', Object.entries(state.inputs).map(([file, contents]) => row([`[${file}](../${file})`, quoted(createHash('sha256').update(contents).digest('hex'))])))
  return document
}

export function verifyDependencies(root = process.cwd(), write = false) {
  const state = readDependencies(root)
  validateDependencies(state)
  const rendered = renderInventory(state)
  if (write) fs.writeFileSync(path.join(root, 'docs/versions.md'), rendered)
  else if (rendered !== state.document) fail('docs/versions.md is stale; run npm run versions:refresh and review the diff')
  return state
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  try { verifyDependencies(process.cwd(), process.argv.includes('--write')); console.log('Dependency consistency and version inventory passed.') }
  catch (error) { console.error(error.message); process.exitCode = 1 }
}

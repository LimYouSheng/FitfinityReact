import assert from 'node:assert/strict'
import { execFileSync, spawnSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import test from 'node:test'
import { verifyBackend } from './verify-backend.mjs'
import { assertPortableSourcePaths } from './verify-code-health.mjs'

const repo = process.cwd()
const files = execFileSync('git', ['ls-files', '--cached', '--others', '--exclude-standard', '-z'], { encoding: 'utf8' }).split('\0').filter(Boolean)

test('source inventory rejects the export filename collision on every filesystem', () => {
  const helper = 'src/features/sessions/sessionExport.jsx'
  assert.throws(() => assertPortableSourcePaths([helper, 'src/features/sessions/SessionExport.jsx']), /Case-insensitive source path collision/)
  assert.doesNotThrow(() => assertPortableSourcePaths([helper, 'src/features/sessions/SessionSummaryExport.jsx']))
})

test('source inventory rejects differently cased parent directories', () => {
  assert.throws(() => assertPortableSourcePaths(['src/features/sessions/a.js', 'src/Features/trainers/b.js']), /Case-insensitive source path collision/)
  assert.doesNotThrow(() => assertPortableSourcePaths(['src/features/sessions/a.js', 'src/features/trainers/b.js']))
})

function fixture(action) {
  const folder = fs.mkdtempSync(path.join(os.tmpdir(), 'fitfinity-health-'))
  try {
    for (const file of files) {
      const target = path.join(folder, file)
      fs.mkdirSync(path.dirname(target), { recursive: true })
      fs.copyFileSync(path.join(repo, file), target)
    }
    execFileSync('git', ['init', '--quiet', folder])
    fs.appendFileSync(path.join(folder, '.git/info/exclude'), '\n/node_modules\n')
    fs.symlinkSync(path.join(repo, 'node_modules'), path.join(folder, 'node_modules'), 'dir')
    return action(folder)
  } finally { fs.rmSync(folder, { recursive: true, force: true }) }
}

function run(folder) {
  return spawnSync(process.execPath, ['scripts/verify-code-health.mjs'], { cwd: folder, encoding: 'utf8', env: { ...process.env, FORCE_COLOR: '1' } })
}

test('canonical health CLI passes the current source without revision hashes', () => fixture(folder => {
  const result = run(folder)
  assert.equal(result.status, 0, result.stdout + result.stderr)
  assert.match(result.stdout, /Code health:/)
}))

const invalidCases = [
  ['syntax', 'src/invalid.js', 'export const broken = ;\n', /parse error/],
  ['missing import', 'src/invalid.js', "import { value } from './missing.js'\nexport { value }\n", /Missing relative import/],
  ['missing dynamic import', 'src/invalid.js', "export const load = () => import('./missing.js')\n", /Missing dynamic import/],
  ['unused import', 'src/invalid.js', "import React from 'react'\nexport const value = 1\n", /Unused imported name/],
  ['unreachable runtime', 'src/invalid.js', 'export const value = 1\n', /Unreachable runtime/],
  ['service UI import', 'src/services/invalid.js', "import { EditGuardProvider } from '../components/EditGuardProvider.jsx'\nexport { EditGuardProvider }\n", /UI imported by domain\/service/],
  ['disabled test', 'scripts/invalid.test.mjs', "test.skip('disabled', () => {})\n", /Disabled\/exclusive test/],
  ['exclusive test', 'scripts/invalid.test.mjs', "test.only('exclusive', () => {})\n", /Disabled\/exclusive test/],
  ['conflict marker', 'docs/invalid.md', '<<<<<<< ours\n', /Conflict marker/],
  ['trailing whitespace', 'docs/invalid.md', 'invalid \n', /Trailing whitespace/],
]

for (const [name, file, content, expected] of invalidCases) {
  test(`health CLI rejects ${name} with a nonzero exit`, () => fixture(folder => {
    fs.writeFileSync(path.join(folder, file), content)
    const result = run(folder)
    assert.equal(result.status, 1)
    assert.match(result.stderr, expected)
    assert.equal(fs.readFileSync(path.join(folder, file), 'utf8'), content)
  }))
}

for (const [name, tail, expected] of [
  ['duplicate CSS property', '.bad { color: red; color: blue; }\n', /Duplicate CSS declaration/],
  ['undefined CSS variable', '.bad { color: var(--not-defined); }\n', /Undefined CSS variable/],
]) {
  test(`health CLI rejects ${name}`, () => fixture(folder => {
    fs.appendFileSync(path.join(folder, 'src/styles.css'), tail)
    const result = run(folder)
    assert.equal(result.status, 1)
    assert.match(result.stderr, expected)
  }))
}

test('health rejects cyclic dependencies', () => fixture(folder => {
  fs.writeFileSync(path.join(folder, 'src/cycle-a.js'), "export { value } from './cycle-b.js'\n")
  fs.writeFileSync(path.join(folder, 'src/cycle-b.js'), "export { value } from './cycle-a.js'\n")
  assert.match(run(folder).stderr, /Static import cycle/)
}))

test('health rejects a second stylesheet', () => fixture(folder => {
  fs.writeFileSync(path.join(folder, 'src/override.css'), '.bad { color: red; }\n')
  const result = run(folder)
  assert.equal(result.status, 1)
  assert.match(result.stderr, /one canonical source stylesheet/)
}))

test('backend gate propagates failure and cleans only its isolated project', () => {
  const calls = []
  assert.throws(() => verifyBackend((_command, args) => {
    calls.push(args)
    return { status: args.includes('up') ? 7 : 0 }
  }), /gate failed \(exit 7\)/)
  const up = calls.find(args => args.includes('up'))
  const down = calls.find(args => args.includes('down'))
  assert.ok(up && down)
  assert.match(up[2], /^fitfinity-verify-\d+-[a-f0-9]{12}$/)
  assert.equal(down[2], up[2])
  assert.ok(down.includes('--volumes'))
})

test('backend gate fails before creating resources when Docker is unavailable', () => {
  const calls = []
  assert.throws(() => verifyBackend((_command, args) => {
    calls.push(args)
    return { status: 1 }
  }), /Start Docker Desktop/)
  assert.deepEqual(calls, [['info']])
})

test('infrastructure failure retains logs and cleans only its isolated container project', () => {
  const calls = []
  assert.throws(() => verifyBackend((_command, args) => {
    calls.push(args)
    return { status: args.includes('up') ? 9 : 0 }
  }, 'infrastructure-tests'), /gate failed \(exit 9\)/)
  const up = calls.find(args => args.includes('up'))
  assert.deepEqual(up.slice(-3), ['--exit-code-from', 'infrastructure-tests', 'infrastructure-tests'])
  assert.ok(calls.some(args => args.includes('logs')))
  const down = calls.find(args => args.includes('down'))
  assert.equal(down[2], up[2])
  assert.match(down[2], /^fitfinity-verify-\d+-[a-f0-9]{12}$/)
  assert.ok(!up.includes('db') && !up.includes('test-db'))
})

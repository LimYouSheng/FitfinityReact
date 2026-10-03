import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { verifyTestResults } from './verify-test-results.mjs'
import { test } from 'node:test'
import { ESLint } from 'eslint'
import { readQualitySetup, verifyQualitySetup } from './verify-quality.mjs'

const lint = new ESLint()
const cases = [
  ['undefined runtime variables', 'export const answer = missingValue + 1', 'no-undef', 'src/quality-fixture.js'],
  ['undefined JSX components', 'export default function Page() { return <Missing /> }', 'no-undef', 'src/quality-fixture.jsx'],
  ['unused variables despite a same-named nested binding', 'const value = 1; export function read(value) { return value }', 'no-unused-vars', 'src/quality-fixture.js'],
  ['conditional Hooks', "import { useState } from 'react'; export function Page({ active }) { if (active) useState(0); return null }", 'react-hooks/rules-of-hooks', 'src/quality-fixture.jsx'],
  ['stale effect inputs', "import { useEffect } from 'react'; export function Page({ value }) { useEffect(() => { document.title = value }, []); return null }", 'react-hooks/exhaustive-deps', 'src/quality-fixture.jsx'],
  ['stale memo inputs', "import { useMemo } from 'react'; export function useValue(value) { return useMemo(() => value.id, []) }", 'react-hooks/exhaustive-deps', 'src/quality-fixture.js'],
  ['undefined service-worker variables', 'self.addEventListener("fetch", () => missingWorkerValue())', 'no-undef', 'public/quality-fixture.js'],
]
for (const [name, source, rule, filePath] of cases) test(`semantic gate rejects ${name}`, async () => {
  const [result] = await lint.lintText(source, { filePath })
  assert.ok(result.messages.some(message => message.ruleId === rule && message.severity === 2), name)
})
test('inline comments cannot disable semantic checks', async () => {
  const [result] = await lint.lintText('/* eslint-disable no-undef */\nexport const result = missingValue', { filePath: 'src/quality-fixture.js' })
  assert.ok(result.messages.some(message => message.ruleId === 'no-undef' && message.severity === 2))
})
test('React component references, complete dependencies and Playwright fixture callbacks pass', async () => {
  for (const [filePath, source] of [
    ['src/quality-fixture.jsx', "import { useMemo } from 'react'; import Panel from './components/Panel.jsx'; export default function Page({ value }) { const title = useMemo(() => value.name, [value]); return <Panel>{title}</Panel> }"],
    ['tests/quality-fixture.js', 'export const fixture = { async context(options, use) { await use(options) } }'],
  ]) {
    const [result] = await lint.lintText(source, { filePath })
    assert.equal(result.messages.length, 0, JSON.stringify(result.messages))
  }
})
test('the actual workflows and direct tooling dependencies satisfy the complete gate contract', () => {
  verifyQualitySetup(readQualitySetup())
})
const mutations = [
  ['missing PR verification', setup => { delete setup.pages.on.pull_request }],
  ['path-filtered PR checks', setup => { setup.pages.on.pull_request.paths = ['backend/**'] }],
  ['optional shared verification', setup => { setup.pages.jobs.verify.if = 'false' }],
  ['missing semantic gate', setup => { setup.verify.jobs.frontend.steps = setup.verify.jobs.frontend.steps.filter(step => !step.run?.includes('verify:lint')) }],
  ['suppressed unit failure', setup => { setup.verify.jobs.frontend.steps.find(step => step.name === 'Unit gate')['continue-on-error'] = true }],
  ['lost pipeline failure status', setup => { const step = setup.verify.jobs.frontend.steps.find(step => step.name === 'Unit gate'); step.run = step.run.replace('set -euo pipefail', 'set -eu') }],
  ['missing backend and infrastructure verification', setup => { delete setup.verify.jobs.backend }],
  ['PR deployment', setup => { delete setup.pages.jobs.deploy.if }],
  ['deployment before verification', setup => { delete setup.pages.jobs.build.needs }],
  ['credentials in PR checks', setup => { setup.verify.jobs.frontend.permissions = { 'id-token': 'write' } }],
  ['transitive-only parser dependency', setup => { delete setup.packageJson.devDependencies.rolldown }],
  ['unlocked lint dependency', setup => { setup.lock.packages['node_modules/eslint'].version = '0.0.0' }],
  ['image publication before tests', setup => { delete setup.pages.jobs.image.needs }],
  ['image publication before activation', setup => { setup.pages.jobs.image.if = "github.event_name != 'pull_request' && github.ref == 'refs/heads/main'" }],
  ['independent image entry bypasses shared gates', setup => { setup.image.on.workflow_dispatch = null }],
  ['image job without environment protection', setup => { delete setup.image.jobs.image.environment }],
  ['image role replaced with verification role', setup => { setup.image.jobs.image.steps.find(step => step.uses?.startsWith('aws-actions/')).with['role-to-assume'] = '${{ vars.AWS_VERIFY_ROLE_ARN }}' }],
  ['image account guard removed', setup => { delete setup.image.jobs.image.steps.find(step => step.uses?.startsWith('aws-actions/')).with['allowed-account-ids'] }],
  ['suppressed image scan failure', setup => { setup.image.jobs.image.steps.find(step => step.run?.includes('image-candidate'))['continue-on-error'] = true }],
  ['image job cancels active AWS operations', setup => { setup.image.concurrency['cancel-in-progress'] = true }],
]
for (const [name, mutate] of mutations) test(`quality setup rejects ${name}`, () => {
  const setup = readQualitySetup()
  mutate(setup)
  assert.throws(() => verifyQualitySetup(setup), /Quality setup:/)
})

function receipt(kind, contents, valid) {
  const folder = fs.mkdtempSync(path.join(os.tmpdir(), 'fitfinity-receipt-'))
  try {
    const file = path.join(folder, 'test.log')
    fs.writeFileSync(file, contents)
    if (valid) verifyTestResults(kind, file)
    else assert.throws(() => verifyTestResults(kind, file))
  } finally { fs.rmSync(folder, { recursive: true, force: true }) }
}
test('complete unit and browser receipts pass exact inventory validation', () => {
  receipt('unit', 'Test Files 86 passed (86)\nTests 872 passed (872)', true)
  receipt('browser', '792 passed (1m)', true)
})
test('unit receipt rejects old totals, missing files, truncation and skipped tests', () => {
  for (const text of ['Test Files 86 passed (86)\nTests 855 passed (855)', 'Test Files 84 passed (84)\nTests 781 passed (781)', 'Test Files 86 passed (86)\nTests 854 passed (854)', 'Test Files 86 passed (86)\nTests 780 passed (780)', 'Test Files 86 passed (86)\nTests 769 passed (769)', 'Test Files 86 passed (86)\nTests 767 passed (767)', 'Test Files 86 passed (86)\nTests 758 passed (758)', 'Test Files 86 passed (86)\nTests 750 passed (750)', 'Test Files 86 passed (86)\nTests 734 passed (734)', 'Test Files 86 passed (86)\nTests 717 passed (717)', 'Test Files 86 passed (86)\nTests 691 passed (691)', 'Test Files 80 passed (80)\nTests 595 passed (595)', 'Test Files 80 passed (80)\nTests 872 passed (872)', 'Tests 872 passed (872)', 'Test Files 86 passed (86)\nTests 872 passed (872)\n1 skipped']) receipt('unit', text, false)
})
test('browser receipt rejects partial totals, retries, skipped tests and errors', () => {
  for (const text of ['789 passed', '765 passed', '788 passed', '723 passed', '717 passed', '714 passed', '711 passed', '708 passed', '696 passed', '707 passed', '792 passed\n(retry #1)', '792 passed\n1 skipped', '792 passed\nError: incomplete']) receipt('browser', text, false)
})

import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { parse } from 'yaml'
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
  ['image acceptance before full CI', setup => { delete setup.acceptance.jobs.accept.needs }],
  ['image acceptance outside main', setup => { delete setup.acceptance.jobs.accept.if }],
  ['image acceptance write credentials', setup => { delete setup.acceptance.jobs.accept.steps.find(step => step.uses?.startsWith('aws-actions/')).with['inline-session-policy'] }],
  ['suppressed image acceptance failure', setup => { setup.acceptance.jobs.accept.steps.find(step => step.run?.includes('image-accept --actions'))['continue-on-error'] = true }],
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
  receipt('unit', 'Test Files 86 passed (86)\nTests 948 passed (948)', true)
  receipt('browser', '849 passed (1m)', true)
})
test('unit receipt rejects old totals, missing files, truncation and skipped tests', () => {
  for (const text of ['Test Files 86 passed (86)\nTests 940 passed (940)', 'Test Files 86 passed (86)\nTests 913 passed (913)', 'Test Files 86 passed (86)\nTests 899 passed (899)', 'Test Files 86 passed (86)\nTests 895 passed (895)', 'Test Files 86 passed (86)\nTests 872 passed (872)', 'Test Files 86 passed (86)\nTests 855 passed (855)', 'Test Files 84 passed (84)\nTests 781 passed (781)', 'Test Files 86 passed (86)\nTests 854 passed (854)', 'Test Files 86 passed (86)\nTests 780 passed (780)', 'Test Files 86 passed (86)\nTests 769 passed (769)', 'Test Files 86 passed (86)\nTests 767 passed (767)', 'Test Files 86 passed (86)\nTests 758 passed (758)', 'Test Files 86 passed (86)\nTests 750 passed (750)', 'Test Files 86 passed (86)\nTests 734 passed (734)', 'Test Files 86 passed (86)\nTests 717 passed (717)', 'Test Files 86 passed (86)\nTests 691 passed (691)', 'Test Files 80 passed (80)\nTests 595 passed (595)', 'Test Files 80 passed (80)\nTests 948 passed (948)', 'Tests 948 passed (948)', 'Test Files 86 passed (86)\nTests 948 passed (948)\n1 skipped']) receipt('unit', text, false)
})
test('browser receipt rejects partial totals, retries, skipped tests and errors', () => {
  for (const text of ['837 passed', '819 passed', '810 passed', '804 passed', '792 passed', '789 passed', '765 passed', '788 passed', '723 passed', '717 passed', '714 passed', '711 passed', '708 passed', '696 passed', '707 passed', '849 passed\n(retry #1)', '849 passed\n1 skipped', '849 passed\nError: incomplete']) receipt('browser', text, false)
})


const runtimeWorkflow = () => parse(fs.readFileSync('.github/workflows/aws-private-runtime.yml', 'utf8'))
const runtimeSteps = () => runtimeWorkflow().jobs.runtime.steps
const runtimeStep = id => runtimeSteps().find(step => step.id === id)

test('runtime workflow keeps protected manual execution and account validation ordering', () => {
  const workflow = runtimeWorkflow(), job = workflow.jobs.runtime, steps = job.steps
  assert.deepEqual(Object.keys(workflow.on), ['workflow_dispatch'])
  assert.equal(job.needs, 'verify')
  assert.equal(job.environment, 'aws-test')
  assert.equal(job.if, "github.repository == 'LimYouSheng/FitfinityReact' && github.ref == 'refs/heads/main'")
  assert.equal(workflow.jobs.verify.uses, './.github/workflows/verify.yml')
  assert.ok(!job['continue-on-error'])
  assert.ok(steps.every(step => !step['continue-on-error']))
  const credentials = steps.find(step => step.id === 'credentials'), account = steps.find(step => step.id === 'account'), operation = steps.find(step => step.id === 'operation')
  assert.equal(credentials.uses, 'aws-actions/configure-aws-credentials@e3dd6a429d7300a6a4c196c26e071d42e0343502')
  assert.ok(!Object.hasOwn(credentials.with, 'allowed-account-ids'))
  assert.equal(credentials.with['role-to-assume'], '${{ vars.AWS_RUNTIME_ROLE_ARN }}')
  assert.equal(credentials.with['aws-region'], 'ap-southeast-1')
  assert.equal(account.env.RUNTIME_ACCOUNT, '${{ steps.credentials.outputs.aws-account-id }}')
  assert.equal(steps.indexOf(account), steps.indexOf(credentials) + 1)
  assert.equal(steps.indexOf(operation), steps.indexOf(account) + 1)
  assert.equal(operation.if, "success() && (inputs.mode == 'plan' || steps.account.outcome == 'success')")
})

for (const [account, expected] of [['', false], ['000000000000', false], ['418638389566', true]]) {
  test(`runtime account output check ${expected ? 'accepts' : 'rejects'} ${account || 'missing account'}`, () => {
    const step = runtimeStep('account')
    assert.ok(step, 'account check must exist')
    const result = spawnSync('/bin/bash', ['-e', '-u', '-o', 'pipefail', '-c', step.run], {
      env: { PATH: '', RUNTIME_ACCOUNT: account }, encoding: 'utf8',
    })
    assert.ifError(result.error)
    assert.equal(result.status === 0, expected)
    assert.equal(result.stdout, '')
  })
}

test('plan skips credential acquisition and account check; execution requires successful authentication', () => {
  const credentials = runtimeStep('credentials'), account = runtimeStep('account'), operation = runtimeStep('operation')
  assert.equal(credentials.if, "inputs.mode != 'plan'")
  assert.equal(account.if, "inputs.mode != 'plan'")
  assert.equal(operation.if, "success() && (inputs.mode == 'plan' || steps.account.outcome == 'success')")
  assert.ok(!operation.run.includes('aws '))
  assert.ok(operation.run.includes('--mode "$RUNTIME_MODE"'))
  assert.equal(operation.env.RUNTIME_MODE, '${{ inputs.mode }}')
  // The actual operator's offline-plan test separately refuses every subprocess call.
})

test('authentication failure retains only allowlisted workflow diagnostics, never recovery state', () => {
  const diagnostic = runtimeStep('diagnostic'), steps = runtimeSteps()
  assert.equal(diagnostic.if, 'always()')
  assert.deepEqual(diagnostic.env, {
    AUTH_OUTCOME: '${{ steps.credentials.outcome }}',
    ACCOUNT_OUTCOME: '${{ steps.account.outcome }}',
    OPERATION_OUTCOME: '${{ steps.operation.outcome }}',
    RUNTIME_MODE: '${{ inputs.mode }}',
  })
  const folder = fs.mkdtempSync(path.join(os.tmpdir(), 'fitfinity-workflow-diagnostic-'))
  try {
    const result = spawnSync('bash', ['-e', '-u', '-o', 'pipefail', '-c', diagnostic.run], {
      env: { ...process.env, RUNNER_TEMP: folder, AUTH_OUTCOME: 'failure', ACCOUNT_OUTCOME: 'skipped', OPERATION_OUTCOME: 'skipped', RUNTIME_MODE: 'collect', AWS_SECRET_ACCESS_KEY: 'must-not-appear', ACTIONS_ID_TOKEN_REQUEST_TOKEN: 'must-not-appear' }, encoding: 'utf8',
    })
    assert.equal(result.status, 0, result.stderr)
    assert.deepEqual(fs.readdirSync(folder), ['private-runtime-workflow-diagnostic.json'])
    const data = JSON.parse(fs.readFileSync(path.join(folder, 'private-runtime-workflow-diagnostic.json'), 'utf8'))
    assert.deepEqual(data, { kind: 'workflow-diagnostic', mode: 'collect', authentication: 'failure', account_check: 'skipped', operation: 'skipped' })
    assert.equal(result.stdout, '')
    const upload = steps.find(step => step.name === 'Preserve workflow diagnostics')
    assert.equal(upload.if, 'always()')
    assert.equal(upload.with['if-no-files-found'], 'error')
    assert.equal(upload.with.path, '${{ runner.temp }}/private-runtime-workflow-diagnostic.json')
    assert.ok(upload.with.name.startsWith('fitfinity-runtime-diagnostic-'))
    const state = steps.find(step => step.name === 'Preserve operation state and partial evidence')
    assert.equal(state.if, "always() && steps.operation.outcome != 'skipped' && steps.operation.outcome != ''")
    assert.equal(state.with['if-no-files-found'], 'error')
    assert.ok(!state.with.path.includes('diagnostic'))
  } finally { fs.rmSync(folder, { recursive: true, force: true }) }
})

import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import { verifyNeeds, verifyBrowsers, verifyBackendGroups } from './verify-ci-groups.mjs'

function browserEvidence() {
  const profiles = ['desktop-chromium', 'phone', 'tablet']
  const reports = profiles.map(id => ({
    config: { shard: null, workers: 1, projects: profiles.map(id => ({ id, retries: 0, repeatEach: 1 })) }, errors: [],
    stats: { expected: 385, unexpected: 0, flaky: 0, skipped: 0 },
    suites: [{ title: 'suite', specs: Array.from({ length: 385 }, (_, i) => ({ id: `${id}-${i}`, file: 'synthetic.spec.js', line: i + 1, column: 1, title: `case ${i}`, tests: [{ projectId: id, expectedStatus: 'passed', status: 'expected', results: [{ status: 'passed', retry: 0, errors: [] }] }] })) }],
  }))
  return { reports, inventory: structuredClone({ errors: [], suites: reports.flatMap(report => report.suites) }) }
}
const identity = { GITHUB_SHA: 'synthetic', GITHUB_RUN_ID: '1', GITHUB_RUN_ATTEMPT: '1' }
function backendEvidence() {
  const ownership = JSON.parse(readFileSync(new URL('../backend/scripts/test-groups.json', import.meta.url)))
  const files = Object.values(ownership).flat()
  const inventory = Array.from({ length: 1445 }, (_, i) => `${files[i % files.length]}::test_${i}`)
  return Object.entries(ownership).map(([group, names]) => {
    const selected = inventory.filter(id => names.includes(id.split('::')[0])).sort()
    return { identity, group, inventory, selected, exitstatus: 0, reports: selected.flatMap(id => ['setup', 'call', 'teardown'].map(phase => ({ id, phase, outcome: 'passed' }))) }
  })
}

test('CI aggregates require successful exact dependency sets including cancelled and skipped jobs', () => {
  verifyNeeds({ a: { result: 'success' } }, ['a'])
  for (const result of ['failure', 'cancelled', 'skipped', undefined]) assert.throws(() => verifyNeeds({ a: { result } }, ['a']))
  assert.throws(() => verifyNeeds({}, ['a']))
  assert.throws(() => verifyNeeds({ a: { result: 'success' }, b: { result: 'success' } }, ['a']))
})
test('browser aggregate accepts complete device coverage once', () => {
  const { reports, inventory } = browserEvidence(); verifyBrowsers(inventory, reports)
})
test('browser aggregate rejects missing duplicate foreign failed skipped and retried results', () => {
  for (const mutate of [
    r => r.pop(), r => { r[1] = r[0] }, r => { r[0].suites[0].specs[0].id = 'foreign' },
    r => r[0].suites[0].specs.pop(), r => { r[0].suites[0].specs[0].tests[0].results[0].status = 'failed' },
    r => { r[0].stats.skipped = 1 }, r => { r[0].config.projects[0].retries = 1 },
    r => { r[0].suites[0].specs[0].tests[0].results[0].retry = 1 }, r => { r[0].errors = ['runner failure'] },
    r => { r[0].config.workers = 2 },
  ]) {
    const { reports, inventory } = browserEvidence(); mutate(reports); assert.throws(() => verifyBrowsers(inventory, reports))
  }
})
test('backend aggregate accepts complete whole-file groups', () => verifyBackendGroups(backendEvidence(), identity))
test('backend aggregate rejects omitted duplicated foreign and failed execution phases', () => {
  for (const mutate of [
    r => r.pop(), r => { r[1] = r[0] }, r => { r[0].identity = { ...identity, GITHUB_SHA: 'other' } },
    r => r[0].reports.pop(), r => r[0].reports.push(r[0].reports[0]),
    r => { r[0].reports[0].outcome = 'failed' }, r => { r[0].reports[0].outcome = 'skipped' },
    r => { r[0].reports[0].id = 'foreign' }, r => { r[0].exitstatus = 1 },
    r => r[0].selected.pop(), r => r[0].inventory.pop(),
  ]) {
    const reports = backendEvidence(); mutate(reports); assert.throws(() => verifyBackendGroups(reports, identity))
  }
})

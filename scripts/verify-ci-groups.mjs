import assert from 'node:assert/strict'
import { readFileSync, readdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import { cases } from './verify-api-shards.mjs'
import { BROWSER_CASES } from './verify-test-results.mjs'

const profiles = ['desktop-chromium', 'phone', 'tablet']
const ownership = JSON.parse(readFileSync(new URL('../backend/scripts/test-groups.json', import.meta.url), 'utf8'))
const read = file => JSON.parse(readFileSync(file, 'utf8'))

/** Keep aggregate gate names while rejecting any failed or missing dependency. */
export function verifyNeeds(needs, expected) {
  assert.deepEqual(Object.keys(needs).sort(), [...expected].sort())
  for (const job of Object.values(needs)) assert.equal(job.result, 'success')
}

/** Match every discovered browser identity once; retain device and execution policy. */
export function verifyBrowsers(inventory, reports) {
  const expected = cases(inventory), seen = new Set(), projects = new Set()
  assert.equal(expected.size, BROWSER_CASES)
  assert.equal(reports.length, profiles.length)
  for (const report of reports) {
    assert.equal(report.config.shard, null)
    assert.equal(report.config.workers, 1)
    assert.deepEqual(report.config.projects.map(project => project.id), profiles)
    for (const project of report.config.projects) {
      assert.equal(project.retries, 0)
      assert.equal(project.repeatEach, 1)
    }
    const actual = cases(report)
    const selected = [...new Set([...actual.values()].map(test => test.projectId))]
    assert.equal(selected.length, 1)
    assert.ok(profiles.includes(selected[0]) && !projects.has(selected[0]))
    projects.add(selected[0])
    assert.equal(actual.size, 385)
    assert.equal(report.stats.expected, actual.size)
    for (const key of ['unexpected', 'flaky', 'skipped']) assert.equal(report.stats[key], 0)
    for (const [key, test] of actual) {
      assert.ok(expected.has(key) && !seen.has(key))
      assert.equal(test.status, 'expected')
      assert.equal(test.results.length, 1)
      const result = test.results[0]
      assert.equal(result.status, 'passed')
      assert.equal(result.retry, 0)
      assert.equal(result.errors.length, 0)
      seen.add(key)
    }
  }
  assert.equal(seen.size, expected.size)
}

/** Backend receipts include complete discovery plus every setup/call/teardown outcome. */
export function verifyBackendGroups(reports, identity) {
  assert.equal(reports.length, Object.keys(ownership).length)
  const groups = new Set(), seen = new Set(), inventories = []
  for (const report of reports) {
    assert.ok(Object.hasOwn(ownership, report.group) && !groups.has(report.group))
    groups.add(report.group)
    assert.deepEqual(report.identity, identity)
    assert.equal(report.exitstatus, 0)
    assert.equal(report.inventory.length, 1431)
    assert.equal(new Set(report.inventory).size, 1431)
    inventories.push([...report.inventory].sort())
    assert.deepEqual([...new Set(report.inventory.map(id => id.split('::')[0]))].sort(), Object.values(ownership).flat().sort())
    const expected = report.inventory.filter(id => ownership[report.group].includes(id.split('::')[0])).sort()
    assert.deepEqual(report.selected, expected)
    assert.ok(expected.length)
    const phases = new Set()
    for (const result of report.reports) {
      assert.ok(expected.includes(result.id))
      assert.ok(['setup', 'call', 'teardown'].includes(result.phase))
      assert.equal(result.outcome, 'passed')
      const key = `${result.id}/${result.phase}`
      assert.ok(!phases.has(key)); phases.add(key)
    }
    assert.equal(phases.size, expected.length * 3)
    for (const id of expected) { assert.ok(!seen.has(id)); seen.add(id) }
  }
  for (const inventory of inventories) assert.deepEqual(inventory, inventories[0])
  assert.equal(seen.size, 1431)
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const [mode, directory] = process.argv.slice(2)
  const expected = mode === 'frontend' ? ['quality', 'unit', 'browser-build', 'browser-profile'] : ['backend-checks', 'infrastructure', 'backend-group']
  verifyNeeds(JSON.parse(process.env.CI_NEEDS), expected)
  const reports = readdirSync(directory, { recursive: true }).filter(file => file.endsWith(mode === 'frontend' ? 'browser-results.json' : 'backend-group.json')).map(file => read(resolve(directory, file)))
  if (mode === 'frontend') verifyBrowsers(read(process.argv[4]), reports)
  else {
    assert.equal(mode, 'backend')
    verifyBackendGroups(reports, Object.fromEntries(['GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'].map(key => [key, process.env[key]])))
  }
  console.log(`${mode}: every required group and case passed exactly once.`)
}

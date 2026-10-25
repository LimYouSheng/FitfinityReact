import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'

const fail = message => { throw new Error(`API browser shards: ${message}`) }

/** Compare stable case identities, not just totals, across independently executed shards. */
export function cases(report) {
  if (!Array.isArray(report.errors) || report.errors.length) fail('missing or nonempty runner errors')
  const found = new Map()
  function visit(suites, parents = []) {
    if (!Array.isArray(suites)) fail('missing suite inventory')
    for (const suite of suites) {
      const titles = [...parents, suite.title]
      for (const spec of suite.specs ?? []) for (const test of spec.tests ?? []) {
        if (!spec.id || !spec.file || !spec.title || !test.projectId || test.expectedStatus !== 'passed') fail('invalid or disabled case')
        const key = JSON.stringify([test.projectId, spec.file, spec.line, spec.column, titles, spec.title, spec.id])
        if (found.has(key)) fail('duplicate case identity')
        found.set(key, test)
      }
      visit(suite.suites ?? [], titles)
    }
  }
  visit(report.suites)
  return found
}

/** Fail closed on incomplete jobs, missing shards, retries, skips and substituted cases. */
export function verifyApiShards(inventory, reports, jobResult) {
  if (jobResult !== 'success') fail('both shard jobs must succeed')
  const expected = cases(inventory)
  if (inventory.config?.shard != null || expected.size !== 303) fail('full inventory must contain exactly 303 cases')
  if (reports.length !== 2) fail('exactly two shard reports required')
  const seen = new Set(), shards = new Set()
  for (const report of reports) {
    const shard = report.config?.shard
    if (shard?.total !== 2 || ![1, 2].includes(shard.current) || shards.has(shard.current)) fail('invalid or duplicate shard')
    shards.add(shard.current)
    if (report.config.workers !== 2 || report.config.projects.some(project => project.retries !== 0 || project.repeatEach !== 1)) fail('worker/retry settings changed')
    const actual = cases(report)
    if (!actual.size || report.stats?.expected !== actual.size || ['unexpected', 'flaky', 'skipped'].some(key => report.stats?.[key] !== 0)) fail('incomplete or failed shard statistics')
    for (const [key, test] of actual) {
      if (!expected.has(key) || seen.has(key)) fail('unexpected or repeated case')
      if (test.status !== 'expected' || test.results?.length !== 1 || test.results[0].status !== 'passed' || test.results[0].retry !== 0 || test.results[0].errors?.length !== 0) fail('case did not pass once without errors')
      seen.add(key)
    }
  }
  if (seen.size !== expected.size) fail('missing cases from complete inventory')
  return seen.size
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try {
    const [inventory, ...reports] = process.argv.slice(2).map(file => JSON.parse(readFileSync(file, 'utf8')))
    const count = verifyApiShards(inventory, reports, process.env.API_BROWSER_SHARD_RESULT)
    console.log(`${count}/${count} real API browser cases passed once across both isolated shards.`)
  } catch (error) { console.error(error.message); process.exitCode = 1 }
}

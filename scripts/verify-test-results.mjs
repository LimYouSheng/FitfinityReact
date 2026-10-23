import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'

const fail = message => { throw new Error(message) }

export function verifyTestResults(kind, logPath) {
  if (!['unit', 'browser', 'api-browser'].includes(kind)) fail('Expected unit, browser or api-browser result kind.')
  const text = readFileSync(logPath, 'utf8').replace(/\u001b\[[0-?]*[ -/]*[@-~]/g, '')
  if (/(?:^|\n)\s*(?:Tests|Test Files)?\s*\d+\s+(?:failed|skipped|flaky|interrupted|did not run|todo)\b/i.test(text) || /\(retry #\d+\)/i.test(text)) fail(`${kind}: failed/skipped/flaky/interrupted tests are NOT GREEN.`)
  if (kind === 'unit') {
    const files = [...text.matchAll(/Test Files\s+(\d+) passed\s*\((\d+)\)/g)].at(-1)
    const tests = [...text.matchAll(/\bTests\s+(\d+) passed\s*\((\d+)\)/g)].at(-1)
    if (!files || !tests || files[1] !== '132' || files[2] !== '132' || tests[1] !== '1293' || tests[2] !== '1293') fail('Unit totals must be exactly 1293 passed / 1293 in 132 passed / 132 files.')
  } else {
    const expected = kind === 'api-browser' ? '120' : '1152'
    const passed = [...text.matchAll(/(?:^|\n)\s*(\d+) passed(?:\s|$)/g)].at(-1)
    if (!passed || passed[1] !== expected || /\bError:|\b(?:Timed out waiting|No tests found)\b/.test(text)) fail(`${kind} gate must finish with exactly ${expected} passed and no errors.`)
  }
  console.log(`\u001b[32m${kind === 'unit' ? '1293/1293 unit tests in 132 files' : kind === 'api-browser' ? '120/120 real API browser cases' : '1152/1152 browser cases'} confirmed.\u001b[0m`)
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try { verifyTestResults(process.argv[2], process.argv[3]) }
  catch (error) { console.error(`\u001b[31m${error.stack ?? error}\u001b[0m`); process.exitCode = 1 }
}

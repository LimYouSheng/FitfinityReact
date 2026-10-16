import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'

const fail = message => { throw new Error(message) }

export function verifyTestResults(kind, logPath) {
  if (!['unit', 'browser'].includes(kind)) fail('Expected unit or browser result kind.')
  const text = readFileSync(logPath, 'utf8').replace(/\u001b\[[0-?]*[ -/]*[@-~]/g, '')
  if (/(?:^|\n)\s*(?:Tests|Test Files)?\s*\d+\s+(?:failed|skipped|flaky|interrupted|did not run|todo)\b/i.test(text) || /\(retry #\d+\)/i.test(text)) fail(`${kind}: failed/skipped/flaky/interrupted tests are NOT GREEN.`)
  if (kind === 'unit') {
    const files = [...text.matchAll(/Test Files\s+(\d+) passed\s*\((\d+)\)/g)].at(-1)
    const tests = [...text.matchAll(/\bTests\s+(\d+) passed\s*\((\d+)\)/g)].at(-1)
    if (!files || !tests || files[1] !== '127' || files[2] !== '127' || tests[1] !== '1245' || tests[2] !== '1245') fail('Unit totals must be exactly 1245 passed / 1245 in 127 passed / 127 files.')
  } else {
    const passed = [...text.matchAll(/(?:^|\n)\s*(\d+) passed(?:\s|$)/g)].at(-1)
    if (!passed || passed[1] !== '1152' || /\bError:|\b(?:Timed out waiting|No tests found)\b/.test(text)) fail('Browser gate must finish with exactly 1152 passed and no errors.')
  }
  console.log(`\u001b[32m${kind === 'unit' ? '1245/1245 unit tests in 127 files' : '1152/1152 browser cases'} confirmed.\u001b[0m`)
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try { verifyTestResults(process.argv[2], process.argv[3]) }
  catch (error) { console.error(`\u001b[31m${error.stack ?? error}\u001b[0m`); process.exitCode = 1 }
}

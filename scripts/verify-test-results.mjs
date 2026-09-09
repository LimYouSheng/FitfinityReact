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
    if (!files || !tests || files[1] !== '59' || files[2] !== '59' || tests[1] !== '329' || tests[2] !== '329') fail('Unit totals must be exactly 329 passed / 329 in 59 passed / 59 files.')
  } else {
    const passed = [...text.matchAll(/(?:^|\n)\s*(\d+) passed(?:\s|$)/g)].at(-1)
    if (!passed || passed[1] !== '483' || /\b(?:Error:|Timed out waiting|No tests found)\b/.test(text)) fail('Browser gate must finish with exactly 483 passed and no errors.')
  }
  console.log(`${kind === 'unit' ? '329/329 unit tests in 59 files' : '483/483 browser cases'} confirmed.`)
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  verifyTestResults(process.argv[2], process.argv[3])
}

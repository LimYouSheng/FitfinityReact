import { spawnSync } from 'node:child_process'
import { randomBytes } from 'node:crypto'
import { resolve } from 'node:path'
import { writeFileSync } from 'node:fs'
import { pathToFileURL } from 'node:url'

export function verifyBackend(run = spawnSync, service = 'tests') {
  if (!['tests', 'infrastructure-tests', 'backend-checks'].includes(service)) throw new Error('Unknown verification service.')
  const options = { cwd: process.cwd(), stdio: 'inherit', env: { ...process.env, FORCE_COLOR: '1' } }
  for (const args of [['info'], ['compose', 'version']]) {
    const result = run('docker', args, options)
    if (result.error || result.status !== 0) throw new Error('Start Docker Desktop with Compose before running the backend gate.')
  }
  // Never reuse the development project: cleanup affects only this newly created verification run.
  const project = `fitfinity-verify-${process.pid}-${randomBytes(6).toString('hex')}`
  const args = ['compose', '--project-name', project, '--file', resolve('backend/compose.yaml'), '--profile', 'test']
  console.log(`Backend verification project: ${project}; development data is separate.`)
  let failure
  try {
    const result = run('docker', [...args, 'up', '--build', '--abort-on-container-exit', '--exit-code-from', service, service], options)
    if (result.error || result.status !== 0) failure = new Error(`Backend/container/PostgreSQL gate failed (exit ${result.status ?? 'unavailable'}).`)
    if (!failure && process.env.FITFINITY_BACKEND_RECEIPT) {
      const logs = run('docker', [...args, 'logs', '--no-log-prefix', service], { ...options, stdio: 'pipe', encoding: 'utf8', maxBuffer: 32 * 1024 * 1024 })
      const receipts = (logs.stdout ?? '').split('\n').filter(line => line.startsWith('FITFINITY_BACKEND_RECEIPT='))
      if (logs.error || logs.status !== 0 || receipts.length !== 1) failure = new Error('Backend group receipt could not be retained.')
      else writeFileSync(process.env.FITFINITY_BACKEND_RECEIPT, JSON.stringify(JSON.parse(receipts[0].slice('FITFINITY_BACKEND_RECEIPT='.length))))
    }
  } finally {
    // Compose up already streams the complete receipt into the caller's retained log.
    // Replay only on failure, when startup/attachment may have omitted diagnostics.
    if (failure) run('docker', [...args, 'logs', '--no-log-prefix'], options)
    const cleanup = run('docker', [...args, 'down', '--volumes', '--remove-orphans'], options)
    if (cleanup.error || cleanup.status !== 0) failure ??= new Error(`Cleanup failed for owned verification project ${project}.`)
  }
  if (failure) throw failure
  const scope = service === 'backend-checks' ? 'offline backend source and partition guards'
    : service === 'infrastructure-tests' ? 'offline infrastructure container gate'
      : process.env.FITFINITY_TEST_GROUP && process.env.FITFINITY_TEST_GROUP !== 'all' ? `isolated backend group ${process.env.FITFINITY_TEST_GROUP}; complete aggregate still required`
        : 'backend container, complete pytest receipt, isolated PostgreSQL and infrastructure gates'
  console.log(`\u001b[32mPASS — ${scope}.\u001b[0m`)
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try { verifyBackend(undefined, process.argv[2] ?? 'tests') }
  catch (error) { console.error(`\u001b[31m${error.stack ?? error}\u001b[0m`); process.exitCode = 1 }
}

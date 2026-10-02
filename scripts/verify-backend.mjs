import { spawnSync } from 'node:child_process'
import { randomBytes } from 'node:crypto'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'

export function verifyBackend(run = spawnSync, service = 'tests') {
  if (!['tests', 'infrastructure-tests'].includes(service)) throw new Error('Unknown verification service.')
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
  } finally {
    const logs = run('docker', [...args, 'logs', '--no-log-prefix'], options)
    if (logs.error || logs.status !== 0) failure ??= new Error('Could not retain backend container logs.')
    const cleanup = run('docker', [...args, 'down', '--volumes', '--remove-orphans'], options)
    if (cleanup.error || cleanup.status !== 0) failure ??= new Error(`Cleanup failed for owned verification project ${project}.`)
  }
  if (failure) throw failure
  console.log(service === 'tests' ? '\u001b[32mPASS — backend container, complete pytest receipt, isolated PostgreSQL and infrastructure gates.\u001b[0m' : '\u001b[32mPASS — offline infrastructure container gate; no network or AWS credentials.\u001b[0m')
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try { verifyBackend() }
  catch (error) { console.error(`\u001b[31m${error.stack ?? error}\u001b[0m`); process.exitCode = 1 }
}

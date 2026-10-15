import { execFileSync } from 'node:child_process'
import { randomUUID } from 'node:crypto'
import { resolve } from 'node:path'

// Every invocation owns its Compose project and ephemeral DB. Never use a deployment URL.
const root = resolve(import.meta.dirname, '..')
const project = `fitfinity-browser-${randomUUID().slice(0, 8)}`
const compose = ['compose', '-p', project, '-f', 'backend/compose.yaml', '-f', 'backend/compose.browser.yaml', '--profile', 'test', '--profile', 'browser']
const env = { ...process.env, FITFINITY_BROWSER_UID: String(process.getuid()), FITFINITY_BROWSER_GID: String(process.getgid()) }
const run = (command, args, options = {}) => execFileSync(command, args, { cwd: root, env, stdio: 'inherit', ...options })
let failure
try {
  run('docker', [...compose, 'up', '-d', '--wait', ...(process.env.FITFINITY_BROWSER_BACKEND_IMAGE ? ['--no-build'] : ['--build']), 'browser-api'])
  const args = ['playwright', 'test', '--config=playwright.api.config.js', '--reporter=list', ...process.argv.slice(2)]
  if (process.env.FITFINITY_BROWSER_RUNNER_IMAGE) {
    const container = execFileSync('docker', [...compose, 'ps', '-q', 'browser-api'], { cwd: root, encoding: 'utf8' }).trim()
    const browsers = process.env.PLAYWRIGHT_BROWSERS_PATH
    if (!browsers) throw new Error('Container runner requires the prepared PLAYWRIGHT_BROWSERS_PATH.')
    run('docker', ['run', '--rm', '--init', '--shm-size=1g', '--user', `${process.getuid()}:${process.getgid()}`,
      '--network', `container:${container}`, '--workdir', root, '-v', `${root}:${root}`,
      '-v', `${browsers}:${browsers}:ro`, '-e', `PLAYWRIGHT_BROWSERS_PATH=${browsers}`, '-e', 'CI=true', '-e', 'npm_config_cache=/tmp/fitfinity-npm-cache',
      process.env.FITFINITY_BROWSER_RUNNER_IMAGE, 'npx', ...args])
  } else run('npx', args)
} catch (error) {
  failure = error
  try { run('docker', [...compose, 'logs', '--no-color', 'browser-api']) } catch { /* Retain original failure. */ }
} finally {
  try { run('docker', [...compose, 'down', '--volumes', '--remove-orphans']) }
  catch (error) { failure ??= error }
}
if (failure) { console.error(failure.message); process.exitCode = 1 }

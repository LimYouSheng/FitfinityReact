import { execFileSync } from 'node:child_process'
import { createRequire } from 'node:module'
import { dirname, join } from 'node:path'

const require = createRequire(import.meta.url)
const cli = join(dirname(require.resolve('vite/package.json')), 'bin/vite.js')
execFileSync(process.execPath, [cli, 'build', '--base=/', '--outDir=dist-api-test'], {
  stdio: 'inherit',
  env: { ...process.env, VITE_PORTAL_MODE: 'api', VITE_API_BASE_URL: '' },
})

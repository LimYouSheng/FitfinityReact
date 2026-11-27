import { execFileSync } from 'node:child_process'
import { verifyBackend } from './verify-backend.mjs'

try {
  execFileSync(process.execPath, ['--test', '--test-isolation=none', 'backend/infrastructure/verify-workflow-inputs.mjs'], { stdio: 'inherit' })
  verifyBackend(undefined, 'infrastructure-tests')
}
catch (error) { console.error(`\u001b[31m${error.stack ?? error}\u001b[0m`); process.exitCode = 1 }

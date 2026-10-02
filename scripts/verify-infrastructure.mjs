import { verifyBackend } from './verify-backend.mjs'

try { verifyBackend(undefined, 'infrastructure-tests') }
catch (error) { console.error(`\u001b[31m${error.stack ?? error}\u001b[0m`); process.exitCode = 1 }

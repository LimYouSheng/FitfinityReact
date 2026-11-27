import fs from 'node:fs'
import { createHash } from 'node:crypto'
import { parse } from 'yaml'

/** Prove the archived dispatch contract required the field absent from the retained request. */
export function missingReviewContract(source) {
  const field = parse(source).on?.workflow_dispatch?.inputs?.review_sha256
  if (!field || field.required !== true || Object.hasOwn(field, 'default')) {
    throw new Error('Archived workflow does not prove required review input')
  }
  return createHash('sha256').update(source).digest('hex')
}

if (process.argv[1]?.endsWith('/retirement_contract.mjs')) {
  try {
    console.log(JSON.stringify({ workflow_sha256: missingReviewContract(fs.readFileSync(0, 'utf8')) }))
  }
  catch {
    console.error('Archived workflow contract could not be verified')
    process.exitCode = 1
  }
}

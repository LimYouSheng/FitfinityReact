import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { parse } from 'yaml'

const root = fileURLToPath(new URL('../../', import.meta.url))

/** Check the actual child contract without exposing input values in errors. */
export function validateInputs(workflow, values) {
  if (!/^aws-[a-z-]+\.yml$/.test(workflow)) throw new Error('Invalid workflow name')
  const document = parse(fs.readFileSync(path.join(root, '.github/workflows', workflow), 'utf8'))
  const schema = document.on?.workflow_dispatch?.inputs
  if (!schema || !values || Array.isArray(values) || typeof values !== 'object') throw new Error('Missing workflow input contract')
  for (const [name, value] of Object.entries(values)) {
    if (!Object.hasOwn(schema, name) || typeof value !== 'string') throw new Error('Unknown input or invalid input type')
  }
  for (const [name, field] of Object.entries(schema)) {
    const value = values[name] ?? field.default
    if (field.required && (value === undefined || value === '')) throw new Error(`Required input missing: ${name}`)
    if (value !== undefined && field.type === 'choice' && !field.options.includes(value)) throw new Error(`Invalid choice: ${name}`)
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try { validateInputs(process.argv[2], JSON.parse(fs.readFileSync(0, 'utf8'))) }
  catch (error) {
    const safe = /^(Required input missing|Invalid choice): [a-z][a-z0-9_]*$/.test(error.message)
    console.error(safe ? error.message : 'Child workflow input contract rejected')
    process.exitCode = 1
  }
}

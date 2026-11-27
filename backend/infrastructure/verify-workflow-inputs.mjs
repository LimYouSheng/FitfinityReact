import assert from 'node:assert/strict'
import test from 'node:test'
import fs from 'node:fs'
import { parse } from 'yaml'
import { missingReviewContract } from './retirement_contract.mjs'
import { validateInputs } from './workflow_inputs.mjs'

test('maintenance rejects the original missing hash and accepts the complete input contract', () => {
  const inputs = { target: 'developer', mode: 'backup', review_run: '123' }
  assert.throws(() => validateInputs('aws-maintenance.yml', inputs), /review_sha256/)
  validateInputs('aws-maintenance.yml', { ...inputs, review_sha256: 'a'.repeat(64) })
  assert.throws(() => validateInputs('aws-maintenance.yml', { ...inputs, review_sha256: 'a'.repeat(64), mode: 'invalid' }), /Invalid choice/)
  assert.throws(() => validateInputs('aws-maintenance.yml', { ...inputs, surprise: 'value' }), /Unknown input/)
})

test('all coordinator child workflow contracts are enforced', () => {
  const common = { target: 'developer', review_run: '123', template_sha256: 'a'.repeat(64) }
  const cases = [
    ['aws-image.yml', { target: 'developer', source_sha: 'b'.repeat(40), verification_run: '123' }],
    ['aws-release-observe.yml', { target: 'developer' }],
    ['aws-release-prepare.yml', { target: 'developer', probe_bindings: '{}' }],
    ['aws-schema-probe.yml', { ...common, mode: 'collect', operation_id: 'c'.repeat(32) }],
    ['aws-schema-upgrade.yml', { ...common, mode: 'invoke' }],
    ['aws-rollout.yml', { target: 'developer', mode: 'deploy', review_json: '{}', review_sha256: 'a'.repeat(64), producer_runs_json: '{}', verification_run: '123' }],
  ]
  for (const [workflow, inputs] of cases) {
    validateInputs(workflow, inputs)
    assert.throws(() => validateInputs(workflow, { ...inputs, unexpected: 'value' }))
  }
})


test('standalone infrastructure installs locked parser dependencies before invoking its guard', () => {
  const workflow = parse(fs.readFileSync(new URL('../../.github/workflows/infrastructure.yml', import.meta.url), 'utf8'))
  const steps = workflow.jobs.verify.steps
  const setup = steps.findIndex(step => step.uses?.startsWith('actions/setup-node@'))
  const install = steps.findIndex(step => step.run?.trim() === 'npm ci --ignore-scripts')
  const verify = steps.findIndex(step => step.run?.includes('npm run verify:infrastructure'))
  assert.ok(setup >= 0 && install > setup && verify > install, 'A clean AWS workflow must install dependencies before infrastructure verification')
  assert.equal(steps[install].if, undefined, 'Installation cannot be conditional')
  assert.equal(steps[install]['continue-on-error'], undefined, 'Installation failure must stop verification')
})


test('retirement requires a genuinely mandatory archived input without a default', () => {
  const source = 'on:\n  workflow_dispatch:\n    inputs:\n      review_sha256:\n        required: true\n'
  assert.match(missingReviewContract(source), /^[a-f0-9]{64}$/)
  assert.throws(() => missingReviewContract(source.replace('true', 'false')))
  assert.throws(() => missingReviewContract(source + '        default: old-value\n'))
  assert.throws(() => missingReviewContract('on: push'))
})

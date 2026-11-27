import assert from 'node:assert/strict'
import test from 'node:test'
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

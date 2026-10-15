import { expect, it } from 'vitest'
import { packageApiFixture } from '../../tests/package-api-fixture.js'

function fixture() {
  const state = { user: { role: 'owner' }, directory: { packages: [] } }
  const invoke = (body, key = '11111111-1111-4111-8111-111111111111', method = 'POST') => {
    let response
    packageApiFixture({ state, path: method === 'GET' ? `/api/packages/saves/${key}` : '/api/packages',
      request: { method, headers: { 'idempotency-key': key } }, body,
      json: value => { response = { status: 200, body: structuredClone(value) } },
      error: (code, status) => { response = { status, code } } })
    return response
  }
  return { state, invoke }
}
const draft = { name: 'Fixture contract', total: 18, status: 'active' }
it('HTTP fixture rejects a changed body for the same key and retains the original receipt', () => {
  const { invoke, state } = fixture()
  const saved = invoke({ draft })
  expect(saved.status).toBe(200)
  expect(invoke({ draft: { ...draft, total: 24 } })).toMatchObject({ status: 409 })
  expect(invoke(undefined, undefined, 'GET')).toEqual(saved)
  expect(state.directory.packages).toEqual([saved.body])
})
it('HTTP fixture replays semantically identical input independently of property order', () => {
  const { invoke, state } = fixture()
  const saved = invoke({ draft })
  expect(invoke({ draft: { status: 'active', total: 18, name: 'Fixture contract' } })).toEqual(saved)
  expect(state.directory.packages).toEqual([saved.body])
})

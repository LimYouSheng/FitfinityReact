import { randomUUID } from 'node:crypto'
import { contentState } from '../src/test/contentApi.js'

// Controlled browser HTTP transport. PostgreSQL tests own transaction/permission evidence.
export function contentApiFixture({ state, path, request, body, json, error }) {
  if (path !== '/api/content' && !path.startsWith('/api/content-saves/')) return false
  if (!['owner', 'admin'].includes(state.user.role)) { error('forbidden', 403); return true }
  state.contentRecords ??= []
  state.contentReceipts ??= new Map()
  if (request.method === 'GET') {
    state.contentReads = (state.contentReads ?? 0) + 1
    if (path === '/api/content') {
      if (state.contentReadFailure) error('service_unavailable', 503); else json(state.contentRecords)
    } else {
      const saved = state.contentReceipts.get(path.split('/').at(-1))
      if (saved) json(saved); else error('not_found', 404)
    }
    return true
  }
  const key = request.headers['idempotency-key']
  const receipt = state.contentReceipts.get(key)
  if (receipt) { json(receipt); return true }
  const current = state.contentRecords.find(row => row.id === body.id)
  if (!key || (body.id && current?.version !== body.expectedVersion)) { error('state_conflict', 409); return true }
  if (state.contentRecords.some(row => row.id !== body.id && row.key === body.draft.key)) { error('duplicate_key', 409); return true }
  const saved = contentState({ ...body.draft, id: body.id ?? randomUUID(), version: (current?.version ?? 0) + 1 })
  state.contentRecords = [saved, ...state.contentRecords.filter(row => row.id !== saved.id)]
  state.contentReceipts.set(key, saved)
  if (state.contentUnknown) { state.contentUnknown = false; error('service_unavailable', 503); return true }
  if (state.contentRefreshFailure) { state.contentRefreshFailure = false; state.contentReadFailure = true }
  json(saved); return true
}

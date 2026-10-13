import { randomUUID } from 'node:crypto'

// Browser HTTP fixture only. Real transaction/security coverage is in test_package_api.py.
export function packageApiFixture({ state, path, request, body, json, error }) {
  if (!path.startsWith('/api/packages')) return false
  if (!['owner', 'admin'].includes(state.user.role)) { error('forbidden', 403); return true }
  state.packageSaves ??= new Map()
  if (request.method === 'GET') {
    const saved = state.packageSaves.get(path.split('/').at(-1))
    if (saved) json(saved); else error('not_found', 404)
    return true
  }
  const key = request.headers['idempotency-key']
  if (!key) { error('validation_error', 422); return true }
  if (state.packageSaves.has(key)) { json(state.packageSaves.get(key)); return true }
  const previous = state.directory.packages.find(p => p.id === body.id)
  if (body.id && previous?.version !== body.expectedVersion) { error('state_conflict', 409); return true }
  const record = { id: body.id ?? randomUUID(), version: (previous?.version ?? 0) + 1, revision: (previous?.revision ?? 0) + 1, name: body.draft.name, total_sessions: body.draft.total, validity_days: Math.ceil(body.draft.total * 90 / 12), status: body.draft.status }
  state.directory.packages = [...state.directory.packages.filter(p => p.id !== record.id), record]
  state.packageSaves.set(key, record)
  if (state.packageUnknown) { state.packageUnknown = false; error('service_unavailable', 503); return true }
  if (state.packageRefreshFailure) { state.packageRefreshFailure = false; state.unavailable = true }
  json(record); return true
}

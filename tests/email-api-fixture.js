import { directoryId } from '../src/test/directory.js'

// Controlled HTTP transport only; real identity, reservations and transactions use PostgreSQL tests.
export function emailApiFixture({ state, path, request, body, json, error }) {
  if (!path.includes('/email-change') && !path.startsWith('/api/trainer-email-requests/')) return false
  const manager = path.startsWith('/api/')
  if (manager ? !['owner', 'admin'].includes(state.user.role) : state.user.role !== 'trainer') { error('forbidden', 403); return true }
  const change = state.emailChange
  if (request.method === 'GET') {
    if (path.startsWith('/api/trainer-email-requests/')) {
      if (change && path.endsWith(state.emailRequestKey)) json(change); else error('not_found', 404)
    } else json({ change: change?.state === 'completed' ? null : change ?? null })
    return true
  }
  if (manager) {
    if (!change) {
      const trainer = state.directory.trainers[0]
      if (body.expectedVersion !== trainer.version) { error('state_conflict', 409); return true }
      state.emailRequestKey = request.headers['idempotency-key']
      state.emailChange = { id: directoryId(90), email: body.email, state: 'requested', signedOut: false }
      if (state.emailRequestUnknown) { state.emailRequestUnknown = false; error('service_unavailable', 503); return true }
    }
    json(state.emailChange); return true
  }
  if (!change || !path.includes(change.id)) { error('not_found', 404); return true }
  if (path.endsWith('/send')) { change.state = 'pending'; json(change); return true }
  if (path.endsWith('/verify')) {
    if (body.code !== '123456') { error('INVALID_CODE', 400); return true }
    state.emailVerified = true
    if (state.emailVerifyUnknown) { state.emailVerifyUnknown = false; change.state = 'verifying'; error('service_unavailable', 503); return true }
  }
  if (state.emailVerified) {
    change.state = 'completed'; change.signedOut = true
    state.user.email = change.email
    state.directory.trainers[0].email = change.email
    state.signedIn = false
  }
  json(change); return true
}

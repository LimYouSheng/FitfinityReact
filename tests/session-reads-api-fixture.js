export function sessionReadsApiFixture({ state, path, json, error }) {
  if (path === '/api/session-calendar') { json(state.sessionCalendar ?? { viewerId: state.user.id, sessions: [], clients: [], trainers: [], purchases: [] }); return true }
  const match = /^\/api\/sessions\/([^/]+)\/(details|client)$/.exec(path)
  if (!match) return false
  if (state.sessionReadUnavailable) { error('service_unavailable', 503); return true }
  const detail = state.sessionDetails?.[match[1]]
  if (!detail) { error('not_found', 404); return true }
  if (match[2] === 'client') {
    if (['completed', 'cancelled'].includes(detail.session.status) || detail.client.status !== 'active' || detail.purchase.status !== 'active') error('not_found', 404)
    else json({ session_id: detail.session.id, client_id: detail.client.id, name: detail.client.name, kind: detail.client.kind, person_names: detail.client.kind === 'couple' ? ['Covered First', 'Covered Second'] : [detail.client.name] })
  } else json(detail)
  return true
}

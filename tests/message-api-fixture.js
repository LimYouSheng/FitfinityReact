import { personalNotice } from '../src/test/messageApi.js'
import { adminMessageAllowed } from '../src/app/adminProjection.js'

export function messageApiFixture({ state, path, request, body, json, error }) {
  const write = /^\/api\/messages\/([^/]+)\/read-state$/.exec(path)
  const receipt = /^\/api\/message-read-saves\/([^/]+)$/.exec(path)
  if (path !== '/api/messages' && !write && !receipt) return false
  state.messageRecords ??= [{ value: personalNotice(), recipients: ['owner', 'trainer'] }]
  state.messageReaderStates ??= new Map()
  state.messageReadReceipts ??= new Map()
  const visible = row => row.recipients.includes(state.user.role) || (state.user.role === 'admin' && row.recipients.includes('owner'))
  const rows = state.messageRecords.filter(row => visible(row) && (state.user.role !== 'admin' || adminMessageAllowed(row.value)))
  const ownState = row => state.messageReaderStates.get(`${state.user.id}/${row.value.id}`) ?? { id: row.value.id, version: row.recipients.includes(state.user.role) ? 1 : 0, read: false, readAt: null }
  if (request.method === 'GET') {
    if (receipt) {
      const saved = state.messageReadReceipts.get(`${state.user.id}/${receipt[1]}`)
      if (saved) json(saved); else error('not_found', 404)
    } else if (state.messageReadFailure) error('service_unavailable', 503)
    else json(rows.map(row => ({ ...row.value, ...ownState(row), recipientUserId: state.user.id })))
    return true
  }
  state.messageWriteRequests ??= []
  state.messageWriteRequests.push({ path, body: structuredClone(body), key: request.headers['idempotency-key'] })
  const key = `${state.user.id}/${request.headers['idempotency-key']}`
  const saved = state.messageReadReceipts.get(key)
  if (saved) { json(saved); return true }
  const row = rows.find(row => row.value.id === write?.[1])
  if (!row) { error('not_found', 404); return true }
  const current = ownState(row)
  if (current.version !== body.expectedVersion) { error('state_conflict', 409); return true }
  if (state.messageAbsentUnknown) { state.messageAbsentUnknown = false; error('service_unavailable', 503); return true }
  const result = { id: row.value.id, version: current.version + 1, read: body.read, readAt: body.read ? current.readAt ?? '2026-10-13T11:00:00Z' : null }
  state.messageReaderStates.set(`${state.user.id}/${row.value.id}`, result)
  state.messageReadReceipts.set(key, result)
  if (state.messageUnknown) { state.messageUnknown = false; error('service_unavailable', 503); return true }
  if (state.messageRefreshFailure) { state.messageRefreshFailure = false; state.messageReadFailure = true }
  json(result); return true
}

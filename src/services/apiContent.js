import { contentErrors } from '../app/content.js'
import { ApiError } from './apiClient.js'
import { reconciledCommand } from './apiCommand.js'

const uuid = value => typeof value === 'string' && /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(value)
const version = value => Number.isSafeInteger(value) && value > 0
const invalid = () => { throw new ApiError('API_RESPONSE', 'The content record could not be verified. Check the original save again.') }
export function contentRecord(value) {
  if (!value || !uuid(value.id) || !version(value.version)
    || !['key', 'title', 'body', 'status'].every(key => typeof value[key] === 'string')
    || Object.keys(contentErrors(value)).length
    || Object.keys(value).some(key => !['id', 'version', 'key', 'title', 'body', 'status', 'created_at', 'updated_at'].includes(key))
    || !['created_at', 'updated_at'].every(key => typeof value[key] === 'string' && Number.isFinite(Date.parse(value[key])))
    || Date.parse(value.updated_at) < Date.parse(value.created_at)) invalid()
  return { id: value.id, version: value.version, key: value.key, title: value.title, body: value.body, status: value.status,
    createdAt: value.created_at, updatedAt: value.updated_at }
}
function commandInput({ id, expectedVersion, draft }) {
  if ((id == null) !== (expectedVersion == null) || (id != null && (!uuid(id) || !version(expectedVersion)))
    || !draft || !['key', 'title', 'body', 'status'].every(key => typeof draft[key] === 'string')
    || Object.keys(draft).some(key => !['key', 'title', 'body', 'status'].includes(key)) || Object.keys(contentErrors(draft)).length) {
    throw new ApiError('INVALID_REQUEST', 'Review the content and its version before saving.')
  }
  return { ...(id ? { id, expectedVersion } : {}), draft: { ...draft, title: draft.title.trim(), body: draft.body.trim() } }
}

export function contentCommands(http, actionSession) {
  const save = reconciledCommand(http, actionSession, {
    label: 'Content', path: () => '/api/content', receiptPath: '/api/content-saves',
    validate(value, input) {
      const record = contentRecord(value)
      if (record.version !== (input.id ? input.expectedVersion + 1 : 1) || (input.id && record.id !== input.id)
        || Object.entries(input.draft).some(([key, value]) => record[key] !== value)) invalid()
      return record
    },
  })
  return {
    save: (input, generation) => save(commandInput(input), generation),
    async read(generation) {
      const session = await actionSession(generation)
      if (!['owner', 'admin'].includes(session.user.role)) throw new ApiError('forbidden', 'Only the Owner or Admin can manage content.', 403)
      await save.reconcile(session.sessionGeneration)
      const value = await http.get('/api/content', { expectedGeneration: session.sessionGeneration })
      if (!Array.isArray(value) || value.length > 2000) invalid()
      const entries = value.map(contentRecord)
      if (new Set(entries.map(row => row.id)).size !== entries.length || new Set(entries.map(row => row.key)).size !== entries.length) invalid()
      return { entries, pending: save.pendingInput(session.sessionGeneration) }
    },
  }
}

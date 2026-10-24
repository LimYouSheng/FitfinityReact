import { ApiError } from './apiClient.js'
import { reconciledCommand } from './apiCommand.js'

const uuid = v => typeof v === 'string' && /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(v)
const keys = (v, fields) => v && Object.keys(v).length === fields.length && fields.every(k => Object.hasOwn(v, k))
const kinds = ['pdf_export', 'pdf_share_opened', 'whatsapp_opened', 'csv_export']
const fail = () => { throw new ApiError('API_RESPONSE', 'Report history could not be verified.') }
const invalid = () => { throw new ApiError('INVALID_REQUEST', 'A report action and purchased package are required.') }
const operationId = action => typeof action?.id === 'string' ? action.id.replace(/^report-/, '') : null
function event(value) {
  if (!keys(value, ['id', 'clientId', 'packageId', 'kind', 'at', 'by']) || !uuid(value.id) || !uuid(value.clientId) || (value.packageId !== null && !uuid(value.packageId)) || !kinds.includes(value.kind) || typeof value.at !== 'string' || !Number.isFinite(Date.parse(value.at)) || !keys(value.by, ['id', 'name']) || !uuid(value.by.id) || typeof value.by.name !== 'string' || !value.by.name.trim()) fail()
  return { ...value, id: `report-${value.id}` }
}

/** Audit the browser's completed launch once; recovery never launches a second file or share. */
export function progressReportCommands(http, actionSession) {
  const command = reconciledCommand(http, actionSession, {
    label: 'Report history', roles: ['owner', 'admin', 'trainer'],
    path: v => `/api/clients/${v.id}/report-actions`, receiptPath: '/api/report-actions',
    keyFor: v => operationId(v.action),
    bodyFor: v => ({ purchaseId: v.action.packageId, kind: v.action.kind }),
    validate(value, input) {
      const saved = event(value)
      if (value.id !== operationId(input.action) || value.clientId !== input.id || value.packageId !== input.action.packageId || value.kind !== input.action.kind) fail()
      return saved
    },
  })
  return {
    async record(input, generation) {
      if (!uuid(input?.id) || !uuid(operationId(input.action)) || !uuid(input.action.packageId) || !kinds.slice(0, 3).includes(input.action.kind)) invalid()
      return command({ id: input.id, action: { id: `report-${operationId(input.action)}`, packageId: input.action.packageId, kind: input.action.kind } }, generation)
    },
    async history({ id, packageId }, generation) {
      if (!uuid(id) || (packageId !== undefined && !uuid(packageId))) invalid()
      const { user, sessionGeneration } = await actionSession(generation)
      if (!['owner', 'admin'].includes(user.role)) throw new ApiError('forbidden', 'Report history is available to Owner or Admin.', 403)
      const rows = await http.get(`/api/clients/${id}/report-history${packageId ? `?purchase_id=${packageId}` : ''}`, { expectedGeneration: sessionGeneration })
      if (!Array.isArray(rows) || rows.length > 2000) fail()
      const result = rows.map(event)
      if (new Set(result.map(r => r.id)).size !== result.length || result.some(r => r.clientId !== id || (packageId !== undefined && r.packageId !== packageId))) fail()
      return result
    },
    pendingInput: command.pendingInput,
  }
}

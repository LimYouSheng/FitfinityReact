import { ApiError } from './apiClient.js'
import { reconciledCommand } from './apiCommand.js'

function verified(value, input) {
  if (!value || value.kind !== input.kind || !/^[0-9a-f]{64}$/.test(value.expected) ||
      value.expected !== input.expected || !value.inputs?.client?.name ||
      (input.kind === 'progress' ? value.inputs.client.id !== input.targetId || value.inputs.client.reportPackageId !== input.purchaseId || !Array.isArray(value.inputs.client.strengthProgress)
        : value.inputs.session?.id !== input.targetId || value.inputs.session.packageId !== input.purchaseId || typeof value.inputs.summary !== 'string' || !Array.isArray(value.inputs.videos))) {
    throw new ApiError('API_RESPONSE', 'The report content could not be verified. Reload before sharing.')
  }
  return value
}

export function reportSharingCommands(http, actionSession) {
  const command = reconciledCommand(http, actionSession, {
    label: 'Report sharing', path: () => '/api/report-sharing', receiptPath: '/api/report-sharing',
    roles: ['owner', 'admin', 'trainer'], validate: verified,
  })
  return {
    async prepare(selection, generation) {
      const { user } = await actionSession(generation)
      if (command.pendingInput(generation)) {
        const pending = command.pendingInput(generation)
        if (['kind', 'targetId', 'purchaseId', 'includeSummary'].some(key => pending[key] !== selection[key]) || JSON.stringify(pending.videoIds) !== JSON.stringify(selection.videoIds)) {
          throw new ApiError('SAVE_PENDING', 'Return to the original report selection to check its uncertain request.')
        }
        const recovered = await command.reconcile(generation)
        if (recovered) return recovered.result
        throw new ApiError('SAVE_UNCERTAIN', 'The original request is not confirmed. Check again or retry the original request.')
      }
      const value = await http.post('/api/report-sharing/review', selection, { csrf: true, idempotencyKey: crypto.randomUUID(), expectedGeneration: generation })
      verified(value, { ...selection, expected: value?.expected })
      // Recover a durable approved/pending proposal after navigation or a fresh login.
      if (user.role === 'admin') {
        const proposals = await http.get('/api/admin-requests', { expectedGeneration: generation })
        if (!Array.isArray(proposals)) throw new ApiError('API_RESPONSE', 'Report requests could not be verified.')
        const existing = proposals.find(item => item.actorId === user.id && item.operation === `report.${selection.kind}` &&
          ['pending', 'approved'].includes(item.status) && item.body?.body?.expected === value.expected &&
          item.body.body.targetId === selection.targetId && item.body.body.purchaseId === selection.purchaseId)
        if (existing) return verified(await http.get(`/api/report-sharing/requests/${existing.id}`, { expectedGeneration: generation }), { ...selection, expected: value.expected })
      }
      return command({ ...selection, expected: value.expected, at: new Date().toISOString() }, generation)
    },
    async retry(selection, generation) {
      const input = command.pendingInput(generation)
      if (!input) throw new ApiError('INVALID_REQUEST', 'Review the report before sharing.')
      if (['kind', 'targetId', 'purchaseId', 'includeSummary'].some(key => input[key] !== selection[key]) || JSON.stringify(input.videoIds) !== JSON.stringify(selection.videoIds)) throw new ApiError('SAVE_PENDING', 'Return to the original report selection to retry its request.')
      return command(input, generation)
    },
  }
}

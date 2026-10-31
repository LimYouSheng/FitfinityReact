import { expect, it, vi } from 'vitest'
import { ApiError } from './apiClient.js'
import { reportSharingCommands } from './apiReportSharing.js'

const selection = { kind: 'session', targetId: 'session', purchaseId: 'purchase', includeSummary: true, videoIds: [] }
const reviewed = { kind: 'session', expected: 'a'.repeat(64), inputs: { client: { name: 'Synthetic client' }, session: { id: 'session', packageId: 'purchase' }, summary: 'Reviewed content', videos: [] } }
function setup() {
  const http = { post: vi.fn().mockResolvedValue(reviewed), get: vi.fn().mockResolvedValue([]) }
  const commands = reportSharingCommands(http, async () => ({ user: { id: 'admin', role: 'admin' }, sessionGeneration: 1 }))
  return { http, commands }
}
it('recovers an approved exact report from its original private proposal after navigation', async () => {
  const { http, commands } = setup()
  http.get.mockResolvedValueOnce([{ id: 'proposal', actorId: 'admin', operation: 'report.session', status: 'approved', body: { body: { ...selection, expected: reviewed.expected } } }]).mockResolvedValueOnce(reviewed)
  expect(await commands.prepare(selection, 1)).toEqual(reviewed)
  expect(http.post).toHaveBeenCalledTimes(1)
  expect(http.get).toHaveBeenLastCalledWith('/api/report-sharing/requests/proposal', { expectedGeneration: 1 })
})
it('checks a lost submission by receipt without automatically creating another proposal', async () => {
  const { http, commands } = setup()
  http.post.mockResolvedValueOnce(reviewed).mockRejectedValueOnce(new ApiError('NETWORK_ERROR', 'Interrupted'))
  await expect(commands.prepare(selection, 1)).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  http.get.mockRejectedValueOnce(new ApiError('APPROVAL_PENDING', 'Waiting', 409))
  await expect(commands.prepare(selection, 1)).rejects.toMatchObject({ code: 'APPROVAL_PENDING' })
  expect(http.post).toHaveBeenCalledTimes(2)
})
it('does not return another report through an unresolved command or changed selection', async () => {
  const { http, commands } = setup()
  http.post.mockResolvedValueOnce(reviewed).mockRejectedValueOnce(new ApiError('NETWORK_ERROR', 'Interrupted'))
  await expect(commands.prepare(selection, 1)).rejects.toThrow('Interrupted')
  await expect(commands.prepare({ ...selection, targetId: 'foreign' }, 1)).rejects.toMatchObject({ code: 'SAVE_PENDING' })
  await expect(commands.retry({ ...selection, videoIds: ['another'] }, 1)).rejects.toMatchObject({ code: 'SAVE_PENDING' })
  expect(http.post).toHaveBeenCalledTimes(2)
})
it('rejects a response for another purchase before preparing or authorizing a report', async () => {
  const { http, commands } = setup()
  http.post.mockResolvedValue({ ...reviewed, inputs: { ...reviewed.inputs, session: { ...reviewed.inputs.session, packageId: 'foreign' } } })
  await expect(commands.prepare(selection, 1)).rejects.toMatchObject({ code: 'API_RESPONSE' })
  expect(http.post).toHaveBeenCalledTimes(1)
  expect(http.get).not.toHaveBeenCalled()
})

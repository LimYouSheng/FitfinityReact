import { expect, it, vi } from 'vitest'
import { ApiError } from './apiClient.js'
import { reportEmailCommands } from './apiReportEmail.js'

const selection = { kind: 'progress', targetId: 'client', purchaseId: 'purchase', includeSummary: true, videoIds: [] }
const input = { ...selection, expected: 'a'.repeat(64) }
const receipt = { requestId: '11111111-1111-4111-8111-111111111111', queued: 1 }
function setup() {
  const http = { post: vi.fn(), get: vi.fn() }
  const commands = reportEmailCommands(http, async () => ({ user: { role: 'owner' }, sessionGeneration: 1 }))
  return { http, commands }
}
it('reviews recipients without submitting an email intent', async () => {
  const { http, commands } = setup()
  const review = { expected: input.expected, recipients: [{ name: 'Synthetic Client', email: 'client@example.test' }] }
  http.post.mockResolvedValue(review)
  expect(await commands.review(selection, 1)).toEqual(review)
  expect(http.post).toHaveBeenCalledExactlyOnceWith('/api/report-email/review', selection, expect.objectContaining({ csrf: true }))
})
it('recovers a lost email response by receipt without another send', async () => {
  const { http, commands } = setup()
  http.post.mockRejectedValue(new ApiError('NETWORK_ERROR', 'Interrupted'))
  await expect(commands.send(input, 1)).rejects.toThrow('Interrupted')
  http.get.mockResolvedValue(receipt)
  expect(await commands.recover(selection, 1)).toEqual(receipt)
  expect(http.post).toHaveBeenCalledTimes(1)
  await expect(commands.retry(selection, 1)).rejects.toMatchObject({ code: 'INVALID_REQUEST' })
})
it('never checks or retries an email while viewing a different client or purchase', async () => {
  const { http, commands } = setup()
  http.post.mockRejectedValue(new ApiError('NETWORK_ERROR', 'Interrupted'))
  await expect(commands.send(input, 1)).rejects.toThrow('Interrupted')
  for (const patch of [{ targetId: 'foreign' }, { purchaseId: 'foreign' }]) {
    await expect(commands.recover({ ...selection, ...patch }, 1)).rejects.toMatchObject({ code: 'SAVE_PENDING' })
    await expect(commands.retry({ ...selection, ...patch }, 1)).rejects.toMatchObject({ code: 'SAVE_PENDING' })
  }
  expect(http.get).not.toHaveBeenCalled()
  expect(http.post).toHaveBeenCalledTimes(1)
})
it('reuses the original request key and content only after explicit retry and a missing receipt', async () => {
  const { http, commands } = setup()
  http.post.mockRejectedValueOnce(new ApiError('NETWORK_ERROR', 'Interrupted')).mockResolvedValueOnce(receipt)
  await expect(commands.send(input, 1)).rejects.toThrow('Interrupted')
  const key = http.post.mock.calls[0][2].idempotencyKey
  http.get.mockRejectedValue(new ApiError('not_found', 'Not found', 404))
  await expect(commands.recover(selection, 1)).rejects.toMatchObject({ code: 'SAVE_UNCERTAIN' })
  expect(http.post).toHaveBeenCalledTimes(1)
  expect(await commands.retry(selection, 1)).toEqual(receipt)
  expect(http.post).toHaveBeenLastCalledWith('/api/report-email', input, expect.objectContaining({ idempotencyKey: key }))
})
it('holds malformed success responses instead of treating them as proof of queuing', async () => {
  const { http, commands } = setup()
  http.post.mockResolvedValue({ ...receipt, queued: 0 })
  await expect(commands.send(input, 1)).rejects.toMatchObject({ code: 'API_RESPONSE' })
  await expect(commands.review(selection, 1)).rejects.toMatchObject({ code: 'SAVE_UNCERTAIN' })
  expect(http.post).toHaveBeenCalledTimes(1)
})

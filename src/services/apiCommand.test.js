import { expect, it, vi } from 'vitest'
import { ApiError } from './apiClient.js'
import { reconciledCommand } from './apiCommand.js'

it.each([true, false])('serializes explicit retries while the original receipt is being checked (committed: %s)', async committed => {
  let resolveReceipt, rejectReceipt
  const receipt = new Promise((resolve, reject) => { resolveReceipt = resolve; rejectReceipt = reject })
  const http = {
    post: vi.fn().mockRejectedValueOnce(new ApiError('NETWORK_ERROR', 'Lost response')).mockResolvedValue({ saved: true }),
    get: vi.fn(() => receipt),
  }
  const command = reconciledCommand(http, async () => ({ user: { role: 'owner' }, sessionGeneration: 1 }), {
    label: 'Probe', path: () => '/write', receiptPath: '/receipt', validate: value => value,
  })
  await expect(command({ value: 'original' }, 1)).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  const retry = command({ value: 'original' }, 1)
  await vi.waitFor(() => expect(http.get).toHaveBeenCalledTimes(1))
  await expect(command({ value: 'original' }, 1)).rejects.toMatchObject({ code: 'SAVE_PENDING' })
  if (committed) resolveReceipt({ saved: true })
  else rejectReceipt(new ApiError('not_found', 'No receipt', 404))
  await expect(retry).resolves.toEqual({ saved: true })
  expect(http.post).toHaveBeenCalledTimes(committed ? 1 : 2)
})

it('keeps uncertain intent when a receipt read is denied rather than treating it as a write rejection', async () => {
  const http = { post: vi.fn().mockRejectedValue(new ApiError('NETWORK_ERROR', 'Lost response')), get: vi.fn().mockRejectedValue(new ApiError('forbidden', 'Denied', 403)) }
  const command = reconciledCommand(http, async () => ({ user: { role: 'owner' }, sessionGeneration: 1 }), {
    label: 'Probe', path: () => '/write', receiptPath: '/receipt', validate: value => value,
  })
  await expect(command({ value: 'original' }, 1)).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  await expect(command({ value: 'original' }, 1)).rejects.toMatchObject({ code: 'forbidden' })
  expect(command.pendingInput(1)).toEqual({ value: 'original' })
  expect(http.post).toHaveBeenCalledTimes(1)
  expect(command.pendingInput(2)).toBeNull()
})

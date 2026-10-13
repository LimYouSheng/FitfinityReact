import { act, renderHook, waitFor } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import useClientNotes from './useClientNotes.js'

const deferred = () => {
  let resolve
  const promise = new Promise(done => { resolve = done })
  return { promise, resolve }
}

it('discards late notes after changing client or login generation', async () => {
  const first = deferred(), second = deferred()
  const service = { getById: vi.fn().mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise) }
  const one = { id: 'one' }, two = { id: 'two' }
  const { result, rerender } = renderHook(({ client, generation }) => useClientNotes(client, true, service, generation), { initialProps: { client: one, generation: 1 } })
  rerender({ client: two, generation: 2 })
  await act(async () => first.resolve({ ...one, healthNotes: 'Old private note' }))
  expect(result.current.client).toBeFalsy()
  await act(async () => second.resolve({ ...two, healthNotes: 'Current note' }))
  expect(result.current.client).toEqual({ ...two, healthNotes: 'Current note' })
})

it('keeps failed scoped reads unavailable and retries explicitly', async () => {
  const client = { id: 'one' }
  const service = { getById: vi.fn().mockRejectedValueOnce(new Error('Unavailable')).mockResolvedValueOnce({ ...client, healthNotes: '' }) }
  const { result } = renderHook(() => useClientNotes(client, true, service, 1))
  await waitFor(() => expect(result.current.error?.message).toBe('Unavailable'))
  expect(result.current.client).toBeFalsy()
  act(() => result.current.retry())
  await waitFor(() => expect(result.current.client).toEqual({ ...client, healthNotes: '' }))
  expect(service.getById).toHaveBeenCalledTimes(2)
})

import { act, cleanup, renderHook, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import useClientNotes from './useClientNotes.js'

afterEach(cleanup)

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

it('keeps an open profile mounted across equivalent periodic directory snapshots', async () => {
  const client = { id: 'one', version: 2, people: [{ id: 'person', version: 1 }] }
  const service = { getById: vi.fn().mockResolvedValue({ ...client, healthNotes: 'Current' }) }
  const { result, rerender } = renderHook(({ value }) => useClientNotes(value, true, service, 1), { initialProps: { value: client } })
  await waitFor(() => expect(result.current.client?.healthNotes).toBe('Current'))
  const retained = result.current.client
  rerender({ value: structuredClone(client) })
  expect(result.current.client).toBe(retained)
  expect(service.getById).toHaveBeenCalledTimes(1)
})

it('retires old notes immediately when directory authority or a person version changes', async () => {
  const later = deferred()
  const client = { id: 'one', trainerId: 'old', people: [{ id: 'person', version: 1 }] }
  const service = { getById: vi.fn().mockResolvedValueOnce({ ...client, healthNotes: 'Old' }).mockReturnValueOnce(later.promise) }
  const { result, rerender } = renderHook(({ value }) => useClientNotes(value, true, service, 1), { initialProps: { value: client } })
  await waitFor(() => expect(result.current.client?.healthNotes).toBe('Old'))
  rerender({ value: { ...client, trainerId: 'new', people: [{ id: 'person', version: 2 }] } })
  expect(result.current.client).toBeFalsy()
  expect(service.getById).toHaveBeenCalledTimes(2)
})

it('uses the scoped notes reader without reloading the full directory', async () => {
  const client = { id: 'one', version: 2, people: [] }
  const service = { getById: vi.fn() }
  const read = vi.fn(async value => ({ ...value, healthNotes: 'Scoped note' }))
  const { result } = renderHook(() => useClientNotes(client, true, service, 1, read))
  await waitFor(() => expect(result.current.client?.healthNotes).toBe('Scoped note'))
  expect(service.getById).not.toHaveBeenCalled()
  expect(read).toHaveBeenCalledWith(client)
})

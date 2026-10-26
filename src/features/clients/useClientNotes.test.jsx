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

it('accepts a refreshed directory version on retry and keeps its editor through equivalent refreshes', async () => {
  const client = { id: 'one', version: 2, people: [] }
  const fresh = { ...client, version: 3 }
  const service = { getById: vi.fn() }
  const read = vi.fn().mockRejectedValueOnce(new Error('Reload and review again')).mockResolvedValue({ ...fresh, healthNotes: 'Another device saved this' })
  const { result, rerender } = renderHook(({ row }) => useClientNotes(row, true, service, 1, read), { initialProps: { row: client } })
  await waitFor(() => expect(result.current.error?.message).toBe('Reload and review again'))
  rerender({ row: fresh })
  act(() => result.current.retry())
  await waitFor(() => expect(result.current.client?.version).toBe(3))
  const displayed = result.current.client
  rerender({ row: structuredClone(fresh) })
  expect(result.current.client).toBe(displayed)
  expect(service.getById).not.toHaveBeenCalled()
})

it('preserves the reviewed client during edits and reads the latest version after editing ends', async () => {
  const client = { id: 'one', version: 1, status: 'active', trainerId: 'trainer', people: [{ id: 'person', version: 1 }] }
  const fresh = { ...client, version: 2, people: [{ id: 'person', version: 2 }] }
  const service = { getById: vi.fn() }
  const read = vi.fn(async row => ({ ...row, healthNotes: `Version ${row.version}` }))
  const { result, rerender } = renderHook(({ row, editing }) => useClientNotes(row, true, service, 1, read, editing), { initialProps: { row: client, editing: false } })
  await waitFor(() => expect(result.current.client?.version).toBe(1))
  const reviewed = result.current.client
  rerender({ row: client, editing: true })
  rerender({ row: fresh, editing: true })
  expect(result.current.client).toBe(reviewed)
  expect(read).toHaveBeenCalledTimes(1)
  rerender({ row: fresh, editing: false })
  expect(result.current.client).toBe(reviewed)
  await waitFor(() => expect(result.current.client?.version).toBe(2))
})

it.each([
  { trainerId: 'another' }, { status: 'inactive' }, { people: [{ id: 'another' }] }, { id: 'another' },
])('immediately retires an active editor when its authority changes: %j', async patch => {
  const client = { id: 'one', trainerId: 'trainer', status: 'active', people: [{ id: 'person' }] }
  const service = { getById: vi.fn().mockResolvedValueOnce(client).mockReturnValue(new Promise(() => {})) }
  const { result, rerender } = renderHook(({ row }) => useClientNotes(row, true, service, 1, undefined, true), { initialProps: { row: client } })
  await waitFor(() => expect(result.current.client).toEqual(client))
  rerender({ row: { ...client, ...patch } })
  expect(result.current.client).toBeFalsy()
})

it.each([401, 403, 404])('removes a previously loaded client after a %s scoped read rejection', async status => {
  const client = { id: 'one', version: 1 }
  const service = { getById: vi.fn().mockResolvedValueOnce(client).mockRejectedValueOnce(Object.assign(new Error('Denied'), { status })) }
  const { result, rerender } = renderHook(({ row }) => useClientNotes(row, true, service, 1), { initialProps: { row: client } })
  await waitFor(() => expect(result.current.client).toEqual(client))
  rerender({ row: { ...client, version: 2 } })
  await waitFor(() => expect(result.current.error?.status).toBe(status))
  expect(result.current.client).toBeFalsy()
})

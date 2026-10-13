import { act, cleanup, renderHook, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import useClientMatches from './useClientMatches.js'

afterEach(cleanup)
const trainer = { id: 'trainer', version: 1, status: 'active', name: 'Reviewed trainer' }
const draft = { packageId: 'package', packageVersion: 1, startDate: '2027-06-07', sessionsPerWeek: 1, genderPreference: 'No gender preference', clientPreferences: [{ days: ['Monday'], from: '18:00', to: '19:00' }] }
const match = { trainerId: 'trainer', trainerVersion: 1, matches: 1, total: 1, schedule: [{ day: 'Monday', from: '18:00', to: '19:00' }] }
const trainers = [trainer]

it('ignores a late match from an older draft', async () => {
  const resolve = []
  const preview = vi.fn(() => new Promise(done => resolve.push(done)))
  const { result, rerender } = renderHook(({ day }) => useClientMatches(preview, { ...draft, startDate: day }, trainers, true), { initialProps: { day: draft.startDate } })
  expect(result.current.loading).toBe(true)
  rerender({ day: '2027-06-14' })
  await act(async () => resolve[1]([]))
  expect(result.current.matches).toEqual([])
  await act(async () => resolve[0]([match]))
  expect(result.current.matches).toEqual([])
  expect(result.current.loading).toBe(false)
})

it('rejects a match whose Trainer profile was not reviewed and supports an explicit retry', async () => {
  const preview = vi.fn().mockResolvedValueOnce([{ ...match, trainerVersion: 2 }]).mockResolvedValueOnce([match])
  const { result } = renderHook(() => useClientMatches(preview, draft, trainers, true))
  await waitFor(() => expect(result.current.error).toContain('Trainer details changed'))
  expect(result.current.matches).toEqual([])
  act(() => result.current.retry())
  await waitFor(() => expect(result.current.matches[0]?.trainer).toEqual(trainer))
  expect(result.current.error).toBe('')
})

it('does not request matching while a creation is being reconciled', () => {
  const preview = vi.fn()
  const { result } = renderHook(() => useClientMatches(preview, draft, trainers, false))
  expect(result.current.matches).toEqual([])
  expect(preview).not.toHaveBeenCalled()
})

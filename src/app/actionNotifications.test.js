import { expect, it } from 'vitest'
import { exerciseNotification, planNotification, scheduleNotification } from './actionNotifications.js'

it('distinguishes submitted requests from immediately applied schedule changes', () => {
  expect(scheduleNotification('Availability', { outcome: 'requested' })).toEqual({ tone: 'info', message: 'Availability request sent for owner approval.' })
  expect(scheduleNotification('Availability', { outcome: 'applied' })).toEqual({ tone: 'success', message: 'Availability saved.' })
})

it('distinguishes exercise creation, edits, lifecycle changes and attachment removal', () => {
  const exercise = { status: 'active', media: { id: 'photo' } }
  expect(exerciseNotification(null, exercise).message).toBe('Exercise created.')
  expect(exerciseNotification(exercise, exercise).message).toBe('Exercise saved.')
  expect(exerciseNotification(exercise, { ...exercise, status: 'inactive' })).toEqual({ tone: 'warning', message: 'Exercise deactivated.' })
  expect(exerciseNotification({ ...exercise, status: 'inactive' }, exercise).message).toBe('Exercise reactivated.')
  expect(exerciseNotification(exercise, { ...exercise, media: null })).toEqual({ tone: 'warning', message: 'Attachment removed. Exercise saved.' })
})

it('reports plan video changes without treating an unchanged video copy as a new upload', () => {
  const item = { id: 'e1', videoAttached: true, video: { attachedAt: '2026-09-06T12:00:00Z', size: 42 } }
  expect(planNotification([item], [structuredClone(item)]).message).toBe('Exercise plan saved.')
  expect(planNotification([item], [{ ...item, videoAttached: false, video: null }]).tone).toBe('warning')
  expect(planNotification([], [item]).message).toBe('Video saved.')
})

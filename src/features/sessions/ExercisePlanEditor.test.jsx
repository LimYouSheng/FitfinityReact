import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { ActionConfirmationProvider } from '../../components/ActionConfirmationProvider.jsx'
import { mockPolicy } from '../../data/mockPolicy.js'
import { formatTimestamp } from '../../utils/date.js'
import ExercisePlanEditor from './ExercisePlanEditor.jsx'

const exercise = {
  id: 'exercise-1', name: 'Squat', weight: '20 kg', reps: '10', rounds: '3', rest: '60 sec', videoAttached: true,
}

function show(overrides = {}) {
  const props = {
    items: [exercise], defaults: mockPolicy.exerciseDefaults, catalog: [], sessionId: 'completed-session',
    canEdit: false, canViewVideo: true, editing: false,
    onBeginEdit: vi.fn(), onEndEdit: vi.fn(), onSave: vi.fn(),
    onLoadVideo: vi.fn().mockResolvedValue(new Blob(['saved video'], { type: 'video/webm' })),
    onSaveVideo: vi.fn(), onRemoveVideo: vi.fn(), ...overrides,
  }
  return { props, ...render(<ActionConfirmationProvider><ExercisePlanEditor {...props} /></ActionConfirmationProvider>) }
}

beforeEach(() => {
  vi.stubGlobal('URL', { createObjectURL: vi.fn().mockReturnValue('blob:saved-video'), revokeObjectURL: vi.fn() })
})
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.resetAllMocks() })

it('opens a completed exercise video for playback without allowing edits and releases its preview when closed', async () => {
  const blob = new Blob(['retained recording'], { type: 'video/webm' })
  const expiresAt = '2026-09-16T10:15:00.000Z'
  const timeZone = 'Asia/Singapore'
  const { props } = show({
    items: [{ ...exercise, video: { expiresAt } }], timeZone,
    onLoadVideo: vi.fn().mockResolvedValue(blob),
  })
  expect(screen.queryByRole('button', { name: 'Edit exercise plan' })).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'View video for Squat' }))
  const dialog = screen.getByRole('dialog', { name: 'Video · Squat' })
  await waitFor(() => expect(dialog.querySelector('video')).toHaveAttribute('src', 'blob:saved-video'))
  expect(dialog.querySelector('video')).toHaveAttribute('controls')
  expect(props.onLoadVideo).toHaveBeenCalledWith('exercise-1')
  expect(URL.createObjectURL).toHaveBeenCalledWith(blob)
  expect(dialog.querySelector('time')).toHaveAttribute('datetime', expiresAt)
  expect(dialog.querySelector('time')).toHaveTextContent(formatTimestamp(expiresAt, timeZone))
  expect(dialog.querySelector('time')).toHaveTextContent(/06:15\s*pm/i)
  expect(dialog.querySelector('time').parentElement).toHaveTextContent('Available until')
  expect(within(dialog).queryByLabelText(/Record new video|Attach video/)).toBeNull()
  expect(within(dialog).queryByRole('button', { name: /Save Video|Remove/ })).toBeNull()
  fireEvent.click(within(dialog).getByRole('button', { name: 'Close dialog' }))
  expect(screen.queryByRole('dialog')).toBeNull()
  await waitFor(() => expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:saved-video'))
  for (const action of [props.onBeginEdit, props.onSave, props.onSaveVideo, props.onRemoveVideo]) {
    expect(action).not.toHaveBeenCalled()
  }
})

it('offers read-only playback only when access is allowed and a saved video exists', () => {
  for (const overrides of [{ canViewVideo: false }, { items: [{ ...exercise, videoAttached: false }] }]) {
    const view = show(overrides)
    expect(screen.queryByRole('button', { name: /video for Squat/i })).toBeNull()
    expect(view.props.onLoadVideo).not.toHaveBeenCalled()
    view.unmount()
  }
  show({ canEdit: true, canViewVideo: undefined })
  expect(screen.getByRole('button', { name: 'Manage video for Squat' })).toBeEnabled()
})

it('shows a stored-video loading failure without enabling edits and still lets the user close the dialog', async () => {
  const { props } = show({ onLoadVideo: vi.fn().mockRejectedValue(new Error('This recording has expired.')) })
  fireEvent.click(screen.getByRole('button', { name: 'View video for Squat' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('This recording has expired.')
  const dialog = screen.getByRole('dialog', { name: 'Video · Squat' })
  expect(dialog.querySelector('video')).toBeNull()
  expect(within(dialog).queryByLabelText(/Record new video|Attach video/)).toBeNull()
  expect(within(dialog).queryByRole('button', { name: /Save Video|Remove/ })).toBeNull()
  fireEvent.click(within(dialog).getByRole('button', { name: 'Close dialog' }))
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(URL.createObjectURL).not.toHaveBeenCalled()
  expect(props.onSaveVideo).not.toHaveBeenCalled()
  expect(props.onRemoveVideo).not.toHaveBeenCalled()
})

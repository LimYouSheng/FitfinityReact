import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ExerciseVideoDialog from './ExerciseVideoDialog.jsx'
import { prepareExerciseVideo, readVideoDuration } from './exerciseVideo.js'

vi.mock('./exerciseVideo.js', async original => ({
  ...await original(), prepareExerciseVideo: vi.fn(), readVideoDuration: vi.fn(),
}))
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

function setup() {
  vi.stubGlobal('MediaRecorder', class {})
  vi.stubGlobal('HTMLCanvasElement', { prototype: { captureStream: vi.fn() } })
  vi.stubGlobal('URL', class extends URL {
    static createObjectURL() { return 'blob:synthetic' }
    static revokeObjectURL() {}
  })
  readVideoDuration.mockResolvedValue(1)
  prepareExerciseVideo.mockImplementation(async (_file, _lines, _progress, options) => ({
    blob: new Blob(['converted'], { type: 'video/webm' }), duration: 1, audioIncluded: options.includeAudio,
  }))
  const onSaved = vi.fn().mockResolvedValue(undefined)
  render(<ExerciseVideoDialog open sessionId="session" exercise={{ id: 'exercise', name: 'Squat' }} onLoad={vi.fn()} onSaved={onSaved} onCancel={vi.fn()} />)
  return onSaved
}
async function choose(file = new File(['original'], 'test.webm', { type: 'video/webm' })) {
  fireEvent.change(screen.getByLabelText('Attach video for Squat'), { target: { files: [file] } })
  await waitFor(() => expect(screen.getByRole('button', { name: 'Save Video' })).toBeEnabled())
}

describe('session video audio selection', () => {
  it('defaults to silent conversion and saves the prepared audio setting', async () => {
    const saved = setup()
    expect(screen.getByRole('checkbox')).not.toBeChecked()
    await choose()
    expect(screen.getByRole('checkbox')).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Save Video' }))
    await waitFor(() => expect(saved).toHaveBeenCalledWith(expect.any(Blob), expect.objectContaining({ audioIncluded: false, processingStatus: 'complete' })))
  })
  it('preserves the opted-in setting through conversion and save', async () => {
    const saved = setup()
    fireEvent.click(screen.getByRole('checkbox'))
    await choose()
    expect(screen.getByText('Original audio included (if present)')).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Save Video' }))
    await waitFor(() => expect(saved).toHaveBeenCalledWith(expect.any(Blob), expect.objectContaining({ audioIncluded: true, processingStatus: 'complete' })))
  })
  it('labels conversion failure honestly and never claims the option was applied', async () => {
    const saved = setup()
    const original = new File([new Uint8Array(10 * 1024 * 1024)], 'original.webm', { type: 'video/webm' })
    prepareExerciseVideo.mockRejectedValue(new Error('Unsupported codec'))
    fireEvent.click(screen.getByRole('checkbox'))
    await choose(original)
    expect(screen.getByRole('status')).toHaveTextContent('captions and your audio option have not been applied')
    fireEvent.click(screen.getByRole('button', { name: 'Save Video' }))
    await waitFor(() => expect(saved).toHaveBeenCalledWith(original, expect.objectContaining({ audioIncluded: null, processingStatus: 'deferred' })))
    expect(saved.mock.calls[0][0]).toBe(original)
  })
  it('cancels preparation without presenting a late result for saving', async () => {
    setup()
    let finish
    prepareExerciseVideo.mockImplementation(() => new Promise(resolve => { finish = resolve }))
    fireEvent.change(screen.getByLabelText('Attach video for Squat'), { target: { files: [new File(['x'], 'test.webm', { type: 'video/webm' })] } })
    await waitFor(() => expect(finish).toBeTypeOf('function'))
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    finish({ blob: new Blob(['late']), duration: 1, audioIncluded: false })
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Save Video' })).not.toBeInTheDocument())
  })
})


it.each(['missing', 'failed'])('keeps removal available after a %s saved preview without claiming it is still loading', async outcome => {
  let finish
  const onLoad = vi.fn(() => new Promise((resolve, reject) => { finish = outcome === 'failed' ? reject : resolve }))
  const onRemoved = vi.fn().mockResolvedValue(undefined)
  const onSaved = vi.fn()
  render(<ExerciseVideoDialog open sessionId="session" exercise={{ id: 'exercise', name: 'Squat', videoAttached: true }}
    onLoad={onLoad} onSaved={onSaved} onRemoved={onRemoved} onCancel={vi.fn()} />)
  expect(screen.getByRole('status')).toHaveTextContent('Loading saved video…')
  finish(outcome === 'failed' ? new Error('Preview download failed') : null)
  expect(await screen.findByRole('alert')).toHaveTextContent(outcome === 'failed' ? 'Preview download failed' : 'The saved video is no longer available.')
  expect(screen.getByRole('status')).toHaveTextContent('Its local preview is unavailable')
  fireEvent.click(screen.getByRole('button', { name: 'Remove saved video' }))
  expect(onRemoved).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Remove Video', exact: true }))
  await waitFor(() => expect(onRemoved).toHaveBeenCalledTimes(1))
  expect(onSaved).not.toHaveBeenCalled()
})

it.each(['loaded', 'missing', 'failed'])('keeps replacement bytes and preview after a late %s saved-video load', async outcome => {
  vi.stubGlobal('MediaRecorder', undefined)
  const replacement = new File(['replacement'], 'replacement.webm', { type: 'video/webm' })
  const create = vi.fn(blob => blob === replacement ? 'blob:replacement' : 'blob:stored')
  vi.stubGlobal('URL', { createObjectURL: create, revokeObjectURL: vi.fn() })
  let finish
  const onLoad = vi.fn(() => new Promise((resolve, reject) => { finish = outcome === 'failed' ? reject : resolve }))
  const onSaved = vi.fn().mockResolvedValue(undefined)
  render(<ExerciseVideoDialog open sessionId="session" exercise={{ id: 'exercise', name: 'Squat', videoAttached: true }}
    onLoad={onLoad} onSaved={onSaved} onRemoved={vi.fn()} onCancel={vi.fn()} />)
  expect(screen.getByRole('status')).toHaveTextContent('Loading saved video')
  await choose(replacement)
  expect(document.querySelector('video')).toHaveAttribute('src', 'blob:replacement')
  await act(async () => { finish(outcome === 'failed' ? new Error('Late saved download failed') : outcome === 'missing' ? null : new Blob(['stored'])) })
  expect(document.querySelector('video')).toHaveAttribute('src', 'blob:replacement')
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  expect(create).toHaveBeenCalledTimes(1)
  expect(URL.revokeObjectURL).not.toHaveBeenCalledWith('blob:replacement')
  fireEvent.click(screen.getByRole('button', { name: 'Save Video' }))
  await waitFor(() => expect(onSaved).toHaveBeenCalledWith(replacement, expect.objectContaining({ processingStatus: 'deferred' })))
})

it('retains the pending saved preview when a replacement fails duration validation', async () => {
  vi.stubGlobal('MediaRecorder', class {})
  vi.stubGlobal('HTMLCanvasElement', { prototype: { captureStream: vi.fn() } })
  vi.stubGlobal('URL', { createObjectURL: vi.fn(() => 'blob:stored'), revokeObjectURL: vi.fn() })
  readVideoDuration.mockResolvedValue(1000)
  let finish
  const onLoad = vi.fn(() => new Promise(resolve => { finish = resolve }))
  render(<ExerciseVideoDialog open sessionId="session" exercise={{ id: 'exercise', name: 'Squat', videoAttached: true }}
    onLoad={onLoad} onSaved={vi.fn()} onRemoved={vi.fn()} onCancel={vi.fn()} />)
  fireEvent.change(screen.getByLabelText('Attach video for Squat'), { target: { files: [new File(['long'], 'long.webm', { type: 'video/webm' })] } })
  expect(await screen.findByRole('alert')).toHaveTextContent('1 minute')
  await act(async () => { finish(new Blob(['stored'])) })
  expect(document.querySelector('video')).toHaveAttribute('src', 'blob:stored')
  expect(screen.queryByRole('button', { name: 'Save Video' })).not.toBeInTheDocument()
})

it('clears obsolete stored-preview errors when prepared replacement bytes become ready', async () => {
  vi.stubGlobal('MediaRecorder', class {})
  vi.stubGlobal('HTMLCanvasElement', { prototype: { captureStream: vi.fn() } })
  vi.stubGlobal('URL', { createObjectURL: vi.fn(() => 'blob:prepared'), revokeObjectURL: vi.fn() })
  readVideoDuration.mockResolvedValue(1)
  let finish, failStored
  prepareExerciseVideo.mockImplementation(() => new Promise(resolve => { finish = resolve }))
  render(<ExerciseVideoDialog open sessionId="session" exercise={{ id: 'exercise', name: 'Squat', videoAttached: true }}
    onLoad={() => new Promise((_resolve, reject) => { failStored = reject })} onSaved={vi.fn()} onRemoved={vi.fn()} onCancel={vi.fn()} />)
  fireEvent.change(screen.getByLabelText('Attach video for Squat'), { target: { files: [new File(['new'], 'new.webm', { type: 'video/webm' })] } })
  await waitFor(() => expect(finish).toBeTypeOf('function'))
  await act(async () => { failStored(new Error('Old download failed')) })
  await act(async () => { finish({ blob: new Blob(['prepared']), duration: 1, audioIncluded: false }) })
  expect(document.querySelector('video')).toHaveAttribute('src', 'blob:prepared')
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Save Video' })).toBeEnabled()
})

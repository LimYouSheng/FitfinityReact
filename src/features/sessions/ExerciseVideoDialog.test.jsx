import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
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

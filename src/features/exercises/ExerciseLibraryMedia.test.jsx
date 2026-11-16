import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { exerciseLibraryMedia } from '../../services/exerciseLibraryMedia.js'
import ExerciseLibraryMedia from './ExerciseLibraryMedia.jsx'
vi.mock('../../services/exerciseLibraryMedia.js', () => ({ exerciseLibraryMedia: { load: vi.fn() } }))
beforeEach(() => {
  vi.stubGlobal('URL', { createObjectURL: vi.fn().mockReturnValue('blob:preview'), revokeObjectURL: vi.fn() })
})
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.resetAllMocks() })
it('loads stored reference media and revokes its preview on unmount', async () => {
  exerciseLibraryMedia.load.mockResolvedValue(new Blob(['photo'], { type: 'image/png' }))
  const { unmount } = render(<ExerciseLibraryMedia onLoad={exerciseLibraryMedia.load} media={{ id: 'media-1', type: 'image/png' }} />)
  expect(await screen.findByRole('img')).toHaveAttribute('src', 'blob:preview')
  unmount(); expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:preview')
})
it('reports missing stored media and handles leaving before a pending load resolves', async () => {
  exerciseLibraryMedia.load.mockResolvedValueOnce(undefined)
  const first = render(<ExerciseLibraryMedia onLoad={exerciseLibraryMedia.load} media={{ id: 'missing', type: 'image/png' }} />)
  expect(await screen.findByRole('alert')).toHaveTextContent('not available'); first.unmount()
  let finish
  exerciseLibraryMedia.load.mockReturnValue(new Promise(resolve => { finish = resolve }))
  const second = render(<ExerciseLibraryMedia onLoad={exerciseLibraryMedia.load} media={{ id: 'later', type: 'image/png' }} />)
  second.unmount(); finish(new Blob(['photo']))
  await waitFor(() => expect(URL.createObjectURL).not.toHaveBeenCalled())
})

it('rejects unusable video metadata, preserves playable previews and recovers on replacement', async () => {
  const file = name => new File(['synthetic'], name, { type: 'video/webm' })
  const view = render(<ExerciseLibraryMedia file={file('initial.webm')} />)
  for (const [duration, videoWidth, videoHeight, invalid] of [
    [0, 1, 1, true], [NaN, 640, 360, true], [Infinity, 640, 360, false],
    [1, 0, 360, true], [1, 640, 0, true], [1, 640, 360, false],
  ]) {
    view.rerender(<ExerciseLibraryMedia file={file(`${duration}-${videoWidth}-${videoHeight}.webm`)} />)
    await waitFor(() => expect(view.container.querySelector('video')).not.toBeNull())
    const video = view.container.querySelector('video')
    Object.defineProperties(video, {
      duration: { value: duration }, videoWidth: { value: videoWidth }, videoHeight: { value: videoHeight },
    })
    fireEvent.loadedMetadata(video)
    if (invalid) {
      expect(screen.getByRole('alert')).toHaveTextContent('This browser cannot preview this video format.')
      expect(view.container.querySelector('video')).toBeNull()
    } else {
      expect(screen.queryByRole('alert')).not.toBeInTheDocument()
      expect(view.container.querySelector('video')).toBe(video)
      fireEvent.error(video)
      expect(screen.getByRole('alert')).toHaveTextContent('This browser cannot preview this video format.')
    }
  }
})

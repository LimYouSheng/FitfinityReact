import { cleanup, render, screen, waitFor } from '@testing-library/react'
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

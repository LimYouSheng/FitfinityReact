import { describe, expect, it } from 'vitest'
import {
  MAX_EXERCISE_VIDEO_BYTES,
  exerciseVideoCaption,
  exerciseVideoCaptionLines,
  exerciseVideoFileValidation,
  exerciseVideoValidation,
} from './exerciseVideo.js'

describe('exercise video rules', () => {
  it('uses planned details as the caption and enforces the upload limits', () => {
    expect(exerciseVideoCaption({
      name: 'Romanian Deadlift',
      weight: '40 kg',
      reps: '8',
      rounds: '2',
      rest: '60 sec',
      customDetails: [{ value: 'Controlled tempo' }],
    })).toBe('Romanian Deadlift — 40 kg · 8 reps · 2 rounds · 1 minute rest interval · Controlled tempo')

    expect(exerciseVideoCaptionLines({
      name: 'Romanian Deadlift',
      weight: '40 kg',
      reps: '8',
      rounds: '2',
      rest: '60 sec',
    })).toEqual(['Romanian Deadlift', '40 kg', '8 reps', '2 rounds', '1 minute rest interval'])

    expect(exerciseVideoFileValidation({ type: 'video/mp4', size: MAX_EXERCISE_VIDEO_BYTES })).toBeNull()
    expect(exerciseVideoFileValidation({ type: 'video/mp4', size: MAX_EXERCISE_VIDEO_BYTES + 1 })).toBe('Video must be 5 MB or smaller.')
    expect(exerciseVideoValidation({ type: 'video/mp4', size: MAX_EXERCISE_VIDEO_BYTES }, 60)).toBeNull()
    expect(exerciseVideoValidation({ type: 'video/mp4', size: MAX_EXERCISE_VIDEO_BYTES + 1 }, 60)).toBe('Video must be 5 MB or smaller.')
    expect(exerciseVideoValidation({ type: 'video/mp4', size: 10 }, 60.01)).toBe('Video must be 1 minute or shorter.')
    expect(exerciseVideoValidation({ type: 'image/png', size: 10 }, 1)).toBe('Choose a video file.')
  })
})

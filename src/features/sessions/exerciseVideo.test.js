import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  MAX_EXERCISE_VIDEO_BYTES,
  readVideoDuration,
  prepareExerciseVideo,
  exerciseVideoCaption,
  exerciseVideoCaptionLines,
  exerciseVideoFileValidation,
  exerciseVideoValidation,
} from './exerciseVideo.js'
import { exerciseVideoExpired, exerciseVideoExpiresAt } from '../../app/video.js'
import { normalizeExercisePlan } from '../../app/sessionRules.js'

describe('exercise video rules', () => {
  it('uses the recorded expiry, derives legacy expiry from policy, and expires exactly at the deadline', () => {
    const video = { attachedAt: '2026-09-09T10:15:00Z', expiresAt: '2026-09-16T10:15:00Z' }
    expect(exerciseVideoExpiresAt(video, 30)).toBe('2026-09-16T10:15:00.000Z')
    expect(exerciseVideoExpiresAt({ attachedAt: video.attachedAt }, 7)).toBe('2026-09-16T10:15:00.000Z')
    expect(exerciseVideoExpired(video, new Date('2026-09-16T10:14:59.999Z'), 7)).toBe(false)
    expect(exerciseVideoExpired(video, new Date('2026-09-16T10:15:00Z'), 7)).toBe(true)
    expect(exerciseVideoExpired({}, new Date('2026-09-09T10:15:00Z'), 7)).toBe(true)
    expect(exerciseVideoExpiresAt({ attachedAt: 'invalid' }, 7)).toBeNull()
    expect(exerciseVideoExpiresAt({ attachedAt: video.attachedAt }, 0)).toBeNull()
    const [normalized] = normalizeExercisePlan([{ name: 'Row', videoAttached: true, video: {
      ...video, duration: null, audioIncluded: null, processingStatus: 'deferred',
    } }])
    expect(normalized.video).toMatchObject({ ...video, duration: null, audioIncluded: null, processingStatus: 'deferred' })
  })
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
    expect(exerciseVideoFileValidation({ type: 'video/mp4', size: MAX_EXERCISE_VIDEO_BYTES + 1 })).toBe('Video must be 10 MB or smaller.')
    expect(exerciseVideoValidation({ type: 'video/mp4', size: MAX_EXERCISE_VIDEO_BYTES }, 60)).toBeNull()
    expect(exerciseVideoValidation({ type: 'video/mp4', size: MAX_EXERCISE_VIDEO_BYTES + 1 }, 60)).toBe('Video must be 10 MB or smaller.')
    expect(exerciseVideoValidation({ type: 'video/mp4', size: 10 }, 60.01)).toBe('Video must be 1 minute or shorter.')
    expect(exerciseVideoValidation({ type: 'image/png', size: 10 }, 1)).toBe('Choose a video file.')
  })
})


// Exercise the real duration/conversion functions, not mocked exports.
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })
function mediaHarness() {
  const create = document.createElement.bind(document)
  const video = create('video'), canvas = create('canvas')
  const context = { fillRect: vi.fn(), drawImage: vi.fn(), fillText: vi.fn(), measureText: () => ({ width: 1 }) }
  vi.spyOn(document, 'createElement').mockImplementation(tag => tag === 'video' ? video : tag === 'canvas' ? canvas : create(tag))
  const createObjectURL = vi.fn(() => 'blob:http://localhost/synthetic-media')
  const revokeObjectURL = vi.fn()
  vi.stubGlobal('URL', class extends URL { static createObjectURL = createObjectURL; static revokeObjectURL = revokeObjectURL })
  vi.spyOn(video, 'pause').mockImplementation(() => {})
  vi.spyOn(video, 'play').mockResolvedValue()
  vi.spyOn(canvas, 'getContext').mockReturnValue(context)
  Object.defineProperties(video, { duration: { value: 1 }, videoWidth: { value: 100 }, videoHeight: { value: 100 } })
  return { video, canvas, context, createObjectURL, revokeObjectURL }
}
const markup = '<svg onload="globalThis.mediaProbeExecuted=true"></svg>'

it('duration reader uses the exact File object as blob bytes and never its active contents or name as a URL', async () => {
  const { video, createObjectURL, revokeObjectURL } = mediaHarness()
  const file = new File([markup], 'javascript:globalThis.mediaProbeExecuted=true', { type: 'video/webm' })
  const result = readVideoDuration(file)
  expect(createObjectURL).toHaveBeenCalledExactlyOnceWith(file)
  expect(video.getAttribute('src')).toBe('blob:http://localhost/synthetic-media')
  video.onloadedmetadata()
  await expect(result).resolves.toBe(1)
  expect(revokeObjectURL).toHaveBeenCalledExactlyOnceWith('blob:http://localhost/synthetic-media')
  expect(video.hasAttribute('src')).toBe(false)
  expect(document.querySelector('[onload]')).toBeNull()
})

it('caption conversion uses a blob video source and canvas text for active captions, with abort cleanup', async () => {
  const { video, canvas, context, createObjectURL, revokeObjectURL } = mediaHarness()
  const stop = vi.fn()
  canvas.captureStream = vi.fn(() => ({ getTracks: () => [{ stop }] }))
  vi.stubGlobal('HTMLCanvasElement', { prototype: { captureStream: vi.fn() } })
  vi.stubGlobal('MediaRecorder', class { state = 'inactive'; start() { this.state = 'recording' } stop() { this.state = 'inactive' } })
  const file = new File([markup], 'javascript:globalThis.mediaProbeExecuted=true', { type: 'video/webm' })
  const controller = new AbortController()
  const result = prepareExerciseVideo(file, [markup], undefined, { signal: controller.signal })
  const rejection = expect(result).rejects.toThrow('The video could not be prepared.')
  expect(createObjectURL).toHaveBeenCalledExactlyOnceWith(file)
  expect(video.getAttribute('src')).toBe('blob:http://localhost/synthetic-media')
  await video.onloadedmetadata()
  expect(context.drawImage).toHaveBeenCalled()
  expect(context.fillText).toHaveBeenCalledWith(markup, expect.any(Number), expect.any(Number))
  expect(document.querySelector('[onload]')).toBeNull()
  controller.abort()
  await rejection
  expect(stop).toHaveBeenCalledOnce()
  expect(revokeObjectURL).toHaveBeenCalledExactlyOnceWith('blob:http://localhost/synthetic-media')
  expect(video.hasAttribute('src')).toBe(false)
})

export const MAX_EXERCISE_VIDEO_BYTES = 5 * 1024 * 1024
export const MAX_EXERCISE_VIDEO_SECONDS = 60

export function exerciseVideoFileValidation(file) {
  if (!file || !file.type?.startsWith('video/')) return 'Choose a video file.'
  if (!file.size) return 'Choose a non-empty video file.'
  if (file.size > MAX_EXERCISE_VIDEO_BYTES) return 'Video must be 5 MB or smaller.'
  return null
}

export function exerciseVideoValidation(file, durationSeconds) {
  const fileError = exerciseVideoFileValidation(file)
  if (fileError) return fileError
  if (!Number.isFinite(durationSeconds)) return 'The video duration could not be read.'
  if (durationSeconds <= 0) return 'Choose a video with a positive duration.'
  if (durationSeconds > MAX_EXERCISE_VIDEO_SECONDS) return 'Video must be 1 minute or shorter.'
  return null
}

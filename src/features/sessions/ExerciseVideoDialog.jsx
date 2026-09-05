import { useEffect, useState } from 'react'
import ConfirmDialog from '../../components/ConfirmDialog.jsx'
import {
  MAX_EXERCISE_VIDEO_SECONDS,
  compressVideoSilently,
  exerciseVideoCaption,
  exerciseVideoCaptionLines,
  exerciseVideoValidation,
  readVideoDuration,
} from './exerciseVideo.js'
import {
  loadExerciseVideoBlob,
  removeExerciseVideoBlob,
  saveExerciseVideoBlob,
} from '../../services/exerciseVideoStore.js'

const formatDuration = seconds => `${Math.max(0, Math.ceil(seconds))} sec`
const formatSize = bytes => `${(bytes / (1024 * 1024)).toFixed(2)} MB`

export default function ExerciseVideoDialog({ open, sessionId, exercise, onCancel, onSaved, onRemoved }) {
  const [mode, setMode] = useState('choose')
  const [candidate, setCandidate] = useState(null)
  const [previewUrl, setPreviewUrl] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [compressionProgress, setCompressionProgress] = useState(0)

  useEffect(() => {
    if (!open || !exercise) return undefined
    let cancelled = false
    setMode('choose')
    setCandidate(null)
    setPreviewUrl('')
    setError('')
    setSaving(false)
    setCompressionProgress(0)

    if (exercise.videoAttached) {
      loadExerciseVideoBlob(sessionId, exercise.id).then(blob => {
        if (!cancelled && blob) setPreviewUrl(URL.createObjectURL(blob))
      })
    }

    return () => {
      cancelled = true
    }
  }, [exercise, open, sessionId])

  useEffect(() => () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl)
  }, [previewUrl])

  if (!open || !exercise) return null

  const caption = exerciseVideoCaption(exercise)
  const captionLines = exerciseVideoCaptionLines(exercise)

  const chooseVideoFile = async (event, source) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    setError('')

    if (!file.type?.startsWith('video/')) {
      setError('Choose a video file.')
      return
    }

    try {
      const duration = await readVideoDuration(file)
      if (!Number.isFinite(duration)) throw new Error('The video duration could not be read.')
      if (duration > MAX_EXERCISE_VIDEO_SECONDS) throw new Error('Video must be 1 minute or shorter.')

      setMode('compressing')
      setCompressionProgress(0)
      const compressed = await compressVideoSilently(file, captionLines, setCompressionProgress)
      const validation = exerciseVideoValidation(compressed.blob, compressed.duration)
      if (validation) throw new Error(validation)
      if (previewUrl) URL.revokeObjectURL(previewUrl)
      setCandidate({ blob: compressed.blob, duration: compressed.duration, source, name: file.name || `${exercise.name}.webm` })
      setPreviewUrl(URL.createObjectURL(compressed.blob))
      setMode('preview')
    } catch (videoError) {
      setMode('choose')
      setError(videoError.message || 'The video could not be prepared.')
    }
  }

  const saveVideo = async () => {
    if (!candidate) return
    setSaving(true)
    try {
      await saveExerciseVideoBlob(sessionId, exercise.id, candidate.blob)
      await onSaved({
        name: candidate.name,
        type: candidate.blob.type,
        size: candidate.blob.size,
        duration: Math.ceil(candidate.duration),
        source: candidate.source,
        caption,
        audioIncluded: false,
        attachedAt: new Date().toISOString(),
      })
      onCancel()
    } catch (saveError) {
      setError(saveError.message || 'The video could not be saved.')
    } finally {
      setSaving(false)
    }
  }

  const removeVideo = async () => {
    setSaving(true)
    try {
      await removeExerciseVideoBlob(sessionId, exercise.id)
      await onRemoved()
      onCancel()
    } catch (removeError) {
      setError(removeError.message || 'The video could not be removed.')
      setMode('choose')
    } finally {
      setSaving(false)
    }
  }

  const removing = mode === 'remove'

  return (
    <ConfirmDialog
      open
      title={`Video · ${exercise.name}`}
      confirmLabel={removing ? (saving ? 'Removing…' : 'Remove Video') : (saving ? 'Saving…' : 'Save Video')}
      confirmDisabled={saving || (!removing && !candidate)}
      hideConfirm={!candidate && !removing}
      danger={removing}
      onCancel={onCancel}
      onConfirm={removing ? removeVideo : saveVideo}
    >
      {removing ? (
        <p>Remove the saved video from <strong>{exercise.name}</strong>? The planned exercise details remain unchanged.</p>
      ) : (
        <div className="exercise-video-dialog">
          <div className="exercise-video-caption">
            <span>Video caption</span>
            <strong>{caption}</strong>
          </div>

          {mode === 'compressing' ? (
            <div className="exercise-video-compressing" role="status">
              <strong>Preparing silent video… {compressionProgress}%</strong>
              <span><i style={{ width: `${compressionProgress}%` }} /></span>
              <p>Keep this popup open. Processing takes approximately the length of the clip.</p>
            </div>
          ) : previewUrl ? (
            <video className="exercise-video-preview" src={previewUrl} controls muted playsInline />
          ) : exercise.videoAttached ? (
            <div className="notice">A saved video is attached. Its local preview is unavailable in this browser session.</div>
          ) : null}

          {mode !== 'compressing' && !candidate && (
            <div className="exercise-video-choices">
              <label className="primary-button exercise-video-file-action">
                Record new video
                <input
                  type="file"
                  accept="video/*"
                  capture="environment"
                  aria-label={`Record new video for ${exercise.name}`}
                  onChange={event => chooseVideoFile(event, 'recorded')}
                />
              </label>
              <label className="secondary-button exercise-video-file-action">
                Attach video
                <input
                  type="file"
                  accept="video/*"
                  aria-label={`Attach video for ${exercise.name}`}
                  onChange={event => chooseVideoFile(event, 'attached')}
                />
              </label>
            </div>
          )}

          {candidate && (
            <dl className="exercise-video-meta">
              <div><dt>Source</dt><dd>{candidate.source === 'recorded' ? 'Camera recording' : candidate.name}</dd></div>
              <div><dt>Duration</dt><dd>{formatDuration(candidate.duration)}</dd></div>
              <div><dt>Size</dt><dd>{formatSize(candidate.blob.size)}</dd></div>
              <div><dt>Audio</dt><dd>None</dd></div>
            </dl>
          )}

          {error && <p className="validation-copy" role="alert">{error}</p>}
          <p className="helper">Maximum 1 minute. Record or attach a clip; it will be converted to a silent file below 5 MB with the planned exercise details on a white panel.</p>

          {exercise.videoAttached && !candidate && (
            <button type="button" className="text-action exercise-video-remove" onClick={() => setMode('remove')}>Remove saved video</button>
          )}
        </div>
      )}
    </ConfirmDialog>
  )
}

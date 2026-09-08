import { useEffect, useRef, useState } from 'react'
import ConfirmDialog from '../../components/ConfirmDialog.jsx'
import {
  compressVideoSilently,
  exerciseVideoCaption,
  exerciseVideoCaptionLines,
  exerciseVideoFileValidation,
  exerciseVideoValidation,
  readVideoDuration,
} from './exerciseVideo.js'


const formatDuration = seconds => `${Math.max(0, Math.ceil(seconds))} sec`
const formatSize = bytes => `${(bytes / (1024 * 1024)).toFixed(2)} MB`
const browserCanProcessVideo = () => Boolean(
  globalThis.MediaRecorder && globalThis.HTMLCanvasElement?.prototype?.captureStream,
)

export default function ExerciseVideoDialog({ open, sessionId, exercise, editable = true, onLoad, onCancel, onSaved, onRemoved }) {
  const processing = useRef(null)
  const committing = useRef(false)
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
      onLoad().then(blob => {
        if (!cancelled && blob) setPreviewUrl(URL.createObjectURL(blob))
      }).catch(failure => { if (!cancelled) setError(failure.message || 'The stored video could not be loaded.') })
    }

    return () => {
      cancelled = true
      processing.current?.abort()
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
    processing.current?.abort()
    const operation = new AbortController()
    processing.current = operation

    const fileError = exerciseVideoFileValidation(file)
    if (fileError) {
      setError(fileError)
      return
    }

    const keepOriginalForDeferredProcessing = duration => {
      if (previewUrl) URL.revokeObjectURL(previewUrl)
      setCandidate({
        blob: file,
        duration: Number.isFinite(duration) ? duration : null,
        source,
        name: file.name || `${exercise.name}.video`,
        processed: false,
      })
      setPreviewUrl(URL.createObjectURL(file))
      setMode('preview')
    }

    // Browser-side captioning/transcoding is an enhancement, not the upload
    // boundary. WebKit builds without the required media APIs keep the
    // original file for the backend media pipeline instead.
    if (!browserCanProcessVideo()) {
      keepOriginalForDeferredProcessing(null)
      return
    }

    let metadataTimer = 0
    let duration = null
    try {
      duration = await Promise.race([
        readVideoDuration(file, { signal: operation.signal }).catch(() => null),
        new Promise(resolve => { metadataTimer = window.setTimeout(() => resolve(null), 1500) }),
      ])
    } finally {
      if (metadataTimer) window.clearTimeout(metadataTimer)
    }
    if (operation.signal.aborted) return

    // Some WebKit/codec combinations expose the browser APIs but cannot read
    // this file reliably. Do not block the upload boundary on local decoding.
    if (!Number.isFinite(duration)) {
      operation.abort()
      keepOriginalForDeferredProcessing(null)
      return
    }

    const sourceValidation = exerciseVideoValidation(file, duration)
    if (sourceValidation) {
      setError(sourceValidation)
      return
    }

    try {
      setMode('compressing')
      setCompressionProgress(0)
      const compressed = await compressVideoSilently(file, captionLines, setCompressionProgress, { signal: operation.signal })
      if (operation.signal.aborted) return
      const validation = exerciseVideoValidation(compressed.blob, compressed.duration)
      if (validation) throw new Error(validation)
      if (previewUrl) URL.revokeObjectURL(previewUrl)
      setCandidate({
        blob: compressed.blob,
        duration: compressed.duration,
        source,
        name: file.name || `${exercise.name}.webm`,
        processed: true,
      })
      setPreviewUrl(URL.createObjectURL(compressed.blob))
      setMode('preview')
    } catch (videoError) {
      if (operation.signal.aborted) return
      // The validated source can still be uploaded and processed later.
      keepOriginalForDeferredProcessing(duration)
    }
  }


  const saveVideo = async () => {
    if (!candidate || committing.current) return
    committing.current = true
    setSaving(true)
    try {
      await onSaved(candidate.blob, {
        name: candidate.name,
        type: candidate.blob.type,
        size: candidate.blob.size,
        duration: Number.isFinite(candidate.duration) ? Math.ceil(candidate.duration) : null,
        source: candidate.source,
        caption,
        audioIncluded: candidate.processed ? false : null,
        processingStatus: candidate.processed ? 'complete' : 'deferred',
        attachedAt: new Date().toISOString(),
      })
      onCancel()
    } catch (saveError) {
      setError(saveError.message || 'The video could not be saved.')
    } finally {
      committing.current = false
      setSaving(false)
    }
  }

  const removeVideo = async () => {
    if (committing.current) return
    committing.current = true
    setSaving(true)
    try {
      await onRemoved()
      onCancel()
    } catch (removeError) {
      setError(removeError.message || 'The video could not be removed.')
      setMode('choose')
    } finally {
      committing.current = false
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
      onCancel={() => { if (!committing.current) { processing.current?.abort(); onCancel() } }}
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
            <video className="exercise-video-preview" src={previewUrl} controls muted playsInline preload="none" />
          ) : exercise.videoAttached ? (
            <div className="notice">A saved video is attached. Its local preview is unavailable in this browser session.</div>
          ) : null}

          {editable && mode !== 'compressing' && !candidate && (
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
              <div><dt>Duration</dt><dd>{Number.isFinite(candidate.duration) ? formatDuration(candidate.duration) : 'Pending'}</dd></div>
              <div><dt>Size</dt><dd>{formatSize(candidate.blob.size)}</dd></div>
              <div><dt>Audio</dt><dd>{candidate.processed ? 'Removed' : 'Pending removal'}</dd></div>
            </dl>
          )}

          {error && <p className="validation-copy" role="alert">{error}</p>}
          <p className="helper">Maximum 1 minute · Under 5 MB · Final video is silent</p>

          {editable && exercise.videoAttached && !candidate && (
            <button type="button" className="text-action exercise-video-remove" onClick={() => setMode('remove')}>Remove saved video</button>
          )}
        </div>
      )}
    </ConfirmDialog>
  )
}

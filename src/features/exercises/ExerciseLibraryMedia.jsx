import { useEffect, useEffectEvent, useState } from 'react'

export default function ExerciseLibraryMedia({ media, file, onLoad }) {
  const [url, setUrl] = useState('')
  const [error, setError] = useState('')
  const mediaId = media?.id
  // Reload on resource changes, with the latest transport callback.
  const loadMedia = useEffectEvent(id => onLoad(id))
  useEffect(() => {
    let cancelled = false, createdUrl = ''
    setUrl(''); setError('')
    if (!file && !mediaId) return
    const load = async () => {
      try {
        const blob = file || await loadMedia(mediaId)
        if (cancelled) return
        if (!blob) throw new Error('This attachment is not available in this browser.')
        createdUrl = URL.createObjectURL(blob)
        setUrl(createdUrl)
      } catch (failure) { if (!cancelled) setError(failure.message || 'Could not load this attachment.') }
    }
    load()
    return () => { cancelled = true; if (createdUrl) URL.revokeObjectURL(createdUrl) }
  }, [file, mediaId])
  if (!media && !file) return null
  if (error) return <p className="validation-copy" role="alert">{error}</p>
  if (!url) return <p className="muted">Loading attachment…</p>
  const type = file?.type || media.type
  const unavailable = () => setError('This browser cannot preview this video format.')
  const checkVideoMetadata = event => {
    const video = event.currentTarget
    // Some decoders expose image payloads as zero-duration video tracks instead
    // of raising an error. Metadata alone does not prove a playable video.
    // WebM may initially expose Infinity until its duration is discovered.
    if (!(video.duration > 0) || video.videoWidth <= 0 || video.videoHeight <= 0) unavailable()
  }
  return <div className="library-media-preview">
    {type.startsWith('image/') ? <img src={url} alt="Exercise reference" /> : <video src={url} controls playsInline preload="none" onLoadedMetadata={checkVideoMetadata} onError={unavailable} />}
  </div>
}

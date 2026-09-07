import { useEffect, useState } from 'react'
import { exerciseLibraryMedia } from '../../services/exerciseLibraryMedia.js'

export default function ExerciseLibraryMedia({ media, file }) {
  const [url, setUrl] = useState('')
  const [error, setError] = useState('')
  useEffect(() => {
    let cancelled = false, createdUrl = ''
    setUrl(''); setError('')
    if (!file && !media) return
    const load = async () => {
      try {
        const blob = file || await exerciseLibraryMedia.load(media.id)
        if (cancelled) return
        if (!blob) throw new Error('This attachment is not available in this browser.')
        createdUrl = URL.createObjectURL(blob)
        setUrl(createdUrl)
      } catch (failure) { if (!cancelled) setError(failure.message || 'Could not load this attachment.') }
    }
    load()
    return () => { cancelled = true; if (createdUrl) URL.revokeObjectURL(createdUrl) }
  }, [file, media?.id])
  if (!media && !file) return null
  if (error) return <p className="validation-copy" role="alert">{error}</p>
  if (!url) return <p className="muted">Loading attachment…</p>
  const type = file?.type || media.type
  return <div className="library-media-preview">
    {type.startsWith('image/') ? <img src={url} alt="Exercise reference" /> : <video src={url} controls playsInline preload="metadata" onError={() => setError('This browser cannot preview this video format.')} />}
  </div>
}

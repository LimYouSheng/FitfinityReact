export const MAX_EXERCISE_VIDEO_BYTES = 5 * 1024 * 1024
export const MAX_EXERCISE_VIDEO_SECONDS = 60

const detailValue = detail => typeof detail === 'string' ? detail : detail?.value

function restCaption(rest) {
  if (!rest) return ''
  const seconds = Number.parseInt(rest, 10)
  if (!Number.isFinite(seconds)) return `${rest} rest interval`
  if (seconds === 60) return '1 minute rest interval'
  if (seconds > 60 && seconds % 60 === 0) return `${seconds / 60} minutes rest interval`
  return `${seconds} seconds rest interval`
}

export function exerciseVideoCaptionLines(exercise) {
  return [
    exercise.name,
    exercise.weight,
    exercise.reps && `${exercise.reps} reps`,
    exercise.rounds && `${exercise.rounds} rounds`,
    restCaption(exercise.rest),
    ...(exercise.customDetails ?? []).map(detailValue),
  ].filter(Boolean)
}

export function exerciseVideoCaption(exercise) {
  const [name, ...details] = exerciseVideoCaptionLines(exercise)
  return `${name}${details.length ? ` — ${details.join(' · ')}` : ''}`
}

export function exerciseVideoValidation(file, durationSeconds) {
  if (!file || !file.type?.startsWith('video/')) return 'Choose a video file.'
  if (file.size > MAX_EXERCISE_VIDEO_BYTES) return 'Video must be 5 MB or smaller.'
  if (!Number.isFinite(durationSeconds)) return 'The video duration could not be read.'
  if (durationSeconds > MAX_EXERCISE_VIDEO_SECONDS) return 'Video must be 1 minute or shorter.'
  return null
}

export function readVideoDuration(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file)
    const video = document.createElement('video')
    const finish = value => {
      video.onloadedmetadata = null
      video.onerror = null
      video.removeAttribute('src')
      URL.revokeObjectURL(url)
      value instanceof Error ? reject(value) : resolve(value)
    }

    video.preload = 'metadata'
    video.muted = true
    video.playsInline = true
    video.onloadedmetadata = () => finish(video.duration)
    video.onerror = () => finish(new Error('The video could not be read.'))
    video.src = url
  })
}

function recorderMimeType() {
  const choices = ['video/webm;codecs=vp8', 'video/webm', 'video/mp4']
  return choices.find(type => globalThis.MediaRecorder?.isTypeSupported?.(type)) ?? ''
}

function drawCoveredVideo(context, video, x, y, width, height) {
  const sourceRatio = video.videoWidth / video.videoHeight
  const targetRatio = width / height
  let sourceX = 0
  let sourceY = 0
  let sourceWidth = video.videoWidth
  let sourceHeight = video.videoHeight

  if (sourceRatio > targetRatio) {
    sourceWidth = video.videoHeight * targetRatio
    sourceX = (video.videoWidth - sourceWidth) / 2
  } else {
    sourceHeight = video.videoWidth / targetRatio
    sourceY = (video.videoHeight - sourceHeight) / 2
  }

  context.drawImage(video, sourceX, sourceY, sourceWidth, sourceHeight, x, y, width, height)
}

function wrapCaptionLine(context, value, maxWidth) {
  const words = String(value).trim().split(/\s+/)
  const lines = []
  let line = ''
  words.forEach(word => {
    const candidate = line ? `${line} ${word}` : word
    if (line && context.measureText(candidate).width > maxWidth) {
      lines.push(line)
      line = word
    } else {
      line = candidate
    }
  })
  if (line) lines.push(line)
  return lines
}

function drawCaptionPanel(context, captionLines, x, width, height) {
  context.fillStyle = '#ffffff'
  context.fillRect(x, 0, width, height)
  context.fillStyle = '#111111'
  context.textAlign = 'center'
  context.textBaseline = 'middle'

  const renderedLines = []
  captionLines.forEach((line, index) => {
    context.font = `${index === 0 ? 700 : 650} ${index === 0 ? 34 : 28}px Arial, sans-serif`
    wrapCaptionLine(context, line, width - 64).forEach(part => renderedLines.push({ part, heading: index === 0 }))
  })

  const lineHeight = 48
  const totalHeight = renderedLines.length * lineHeight
  let y = (height - totalHeight) / 2 + lineHeight / 2
  renderedLines.forEach(({ part, heading }) => {
    context.font = `${heading ? 700 : 650} ${heading ? 34 : 28}px Arial, sans-serif`
    context.fillText(part, x + width / 2, y)
    y += lineHeight
  })
}

export function compressVideoSilently(file, captionLines, onProgress = () => {}) {
  return new Promise((resolve, reject) => {
    if (!globalThis.MediaRecorder || !globalThis.HTMLCanvasElement?.prototype.captureStream) {
      reject(new Error('Video preparation is not supported in this browser.'))
      return
    }

    const sourceUrl = URL.createObjectURL(file)
    const video = document.createElement('video')
    const canvas = document.createElement('canvas')
    const context = canvas.getContext('2d')
    let recorder
    let animationFrame = 0
    let settled = false
    const chunks = []

    const cleanUp = () => {
      window.cancelAnimationFrame(animationFrame)
      video.onloadedmetadata = null
      video.onended = null
      video.onerror = null
      video.pause()
      video.removeAttribute('src')
      URL.revokeObjectURL(sourceUrl)
    }

    const fail = error => {
      if (settled) return
      settled = true
      cleanUp()
      reject(error instanceof Error ? error : new Error('The video could not be prepared.'))
    }

    if (!context) {
      fail(new Error('The video canvas could not be created.'))
      return
    }

    const drawFrame = () => {
      drawCoveredVideo(context, video, 0, 0, canvas.width / 2, canvas.height)
      drawCaptionPanel(context, captionLines, canvas.width / 2, canvas.width / 2, canvas.height)
    }

    video.preload = 'auto'
    video.muted = true
    video.playsInline = true
    video.onerror = () => fail(new Error('The video could not be read.'))
    video.onloadedmetadata = async () => {
      const duration = video.duration
      if (!Number.isFinite(duration) || duration <= 0) {
        fail(new Error('The video duration could not be read.'))
        return
      }
      if (duration > MAX_EXERCISE_VIDEO_SECONDS) {
        fail(new Error('Video must be 1 minute or shorter.'))
        return
      }

      canvas.width = 720
      canvas.height = 720
      const stream = canvas.captureStream(24)
      const mimeType = recorderMimeType()
      const targetBytes = 4.25 * 1024 * 1024
      const videoBitsPerSecond = Math.min(600000, Math.max(180000, Math.floor((targetBytes * 8) / duration)))

      try {
        recorder = new MediaRecorder(stream, {
          ...(mimeType ? { mimeType } : {}),
          videoBitsPerSecond,
        })
      } catch {
        fail(new Error('Video preparation could not start in this browser.'))
        return
      }

      recorder.ondataavailable = event => {
        if (event.data.size) chunks.push(event.data)
      }
      recorder.onerror = () => fail(new Error('The video could not be prepared.'))
      recorder.onstop = () => {
        if (settled) return
        settled = true
        const blob = new Blob(chunks, { type: recorder.mimeType || mimeType || 'video/webm' })
        cleanUp()
        if (blob.size > MAX_EXERCISE_VIDEO_BYTES) {
          reject(new Error('The prepared video is still above 5 MB. Try a lower-resolution clip.'))
          return
        }
        onProgress(100)
        resolve({ blob, duration })
      }

      const render = () => {
        if (video.ended || video.paused) return
        drawFrame()
        onProgress(Math.min(99, Math.round((video.currentTime / duration) * 100)))
        animationFrame = window.requestAnimationFrame(render)
      }

      video.onended = () => {
        drawFrame()
        if (recorder.state === 'recording') recorder.stop()
      }

      try {
        drawFrame()
        recorder.start(500)
        await video.play()
        render()
      } catch {
        if (recorder.state === 'recording') recorder.stop()
        fail(new Error('The browser could not play the video for preparation.'))
      }
    }
    video.src = sourceUrl
  })
}

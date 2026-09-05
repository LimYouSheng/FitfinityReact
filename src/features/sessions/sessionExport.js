import { exerciseVideoCaption } from './exerciseVideo.js'

export function sessionSummaryWhatsAppText(client, session, summary, videos = []) {
  const lines = [
    `${client.name} — Session Summary`,
    '',
    summary.trim(),
  ]

  if (videos.length) {
    lines.push('', `Exercise videos (${videos.length})`)
    videos.forEach(item => lines.push(`• ${exerciseVideoCaption(item)}`))
  }

  lines.push('', `Session ${session.sessionNumber} / ${session.packageTotal}`)
  return lines.join('\n')
}

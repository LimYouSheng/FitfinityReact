import { renderToStaticMarkup } from 'react-dom/server'
import { exerciseVideoCaption } from './exerciseVideo.js'
import { packageForRecord } from '../../app/clientPackages.js'
import { formatDate } from '../../utils/date.js'
import { wrapText } from '../../utils/reportText.js'
import { renderReportPdf } from '../../utils/reportPdf.js'

export function sessionSummaryText(client, session, summary, videos = []) {
  const purchased = packageForRecord(client, session)
  const lines = [
    `${client.name} — Session Summary`,
    `${formatDate(session.date)} · ${session.from}–${session.to}`,
    `Session ${session.sessionNumber} / ${purchased?.total ?? '—'}`,
  ]
  if (purchased) lines.push(`${purchased.name ?? `${purchased.total} Sessions`} · ${formatDate(purchased.startDate)} – ${formatDate(purchased.endDate)}`)
  if (summary?.trim()) lines.push('', 'Client-Facing Summary', summary.trim())
  if (videos.length) {
    lines.push('', `Selected video captions (${videos.length})`)
    videos.forEach(item => lines.push(`• ${exerciseVideoCaption(item)}`))
  }
  return lines.join('\n')
}

export function sessionSummaryPages({ client, session, summary, videos }) {
  const lines = sessionSummaryText(client, session, summary, videos).split('\n').flatMap(line => wrapText(line, 82))
  const pages = []
  const perPage = 42
  for (let offset = 0; offset < lines.length; offset += perPage) {
    const pageLines = lines.slice(offset, offset + perPage)
    pages.push({ width: 1000, height: 1414, svg: renderToStaticMarkup(
      <svg xmlns="http://www.w3.org/2000/svg" width="1000" height="1414" viewBox="0 0 1000 1414" fontFamily="Arial, sans-serif">
        <rect width="1000" height="1414" fill="#050509" />
        <text x="48" y="55" fill="#cfd5ff" fontSize="18" fontWeight="800">FITFINITY / SESSION SUMMARY</text>
        {pageLines.map((line, index) => <text key={index} x="48" y={108 + index * 28} fill="#f7f7f8" fontSize="18">{line}</text>)}
        <text x="952" y="1370" textAnchor="end" fill="#a9b2c2" fontSize="13">{offset / perPage + 1} / {Math.ceil(lines.length / perPage)}</text>
      </svg>,
    ) })
  }
  return pages
}

export function sessionSummaryPdf(input) {
  return renderReportPdf(sessionSummaryPages(input), `${input.client.name} - Session Summary`)
}

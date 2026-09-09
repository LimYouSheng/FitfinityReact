import { renderToStaticMarkup } from 'react-dom/server'
import StrengthProgressChart from './StrengthProgressChart.jsx'
import { PROGRESS_FONT, progressNumber, progressSummary, progressChange } from './progressChart.js'
import { formatDate, formatTimestamp } from '../../utils/date.js'
import { reportPdfDocument } from './reportPdfDocument.js'

const PAGE = { width: 1000, height: 1414, margin: 48, rowHeight: 34 }

// Break at words where possible, including long names without spaces. Array.from
// keeps surrogate pairs intact, and React escapes all names before SVG rendering.
function wrapText(value, limit) {
  const width = text => Array.from(text).reduce((sum, letter) => sum + (/[^\u0000-\u024f]/u.test(letter) ? 2 : /[MW@]/.test(letter) ? 1.5 : 1), 0)
  const lines = []
  let line = ''
  for (const word of String(value).split(/\s+/)) {
    if (line && width(`${line} ${word}`) > limit) { lines.push(line); line = '' }
    if (line) line += ' '
    for (const letter of Array.from(word)) {
      if (line && width(line + letter) > limit) { lines.push(line); line = '' }
      line += letter
    }
  }
  if (line) lines.push(line)
  return lines.length ? lines : ['']
}

export function progressReportPages(client, { at = new Date().toISOString(), timeZone } = {}) {
  const pages = []
  const clientLines = wrapText(client.name, 40)
  for (const exercise of client.strengthProgress ?? []) {
    if (!exercise.points?.length) continue
    const nameLines = wrapText(exercise.name, 64)
    const chartTop = 224 + clientLines.length * 40 + nameLines.length * 26
    const tableTop = chartTop + 334
    const rowsPerPage = Math.max(1, Math.floor((PAGE.height - 100 - tableTop - 40) / PAGE.rowHeight))
    for (let offset = 0; offset < exercise.points.length; offset += rowsPerPage) {
      pages.push({ exercise, clientLines, nameLines, chartTop, tableTop, offset, rows: exercise.points.slice(offset, offset + rowsPerPage) })
    }
  }
  if (!pages.length) throw new Error('No completed exercise loads are available to export.')
  return pages.map((page, index) => ({
    width: PAGE.width, height: PAGE.height,
    svg: renderToStaticMarkup(<ReportPage {...page} at={at} timeZone={timeZone} pageNumber={index + 1} pageCount={pages.length} />),
  }))
}

function ReportPage({ exercise, clientLines, nameLines, chartTop, tableTop, offset, rows, at, timeZone, pageNumber, pageCount }) {
  const summary = progressSummary(exercise)
  const headerTop = 92 + clientLines.length * 40
  const summaryTop = chartTop - 42
  return <svg xmlns="http://www.w3.org/2000/svg" width={PAGE.width} height={PAGE.height} viewBox={`0 0 ${PAGE.width} ${PAGE.height}`} fontFamily={PROGRESS_FONT}>
    <rect width={PAGE.width} height={PAGE.height} fill="#050509" />
    <text x="48" y="55" fill="#cfd5ff" fontSize="18" fontWeight="800">FITFINITY / STRENGTH PROGRESS</text>
    {clientLines.map((line, index) => <text key={index} x="48" y={104 + index * 40} fill="#f7f7f8" fontSize="32" fontWeight="800">{line}</text>)}
    <text x="48" y={headerTop + 4} fill="#a9b2c2" fontSize="14">{formatTimestamp(at, timeZone)}</text>
    <rect x="32" y={headerTop + 28} width="936" height={tableTop - headerTop - 80} rx="12" fill="#111319" stroke="#2b2e37" />
    {nameLines.map((line, index) => <text key={index} x="52" y={headerTop + 56 + index * 26} fill="#c2c8d3" fontSize="19" fontWeight="800">{line}</text>)}
    <text x="52" y={summaryTop} fill="#f7f7f8" fontSize="30" fontWeight="800">{progressNumber(summary.latest)}<tspan dx="5" fill="#8f98a8" fontSize="14">kg</tspan></text>
    <text x="534" y={summaryTop - 25} fill="#7f8796" fontSize="11" fontWeight="800">CHANGE</text>
    <text x="534" y={summaryTop} fill="#7ae5b2" fontSize="20" fontWeight="800">{progressChange(summary.change)} kg</text>
    <text x="780" y={summaryTop - 25} fill="#7f8796" fontSize="11" fontWeight="800">COMPLETED</text>
    <text x="780" y={summaryTop} fill="#f7f7f8" fontSize="20" fontWeight="800">{exercise.points.length}</text>
    <StrengthProgressChart exercise={exercise} x="48" y={chartTop - 16} width="904" height="281.24" />
    <text x="48" y={tableTop - 18} fill="#cfd5ff" fontSize="17" fontWeight="800">Recorded exercises{offset ? ' (continued)' : ''}</text>
    <rect x="32" y={tableTop} width="936" height="38" rx="6" fill="#171a22" />
    {['Date', 'Load (kg)', 'Sets', 'Reps'].map((label, index) => <text key={label} x={[48, 440, 670, 830][index]} y={tableTop + 25} fill="#a9b2c2" fontSize="14" fontWeight="800">{label}</text>)}
    {rows.map((point, index) => {
      const y = tableTop + 64 + index * PAGE.rowHeight
      const values = [formatDate(point.date), progressNumber(point.load), point.sets ?? exercise.sets ?? '—', point.reps ?? exercise.reps ?? '—']
      return <g key={`${point.id ?? point.date}-${offset + index}`}>
        {values.map((value, column) => <text key={column} x={[48, 440, 670, 830][column]} y={y} fill="#e8ebf2" fontSize="15">{value}</text>)}
        <line x1="48" x2="952" y1={y + 12} y2={y + 12} stroke="#2b2e37" />
      </g>
    })}
    <text x="48" y="1370" fill="#747d8d" fontSize="13">Completed exercise loads over time</text>
    <text x="952" y="1370" textAnchor="end" fill="#747d8d" fontSize="13">{pageNumber} / {pageCount}</text>
  </svg>
}

async function rasterizePage(page) {
  const url = URL.createObjectURL(new Blob([page.svg], { type: 'image/svg+xml;charset=utf-8' }))
  const image = new Image()
  const canvas = document.createElement('canvas')
  try {
    await new Promise((resolve, reject) => {
      image.onload = resolve
      image.onerror = () => reject(new Error('The progress chart could not be rendered. Please try exporting again.'))
      image.src = url
    })
    canvas.width = page.width * 2; canvas.height = page.height * 2
    const context = canvas.getContext('2d')
    if (!context) throw new Error('Your browser could not create the progress report. Please try another browser.')
    context.drawImage(image, 0, 0, canvas.width, canvas.height)
    const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.95))
    if (!blob || blob.type !== 'image/jpeg') throw new Error('Your browser could not encode the progress report. Please try another browser.')
    return { width: canvas.width, height: canvas.height, bytes: new Uint8Array(await blob.arrayBuffer()) }
  } finally {
    URL.revokeObjectURL(url)
    image.onload = null; image.onerror = null
    canvas.width = 0; canvas.height = 0
  }
}

export async function progressReportPdf(client, options) {
  await document.fonts?.ready
  const pages = []
  // Serial rasterization releases each canvas before creating the next, keeping
  // mobile memory bounded even when a client has many exercises or results.
  for (const page of progressReportPages(client, options)) pages.push(await rasterizePage(page))
  return reportPdfDocument(pages, `${client.name} - Progress Report`)
}

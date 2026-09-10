import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { progressReportFilename } from './progressReport.js'
import { progressReportPages } from './progressReportPdf.jsx'
import { reportPdfDocument } from './reportPdfDocument.js'
import StrengthProgressChart from './StrengthProgressChart.jsx'
import { progressChange } from './progressChart.js'

const client = {
  name: 'Amanda Lim',
  strengthProgress: [{
    id: 'squat', name: 'Smith back squat', sets: 3, reps: 8,
    points: [{ id: 'p1', date: '2026-07-10', load: 20 }, { id: 'p2', date: '2026-07-20', load: 25, reps: 10 }],
  }],
}
const options = { at: '2026-09-09T04:00:00Z', timeZone: 'Asia/Singapore' }
const parse = svg => new DOMParser().parseFromString(svg, 'image/svg+xml')
const readBytes = blob => new Promise(resolve => {
  const reader = new FileReader()
  reader.onload = () => resolve(new Uint8Array(reader.result))
  reader.readAsArrayBuffer(blob)
})

describe('progress report export', () => {
  it('exports every exercise and its recorded loads, dates, sets and reps in a PDF visual', () => {
    const input = { ...client, strengthProgress: [...client.strengthProgress, {
      id: 'row', name: 'Cable row', points: [{ id: 'r1', date: '2026-08-10', load: 35, reps: 12, sets: 4 }],
    }] }
    const pages = progressReportPages(input, options)
    expect(progressReportFilename(client)).toBe('amanda-lim-progress-report.pdf')
    expect(pages).toHaveLength(2)
    const texts = pages.map(page => parse(page.svg).documentElement.textContent)
    expect(texts[0]).toContain('Smith back squat')
    expect(texts[0]).toContain('10 Jul 20262038')
    expect(texts[0]).toContain('20 Jul 202625310')
    expect(texts[0]).toContain('12:00')
    expect(texts[1]).toContain('Cable row')
    expect(texts[1]).toContain('10 Aug 202635412')
  })

  it('uses exactly the app chart for each exercise, including one point and decreasing loads', () => {
    for (const points of [client.strengthProgress[0].points, [client.strengthProgress[0].points[0]], [
      { id: 'high', date: '2026-07-10', load: 25 }, { id: 'low', date: '2026-07-20', load: 20 },
    ]]) {
      const exercise = { ...client.strengthProgress[0], points }
      const app = parse(renderToStaticMarkup(createElement(StrengthProgressChart, { exercise }))).documentElement
      const report = parse(progressReportPages({ ...client, strengthProgress: [exercise] }, options)[0].svg).querySelector('.strength-chart')
      const normalize = element => element.innerHTML.replace(/strength-(line|area)-[a-zA-Z0-9_-]+/g, 'strength-$1')
      expect(normalize(report)).toBe(normalize(app))
      expect(report.getAttribute('viewBox')).toBe(app.getAttribute('viewBox'))
      expect(report.getAttribute('font-family')).toBe(app.getAttribute('font-family'))
      expect(app.querySelectorAll('circle')).toHaveLength(points.length)
      expect(Array.from(app.querySelectorAll('g > title'), node => node.textContent)).toEqual(points.map(point => `${point.date === '2026-07-10' ? '10' : '20'} Jul 2026: ${point.load} kg`))
      expect(app.querySelectorAll('polygon, polyline')).toHaveLength(points.length === 1 ? 0 : 2)
    }
    expect(progressChange(-5)).toBe('-5')
  })

  it('paginates all records and safely renders long unicode names and text without truncating records', () => {
    const exercise = { ...client.strengthProgress[0], name: '练习 <script>alert(1)</script> '.repeat(4), points: Array.from({ length: 80 }, (_, index) => ({
      id: `p${index}`, date: '2026-07-10', load: index, reps: index + 1, sets: 3,
    })) }
    const pages = progressReportPages({ ...client, name: '陈 & Amanda 😀', strengthProgress: [exercise] }, options)
    expect(pages.length).toBeGreaterThan(1)
    const documents = pages.map(page => parse(page.svg))
    const rows = documents.flatMap(document => Array.from(document.querySelectorAll('g')).filter(group => group.querySelectorAll(':scope > text').length === 4))
    expect(rows).toHaveLength(80)
    expect(rows.map(row => row.querySelectorAll('text')[1].textContent)).toEqual(Array.from({ length: 80 }, (_, index) => String(index)))
    for (const document of documents) {
      expect(document.querySelector('script, parsererror')).toBeNull()
      const chart = document.querySelector('.strength-chart')
      expect(chart.querySelectorAll('circle')).toHaveLength(80)
      expect(chart.querySelectorAll('g > title')).toHaveLength(80)
      expect(chart.querySelectorAll('text[y="258"]').length).toBeLessThanOrEqual(13)
      expect(chart.querySelector('g:first-of-type title').textContent).toContain('0 kg')
      expect(chart.querySelector('g:last-of-type title').textContent).toContain('79 kg')
      const tableTexts = Array.from(document.querySelectorAll('g > text')).filter(text => Number(text.getAttribute('x')) === 440)
      expect(tableTexts.every(text => Number(text.getAttribute('y')) < 1340)).toBe(true)
    }
  })

  it('writes a PDF with correct page references, byte offsets and unicode metadata', async () => {
    const jpeg = new Uint8Array([255, 216, 255, 224, 0, 1, 255, 217])
    const pdf = reportPdfDocument([{ width: 2000, height: 2828, bytes: jpeg }, { width: 2000, height: 2828, bytes: jpeg }], '陈 - Progress')
    expect(pdf.type).toBe('application/pdf')
    const bytes = await readBytes(pdf)
    const text = new TextDecoder('latin1').decode(bytes)
    expect(text).toMatch(/^%PDF-1\.4\n/)
    expect(text).toContain('/Count 2 /Kids [3 0 R 6 0 R]')
    expect(text).toContain('/Title <FEFF9648')
    const xref = Number(text.match(/startxref\n(\d+)/)[1])
    expect(text.slice(xref, xref + 4)).toBe('xref')
    const entries = text.slice(xref).split('\n').slice(3, 12)
    entries.forEach((entry, index) => expect(text.slice(Number(entry.slice(0, 10)))).toMatch(new RegExp(`^${index + 1} 0 obj\\n`)))
    expect(text.match(/\/Subtype \/Image/g)).toHaveLength(2)
    expect(text).toContain('/Length 8 >>\nstream\n')
  })

  it('rejects an empty report before creating a misleading PDF', () => {
    expect(() => progressReportPages({ ...client, strengthProgress: [] }, options)).toThrow('No completed exercise loads')
    expect(() => reportPdfDocument([], client.name)).toThrow('No progress report pages')
  })
})

import { createElement } from 'react'
import { runInNewContext } from 'node:vm'
import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { reportFilename } from '../../services/reportService.js'
import { progressReportPages } from './progressReportPdf.jsx'
import { renderReportPdf, reportPdfDocument } from '../../utils/reportPdf.js'
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

// Exercise the real PDF pipeline while replacing only browser image/codec APIs.
function rasterizer({ offscreen = true, failure, controlled = false } = {}) {
  const canvases = [], images = [], bitmaps = [], workers = [], urls = new Map(), pending = new Map()
  const encode = vi.fn(async (canvas, type, quality) => {
    expect([canvas.width, canvas.height, type, quality]).toEqual([2000, 2828, 'image/jpeg', 0.95])
    expect(canvases.filter(item => item.width > 0 && item.height > 0).length).toBeLessThanOrEqual(offscreen ? 4 : 1)
    const page = canvas.page
    if (controlled) await new Promise((resolve, reject) => pending.set(page, { resolve, reject }))
    if (failure === 'encoder') throw new Error('Encoder failed')
    return failure === 'empty' ? null : {
      type: failure === 'format' ? 'image/png' : 'image/jpeg',
      arrayBuffer: async () => new Uint8Array([255, 216, page, 255, 217]).buffer,
    }
  })
  const context = function () {
    return failure === 'context' ? null : {
      clearRect: vi.fn(() => { this.page = null }),
      drawImage: vi.fn(image => {
        expect(this.page == null).toBe(true)
        this.page = image.page
      }),
    }
  }
  class DetachedCanvas {
    constructor(width, height) { this.width = width; this.height = height; canvases.push(this) }
    getContext() { return context.call(this) }
    convertToBlob({ type, quality }) { return encode(this, type, quality) }
    transferToImageBitmap() { const bitmap = { page: this.page, close: vi.fn() }; bitmaps.push(bitmap); return bitmap }
  }
  vi.stubGlobal('OffscreenCanvas', offscreen ? DetachedCanvas : undefined)
  vi.stubGlobal('Worker', class {
    constructor(url) {
      if (failure === 'startup' || failure === 'second-startup' && workers.length === 1) throw new Error('Workers unavailable')
      workers.push(this)
      this.scope = { self: { postMessage: data => queueMicrotask(() => this.onmessage?.({ data })) }, OffscreenCanvas: DetachedCanvas }
      // Run the actual self-contained worker body, with controlled codec APIs.
      this.ready = readBytes(urls.get(url)).then(bytes => runInNewContext(new TextDecoder().decode(bytes), this.scope))
      this.terminate = vi.fn()
      if (failure === 'worker') queueMicrotask(() => this.onerror?.())
    }
    postMessage(message, transfer) {
      expect(transfer).toEqual([message.bitmap])
      this.ready.then(() => this.scope.self.onmessage({ data: message }))
    }
  })
  vi.stubGlobal('Image', class {
    constructor() { images.push(this) }
    set src(value) {
      this.url = value
      readBytes(urls.get(value)).then(bytes => {
        this.page = Number(new TextDecoder().decode(bytes).match(/Page (\d+)/)?.[1] ?? 1)
        failure === 'image' ? this.onerror?.() : this.onload?.()
      })
    }
  })
  vi.spyOn(URL, 'createObjectURL').mockImplementation(blob => {
    const url = `blob:report-${urls.size}`
    urls.set(url, blob)
    return url
  })
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(function () {
    if (!canvases.includes(this)) canvases.push(this)
    return context.call(this)
  })
  vi.spyOn(HTMLCanvasElement.prototype, 'toBlob').mockImplementation(function (callback, type, quality) {
    encode(this, type, quality).then(callback)
  })
  return { canvases, images, encode, bitmaps, workers, urls, pending }
}

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })

describe('progress report export', () => {
  it('exports every exercise and its recorded loads, dates, sets and reps in a PDF visual', () => {
    const input = { ...client, strengthProgress: [...client.strengthProgress, {
      id: 'row', name: 'Cable row', points: [{ id: 'r1', date: '2026-08-10', load: 35, reps: 12, sets: 4 }],
    }] }
    const pages = progressReportPages(input, options)
    expect(reportFilename(client.name, 'progress-report')).toBe('amanda-lim-progress-report.pdf')
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

    const pages = Array.from({ length: 12 }, (_, index) => ({ width: 1000, height: 1414, svg: `<svg><text>Page ${index + 1}</text></svg>` }))
    for (const settings of [{ offscreen: true }, { offscreen: false }, { offscreen: true, failure: 'second-startup' }]) {
      const { offscreen, failure } = settings
      const workerCount = !offscreen ? 0 : failure ? 1 : 2
      const { canvases, images, encode, bitmaps, workers, urls } = rasterizer(settings)
      const rendered = new TextDecoder().decode(await readBytes(await renderReportPdf(pages, 'Twelve exercises')))
      expect(rendered).toContain('/Count 12 /Kids')
      expect(rendered.match(/\/Subtype \/Image/g)).toHaveLength(12)
      expect(encode).toHaveBeenCalledTimes(12)
      expect(HTMLCanvasElement.prototype.toBlob).toHaveBeenCalledTimes(offscreen ? 0 : 12)
      expect(canvases).toHaveLength(offscreen ? 12 + workerCount : 1)
      expect(canvases.every(canvas => canvas.width === 0 && canvas.height === 0)).toBe(true)
      expect(images.every(image => image.onload === null && image.onerror === null)).toBe(true)
      expect(new Set(URL.revokeObjectURL.mock.calls.flat())).toEqual(new Set(urls.keys()))
      expect(bitmaps).toHaveLength(offscreen ? 12 : 0)
      bitmaps.forEach(bitmap => expect(bitmap.close).toHaveBeenCalledTimes(1))
      expect(workers).toHaveLength(workerCount)
      workers.forEach(worker => expect(worker.terminate).toHaveBeenCalledTimes(1))
      vi.restoreAllMocks(); vi.unstubAllGlobals()
    }

    // A slow first page must not serialize the whole report or reorder its contents.
    const { canvases, encode, workers, bitmaps, pending } = rasterizer({ controlled: true })
    let settled = false
    const result = renderReportPdf(pages, 'Out-of-order completion').then(blob => { settled = true; return blob })
    await vi.waitFor(() => expect(encode).toHaveBeenCalledTimes(2))
    expect([...pending.keys()]).toEqual([1, 2])
    for (let page = 2; page <= 12; page += 1) {
      await vi.waitFor(() => expect(pending.has(page)).toBe(true))
      expect(encode).toHaveBeenCalledTimes(page)
      expect(settled).toBe(false)
      bitmaps.forEach(bitmap => expect(bitmap.close).toHaveBeenCalledTimes(1))
      pending.get(page).resolve()
    }
    expect(settled).toBe(false)
    pending.get(1).resolve()
    const ordered = await readBytes(await result)
    const pageMarkers = []
    for (let index = 0; index < ordered.length - 4; index += 1) {
      if (ordered[index] === 255 && ordered[index + 1] === 216 && ordered[index + 3] === 255 && ordered[index + 4] === 217) pageMarkers.push(ordered[index + 2])
    }
    expect(pageMarkers).toEqual(Array.from({ length: 12 }, (_, index) => index + 1))
    expect(workers).toHaveLength(2)
    expect(canvases).toHaveLength(14)
    expect(canvases.every(canvas => canvas.width === 0 && canvas.height === 0)).toBe(true)
    workers.forEach(worker => expect(worker.terminate).toHaveBeenCalledTimes(1))
  })

  it('rejects an empty or unrenderable report and releases temporary resources', async () => {
    expect(() => progressReportPages({ ...client, strengthProgress: [] }, options)).toThrow('No completed exercise loads')
    expect(() => reportPdfDocument([], client.name)).toThrow('No progress report pages')
    await expect(renderReportPdf([], client.name)).rejects.toThrow('No progress report pages')
    for (const failure of ['image', 'context', 'encoder', 'empty', 'format', 'worker']) {
      const { canvases, images, workers, bitmaps, urls } = rasterizer({ failure })
      await expect(renderReportPdf([{ width: 1000, height: 1414, svg: '<svg/>' }], client.name)).rejects.toThrow()
      expect(canvases.every(canvas => canvas.width === 0 && canvas.height === 0)).toBe(true)
      expect(images.every(image => image.onload === null && image.onerror === null)).toBe(true)
      expect(new Set(URL.revokeObjectURL.mock.calls.flat())).toEqual(new Set(urls.keys()))
      workers.forEach(worker => expect(worker.terminate).toHaveBeenCalledTimes(1))
      bitmaps.forEach(bitmap => expect(bitmap.close).toHaveBeenCalledTimes(1))
      vi.restoreAllMocks(); vi.unstubAllGlobals()
    }
    const { encode, urls } = rasterizer({ failure: 'startup' })
    await expect(renderReportPdf([{ width: 1000, height: 1414, svg: '<svg/>' }], client.name)).resolves.toHaveProperty('type', 'application/pdf')
    expect(encode).toHaveBeenCalledTimes(1)
    expect(HTMLCanvasElement.prototype.toBlob).toHaveBeenCalledTimes(1)
    expect(new Set(URL.revokeObjectURL.mock.calls.flat())).toEqual(new Set(urls.keys()))
    vi.restoreAllMocks(); vi.unstubAllGlobals()

    // Failure in one lane must drain the other page and never start the rest.
    const failed = rasterizer({ controlled: true })
    const pages = Array.from({ length: 12 }, (_, index) => ({ width: 1000, height: 1414, svg: `<svg><text>Page ${index + 1}</text></svg>` }))
    let settled = false
    const rejected = renderReportPdf(pages, client.name).catch(error => { settled = true; return error })
    await vi.waitFor(() => expect(failed.encode).toHaveBeenCalledTimes(2))
    failed.pending.get(1).reject(new Error('Page 1 failed'))
    await vi.waitFor(() => expect(failed.canvases.filter(canvas => canvas.width > 0)).toHaveLength(2))
    expect(settled).toBe(false)
    failed.pending.get(2).resolve()
    expect((await rejected).message).toBe('Page 1 failed')
    expect(failed.encode).toHaveBeenCalledTimes(2)
    expect(failed.images).toHaveLength(2)
    expect(failed.canvases.every(canvas => canvas.width === 0 && canvas.height === 0)).toBe(true)
    expect(failed.images.every(image => image.onload === null && image.onerror === null)).toBe(true)
    expect(new Set(URL.revokeObjectURL.mock.calls.flat())).toEqual(new Set(failed.urls.keys()))
    failed.bitmaps.forEach(bitmap => expect(bitmap.close).toHaveBeenCalledTimes(1))
    failed.workers.forEach(worker => expect(worker.terminate).toHaveBeenCalledTimes(1))
  })
})

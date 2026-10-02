// A PDF page contains one high-resolution JPEG of the shared SVG report visual.
// Binary stream lengths and xref offsets are measured in bytes, not characters.
export function reportPdfDocument(pages, title) {
  if (!pages.length) throw new Error('No progress report pages are available.')
  const encoder = new TextEncoder()
  const chunks = [], offsets = [0]
  let length = 0
  const append = value => {
    const bytes = typeof value === 'string' ? encoder.encode(value) : value
    chunks.push(bytes); length += bytes.length
  }
  const object = (id, content) => {
    offsets[id] = length
    append(`${id} 0 obj\n`); append(content); append('\nendobj\n')
  }
  const stream = (id, dictionary, bytes) => {
    offsets[id] = length
    append(`${id} 0 obj\n<< ${dictionary} /Length ${bytes.length} >>\nstream\n`)
    append(bytes); append('\nendstream\nendobj\n')
  }
  append('%PDF-1.4\n')
  object(1, '<< /Type /Catalog /Pages 2 0 R >>')
  object(2, `<< /Type /Pages /Count ${pages.length} /Kids [${pages.map((_, index) => `${3 + index * 3} 0 R`).join(' ')}] >>`)
  pages.forEach((page, index) => {
    const id = 3 + index * 3
    object(id, `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595.28 841.89] /Resources << /XObject << /Visual ${id + 1} 0 R >> >> /Contents ${id + 2} 0 R >>`)
    stream(id + 1, `/Type /XObject /Subtype /Image /Width ${page.width} /Height ${page.height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode`, page.bytes)
    stream(id + 2, '', encoder.encode('q\n595.28 0 0 841.89 0 0 cm\n/Visual Do\nQ'))
  })
  const infoId = 3 + pages.length * 3
  let encodedTitle = 'FEFF'
  for (let index = 0; index < title.length; index += 1) encodedTitle += title.charCodeAt(index).toString(16).padStart(4, '0')
  object(infoId, `<< /Title <${encodedTitle}> /Producer (Fitfinity) >>`)
  const xref = length
  append(`xref\n0 ${infoId + 1}\n0000000000 65535 f \n`)
  for (let id = 1; id <= infoId; id += 1) append(`${String(offsets[id]).padStart(10, '0')} 00000 n \n`)
  append(`trailer\n<< /Size ${infoId + 1} /Root 1 0 R /Info ${infoId} 0 R >>\nstartxref\n${xref}\n%%EOF\n`)
  return new Blob(chunks, { type: 'application/pdf' })
}

// Keep the worker body self-contained so the PDF owner also owns its encoder.
function reportEncoderWorker() {
  self.onmessage = async ({ data: { bitmap, width, height } }) => {
    let canvas, consumed = false
    try {
      canvas = new OffscreenCanvas(width, height)
      const context = canvas.getContext('2d')
      if (!context) throw new Error('The progress report encoder could not create a canvas.')
      context.drawImage(bitmap, 0, 0)
      bitmap.close()
      consumed = true
      const blob = await canvas.convertToBlob({ type: 'image/jpeg', quality: 0.95 })
      self.postMessage({ blob })
    } catch (error) {
      self.postMessage({ error: error.message || 'The progress report could not be encoded.' })
    } finally {
      if (!consumed) bitmap.close()
      if (canvas) { canvas.width = 0; canvas.height = 0 }
    }
  }
}

function createPageEncoder() {
  if (typeof globalThis.Worker !== 'function' ||
      typeof globalThis.OffscreenCanvas?.prototype?.transferToImageBitmap !== 'function' ||
      typeof globalThis.OffscreenCanvas?.prototype?.convertToBlob !== 'function') return null
  const url = URL.createObjectURL(new Blob([`(${reportEncoderWorker.toString()})()`], { type: 'text/javascript' }))
  let worker
  try { worker = new Worker(url) } catch { URL.revokeObjectURL(url); return null }
  let pending, failure
  const fail = message => {
    failure = new Error(message)
    pending?.reject(failure)
    pending = null
  }
  worker.onmessage = ({ data }) => {
    if (data.error) { fail(data.error); return }
    pending?.resolve(data.blob)
    pending = null
  }
  worker.onerror = () => fail('The progress report encoder could not start. Please try exporting again.')
  worker.onmessageerror = () => fail('The progress report encoder returned an unreadable page.')
  return {
    encode(canvas) {
      return new Promise((resolve, reject) => {
        if (failure) { reject(failure); return }
        pending = { resolve, reject }
        let bitmap
        try {
          bitmap = canvas.transferToImageBitmap()
          worker.postMessage({ bitmap, width: canvas.width, height: canvas.height }, [bitmap])
        } catch (error) { bitmap?.close(); pending = null; reject(error) }
      })
    },
    dispose() { worker.terminate(); URL.revokeObjectURL(url) },
  }
}

async function rasterizePage(page, encoder, canvas) {
  const url = URL.createObjectURL(new Blob([page.svg], { type: 'image/svg+xml;charset=utf-8' }))
  const image = new Image()
  try {
    await new Promise((resolve, reject) => {
      image.onload = resolve
      image.onerror = () => reject(new Error('The progress chart could not be rendered. Please try exporting again.'))
      image.src = url
    })
    if (canvas.width !== page.width * 2) canvas.width = page.width * 2
    if (canvas.height !== page.height * 2) canvas.height = page.height * 2
    const context = canvas.getContext('2d')
    if (!context) throw new Error('Your browser could not create the progress report. Please try another browser.')
    context.clearRect(0, 0, canvas.width, canvas.height)
    context.drawImage(image, 0, 0, canvas.width, canvas.height)
    const blob = encoder
      ? await encoder.encode(canvas)
      : await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.95))
    if (!blob || blob.type !== 'image/jpeg') throw new Error('Your browser could not encode the progress report. Please try another browser.')
    return { width: canvas.width, height: canvas.height, bytes: new Uint8Array(await blob.arrayBuffer()) }
  } finally {
    URL.revokeObjectURL(url)
    image.onload = null; image.onerror = null
  }
}

export async function renderReportPdf(pages, title) {
  if (!pages.length) throw new Error('No progress report pages are available.')
  await document.fonts?.ready
  // Bound expensive full-resolution work to two pages. Reuse each drawing canvas,
  // keep the fallback sequential, and store by page index regardless of finish order.
  const encoders = [], images = new Array(pages.length)
  let nextPage = 0, failure
  try {
    const first = createPageEncoder()
    encoders.push(first)
    if (first && pages.length > 1) {
      const second = createPageEncoder()
      if (second) encoders.push(second)
    }
    await Promise.all(encoders.map(async encoder => {
      let canvas
      try {
        canvas = encoder ? new OffscreenCanvas(1, 1) : document.createElement('canvas')
        while (!failure && nextPage < pages.length) {
          const index = nextPage++
          images[index] = await rasterizePage(pages[index], encoder, canvas)
        }
      } catch (error) { failure ??= error }
      finally { if (canvas) { canvas.width = 0; canvas.height = 0 } }
    }))
    // Every in-flight page has settled and released its resources, including on failure.
    if (failure) throw failure
    return reportPdfDocument(images, title)
  } finally { encoders.forEach(encoder => encoder?.dispose()) }
}

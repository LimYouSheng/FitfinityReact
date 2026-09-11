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

export async function renderReportPdf(pages, title) {
  await document.fonts?.ready
  const images = []
  for (const page of pages) images.push(await rasterizePage(page))
  return reportPdfDocument(images, title)
}

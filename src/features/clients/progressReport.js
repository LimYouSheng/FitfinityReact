export function progressReportFilename(client) {
  const clientSlug = client.name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)/g, '')

  return `${clientSlug || 'client'}-progress-report.pdf`
}

export async function progressReportFile(client, options) {
  const { progressReportPdf } = await import('./progressReportPdf.jsx')
  const blob = await progressReportPdf(client, options)
  return new File([blob], progressReportFilename(client), { type: 'application/pdf' })
}

export function downloadProgressReport(file) {
  const url = URL.createObjectURL(file)
  const link = document.createElement('a')
  try {
    link.href = url
    link.download = file.name
    document.body.append(link)
    link.click()
  } finally {
    link.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
  }
}

export function canShareProgressReport(file) {
  try { return Boolean(file && navigator.share && navigator.canShare?.({ files: [file] })) }
  catch { return false }
}

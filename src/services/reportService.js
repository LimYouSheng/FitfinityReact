// Device operations are injected separately from authenticated data operations.
// Keep share/open synchronous up to the browser call to retain user activation.
export function reportFilename(name, suffix) {
  const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '')
  return `${slug || 'client'}-${suffix}.pdf`
}

export function downloadReport(file) {
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

export function openReport(file) {
  const url = URL.createObjectURL(file)
  let opened
  try {
    opened = window.open(url, '_blank')
    if (!opened) throw new Error('The PDF window was blocked. Allow pop-ups or use Download PDF.')
    opened.opener = null
  } finally {
    window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
  }
}

export function reportShareError(error) {
  const messages = {
    NotAllowedError: 'Your browser blocked file sharing. Try Open PDF or Download PDF.',
    DataError: 'The browser could not transfer the PDF. Try Open PDF or Download PDF.',
    InvalidStateError: 'Close the other share menu, then try Share PDF again.',
    TypeError: 'This browser cannot share this PDF. Use Open PDF or Download PDF.',
  }
  return messages[error.name] ?? error.message ?? 'The PDF could not be shared. Use Download PDF.'
}

export function canShareReport(file) {
  try { return Boolean(file && navigator.share && navigator.canShare?.({ files: [file] })) }
  catch { return false }
}

export const browserReportService = {
  async progressFile({ client, timeZone }) {
    const { progressReportPdf } = await import('../features/clients/progressReportPdf.jsx')
    const blob = await progressReportPdf(client, { timeZone })
    return new File([blob], reportFilename(client.name, 'progress-report'), { type: 'application/pdf' })
  },
  async sessionFile(input) {
    const { sessionSummaryPdf } = await import('../features/sessions/sessionExport.jsx')
    const blob = await sessionSummaryPdf(input)
    return new File([blob], reportFilename(input.client.name, `session-${input.session.sessionNumber}-summary`), { type: 'application/pdf' })
  },
  canShare: canShareReport,
  share(file) {
    if (!canShareReport(file)) throw new Error('PDF sharing is unavailable in this browser. Use Download PDF to share the file manually.')
    return navigator.share({ files: [file] })
  },
  download: downloadReport,
  open: openReport,
}

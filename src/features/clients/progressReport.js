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

export function openProgressReport(file) {
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

export function openProgressWhatsApp(client) {
  const phone = (typeof client.phone === 'string' ? client.phone : `${client.phone?.countryCode ?? ''}${client.phone?.number ?? ''}`).replace(/\D/g, '')
  if (!phone) throw new Error('This client has no WhatsApp number.')
  const opened = window.open(`https://wa.me/${phone}`, '_blank')
  if (!opened) throw new Error('The WhatsApp window was blocked. Allow pop-ups and try again.')
  opened.opener = null
}

export function progressShareError(error) {
  const messages = {
    NotAllowedError: 'Your browser blocked file sharing. Try Open PDF or Download PDF.',
    DataError: 'The browser could not transfer the PDF. Try Open PDF or Download PDF.',
    InvalidStateError: 'Close the other share menu, then try Share PDF again.',
    TypeError: 'This browser cannot share this PDF. Use Open PDF or Download PDF.',
  }
  return messages[error.name] ?? error.message ?? 'The PDF could not be shared. Use Download PDF.'
}

export function canShareProgressReport(file) {
  try { return Boolean(file && navigator.share && navigator.canShare?.({ files: [file] })) }
  catch { return false }
}

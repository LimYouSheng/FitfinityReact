import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import StrengthProgress from './StrengthProgress.jsx'
import { progressReportPdf } from './progressReportPdf.jsx'

vi.mock('./progressReportPdf.jsx', () => ({ progressReportPdf: vi.fn() }))
beforeEach(() => { vi.mocked(progressReportPdf).mockReset().mockResolvedValue(new Blob(['%PDF-1.4'], { type: 'application/pdf' })) })

const client = { id: 'c1', name: 'Amanda Lim', phone: '+65 91234567', strengthProgress: [{ id: 'squat', name: 'Squat', points: [{ id: 'p1', date: '2026-09-01', load: 20, reps: 8, sets: 3 }] }] }
const owner = { id: 'u-owner', role: 'owner' }
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

function nativeShare(share = vi.fn().mockResolvedValue(), canShare = vi.fn().mockReturnValue(true)) {
  vi.stubGlobal('navigator', { share, canShare })
  return share
}

async function prepareShare() {
  fireEvent.click(screen.getByRole('button', { name: 'Share Progress Report via WhatsApp' }))
  return screen.findByRole('button', { name: 'Share PDF' })
}

it('retries failed export history without starting a second download', async () => {
  vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:report')
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
  const download = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  const save = vi.fn().mockRejectedValueOnce(new Error('Offline')).mockResolvedValue({})
  render(<StrengthProgress client={client} user={owner} onRecordAction={save} />)
  fireEvent.click(screen.getByRole('button', { name: 'Export Progress Report' }))
  await screen.findByText('PDF export started, but its history could not be saved.')
  expect(screen.getByRole('button', { name: 'Export Progress Report' })).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: 'Retry History Save' }))
  await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
  expect(download).toHaveBeenCalledTimes(1)
  expect(progressReportPdf).toHaveBeenCalledTimes(1)
  expect(save.mock.calls[0][0].kind).toBe('pdf_export')
  expect(save).toHaveBeenCalledTimes(2)
  expect(save.mock.calls[1][0]).toEqual(save.mock.calls[0][0])
})

it('shares the generated PDF file after an explicit click and does not log a cancelled share', async () => {
  const share = nativeShare(vi.fn().mockRejectedValueOnce(new DOMException('Cancelled', 'AbortError')).mockResolvedValue())
  const save = vi.fn().mockResolvedValue({})
  render(<StrengthProgress client={client} user={owner} onRecordAction={save} />)
  const button = await prepareShare()
  expect(share).not.toHaveBeenCalled()
  fireEvent.click(button)
  await waitFor(() => expect(button).toBeEnabled())
  expect(save).not.toHaveBeenCalled()
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  fireEvent.click(button)
  expect(share).toHaveBeenCalledTimes(2)
  await waitFor(() => expect(save).toHaveBeenCalledTimes(1))
  const file = share.mock.calls[0][0].files[0]
  expect(file).toBeInstanceOf(File)
  expect(file.name).toBe('amanda-lim-progress-report.pdf')
  expect(file.type).toBe('application/pdf')
  expect(file.size).toBe(8)
  expect(share.mock.calls[0][0]).toEqual({ files: [file] })
  expect(share.mock.calls[1][0].files[0]).toBe(file)
  expect(progressReportPdf).toHaveBeenCalledWith(client, { timeZone: undefined })
  expect(progressReportPdf).toHaveBeenCalledTimes(1)
  expect(save.mock.calls[0][0].kind).toBe('pdf_share_opened')
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  expect(screen.queryByText(/sent|delivered/i)).not.toBeInTheDocument()
})

it('downloads the prepared PDF for manual attachment when native file sharing is unavailable', async () => {
  const share = nativeShare(vi.fn(), vi.fn(() => { throw new Error('Unsupported') }))
  const objectUrl = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:report')
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
  const download = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  const save = vi.fn().mockResolvedValue({})
  render(<StrengthProgress client={client} user={owner} onRecordAction={save} />)
  fireEvent.click(screen.getByRole('button', { name: 'Share Progress Report via WhatsApp' }))
  const button = await screen.findByRole('button', { name: 'Download PDF' })
  expect(screen.queryByRole('button', { name: 'Share PDF' })).not.toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Open WhatsApp' })).toHaveAttribute('href', 'https://wa.me/6591234567')
  expect(save).not.toHaveBeenCalled()
  fireEvent.click(button)
  await waitFor(() => expect(save).toHaveBeenCalledTimes(1))
  expect(objectUrl.mock.calls[0][0]).toMatchObject({ name: 'amanda-lim-progress-report.pdf', type: 'application/pdf', size: 8 })
  expect(download).toHaveBeenCalledTimes(1)
  expect(progressReportPdf).toHaveBeenCalledTimes(1)
  expect(save.mock.calls[0][0].kind).toBe('pdf_export')
  expect(share).not.toHaveBeenCalled()
})

it('retries a failed native share separately from its history without sharing or rendering twice', async () => {
  const share = nativeShare(vi.fn().mockRejectedValueOnce(new DOMException('Sharing is unavailable.', 'NotAllowedError')).mockResolvedValue())
  const save = vi.fn().mockRejectedValueOnce(new Error('Offline')).mockResolvedValue({})
  render(<StrengthProgress client={client} user={owner} onRecordAction={save} />)
  const button = await prepareShare()
  fireEvent.click(button)
  await screen.findByText('Sharing is unavailable.')
  expect(save).not.toHaveBeenCalled()
  fireEvent.click(button)
  await screen.findByText('PDF share opened, but its history could not be saved.')
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  fireEvent.click(screen.getByRole('button', { name: 'Retry History Save' }))
  await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
  expect(share).toHaveBeenCalledTimes(2)
  expect(progressReportPdf).toHaveBeenCalledTimes(1)
  expect(save).toHaveBeenCalledTimes(2)
  expect(save.mock.calls[1][0]).toEqual(save.mock.calls[0][0])
})

it('retries PDF preparation and ignores a late render after closing the share dialog', async () => {
  const share = nativeShare()
  const save = vi.fn()
  let finish
  vi.mocked(progressReportPdf).mockRejectedValueOnce(new Error('Could not render chart.')).mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
  render(<StrengthProgress client={client} user={owner} onRecordAction={save} />)
  fireEvent.click(screen.getByRole('button', { name: 'Share Progress Report via WhatsApp' }))
  await screen.findByText('Could not render chart.')
  fireEvent.click(screen.getByRole('button', { name: 'Retry PDF' }))
  await waitFor(() => expect(progressReportPdf).toHaveBeenCalledTimes(2))
  expect(screen.getByRole('status')).toHaveTextContent('Preparing PDF')
  fireEvent.click(screen.getByRole('button', { name: 'Close', exact: true }))
  await act(async () => { finish(new Blob(['%PDF-1.4'], { type: 'application/pdf' })) })
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(share).not.toHaveBeenCalled()
  expect(save).not.toHaveBeenCalled()
})

it('lets only the owner view history, including when the client has no remaining progress points', async () => {
  const load = vi.fn().mockResolvedValue([{ id: 'one', kind: 'csv_export', at: '2026-09-02T04:00:00Z', by: { name: 'Marcus Tan' } }])
  const empty = { ...client, strengthProgress: [] }
  const view = render(<StrengthProgress client={empty} user={{ role: 'trainer' }} onLoadHistory={load} />)
  expect(screen.queryByRole('button', { name: 'View Export/WhatsApp History' })).not.toBeInTheDocument()
  expect(load).not.toHaveBeenCalled()
  view.rerender(<StrengthProgress client={empty} user={owner} timeZone="Asia/Singapore" onLoadHistory={load} />)
  fireEvent.click(screen.getByRole('button', { name: 'View Export/WhatsApp History' }))
  await screen.findByText('Marcus Tan')
  expect(document.querySelector('.report-history-row time')).toHaveTextContent('12:00')
})

it('retries loading history and shows every entry through pagination', async () => {
  const entries = Array.from({ length: 11 }, (_, index) => ({ id: String(index), kind: 'csv_export', at: '2026-09-02T04:00:00Z', by: { name: `Staff ${index}` } }))
  const load = vi.fn().mockRejectedValueOnce(new Error('History unavailable')).mockResolvedValue(entries)
  render(<StrengthProgress client={client} user={owner} onLoadHistory={load} />)
  fireEvent.click(screen.getByRole('button', { name: 'View Export/WhatsApp History' }))
  await screen.findByText('History unavailable')
  fireEvent.click(screen.getByRole('button', { name: 'Retry History' }))
  await screen.findByText('Staff 0')
  expect(document.querySelectorAll('.report-history-row')).toHaveLength(10)
  fireEvent.click(screen.getByRole('button', { name: 'Next' }))
  expect(screen.getByText('Staff 10')).toBeVisible()
  expect(document.querySelectorAll('.report-history-row')).toHaveLength(1)
})

it('does not log a failed PDF render and permits retrying the export', async () => {
  vi.mocked(progressReportPdf).mockRejectedValueOnce(new Error('The progress chart could not be rendered.'))
  const save = vi.fn()
  render(<StrengthProgress client={client} user={owner} onRecordAction={save} />)
  fireEvent.click(screen.getByRole('button', { name: 'Export Progress Report' }))
  await screen.findByText('The progress chart could not be rendered.')
  expect(save).not.toHaveBeenCalled()
  expect(screen.getByRole('button', { name: 'Export Progress Report' })).toBeEnabled()
  expect(screen.queryByRole('button', { name: 'Retry History Save' })).not.toBeInTheDocument()
})

import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import StrengthProgress from './StrengthProgress.jsx'
import { PageState } from '../../hooks/usePageState.js'
import { useState } from 'react'
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

it('opens one exercise chart at a time from compact rows and refreshes its values without closing it', () => {
  const data = { ...client, strengthProgress: [...client.strengthProgress,
    { id: 'row', name: 'Seated Row', points: [{ id: 'row-1', date: '2026-09-01', load: 30 }] }] }
  const view = render(<StrengthProgress client={data} user={owner} />)
  expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  expect(screen.queryByRole('img')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Show Squat progress chart', exact: true }))
  expect(screen.getByRole('img', { name: 'Squat load progress chart' })).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: 'Show Seated Row progress chart', exact: true }))
  expect(screen.queryByRole('img', { name: 'Squat load progress chart' })).not.toBeInTheDocument()
  expect(screen.getAllByRole('img')).toHaveLength(1)
  const refreshed = structuredClone(data)
  refreshed.strengthProgress[1].points.push({ id: 'row-2', date: '2026-09-02', load: 35 })
  view.rerender(<StrengthProgress client={refreshed} user={owner} />)
  expect(screen.getByRole('button', { name: 'Hide Seated Row progress chart' })).toHaveTextContent('35 kg')
  expect(document.querySelector('.strength-chart-summary')).toHaveTextContent('Completed2')
  fireEvent.click(screen.getByRole('button', { name: 'Hide Seated Row progress chart', exact: true }))
  expect(screen.queryByRole('img')).not.toBeInTheDocument()
})

it('exports every exercise through the unchanged PDF renderer even when all charts are collapsed', async () => {
  vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:report')
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  const data = { ...client, strengthProgress: [...client.strengthProgress,
    { id: 'row', name: 'Seated Row', points: [{ id: 'row-1', date: '2026-09-01', load: 30 }] }] }
  const save = vi.fn().mockResolvedValue({})
  render(<StrengthProgress client={data} user={owner} onRecordAction={save} timeZone="Asia/Singapore" />)
  fireEvent.click(screen.getByRole('button', { name: 'Export Progress Report' }))
  await waitFor(() => expect(save).toHaveBeenCalledTimes(1))
  expect(progressReportPdf).toHaveBeenCalledExactlyOnceWith(data, { timeZone: 'Asia/Singapore' })
  expect(screen.queryByRole('img')).not.toBeInTheDocument()
})

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
  expect(screen.getByRole('button', { name: 'Open WhatsApp' })).toBeEnabled()
  expect(save).not.toHaveBeenCalled()
  fireEvent.click(button)
  await waitFor(() => expect(save).toHaveBeenCalledTimes(1))
  expect(objectUrl.mock.calls[0][0]).toMatchObject({ name: 'amanda-lim-progress-report.pdf', type: 'application/pdf', size: 8 })
  expect(download).toHaveBeenCalledTimes(1)
  expect(progressReportPdf).toHaveBeenCalledTimes(1)
  expect(save.mock.calls[0][0].kind).toBe('pdf_export')
  expect(share).not.toHaveBeenCalled()
})

it('tracks only a successful WhatsApp fallback opening and retries its failed audit without reopening the window', async () => {
  nativeShare(vi.fn(), vi.fn().mockReturnValue(false))
  const popup = { opener: window }, open = vi.spyOn(window, 'open').mockReturnValueOnce(null).mockReturnValue(popup)
  const save = vi.fn().mockRejectedValueOnce(new Error('Offline')).mockResolvedValue({})
  render(<StrengthProgress client={{ ...client, reportPackageId: 'purchase' }} user={owner} onRecordAction={save} />)
  fireEvent.click(screen.getByRole('button', { name: 'Share Progress Report via WhatsApp' }))
  const button = await screen.findByRole('button', { name: 'Open WhatsApp' })
  fireEvent.click(button)
  await screen.findByText('The WhatsApp window was blocked. Allow pop-ups and try again.')
  expect(save).not.toHaveBeenCalled()
  fireEvent.click(button)
  await screen.findByText('WhatsApp opened, but its history could not be saved.')
  expect(button).toBeDisabled()
  expect(open).toHaveBeenCalledTimes(2)
  expect(open).toHaveBeenLastCalledWith('https://wa.me/6591234567', '_blank')
  expect(popup.opener).toBeNull()
  expect(save.mock.calls[0][0]).toMatchObject({ kind: 'whatsapp_opened', packageId: 'purchase' })
  fireEvent.click(screen.getByRole('button', { name: 'Retry History Save' }))
  await waitFor(() => expect(button).toBeEnabled())
  expect(save).toHaveBeenCalledTimes(2)
  expect(save.mock.calls[1][0]).toEqual(save.mock.calls[0][0])
  expect(open).toHaveBeenCalledTimes(2)
  expect(screen.queryByText(/sent|delivered/i)).not.toBeInTheDocument()
})

it('restores a loaded history page and retains its rows during refresh without a pagination reload loop', async () => {
  const entries = Array.from({ length: 12 }, (_, index) => ({ id: String(index), kind: 'pdf_export', at: '2026-09-02T04:00:00Z', by: { name: `Staff ${index}` } }))
  let finish
  const load = vi.fn().mockImplementation(() => new Promise(resolve => { finish = resolve }))
  function View() {
    const [values, setValues] = useState({ 'client.c1.reportHistoryOpen': true,
      'client.c1.purchase.reportHistoryPage': { resetKey: 'c1.purchase', page: 2 } })
    return <PageState.Provider value={{ values, setValue: (key, value) => setValues(previous => ({ ...previous, [key]: value })) }}>
      <StrengthProgress client={{ ...client, reportPackageId: 'purchase' }} user={owner} onLoadHistory={load} />
    </PageState.Provider>
  }
  const view = render(<View />)
  await waitFor(() => expect(load).toHaveBeenCalledTimes(1))
  await act(async () => finish(entries))
  expect(screen.getByText('Staff 10')).toBeVisible()
  expect(screen.getByLabelText('List pages')).toHaveTextContent('Page 2')
  view.rerender(<View />)
  expect(load).toHaveBeenCalledTimes(1)
  await act(async () => window.dispatchEvent(new Event('focus')))
  await waitFor(() => expect(load).toHaveBeenCalledTimes(2))
  expect(screen.getByText('Staff 10')).toBeVisible()
  expect(screen.queryByText('Loading history…')).not.toBeInTheDocument()
  await act(async () => finish(entries))
  expect(screen.getByLabelText('List pages')).toHaveTextContent('Page 2')
  expect(load).toHaveBeenCalledTimes(2)
})

it('retries a failed native share separately from its history without sharing or rendering twice', async () => {
  const share = nativeShare(vi.fn().mockRejectedValueOnce(new DOMException('Sharing is unavailable.', 'NotAllowedError')).mockResolvedValue())
  const save = vi.fn().mockRejectedValueOnce(new Error('Offline')).mockResolvedValue({})
  render(<StrengthProgress client={client} user={owner} onRecordAction={save} />)
  const button = await prepareShare()
  fireEvent.click(button)
  await screen.findByText('Your browser blocked file sharing. Try Open PDF or Download PDF.')
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

it('opens the prepared PDF synchronously for the browser viewer and reports blocked pop-ups without claiming a share', async () => {
  nativeShare(vi.fn(), vi.fn().mockReturnValue(false))
  const objectUrl = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:prepared-pdf')
  const popup = { opener: window }
  const open = vi.spyOn(window, 'open').mockReturnValueOnce(null).mockReturnValueOnce(popup)
  const save = vi.fn()
  render(<StrengthProgress client={client} user={owner} onRecordAction={save} />)
  fireEvent.click(screen.getByRole('button', { name: 'Share Progress Report via WhatsApp' }))
  const button = await screen.findByRole('button', { name: 'Open PDF' })
  fireEvent.click(button)
  expect(open).toHaveBeenCalledWith('blob:prepared-pdf', '_blank')
  expect(screen.getByRole('alert')).toHaveTextContent('PDF window was blocked')
  fireEvent.click(button)
  expect(open).toHaveBeenCalledTimes(2)
  expect(popup.opener).toBeNull()
  expect(objectUrl.mock.calls[1][0]).toBe(objectUrl.mock.calls[0][0])
  expect(progressReportPdf).toHaveBeenCalledTimes(1)
  expect(save).not.toHaveBeenCalled()
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

it('paginates exercises and report history independently while exporting every exercise from any page', async () => {
  const data = { ...client, reportPackageId: 'purchase', strengthProgress: Array.from({ length: 12 }, (_, index) => ({
    id: `exercise-${index}`, name: `Exercise ${index}`, points: [{ id: `point-${index}`, date: '2026-09-01', load: index + 1, packageId: 'purchase' }],
  })) }
  const entries = Array.from({ length: 12 }, (_, index) => ({ id: `entry-${index}`, kind: 'pdf_export', at: '2026-09-02T04:00:00Z', by: { name: `Staff ${index}` } }))
  const record = vi.fn().mockResolvedValue()
  vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:report')
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  render(<StrengthProgress client={data} user={owner} onRecordAction={record} onLoadHistory={vi.fn().mockResolvedValue(entries)} />)
  const exercises = screen.getByRole('heading', { name: 'Strength Progress' }).closest('section')
  expect(exercises.querySelectorAll('.strength-progress-item')).toHaveLength(10)
  fireEvent.click(within(exercises).getByRole('button', { name: 'Next' }))
  expect(exercises.querySelectorAll('.strength-progress-item')).toHaveLength(2)
  fireEvent.click(screen.getByRole('button', { name: 'Show Exercise 11 progress chart' }))
  fireEvent.click(screen.getByRole('button', { name: 'View Export/WhatsApp History' }))
  await screen.findByText('Staff 0')
  const history = screen.getByLabelText('Export/WhatsApp history')
  expect(history.querySelectorAll('article')).toHaveLength(10)
  fireEvent.click(within(history).getByRole('button', { name: 'Next' }))
  expect(history.querySelectorAll('article')).toHaveLength(2)
  expect(screen.getByRole('button', { name: 'Hide Exercise 11 progress chart' })).toHaveAttribute('aria-expanded', 'true')
  fireEvent.click(screen.getByRole('button', { name: 'Export Progress Report' }))
  await waitFor(() => expect(record).toHaveBeenCalledTimes(1))
  expect(progressReportPdf.mock.calls[0][0].strengthProgress).toEqual(data.strengthProgress)
  expect(within(exercises).getByLabelText('List pages')).toHaveTextContent('Page 2 of 2')
  expect(within(history).getByLabelText('List pages')).toHaveTextContent('Page 2 of 2')
})

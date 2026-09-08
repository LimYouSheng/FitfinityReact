import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import StrengthProgress from './StrengthProgress.jsx'

const client = { id: 'c1', name: 'Amanda Lim', phone: '+65 91234567', strengthProgress: [{ id: 'squat', name: 'Squat', points: [{ id: 'p1', date: '2026-09-01', load: 20, reps: 8, sets: 3 }] }] }
const owner = { id: 'u-owner', role: 'owner' }
afterEach(() => { cleanup(); vi.restoreAllMocks() })

it('retries failed export history without starting a second download', async () => {
  vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:report')
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
  const download = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  const save = vi.fn().mockRejectedValueOnce(new Error('Offline')).mockResolvedValue({})
  render(<StrengthProgress client={client} user={owner} onRecordAction={save} />)
  fireEvent.click(screen.getByRole('button', { name: 'Export Progress Report' }))
  await screen.findByText('CSV export started, but its history could not be saved.')
  expect(screen.getByRole('button', { name: 'Export Progress Report' })).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: 'Retry History Save' }))
  await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
  expect(download).toHaveBeenCalledTimes(1)
  expect(save).toHaveBeenCalledTimes(2)
  expect(save.mock.calls[1][0]).toEqual(save.mock.calls[0][0])
})

it('does not log a blocked WhatsApp window and logs an opened handoff without claiming delivery', async () => {
  const replace = vi.fn(), close = vi.fn(), popup = { opener: window, location: { replace }, close }
  const open = vi.spyOn(window, 'open').mockReturnValueOnce(null).mockReturnValueOnce(popup)
  const save = vi.fn().mockResolvedValue({})
  render(<StrengthProgress client={client} user={owner} onRecordAction={save} />)
  const share = screen.getByRole('link', { name: 'Share Progress Report via WhatsApp' })
  fireEvent.click(share)
  await screen.findByText('WhatsApp could not be opened. Allow pop-ups and try again.')
  expect(save).not.toHaveBeenCalled()
  fireEvent.click(share)
  await waitFor(() => expect(save).toHaveBeenCalledTimes(1))
  expect(open).toHaveBeenCalledTimes(2)
  expect(popup.opener).toBeNull()
  expect(replace).toHaveBeenCalledWith(expect.stringMatching(/^https:\/\/wa\.me\/6591234567\?text=/))
  expect(save.mock.calls[0][0].kind).toBe('whatsapp_opened')
  expect(screen.queryByText(/sent|delivered/i)).not.toBeInTheDocument()
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

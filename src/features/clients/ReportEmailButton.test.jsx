import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { PortalData } from '../../hooks/usePortalData.js'
import { ApiError } from '../../services/apiClient.js'
import ReportEmailButton from './ReportEmailButton.jsx'

const { confirm, notify } = vi.hoisted(() => ({ confirm: vi.fn(), notify: vi.fn() }))
vi.mock('../../components/ActionConfirmationProvider.jsx', () => ({ useActionConfirmation: () => confirm }))
vi.mock('../../components/NotificationProvider.jsx', () => ({ useNotifications: () => ({ notify }) }))
vi.mock('../../components/LoadingIndicator.jsx', () => ({ default: () => <div role="status">Lifting the weights...</div> }))
afterEach(() => { cleanup(); vi.resetAllMocks() })
function setup() {
  const services = {
    prepareReportSharing: vi.fn().mockResolvedValue({}), retryReportSharing: vi.fn().mockResolvedValue({}),
    reviewReportEmail: vi.fn().mockResolvedValue({ expected: 'a'.repeat(64), recipients: [{ name: 'Client', email: 'client@example.test' }] }),
    sendReportEmail: vi.fn().mockResolvedValue({ queued: 1 }), recoverReportEmail: vi.fn(), retryReportEmail: vi.fn(),
  }
  render(<PortalData.Provider value={{ services }}><ReportEmailButton clientId="client" purchaseId="purchase" /></PortalData.Provider>)
  return services
}
it('requires recipient confirmation and reports queuing rather than delivery', async () => {
  const services = setup()
  confirm.mockResolvedValue(true)
  fireEvent.click(screen.getByRole('button', { name: 'Email Report' }))
  await waitFor(() => expect(services.sendReportEmail).toHaveBeenCalledTimes(1))
  expect(confirm).toHaveBeenCalledWith(expect.objectContaining({ message: expect.stringContaining('client@example.test') }))
  expect(services.sendReportEmail).toHaveBeenCalledWith(expect.objectContaining({ targetId: 'client', purchaseId: 'purchase', expected: 'a'.repeat(64) }))
  expect(notify).toHaveBeenCalledWith({ message: 'Progress report email queued. Delivery is not yet confirmed.' })
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
})
it('cancelling recipient confirmation sends nothing', async () => {
  const services = setup()
  confirm.mockResolvedValue(false)
  fireEvent.click(screen.getByRole('button', { name: 'Email Report' }))
  await waitFor(() => expect(confirm).toHaveBeenCalledTimes(1))
  await waitFor(() => expect(screen.getByRole('button', { name: 'Email Report' })).toBeEnabled())
  expect(services.sendReportEmail).not.toHaveBeenCalled()
  expect(notify).not.toHaveBeenCalled()
})
it('recovers uncertain approval preparation separately from an email submission', async () => {
  const services = setup()
  services.prepareReportSharing.mockRejectedValue(new ApiError('SAVE_UNCERTAIN', 'Check preparation'))
  fireEvent.click(screen.getByRole('button', { name: 'Email Report' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Retry Report Preparation' }))
  await waitFor(() => expect(services.retryReportSharing).toHaveBeenCalledTimes(1))
  expect(services.recoverReportEmail).not.toHaveBeenCalled()
  expect(services.retryReportEmail).not.toHaveBeenCalled()
  expect(services.sendReportEmail).not.toHaveBeenCalled()
})

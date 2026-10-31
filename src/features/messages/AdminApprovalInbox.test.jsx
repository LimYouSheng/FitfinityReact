import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { ActionConfirmationProvider } from '../../components/ActionConfirmationProvider.jsx'
import AdminApprovalInbox from './AdminApprovalInbox.jsx'

afterEach(cleanup)
const proposal = {
  id: 'proposal', version: 1, actorId: 'admin', actorName: 'Test Admin',
  operation: 'content.save', area: 'content', status: 'pending',
  body: { body: { draft: { key: 'about', title: 'Reviewed title', body: 'Reviewed body', status: 'draft' } } },
}
function show(overrides = {}, role = 'owner') {
  const services = {
    readAdminRequests: vi.fn().mockResolvedValue({ items: [proposal], pending: null }),
    decideAdminRequest: vi.fn(), recoverAdminDecision: vi.fn(), ...overrides,
  }
  render(<ActionConfirmationProvider><AdminApprovalInbox services={services} user={{ id: role, role }} /></ActionConfirmationProvider>)
  return services
}
async function review() { fireEvent.click(await screen.findByRole('button', { name: 'Review', exact: true })) }
async function approve() {
  fireEvent.click(screen.getByRole('button', { name: 'Approve', exact: true }))
  fireEvent.click(within(await screen.findByRole('dialog', { name: 'Approve?' })).getByRole('button', { name: 'Approve', exact: true }))
}

it('reviews the exact content and recovers a lost decision response without repeating its write', async () => {
  const services = show({
    decideAdminRequest: vi.fn().mockRejectedValue(new Error('Lost response')),
    recoverAdminDecision: vi.fn().mockResolvedValue({ result: { ...proposal, version: 2, status: 'approved' } }),
  })
  await review()
  expect(screen.getByRole('heading', { name: 'Reviewed title' })).toBeInTheDocument()
  expect(screen.getByText('Reviewed body')).toBeInTheDocument()
  await approve()
  expect(await screen.findByRole('alert')).toHaveTextContent('Lost response')
  expect(screen.getByRole('button', { name: 'Back to Requests' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Refresh Requests' })).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: 'Check Original Decision' }))
  await screen.findByText('Test Admin · approved')
  expect(services.decideAdminRequest).toHaveBeenCalledExactlyOnceWith({ id: proposal.id, expectedVersion: 1, decision: 'approved' })
  expect(services.recoverAdminDecision).toHaveBeenCalledTimes(1)
  expect(screen.queryByRole('button', { name: 'Approve', exact: true })).not.toBeInTheDocument()
})

it('offers an Admin only cancellation of their own pending request', async () => {
  const services = show({ decideAdminRequest: vi.fn().mockResolvedValue({ ...proposal, version: 2, status: 'cancelled' }) }, 'admin')
  await review()
  expect(screen.queryByRole('button', { name: 'Approve', exact: true })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Reject', exact: true })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Cancel Request', exact: true }))
  fireEvent.click(within(await screen.findByRole('dialog', { name: 'Cancel Request?' })).getByRole('button', { name: 'Cancel Request', exact: true }))
  await screen.findByText('Test Admin · cancelled')
  expect(services.decideAdminRequest).toHaveBeenCalledExactlyOnceWith({ id: proposal.id, expectedVersion: 1, decision: 'cancelled' })
})

it('blocks approval when the current screen cannot fully review the requested operation', async () => {
  show({ readAdminRequests: vi.fn().mockResolvedValue({ items: [{ ...proposal, operation: 'unknown.future' }], pending: null }) })
  await review()
  expect(screen.getByRole('button', { name: 'Approve', exact: true })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Reject', exact: true })).toBeEnabled()
})

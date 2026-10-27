import { afterEach, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import ClientRenewalRecovery from './ClientRenewalRecovery.jsx'
import ClientProfileRoute from './ClientProfileRoute.jsx'
import { ActionConfirmationProvider } from '../../components/ActionConfirmationProvider.jsx'
import { EditGuardProvider } from '../../components/EditGuardProvider.jsx'

const actions = vi.hoisted(() => ({ runAction: vi.fn(fn => fn()), reload: vi.fn(), props: null, renewPackage: vi.fn() }))
vi.mock('../../hooks/usePortalActions.js', () => ({ default: () => actions }))
vi.mock('../../hooks/usePortalData.js', async importOriginal => ({ ...await importOriginal(), default: () => ({ snapshot: { user: { role: 'owner' }, data: { trainers: [], clients: [], packages: [] }, policy: {}, capabilities: { apiBackedWorkflows: true, clientRenewalWrites: true } }, services: { clientService: { renewPackage: actions.renewPackage } } }) }))
vi.mock('./useClientNotes.js', () => ({ default: client => ({ client }) }))
vi.mock('./ClientProfilePage.jsx', () => ({ default: props => { actions.props = props; return null } }))
afterEach(() => { cleanup(); vi.clearAllMocks(); actions.reload.mockReset(); actions.renewPackage.mockReset() })
const pending = { id: 'client', draft: { requestId: 'original', clientName: 'Client One', packageName: 'PT package', startDate: '2027-06-07' } }
it('coalesces checks and retries exactly the retained renewal command', async () => {
  let finish
  const renewPackage = vi.fn(() => new Promise(resolve => { finish = resolve }))
  render(<ClientRenewalRecovery pending={pending} services={{ clientService: { renewPackage } }} />)
  fireEvent.click(screen.getByRole('button', { name: 'Check Package Addition' }))
  fireEvent.click(screen.getByRole('button', { name: 'Checking Package…' }))
  expect(renewPackage).toHaveBeenCalledExactlyOnceWith(pending)
  await act(async () => finish({ id: pending.id }))
  expect(actions.reload).toHaveBeenCalledTimes(1)
})
it.each([409, 503])('clears a definitive rejection but retains unknown status %i', async status => {
  const renewPackage = vi.fn().mockRejectedValue({ status })
  render(<ClientRenewalRecovery pending={pending} services={{ clientService: { renewPackage } }} />)
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Check Package Addition' })))
  expect(actions.reload).toHaveBeenCalledTimes(status === 409 ? 1 : 0)
  expect(screen.getByRole('button', { name: 'Check Package Addition' })).toBeEnabled()
})
it.each(['NETWORK_ERROR', 'SAVE_UNCERTAIN'])('accepts only the original reconciled save after %s', async code => {
  const result = { id: 'client', version: 3, purchaseId: 'purchase' }
  actions.renewPackage.mockRejectedValue({ code })
  actions.reload.mockResolvedValue({ clientRenewalRecovered: { input: pending, result } })
  render(<ActionConfirmationProvider><EditGuardProvider><ClientProfileRoute selectedClient={{ id: 'client' }} parts={['clients', 'client']} /></EditGuardProvider></ActionConfirmationProvider>)
  const attempt = actions.props.onRenewPackage(pending.draft)
  if (code === 'SAVE_UNCERTAIN') await expect(attempt).rejects.toMatchObject({ code })
  else expect(await attempt).toEqual(result)
  expect(actions.runAction).toHaveBeenCalledTimes(code === 'SAVE_UNCERTAIN' ? 1 : 2)
})
it('does not refresh a confirmed API save until the wizard releases its edit guard', async () => {
  const result = { id: 'client', version: 3, purchaseId: 'purchase' }
  actions.renewPackage.mockResolvedValue(result)
  render(<ActionConfirmationProvider><EditGuardProvider><ClientProfileRoute selectedClient={{ id: 'client' }} parts={['clients', 'client']} /></EditGuardProvider></ActionConfirmationProvider>)
  expect(await actions.props.onRenewPackage(pending.draft)).toEqual(result)
  expect(actions.reload).not.toHaveBeenCalled()
  await actions.props.renewalWorkflow.saved()
  expect(actions.reload).toHaveBeenCalledTimes(1)
})

import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { ActionConfirmationProvider } from '../../components/ActionConfirmationProvider.jsx'
import { EditGuardProvider, useEditGuard } from '../../components/EditGuardProvider.jsx'
import { reactivationReview } from '../../test/clientLifecycleApi.js'
import ApiClientReactivationButton from './ApiClientReactivationButton.jsx'

afterEach(cleanup)
const reviewed = reactivationReview()
function Harness({ workflow }) {
  const { setActiveEdit, guardNavigation } = useEditGuard()
  return <ApiClientReactivationButton workflow={{ ...workflow, saved: () => guardNavigation(workflow.saved) }} onEditing={editing => setActiveEdit(editing ? 'Client reactivation' : null)} />
}
const show = workflow => render(<ActionConfirmationProvider><EditGuardProvider><Harness workflow={workflow} /></EditGuardProvider></ActionConfirmationProvider>)
const workflowFor = patch => ({ review: vi.fn().mockResolvedValue({ reviewed, dates: {}, uncertain: false }), preview: vi.fn(), save: vi.fn().mockResolvedValue({}), saved: vi.fn().mockResolvedValue(), ...patch })

it('requires confirmation and blocks duplicate saves until successful close', async () => {
  let finish
  const workflow = workflowFor({ save: vi.fn(() => new Promise(resolve => { finish = resolve })) })
  show(workflow)
  fireEvent.click(screen.getByRole('button', { name: 'Reactivate Client' }))
  const dialog = await screen.findByRole('dialog')
  expect(workflow.save).not.toHaveBeenCalled()
  fireEvent.click(within(dialog).getByRole('button', { name: 'Reactivate Client' }))
  fireEvent.click(within(dialog).getByRole('button', { name: 'Checking…' }))
  expect(workflow.save).toHaveBeenCalledTimes(1)
  finish()
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  await waitFor(() => expect(workflow.saved).toHaveBeenCalledTimes(1))
})
it('retains an uncertain command and retries its exact reviewed values', async () => {
  const workflow = workflowFor({ save: vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValue({}) })
  show(workflow)
  fireEvent.click(screen.getByRole('button', { name: 'Reactivate Client' }))
  const dialog = await screen.findByRole('dialog')
  fireEvent.click(within(dialog).getByRole('button', { name: 'Reactivate Client' }))
  fireEvent.click(await within(dialog).findByRole('button', { name: 'Check Reactivation' }))
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  expect(workflow.save.mock.calls[1]).toEqual(workflow.save.mock.calls[0])
})
it('does not turn a confirmed save into an uncertain retry when the following refresh fails', async () => {
  const workflow = workflowFor({ saved: vi.fn().mockRejectedValue(new Error('refresh failed')) })
  show(workflow)
  fireEvent.click(screen.getByRole('button', { name: 'Reactivate Client' }))
  fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Reactivate Client' }))
  await waitFor(() => expect(workflow.saved).toHaveBeenCalled())
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(screen.queryByRole('button', { name: 'Check Reactivation' })).toBeNull()
  expect(workflow.save).toHaveBeenCalledTimes(1)
})

it('shows an open session with an inactive trainer without inventing an editable date', async () => {
  const open = { ...reviewed, rows: reviewed.rows.map(row => ({ ...row, scheduleState: 'open', originalDate: null, date: null, startsAt: null, endsAt: null, error: 'Reactivate the assigned trainer before restoring this session.' })) }
  const workflow = workflowFor({ review: vi.fn().mockResolvedValue({ reviewed: open, dates: {}, uncertain: false }) })
  show(workflow)
  fireEvent.click(screen.getByRole('button', { name: 'Reactivate Client' }))
  const dialog = await screen.findByRole('dialog')
  expect(within(dialog).getByText('Open session · No date or time assigned.')).toBeTruthy()
  expect(within(dialog).queryByRole('textbox')).toBeNull()
  expect(within(dialog).getByRole('button', { name: 'Reactivate Client' }).disabled).toBe(true)
  expect(workflow.save).not.toHaveBeenCalled()
})

it('restores one package through the shared guarded confirmation without client lifecycle copy', async () => {
  const packageReview = { ...reviewed, packageId: reviewed.purchaseIds[0] }
  const workflow = workflowFor({ review: vi.fn().mockResolvedValue({ reviewed: packageReview, dates: {}, uncertain: false }) })
  function PackageHarness() {
    const { setActiveEdit } = useEditGuard()
    return <ApiClientReactivationButton packageName="Purchased Twelve" workflow={workflow} onEditing={editing => setActiveEdit(editing ? 'Package reactivation' : null)} />
  }
  render(<ActionConfirmationProvider><EditGuardProvider><PackageHarness /></EditGuardProvider></ActionConfirmationProvider>)
  fireEvent.click(screen.getByRole('button', { name: 'Reactivate Package', exact: true }))
  const dialog = await screen.findByRole('dialog', { name: 'Reactivate Package?' })
  expect(dialog).toHaveTextContent('Purchased Twelve will become active again.')
  expect(dialog).not.toHaveTextContent('Packages disabled with this client')
  fireEvent.click(within(dialog).getByRole('button', { name: 'Reactivate Package', exact: true }))
  await waitFor(() => expect(workflow.saved).toHaveBeenCalledTimes(1))
  expect(workflow.save).toHaveBeenCalledWith({ id: reviewed.id, reviewed: packageReview, dates: {} })
  expect(screen.queryByRole('dialog')).toBeNull()
})

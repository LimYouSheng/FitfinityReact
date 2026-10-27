import { afterEach, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { ActionConfirmationProvider } from '../../components/ActionConfirmationProvider.jsx'
import { EditGuardProvider, useEditGuard } from '../../components/EditGuardProvider.jsx'
import { trainerDeactivationReview } from '../../test/trainerDeactivation.js'
import ApiTrainerDeactivationButton from './ApiTrainerDeactivationButton.jsx'

afterEach(cleanup)
const reviewed = trainerDeactivationReview()
function Harness({ workflow }) {
  const { setActiveEdit, guardNavigation } = useEditGuard()
  return <ApiTrainerDeactivationButton trainer={reviewed} workflow={{ ...workflow, saved: () => guardNavigation(workflow.saved) }} onEditing={editing => setActiveEdit(editing ? 'Trainer deactivation' : null)} />
}
const show = workflow => render(<ActionConfirmationProvider><EditGuardProvider><Harness workflow={workflow} /></EditGuardProvider></ActionConfirmationProvider>)
const workflowFor = patch => ({ review: vi.fn().mockResolvedValue({ reviewed, replacements: {}, uncertain: false }), preview: vi.fn().mockResolvedValue(reviewed), save: vi.fn().mockResolvedValue({}), saved: vi.fn().mockResolvedValue(), ...patch })
async function choose(workflow) {
  fireEvent.click(screen.getByRole('button', { name: 'Deactivate Trainer', exact: true }))
  const dialog = await screen.findByRole('dialog', { name: `Deactivate ${reviewed.name}?` })
  expect(within(dialog).getByRole('button', { name: 'Deactivate Trainer' })).toBeDisabled()
  fireEvent.change(screen.getByLabelText('Reassign API Client'), { target: { value: reviewed.sessions[0].choices[0].id } })
  await waitFor(() => expect(workflow.preview).toHaveBeenCalledTimes(1))
  await waitFor(() => expect(within(dialog).getByRole('button', { name: 'Deactivate Trainer' })).toBeEnabled())
  return dialog
}
it('checks the batch and releases its edit guard before refresh', async () => {
  const workflow = workflowFor({ saved: vi.fn().mockRejectedValue(new Error('refresh unavailable')) })
  show(workflow)
  const dialog = await choose(workflow)
  fireEvent.click(within(dialog).getByRole('button', { name: 'Deactivate Trainer' }))
  await waitFor(() => expect(workflow.saved).toHaveBeenCalledTimes(1))
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(workflow.save).toHaveBeenCalledTimes(1)
})
it('freezes unknown replacement choices and checks the identical save explicitly', async () => {
  const workflow = workflowFor({ save: vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValue({}) })
  show(workflow)
  const dialog = await choose(workflow)
  fireEvent.click(within(dialog).getByRole('button', { name: 'Deactivate Trainer' }))
  const retry = await screen.findByRole('button', { name: 'Check Deactivation' })
  expect(screen.getByLabelText('Reassign API Client')).toBeDisabled()
  fireEvent.click(retry)
  await waitFor(() => expect(workflow.saved).toHaveBeenCalledTimes(1))
  expect(workflow.save.mock.calls[1]).toEqual(workflow.save.mock.calls[0])
})
it('does not submit when server batch preview reports a replacement conflict', async () => {
  const blocked = trainerDeactivationReview(); blocked.sessions[0].choices[0].error = 'Already booked'
  const workflow = workflowFor({ preview: vi.fn().mockResolvedValue(blocked) })
  show(workflow)
  fireEvent.click(screen.getByRole('button', { name: 'Deactivate Trainer' }))
  const dialog = await screen.findByRole('dialog')
  fireEvent.change(screen.getByLabelText('Reassign API Client'), { target: { value: reviewed.sessions[0].choices[0].id } })
  await screen.findByText('No active trainer is free for this session. Resolve the booking conflict before deactivation.')
  expect(within(dialog).getByRole('button', { name: 'Deactivate Trainer' })).toBeDisabled()
  expect(workflow.save).not.toHaveBeenCalled()
})

it.each(['unmounted', 'another edit', 'edit ended'])('ignores a delayed review after the button is %s', async change => {
  let resolve
  const workflow = workflowFor({ review: vi.fn(() => new Promise(done => { resolve = done })) })
  const onEditing = vi.fn()
  const app = (visible, disabled = false) => <ActionConfirmationProvider><EditGuardProvider>{visible && <ApiTrainerDeactivationButton trainer={reviewed} workflow={workflow} disabled={disabled} onEditing={onEditing} />}</EditGuardProvider></ActionConfirmationProvider>
  const view = render(app(true))
  fireEvent.click(screen.getByRole('button', { name: 'Deactivate Trainer', exact: true }))
  view.rerender(app(change !== 'unmounted', true))
  if (change === 'edit ended') view.rerender(app(true))
  await act(async () => resolve({ reviewed, replacements: {}, uncertain: false }))
  expect(onEditing).not.toHaveBeenCalled()
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(workflow.save).not.toHaveBeenCalled()
})

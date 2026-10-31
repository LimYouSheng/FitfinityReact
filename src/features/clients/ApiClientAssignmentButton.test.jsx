import { afterEach, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { ActionConfirmationProvider } from '../../components/ActionConfirmationProvider.jsx'
import { EditGuardProvider, useEditGuard } from '../../components/EditGuardProvider.jsx'
import { assignmentReview } from '../../test/clientAssignment.js'
import ApiClientAssignmentButton from './ApiClientAssignmentButton.jsx'

afterEach(cleanup)
const reviewed = assignmentReview()
function Harness({ workflow, client = reviewed }) {
  const { setActiveEdit, guardNavigation } = useEditGuard()
  return <ApiClientAssignmentButton client={client} timeZone="Asia/Singapore" workflow={{ ...workflow, saved: () => guardNavigation(workflow.saved) }} onEditing={editing => setActiveEdit(editing ? 'Trainer reassignment' : null)} />
}
const show = workflow => render(<ActionConfirmationProvider><EditGuardProvider><Harness workflow={workflow} /></EditGuardProvider></ActionConfirmationProvider>)
const workflowFor = patch => ({ review: vi.fn().mockResolvedValue({ reviewed, trainerId: '', uncertain: false }), save: vi.fn().mockResolvedValue({}), saved: vi.fn().mockResolvedValue(), ...patch })
async function confirm() {
  fireEvent.click(screen.getByRole('button', { name: 'Reassign Trainer', exact: true }))
  await screen.findByRole('dialog', { name: 'Permanently Reassign Trainer' })
  fireEvent.change(screen.getByLabelText('New trainer'), { target: { value: reviewed.choices[0].id } })
  fireEvent.click(screen.getByRole('button', { name: 'Review Reassignment' }))
  const dialog = await screen.findByRole('dialog', { name: `Reassign trainer for ${reviewed.name}?` })
  expect(dialog).toHaveTextContent('1 eligible upcoming sessions and 1 selected package')
  fireEvent.click(within(dialog).getByRole('button', { name: 'Reassign Trainer', exact: true }))
}
it('keeps uncertain selection fixed and explicitly retries the original reviewed assignment', async () => {
  const workflow = workflowFor({ save: vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValue({}) })
  show(workflow)
  await confirm()
  fireEvent.click(await screen.findByRole('button', { name: 'Check Reassignment' }))
  await waitFor(() => expect(workflow.saved).toHaveBeenCalledTimes(1))
  expect(workflow.save.mock.calls[1]).toEqual(workflow.save.mock.calls[0])
  expect(workflow.save.mock.calls[0][0]).toMatchObject({ reviewed, purchaseId: reviewed.purchases[0].id, trainerId: reviewed.choices[0].id })
  expect(screen.queryByRole('dialog')).toBeNull()
})
it('releases the edit guard before refresh and never retries a confirmed save after refresh failure', async () => {
  const workflow = workflowFor({ saved: vi.fn().mockRejectedValue(new Error('refresh unavailable')) })
  show(workflow)
  await confirm()
  await waitFor(() => expect(workflow.saved).toHaveBeenCalledTimes(1))
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(screen.queryByRole('button', { name: 'Check Reassignment' })).toBeNull()
  expect(workflow.save).toHaveBeenCalledTimes(1)
})
it('shows server conflicts and keeps unavailable replacements unselectable', async () => {
  const review = { ...reviewed, choices: reviewed.choices.map(t => ({ ...t, error: 'Already booked at this time.' })) }
  const workflow = workflowFor({ review: vi.fn().mockResolvedValue({ reviewed: review, trainerId: '', uncertain: false }) })
  show(workflow)
  fireEvent.click(screen.getByRole('button', { name: 'Reassign Trainer', exact: true }))
  await screen.findByRole('dialog')
  expect(screen.getByRole('option', { name: 'Replacement Trainer — Unavailable' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Review Reassignment' })).toBeDisabled()
  expect(screen.getByText('Replacement Trainer: Already booked at this time.')).toBeVisible()
  expect(workflow.save).not.toHaveBeenCalled()
})
it('offers a fresh assignment review after successful refresh without repeating the prior save', async () => {
  const next = { ...reviewed, version: 3, current: { id: reviewed.choices[0].id, name: 'Replacement Trainer' }, choices: [{ ...reviewed.current, version: 1, error: null }] }
  const workflow = workflowFor({ review: vi.fn().mockResolvedValueOnce({ reviewed, trainerId: '', uncertain: false }).mockResolvedValueOnce({ reviewed: next, trainerId: '', uncertain: false }), saved: vi.fn().mockResolvedValue({ refreshed: true }) })
  show(workflow)
  await confirm()
  await waitFor(() => expect(workflow.saved).toHaveBeenCalledTimes(1))
  fireEvent.click(await screen.findByRole('button', { name: 'Reassign Trainer', exact: true }))
  await screen.findByRole('dialog', { name: 'Permanently Reassign Trainer' })
  expect(screen.getByRole('option', { name: 'Current Trainer', exact: true })).toBeEnabled()
  expect(workflow.review).toHaveBeenCalledTimes(2)
  expect(workflow.save).toHaveBeenCalledTimes(1)
})

it.each(['unmounted', 'another edit', 'edit ended'])('ignores a delayed review after the button is %s', async change => {
  let resolve
  const workflow = workflowFor({ review: vi.fn(() => new Promise(done => { resolve = done })) })
  const onEditing = vi.fn()
  const app = (visible, disabled = false) => <ActionConfirmationProvider><EditGuardProvider>{visible && <ApiClientAssignmentButton client={reviewed} workflow={workflow} disabled={disabled} onEditing={onEditing} />}</EditGuardProvider></ActionConfirmationProvider>
  const view = render(app(true))
  fireEvent.click(screen.getByRole('button', { name: 'Reassign Trainer', exact: true }))
  view.rerender(app(change !== 'unmounted', true))
  if (change === 'edit ended') view.rerender(app(true))
  await act(async () => resolve({ reviewed, trainerId: '', uncertain: false }))
  expect(onEditing).not.toHaveBeenCalled()
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(workflow.save).not.toHaveBeenCalled()
})

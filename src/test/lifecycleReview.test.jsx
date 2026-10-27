import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { ActionConfirmationProvider } from '../components/ActionConfirmationProvider.jsx'
import { EditGuardProvider, useEditGuard } from '../components/EditGuardProvider.jsx'
import ClientDeactivationButton from '../features/clients/ClientDeactivationButton.jsx'
import ApiClientReactivationButton from '../features/clients/ApiClientReactivationButton.jsx'
import ApiPackageActionButton from '../features/clients/ApiPackageActionButton.jsx'
import ApiFixedWeeklySchedule from '../features/clients/ApiFixedWeeklySchedule.jsx'
import TrainerReactivationButton from '../features/trainers/TrainerReactivationButton.jsx'
import { deactivationReview, reactivationReview } from './clientLifecycleApi.js'
import { weeklyReview } from './clientWeeklySchedule.js'
import { weeklySlots } from '../services/apiClientWeeklySchedule.js'

afterEach(cleanup)
function GuardState() {
  const { activeEdit } = useEditGuard()
  return <output data-testid="active-edit">{activeEdit ?? 'none'}</output>
}
const cases = [
  ['Client deactivation', 'Deactivate Client', ClientDeactivationButton, { reviewed: deactivationReview() }],
  ['Trainer reactivation', 'Reactivate Trainer', TrainerReactivationButton, { reviewed: { id: 'trainer' } }],
  ['Client reactivation', 'Reactivate Client', ApiClientReactivationButton, { reviewed: reactivationReview(), dates: {}, uncertain: false }],
  ['Package deactivation', 'Deactivate Package', ApiPackageActionButton, { reviewed: { name: 'Purchased', eligible: [] }, deleteUpcomingSessions: false }],
  ['Weekly schedule', 'Edit', ApiFixedWeeklySchedule, { reviewed: weeklyReview(), slots: weeklySlots(weeklyReview()) }],
]
for (const [label, button, Component, result] of cases) it.each(['removed', 'disabled', 'resumed', ...(['Client reactivation', 'Package deactivation'].includes(label) ? ['record changed'] : [])])(`${label} retires a delayed opening review when %s`, async change => {
  let resolve
  const review = vi.fn(() => new Promise(done => { resolve = done }))
  const save = vi.fn(), onEditing = vi.fn()
  const app = (visible, disabled = false, recordId = 'first') => <ActionConfirmationProvider><EditGuardProvider>
    <GuardState />
    {visible && <Component recordId={recordId} disabled={disabled} workflow={{ review, save }} onReview={review} onDeactivate={save} onReactivate={save}
      onEditing={onEditing} trainer={{ id: 'trainer', name: 'Trainer' }} client={{ id: 'client', fixedWeeklySchedule: [] }}
      operation="deactivate" editable editing={false} />}
  </EditGuardProvider></ActionConfirmationProvider>
  const view = render(app(true))
  fireEvent.click(screen.getByRole('button', { name: button, exact: true }))
  expect(review).toHaveBeenCalledTimes(1)
  if (change === 'record changed') view.rerender(app(true, false, 'second'))
  else {
    view.rerender(app(change !== 'removed', true))
    if (change === 'resumed') view.rerender(app(true))
  }
  await act(async () => resolve(result))
  expect(onEditing).not.toHaveBeenCalled()
  expect(screen.getByTestId('active-edit')).toHaveTextContent('none')
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(save).not.toHaveBeenCalled()
})

import { afterEach, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import AddTrainerPage from './AddTrainerPage.jsx'
import { createCreationState } from '../../app/creationState.js'
import { mockPolicy } from '../../data/mockPolicy.js'
import { ActionConfirmationProvider } from '../../components/ActionConfirmationProvider.jsx'
import { EditGuardProvider } from '../../components/EditGuardProvider.jsx'

vi.stubGlobal('scrollTo', vi.fn())
Element.prototype.scrollIntoView = vi.fn()
afterEach(cleanup)
const draft = { requestId: '00000000-0000-4000-8000-000000000040', name: 'New Trainer', email: 'new@example.test', phone: { countryCode: '+65', number: '91234567' }, birthday: '1990-01-01', gender: 'Female', trainerType: 'Personal Trainer', qualifications: '', publicProfile: 'Visible', rates: { peak: '80', offPeak: '55' }, availabilityBlocks: [{ id: 'trainer-block-1', days: ['Monday'], from: '18:00', to: '19:00' }], approvalNeeded: mockPolicy.approvalDefaults }
function workflow() {
  const recovery = createCreationState('owner')
  recovery.update({ form: { initialDraft: {}, draft, stepIndex: 4, returningToReview: false, selectedDays: [], from: '18:00', to: '19:00', errors: {}, saving: false, created: null, submitted: null } })
  return recovery
}
function setup(recovery, onCreate, onCreated = vi.fn()) {
  return render(<ActionConfirmationProvider><EditGuardProvider><AddTrainerPage viewer={{ role: 'owner' }} trainers={[]} policy={mockPolicy} realAuthentication recovery={recovery} onCreate={onCreate} onCreated={onCreated} onCancel={() => {}} /></EditGuardProvider></ActionConfirmationProvider>)
}
async function confirm() {
  fireEvent.click(screen.getByRole('button', { name: 'Create Trainer', exact: true }))
  const dialog = await screen.findByRole('dialog')
  expect(within(dialog).getByText(/request a login invitation/)).toBeVisible()
  fireEvent.click(within(dialog).getByRole('button', { name: 'Create Trainer', exact: true }))
}
it('retains the original uncertain submission through remount and explicitly checks it', async () => {
  const recovery = workflow(), onCreated = vi.fn()
  const onCreate = vi.fn().mockRejectedValueOnce(new Error('Connection lost')).mockResolvedValueOnce({ id: 'saved-trainer', invitation: 'unknown' })
  const first = setup(recovery, onCreate, onCreated)
  await confirm()
  await screen.findByRole('button', { name: 'Check Trainer Creation' })
  expect(screen.getByRole('button', { name: 'Edit General Information' })).toBeDisabled()
  first.unmount()
  setup(recovery, onCreate, onCreated)
  fireEvent.click(screen.getByRole('button', { name: 'Check Trainer Creation' }))
  await waitFor(() => expect(onCreated).toHaveBeenCalledWith('saved-trainer', { id: 'saved-trainer', invitation: 'unknown' }))
  expect(onCreate.mock.calls).toEqual([[draft], [draft]])
  expect(recovery.getSnapshot().form.submitted).toBeNull()
})
it('cannot restore a retired login from a late successful creation', async () => {
  const recovery = workflow(), onCreated = vi.fn()
  let finish
  setup(recovery, () => new Promise(resolve => { finish = resolve }), onCreated)
  await confirm()
  await waitFor(() => expect(finish).toBeTypeOf('function'))
  await act(async () => { recovery.retire(); finish({ id: 'late', invitation: 'sent' }) })
  expect(recovery.getSnapshot()).toEqual({})
  expect(onCreated).not.toHaveBeenCalled()
})

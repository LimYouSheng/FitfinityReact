import { useState } from 'react'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ActionConfirmationProvider } from '../../components/ActionConfirmationProvider.jsx'
import AppShell from '../../components/AppShell.jsx'
import { EditGuardProvider, useEditGuard } from '../../components/EditGuardProvider.jsx'
import { DEFAULT_EXERCISES } from '../../app/exerciseCatalog.js'
import ExerciseLibraryPage from './ExerciseLibraryPage.jsx'

afterEach(cleanup)
function Harness({ detailId, onSave, onOutsideClick, user = { id: 'u-owner', name: 'Owner', role: 'owner' } }) {
  const [detail, setDetail] = useState(detailId), [exercises, setExercises] = useState(DEFAULT_EXERCISES)
  const { guardNavigation } = useEditGuard()
  return <AppShell user={user} users={[user]} userId={user.id} route="exercises" messages={[]}
    onRoute={path => guardNavigation(() => setDetail(path.split('/')[1]))} onUserChange={vi.fn()} onReset={vi.fn()}>
    {onOutsideClick && <button type="button" onClick={onOutsideClick}>Outside action</button>}
    <ExerciseLibraryPage user={user} exercises={exercises} detailId={detail}
    onNavigate={path => guardNavigation(() => setDetail(path.split('/')[1]))}
    onBack={() => guardNavigation(() => setDetail(null))}
    onSave={async options => {
      await onSave(options)
      const saved = { ...options.draft, id: options.id || 'created', version: 2, createdAt: '2026-09-06T00:00:00Z' }
      setExercises(current => [saved, ...current.filter(item => item.id !== saved.id)])
      return saved
    }} />
  </AppShell>
}
function mount(props = {}) {
  const onSave = props.onSave || vi.fn().mockResolvedValue(undefined)
  render(<ActionConfirmationProvider><EditGuardProvider><Harness {...props} onSave={onSave} /></EditGuardProvider></ActionConfirmationProvider>)
  return onSave
}
const click = name => fireEvent.click(screen.getByRole('button', { name, exact: true }))
const nameField = () => screen.getByLabelText('Exercise name', { exact: false })
const setName = value => fireEvent.change(nameField(), { target: { value } })
async function confirm(name) {
  fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name, exact: true }))
}
describe('exercise library form and summary', () => {
  it('paginates the original catalog and combines category, search and status filters', () => {
    mount(); expect(screen.getAllByRole('row')).toHaveLength(11)
    click('Next'); expect(screen.getByText('Page 2 of 5')).toBeVisible()
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'Smith' } })
    expect(screen.queryByText('Page 2 of 5')).not.toBeInTheDocument()
    expect(screen.getByText('Smith chest press')).toBeVisible()
    fireEvent.change(screen.getByLabelText('Exercise category'), { target: { value: 'Cardio' } })
    expect(screen.getByText('No exercises match your filters.')).toBeVisible()
    fireEvent.change(screen.getByLabelText('Exercise status'), { target: { value: 'inactive' } })
    expect(screen.getByText('0 exercises')).toBeVisible()
  })
  it('validates required fields and saves only after confirmation, then opens the editable summary', async () => {
    const save = mount({ detailId: 'new' })
    click('Create Exercise'); expect(nameField()).toHaveAttribute('aria-invalid', 'true'); expect(save).not.toHaveBeenCalled()
    setName('Band row'); click('Create Exercise')
    expect(save).not.toHaveBeenCalled()
    fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Cancel', exact: true }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Create Exercise', exact: true })).toBeEnabled())
    expect(nameField()).toHaveValue('Band row'); click('Create Exercise'); await confirm('Create Exercise')
    expect(await screen.findByRole('heading', { name: 'Band row' })).toBeVisible()
    expect(save).toHaveBeenCalledOnce()
    click('Edit Exercise'); expect(nameField()).toHaveValue('Band row')
  })
  it('preserves a failed save for retry and blocks invalid attachments until removed', async () => {
    const save = vi.fn().mockRejectedValueOnce(new Error('Storage full')).mockResolvedValue(undefined)
    mount({ detailId: 'new', onSave: save }); setName('Band row')
    fireEvent.change(screen.getByLabelText('Photo / video'), { target: { files: [new File(['x'], 'x.html', { type: 'text/html' })] } })
    click('Create Exercise'); expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    click('Remove Attachment'); click('Create Exercise'); await confirm('Create Exercise')
    expect(await screen.findByRole('alert')).toHaveTextContent('Storage full'); expect(nameField()).toHaveValue('Band row')
    click('Create Exercise'); await confirm('Create Exercise')
    expect(await screen.findByRole('heading', { name: 'Band row' })).toBeVisible(); expect(save).toHaveBeenCalledTimes(2)
  })
  it('preserves the draft when navigation is cancelled and discards it only when confirmed', async () => {
    const save = mount({ detailId: 'new' }); setName('Draft movement'); click('Back to Exercise Library')
    const dialog = await screen.findByRole('dialog', { name: 'Leave this edit?' })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel', exact: true }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(nameField()).toHaveValue('Draft movement')
    click('Back to Exercise Library'); await confirm('Leave Without Saving')
    expect(await screen.findByRole('table')).toBeVisible(); expect(save).not.toHaveBeenCalled()
  })
  it('requires confirmation to deactivate and keeps the summary available for reactivation', async () => {
    const save = mount({ detailId: 'library-001' })
    click('Deactivate Exercise'); expect(save).not.toHaveBeenCalled(); await confirm('Deactivate Exercise')
    expect(await screen.findByText('Inactive', { exact: true })).toBeVisible()
    expect(save).toHaveBeenCalledWith(expect.objectContaining({ id: 'library-001', expectedVersion: 1, draft: expect.objectContaining({ status: 'inactive' }) }))
    click('Reactivate Exercise'); await confirm('Reactivate Exercise')
    expect(await screen.findByText('Active', { exact: true })).toBeVisible()
  })
  it('keeps form actions usable while the app shell blocks unrelated content, then releases the lock after cancellation', async () => {
    const outside = vi.fn()
    mount({ detailId: 'new', onOutsideClick: outside })
    setName('Draft movement')
    click('Outside action'); expect(outside).not.toHaveBeenCalled()
    click('Create Exercise')
    const dialog = await screen.findByRole('dialog', { name: 'Create Exercise?' })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel', exact: true }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    click('Cancel'); await confirm('Leave Without Saving')
    await screen.findByRole('table')
    click('Outside action'); expect(outside).toHaveBeenCalledOnce()
  })
  it('does not render management controls for a trainer even on a direct new-entry route', () => {
    mount({ detailId: 'new', user: { id: 'u-trainer', name: 'Trainer', role: 'trainer' } })
    expect(screen.getByText('Exercise library management is available to the owner.')).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Create Exercise', exact: true })).not.toBeInTheDocument()
  })
})

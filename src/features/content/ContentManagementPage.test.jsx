import { afterEach, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { ActionConfirmationProvider } from '../../components/ActionConfirmationProvider.jsx'
import { EditGuardProvider } from '../../components/EditGuardProvider.jsx'
import { contentRecord } from '../../services/apiContent.js'
import { contentDraft, contentState } from '../../test/contentApi.js'
import ContentManagementPage from './ContentManagementPage.jsx'
import ApiContentWorkspace from './ApiContentWorkspace.jsx'

vi.mock('../../hooks/usePortalActions.js', () => ({ default: () => ({ runAction: operation => operation() }) }))
afterEach(cleanup)
const saved = contentRecord(contentState())
const wrap = child => <ActionConfirmationProvider><EditGuardProvider>{child}</EditGuardProvider></ActionConfirmationProvider>
function show(props = {}) {
  const options = { entries: [saved], detailId: saved.id, onSave: vi.fn(), onNavigate: vi.fn(), onBack: vi.fn(), guardUncertain: true, ...props }
  const view = value => wrap(<ContentManagementPage {...value} />)
  return { ...render(view(options)), options, view }
}
async function submit() {
  fireEvent.click(screen.getByRole('button', { name: 'Save Content', exact: true }))
  fireEvent.click(within(await screen.findByRole('dialog', { name: 'Save content?' })).getByRole('button', { name: 'Save Content', exact: true }))
}

it('freezes an uncertain edit and checks the original values without another confirmation', async () => {
  const onSave = vi.fn().mockRejectedValueOnce(new Error('Interrupted')).mockResolvedValue({ ...saved, title: 'Changed', version: 2 })
  show({ onSave })
  fireEvent.change(screen.getByLabelText('Content title'), { target: { value: 'Changed' } })
  await submit()
  expect(await screen.findByText('Interrupted')).toBeInTheDocument()
  expect(screen.getByLabelText('Content title')).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: 'Check Content Save' }))
  await screen.findByRole('heading', { name: 'Changed' })
  expect(onSave).toHaveBeenCalledTimes(2)
  expect(onSave.mock.calls[1][0]).toEqual(onSave.mock.calls[0][0])
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
})

it('retains the reviewed version when a newer record arrives during editing', async () => {
  const { options, rerender, view } = show({ onSave: vi.fn().mockRejectedValue(Object.assign(new Error('Changed elsewhere'), { status: 409 })) })
  fireEvent.change(screen.getByLabelText('Content body'), { target: { value: 'My edit' } })
  rerender(view({ ...options, entries: [{ ...saved, version: 2, body: 'Someone else' }] }))
  await submit()
  await screen.findByText('Changed elsewhere')
  expect(options.onSave).toHaveBeenCalledWith({ id: saved.id, expectedVersion: 1, draft: { ...contentDraft, body: 'My edit' } })
  expect(screen.getByLabelText('Content body')).toBeEnabled()
})

it('uses the confirmed revision when explicitly editing again after success', async () => {
  const onSave = vi.fn().mockResolvedValue({ ...saved, version: 2, title: 'First edit' })
  show({ onSave })
  fireEvent.change(screen.getByLabelText('Content title'), { target: { value: 'First edit' } })
  await submit()
  fireEvent.click(await screen.findByRole('button', { name: 'Edit Content', exact: true }))
  fireEvent.change(screen.getByLabelText('Content title'), { target: { value: 'Second edit' } })
  await submit()
  await waitFor(() => expect(onSave).toHaveBeenCalledTimes(2))
  expect(onSave.mock.calls[1][0]).toMatchObject({ expectedVersion: 2, draft: { title: 'Second edit' } })
})

it('retires loaded content immediately on a changed login generation', async () => {
  let complete
  const services = { readContent: vi.fn().mockResolvedValueOnce({ entries: [saved], pending: null }).mockReturnValueOnce(new Promise(resolve => { complete = resolve })) }
  const view = generation => wrap(<ApiContentWorkspace services={services} generation={generation} detailId={saved.id} />)
  const { rerender } = render(view(1))
  await screen.findByLabelText('Content title')
  rerender(view(2))
  expect(screen.queryByLabelText('Content title')).not.toBeInTheDocument()
  expect(screen.getByRole('status')).toHaveTextContent('Loading content')
  await act(async () => complete({ entries: [], pending: null }))
  expect(screen.queryByLabelText('Content title')).not.toBeInTheDocument()
})

it('replaces the editor with an honest submitted state after approval submission', async () => {
  const onSave = vi.fn().mockRejectedValue(Object.assign(new Error('Submitted for Owner approval.'), { code: 'APPROVAL_PENDING', status: 409 }))
  const { options } = show({ onSave })
  fireEvent.change(screen.getByLabelText('Content title'), { target: { value: 'Needs review' } })
  await submit()
  expect(await screen.findByRole('status')).toHaveTextContent('No changes have been applied.')
  expect(screen.queryByRole('button', { name: 'Save Content', exact: true })).not.toBeInTheDocument()
  expect(screen.queryByRole('heading', { name: 'Needs review' })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'View Requests' }))
  expect(options.onNavigate).toHaveBeenCalledWith('messages')
  expect(onSave).toHaveBeenCalledTimes(1)
})

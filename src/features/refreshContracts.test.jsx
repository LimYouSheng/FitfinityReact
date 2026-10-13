import ClientEditableText from './clients/ClientEditableText.jsx'
import { useState } from 'react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, within, waitFor } from '@testing-library/react'
import { seed } from '../data/seed.js'
import { ActionConfirmationProvider } from '../components/ActionConfirmationProvider.jsx'
import { EditGuardProvider } from '../components/EditGuardProvider.jsx'
import ClientGeneralInformation from './clients/ClientGeneralInformation.jsx'
import TrainerProfilePage from './trainers/TrainerProfilePage.jsx'
import SessionNotes from './sessions/SessionNotes.jsx'
import ExerciseLibraryMedia from './exercises/ExerciseLibraryMedia.jsx'

const owner = seed.users.find(user => user.role === 'owner')
const Wrapper = ({ children }) => <ActionConfirmationProvider><EditGuardProvider>{children}</EditGuardProvider></ActionConfirmationProvider>
beforeEach(() => vi.stubGlobal('matchMedia', () => ({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() })))
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })
const general = () => within(screen.getByRole('heading', { name: 'General Information' }).closest('.panel'))

it('personal client edits retain client/person versions and close before refresh without enabling assignment', async () => {
  const save = vi.fn().mockResolvedValue({ version: 3 })
  const refreshed = vi.fn(() => expect(screen.queryByRole('button', { name: 'Save', exact: true })).not.toBeInTheDocument())
  const client = { ...seed.clients[0], version: 2, people: [{ ...seed.clients[0], id: 'person-one', version: 1 }] }
  function Profile({ value }) {
    const [activeEditor, setActiveEditor] = useState(null)
    return <ClientGeneralInformation client={value} policy={seed.settings} ownerEditable={false} personalEditable activeEditor={activeEditor} setActiveEditor={setActiveEditor} onUpdate={save} onSaved={refreshed} />
  }
  const { rerender } = render(<Profile value={client} />, { wrapper: Wrapper })
  expect(screen.queryByRole('button', { name: 'Reassign Trainer' })).not.toBeInTheDocument()
  fireEvent.click(general().getByRole('button', { name: 'Edit', exact: true }))
  fireEvent.change(screen.getByLabelText('Client name'), { target: { value: 'Reviewed Name' } })
  rerender(<Profile value={{ ...client, version: 9, people: [{ ...client.people[0], version: 8 }] }} />)
  fireEvent.click(general().getByRole('button', { name: 'Save', exact: true }))
  fireEvent.click(await screen.findByRole('button', { name: 'Save Changes', exact: true }))
  await waitFor(() => expect(save).toHaveBeenCalledWith(expect.objectContaining({ people: [expect.objectContaining({ name: 'Reviewed Name' })] }), { expectedVersion: 2, people: [{ id: 'person-one', expectedVersion: 1 }] }))
  await waitFor(() => expect(refreshed).toHaveBeenCalledTimes(1))
})

it('approval edits retain the reviewed version across refresh and close before post-save reload', async () => {
  const save = vi.fn().mockResolvedValue({ version: 2 })
  const reloaded = vi.fn(() => expect(screen.queryByRole('button', { name: 'Save', exact: true })).not.toBeInTheDocument())
  const props = { trainer: { ...seed.trainers[0], version: 1 }, viewer: owner, trainers: seed.trainers, clients: seed.clients, sessions: seed.sessions, policy: seed.settings, readOnly: true, autonomyReadOnly: false, onSaveAutonomy: save, onAutonomySaved: reloaded }
  const { rerender } = render(<TrainerProfilePage {...props} />, { wrapper: Wrapper })
  const section = () => within(screen.getByRole('heading', { name: 'Owner Approval Needed' }).closest('.panel'))
  expect(general().queryByRole('button', { name: 'Edit', exact: true })).not.toBeInTheDocument()
  fireEvent.click(section().getByRole('button', { name: 'Edit', exact: true }))
  fireEvent.click(section().getByRole('checkbox', { name: 'Availability changes' }))
  rerender(<TrainerProfilePage {...props} trainer={{ ...props.trainer, version: 9 }} />)
  fireEvent.click(section().getByRole('button', { name: 'Save', exact: true }))
  fireEvent.click(await screen.findByRole('button', { name: 'Save Controls', exact: true }))
  await waitFor(() => expect(save).toHaveBeenCalledWith({ ...props.trainer.approvalNeeded, availability: !props.trainer.approvalNeeded.availability }, 1))
  await waitFor(() => expect(reloaded).toHaveBeenCalledTimes(1))
})

it('preserves an active client draft across snapshot and policy refreshes, then uses the latest saved record after Cancel', () => {
  function Client({ client, policy }) {
    const [activeEditor, setActiveEditor] = useState(null)
    return <ClientGeneralInformation client={client} policy={policy} ownerEditable activeEditor={activeEditor} setActiveEditor={setActiveEditor} />
  }
  const { rerender } = render(<Client client={seed.clients[0]} policy={seed.settings} />, { wrapper: Wrapper })
  fireEvent.click(general().getByRole('button', { name: 'Edit', exact: true }))
  fireEvent.change(screen.getByLabelText('Client name'), { target: { value: 'Unsaved client name' } })
  const refreshed = { ...seed.clients[0], email: 'refreshed@example.test' }
  rerender(<Client client={refreshed} policy={{ ...seed.settings }} />)
  expect(screen.getByLabelText('Client name')).toHaveValue('Unsaved client name')
  fireEvent.click(general().getByRole('button', { name: 'Cancel' }))
  fireEvent.click(general().getByRole('button', { name: 'Edit', exact: true }))
  expect(screen.getByLabelText('Client name')).toHaveValue(seed.clients[0].name)
  expect(screen.getByLabelText('Client email')).toHaveValue('refreshed@example.test')
})

it('preserves an active trainer draft across refresh and updates ordinary read-only fields after Cancel', () => {
  const props = { trainer: seed.trainers[0], viewer: owner, trainers: seed.trainers, clients: seed.clients, sessions: seed.sessions, policy: seed.settings }
  const { rerender } = render(<TrainerProfilePage {...props} />, { wrapper: Wrapper })
  fireEvent.click(general().getByRole('button', { name: 'Edit', exact: true }))
  fireEvent.change(screen.getByLabelText('Trainer qualifications'), { target: { value: 'Unsaved qualifications' } })
  rerender(<TrainerProfilePage {...props} trainer={{ ...props.trainer, qualifications: 'Refreshed qualifications' }} policy={{ ...seed.settings }} />)
  expect(screen.getByLabelText('Trainer qualifications')).toHaveValue('Unsaved qualifications')
  fireEvent.click(general().getByRole('button', { name: 'Cancel' }))
  fireEvent.click(general().getByRole('button', { name: 'Edit', exact: true }))
  expect(screen.getByLabelText('Trainer qualifications')).toHaveValue('Refreshed qualifications')
})

it('preserves session comments while editing and uses refreshed outcome data after Cancel', () => {
  function Notes({ outcome }) {
    const [activeEditor, setActiveEditor] = useState(null)
    return <SessionNotes session={seed.sessions[0]} outcome={outcome} displayedSummary="Summary" canEditNotes activeEditor={activeEditor} setActiveEditor={setActiveEditor} />
  }
  const { rerender } = render(<Notes outcome={{ trainerComments: 'Original', durationMinutes: 60 }} />, { wrapper: Wrapper })
  const panel = () => within(screen.getByRole('heading', { name: 'Session Outcome' }).closest('.panel'))
  fireEvent.click(panel().getByRole('button', { name: 'Edit' }))
  fireEvent.change(screen.getByLabelText('Trainer comments'), { target: { value: 'Unsaved comments' } })
  rerender(<Notes outcome={{ trainerComments: 'Refreshed', durationMinutes: 90 }} />)
  expect(screen.getByLabelText('Trainer comments')).toHaveValue('Unsaved comments')
  fireEvent.click(panel().getByRole('button', { name: 'Cancel' }))
  fireEvent.click(panel().getByRole('button', { name: 'Edit' }))
  expect(screen.getByLabelText('Trainer comments')).toHaveValue('Refreshed')
})

it('retains a loaded media preview across callback refreshes and uses the latest loader for a changed resource', async () => {
  const createUrl = vi.spyOn(URL, 'createObjectURL').mockReturnValueOnce('blob:first').mockReturnValueOnce('blob:second')
  const revoke = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
  const first = vi.fn().mockResolvedValue(new Blob(['one'])), latest = vi.fn().mockResolvedValue(new Blob(['two']))
  const { rerender, unmount } = render(<ExerciseLibraryMedia media={{ id: 'one', type: 'image/png' }} onLoad={first} />)
  expect(await screen.findByRole('img')).toHaveAttribute('src', 'blob:first')
  rerender(<ExerciseLibraryMedia media={{ id: 'one', type: 'image/png' }} onLoad={latest} />)
  expect(latest).not.toHaveBeenCalled()
  expect(createUrl).toHaveBeenCalledTimes(1)
  rerender(<ExerciseLibraryMedia media={{ id: 'two', type: 'image/png' }} onLoad={latest} />)
  expect(await screen.findByRole('img')).toHaveAttribute('src', 'blob:second')
  expect(latest).toHaveBeenCalledWith('two')
  expect(first).toHaveBeenCalledTimes(1)
  expect(revoke).toHaveBeenCalledWith('blob:first')
  unmount()
  expect(revoke).toHaveBeenCalledWith('blob:second')
})


it('general notes retain the reviewed version and draft through refresh and close before reload', async () => {
  const save = vi.fn().mockResolvedValue({ version: 3 })
  const refreshed = vi.fn(() => expect(screen.queryByRole('button', { name: 'Save', exact: true })).not.toBeInTheDocument())
  function Notes({ version, value }) {
    const [editing, setEditing] = useState(false)
    return <ClientEditableText title="General notes" value={value} version={version} editable multiline editing={editing} onBeginEdit={() => setEditing(true)} onEndEdit={() => setEditing(false)} onSave={save} onSaved={refreshed} />
  }
  const { rerender } = render(<Notes version={2} value="Original" />, { wrapper: Wrapper })
  fireEvent.click(screen.getByRole('button', { name: 'Edit', exact: true }))
  fireEvent.change(screen.getByLabelText('General notes'), { target: { value: 'Draft' } })
  rerender(<Notes version={9} value="Other editor" />)
  expect(screen.getByLabelText('General notes')).toHaveValue('Draft')
  fireEvent.click(screen.getByRole('button', { name: 'Save', exact: true }))
  fireEvent.click(await screen.findByRole('button', { name: 'Save Changes', exact: true }))
  await waitFor(() => expect(save).toHaveBeenCalledWith('Draft', { expectedVersion: 2 }))
  await waitFor(() => expect(refreshed).toHaveBeenCalledTimes(1))
})

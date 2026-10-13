import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { useState } from 'react'
import { ActionConfirmationProvider } from '../../components/ActionConfirmationProvider.jsx'
import TrainerEmailEditor from './TrainerEmailEditor.jsx'

afterEach(cleanup)
const trainer = { id: 'trainer-id', version: 1, status: 'active' }
const pending = { id: 'pending-id', email: 'new@example.test', state: 'requested', signedOut: false }
function Wrapper({ trainer: current, auth, request }) {
  const [editing, setEditing] = useState(false)
  return <ActionConfirmationProvider><TrainerEmailEditor trainer={current} auth={auth} onRequest={request} editing={editing} disabled={editing} onEdit={() => setEditing(true)} onClose={() => setEditing(false)} /></ActionConfirmationProvider>
}

it('captures the reviewed version and shows pending verification without claiming an email switch', async () => {
  const auth = { pendingTrainerEmailChange: vi.fn().mockResolvedValue(null) }
  const request = vi.fn().mockResolvedValue(pending)
  const { rerender } = render(<Wrapper trainer={trainer} auth={auth} request={request} />)
  fireEvent.click(await screen.findByRole('button', { name: 'Change Login Email' }))
  fireEvent.change(screen.getByLabelText('New trainer login email'), { target: { value: 'new@example.test' } })
  rerender(<Wrapper trainer={{ ...trainer, version: 2 }} auth={auth} request={request} />)
  fireEvent.click(screen.getByRole('button', { name: 'Request Verification' }))
  fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Request Verification' }))
  await waitFor(() => expect(request).toHaveBeenCalledWith({ email: 'new@example.test' }, 1))
  expect(await screen.findByText(/Awaiting the trainer’s verification/)).toHaveTextContent('current email is still active')
  expect(screen.queryByLabelText('New trainer login email')).not.toBeInTheDocument()
})

it('restores the pending request after reload and does not create another request', async () => {
  const auth = { pendingTrainerEmailChange: vi.fn().mockResolvedValue(pending) }
  const request = vi.fn()
  render(<Wrapper trainer={trainer} auth={auth} request={request} />)
  await screen.findByText(/Awaiting the trainer’s verification/)
  expect(screen.queryByRole('button', { name: 'Change Login Email' })).not.toBeInTheDocument()
  expect(request).not.toHaveBeenCalled()
})

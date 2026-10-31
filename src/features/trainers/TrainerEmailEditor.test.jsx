import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { useState } from 'react'
import { ActionConfirmationProvider } from '../../components/ActionConfirmationProvider.jsx'
import TrainerEmailEditor from './TrainerEmailEditor.jsx'

afterEach(cleanup)
const trainer = { id: 'trainer-id', version: 1, status: 'active' }
const pending = { id: 'pending-id', email: 'new@example.test', state: 'requested', signedOut: false }
function Wrapper({ trainer: current, auth, request, canCorrect = true }) {
  const [editing, setEditing] = useState(false)
  return <ActionConfirmationProvider><TrainerEmailEditor canCorrect={canCorrect} trainer={current} auth={auth} onRequest={request} editing={editing} disabled={editing} onEdit={() => setEditing(true)} onClose={() => setEditing(false)} /></ActionConfirmationProvider>
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


it('corrects only the reviewed pending identity and profile version after confirmation', async () => {
  const auth = { pendingTrainerEmailChange: vi.fn().mockResolvedValue(pending) }
  const request = vi.fn().mockResolvedValue({ ...pending, id: 'corrected-id', email: 'correct@example.test' })
  const { rerender } = render(<Wrapper trainer={trainer} auth={auth} request={request} />)
  fireEvent.click(await screen.findByRole('button', { name: 'Correct Pending Email' }))
  fireEvent.change(screen.getByLabelText('New trainer login email'), { target: { value: 'correct@example.test' } })
  rerender(<Wrapper trainer={{ ...trainer, version: 2 }} auth={auth} request={request} />)
  fireEvent.click(screen.getByRole('button', { name: 'Request Verification' }))
  expect(request).not.toHaveBeenCalled()
  fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Request Verification' }))
  await waitFor(() => expect(request).toHaveBeenCalledWith({ email: 'correct@example.test', supersedes: pending.id }, 1))
  expect(await screen.findByText(/Awaiting the trainer’s verification/)).toHaveTextContent('correct@example.test')
})

it('keeps uncertain provider actions out of the correction editor', async () => {
  const auth = { pendingTrainerEmailChange: vi.fn().mockResolvedValue({ ...pending, state: 'verifying' }) }
  const request = vi.fn()
  render(<Wrapper trainer={trainer} auth={auth} request={request} />)
  await screen.findByText(/must check the pending verification/)
  expect(screen.queryByRole('button', { name: 'Correct Pending Email' })).not.toBeInTheDocument()
  expect(request).not.toHaveBeenCalled()
})

it('freezes an uncertain correction and checks the original request without a second confirmation', async () => {
  const auth = { pendingTrainerEmailChange: vi.fn().mockResolvedValue(pending) }
  const request = vi.fn().mockRejectedValueOnce(new Error('Lost response')).mockResolvedValueOnce({ ...pending, id: 'corrected-id', email: 'correct@example.test' })
  render(<Wrapper trainer={trainer} auth={auth} request={request} />)
  fireEvent.click(await screen.findByRole('button', { name: 'Correct Pending Email' }))
  fireEvent.change(screen.getByLabelText('New trainer login email'), { target: { value: 'correct@example.test' } })
  fireEvent.click(screen.getByRole('button', { name: 'Request Verification' }))
  fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Request Verification' }))
  await screen.findByRole('button', { name: 'Check Original Request' })
  expect(screen.getByLabelText('New trainer login email')).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: 'Check Original Request' }))
  await screen.findByText(/Awaiting the trainer’s verification of correct@example.test/)
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(request.mock.calls).toEqual([
    [{ email: 'correct@example.test', supersedes: pending.id }, 1],
    [{ email: 'correct@example.test', supersedes: pending.id }, 1],
  ])
})


it('does not offer correction before compatible-runtime activation', async () => {
  const auth = { pendingTrainerEmailChange: vi.fn().mockResolvedValue(pending) }
  const request = vi.fn()
  render(<Wrapper trainer={trainer} auth={auth} request={request} canCorrect={false} />)
  await screen.findByText(/Awaiting the trainer’s verification/)
  expect(screen.queryByRole('button', { name: 'Correct Pending Email' })).not.toBeInTheDocument()
  expect(request).not.toHaveBeenCalled()
})

it.each([false, true])('confirmed approval submission retires the email editor without claiming verification (lost response: %s)', async lost => {
  const auth = { pendingTrainerEmailChange: vi.fn().mockResolvedValue(null) }
  const approval = Object.assign(new Error('Submitted for Owner approval.'), { code: 'APPROVAL_PENDING', status: 409 })
  const request = vi.fn().mockRejectedValue(approval)
  if (lost) request.mockRejectedValueOnce(new Error('Lost response'))
  render(<Wrapper trainer={trainer} auth={auth} request={request} />)
  fireEvent.click(await screen.findByRole('button', { name: 'Change Login Email' }))
  fireEvent.change(screen.getByLabelText('New trainer login email'), { target: { value: 'reviewed@example.test' } })
  fireEvent.click(screen.getByRole('button', { name: 'Request Verification' }))
  fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Request Verification' }))
  if (lost) fireEvent.click(await screen.findByRole('button', { name: 'Check Original Request' }))
  expect(await screen.findByRole('status')).toHaveTextContent('Submitted for Owner approval. The current email is still active.')
  expect(screen.queryByRole('button', { name: 'Request Verification' })).not.toBeInTheDocument()
  expect(screen.queryByText(/Awaiting the trainer’s verification/)).not.toBeInTheDocument()
  expect(screen.queryByLabelText('New trainer login email')).not.toBeInTheDocument()
  expect(request).toHaveBeenCalledTimes(lost ? 2 : 1)
})

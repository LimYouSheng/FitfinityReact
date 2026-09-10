import { afterEach, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ActionConfirmationProvider } from '../../components/ActionConfirmationProvider.jsx'
import RequestReview from './RequestReview.jsx'
afterEach(cleanup)
const message = {id:'r1', status:'pending', request:{type:'session_time',sessionId:'s1',previous:{date:'2026-09-05',from:'10:00',to:'11:00'},next:{date:'2026-09-06',from:'12:00',to:'13:00'}}}
function show(onResolve) {
  return render(<ActionConfirmationProvider><RequestReview message={message} trainers={[]} sessions={[]} onResolve={onResolve} /></ActionConfirmationProvider>)
}
it('shows both schedules and applies only after explicit confirmation', async () => {
  const user = userEvent.setup(), resolve = vi.fn().mockResolvedValue(undefined)
  show(resolve)
  expect(screen.getByText(/Sunday, .*12:00–13:00/)).toBeVisible()
  await user.click(screen.getByRole('button',{name:'Approve Request'}))
  expect(resolve).not.toHaveBeenCalled()
  await user.click(within(screen.getByRole('dialog')).getByRole('button',{name:'Approve Request'}))
  expect(resolve).toHaveBeenCalledExactlyOnceWith('r1','approved')
})
it('shows a service failure and permits rejection afterward', async () => {
  const user = userEvent.setup(), resolve = vi.fn().mockRejectedValue(new Error('The session changed.'))
  show(resolve)
  await user.click(screen.getByRole('button',{name:'Approve Request'}))
  await user.click(within(screen.getByRole('dialog')).getByRole('button',{name:'Approve Request'}))
  expect(await screen.findByRole('alert')).toHaveTextContent('The session changed.')
  expect(screen.getByRole('button',{name:'Reject Request'})).toBeEnabled()
})

it('shows the proposal to its requester and cancels only after confirmation, preserving a dismissed review', async () => {
  const user = userEvent.setup(), cancel = vi.fn().mockResolvedValue(undefined)
  render(<ActionConfirmationProvider><RequestReview message={{ ...message, id: 'receipt', requestId: 'r1' }} trainers={[]} sessions={[]} onCancel={cancel} /></ActionConfirmationProvider>)
  expect(screen.queryByRole('button', { name: 'Approve Request' })).not.toBeInTheDocument()
  expect(screen.getByLabelText('Requested')).toHaveTextContent('12:00–13:00')
  await user.click(screen.getByRole('button', { name: 'Cancel Request' }))
  expect(cancel).not.toHaveBeenCalled()
  await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel', exact: true }))
  expect(cancel).not.toHaveBeenCalled()
  await user.click(screen.getByRole('button', { name: 'Cancel Request' }))
  await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel Request' }))
  expect(cancel).toHaveBeenCalledExactlyOnceWith('r1')
})

it('coalesces cancellation clicks, keeps service failures retryable and removes the action after settlement', async () => {
  let finish
  const cancel = vi.fn().mockRejectedValueOnce(new Error('Request already approved.')).mockImplementation(() => new Promise(resolve => { finish = resolve }))
  const view = render(<ActionConfirmationProvider><RequestReview message={message} trainers={[]} sessions={[]} onCancel={cancel} /></ActionConfirmationProvider>)
  await userEvent.click(screen.getByRole('button', { name: 'Cancel Request' }))
  await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel Request' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('already approved')
  fireEvent.click(screen.getByRole('button', { name: 'Cancel Request' }))
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel Request' }))
  await act(async () => {})
  fireEvent.click(screen.getByRole('button', { name: 'Cancel Request' }))
  expect(cancel).toHaveBeenCalledTimes(2)
  await act(async () => finish())
  view.rerender(<ActionConfirmationProvider><RequestReview message={{ ...message, status: 'cancelled' }} trainers={[]} sessions={[]} onCancel={cancel} /></ActionConfirmationProvider>)
  expect(screen.queryByRole('button', { name: 'Cancel Request' })).not.toBeInTheDocument()
})

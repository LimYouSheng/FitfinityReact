import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen, within } from '@testing-library/react'
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

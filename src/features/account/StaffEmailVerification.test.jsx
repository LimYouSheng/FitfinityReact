import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import StaffEmailVerification from './StaffEmailVerification.jsx'

const pending = { id: 'pending-id', email: 'new@example.test', state: 'pending', signedOut: false }
afterEach(cleanup)

it('requires explicit status reconciliation after an uncertain verification', async () => {
  const auth = {
    pendingEmailChange: vi.fn().mockResolvedValue(pending),
    verifyEmailChange: vi.fn().mockRejectedValue(Object.assign(new Error('Connection interrupted'), { status: 503 })),
    reconcileEmailChange: vi.fn().mockResolvedValue({ ...pending, state: 'completed', signedOut: true }),
    sendEmailCode: vi.fn(),
  }
  const completed = vi.fn()
  render(<StaffEmailVerification auth={auth} onCompleted={completed} />)
  fireEvent.change(await screen.findByLabelText('Email verification code'), { target: { value: '123456' } })
  fireEvent.click(screen.getByRole('button', { name: 'Verify New Email' }))
  await screen.findByText('Connection interrupted')
  expect(screen.getByRole('button', { name: 'Verify New Email' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Send New Code' })).toBeDisabled()
  expect(auth.sendEmailCode).not.toHaveBeenCalled()
  expect(auth.reconcileEmailChange).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Check Verification Status' }))
  await waitFor(() => expect(completed).toHaveBeenCalledTimes(1))
  expect(auth.verifyEmailChange).toHaveBeenCalledTimes(1)
  expect(await screen.findByText('Email verified. Sign in with your new email.')).toBeInTheDocument()
})

it('shows failed status reads with retry and ignores the previous account response', async () => {
  let resolveOld
  const old = { pendingEmailChange: vi.fn(() => new Promise(resolve => { resolveOld = resolve })) }
  const current = { pendingEmailChange: vi.fn().mockRejectedValueOnce(new Error('Status unavailable')).mockResolvedValue(null) }
  const { rerender } = render(<StaffEmailVerification auth={old} onCompleted={vi.fn()} />)
  rerender(<StaffEmailVerification auth={current} onCompleted={vi.fn()} />)
  await screen.findByText('Status unavailable')
  await act(async () => resolveOld(pending))
  expect(screen.queryByText('new@example.test')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Retry Email Status' }))
  await waitFor(() => expect(screen.queryByText('Status unavailable')).not.toBeInTheDocument())
})

it('loads an interrupted send as uncertain and never sends on mount', async () => {
  const auth = { pendingEmailChange: vi.fn().mockResolvedValue({ ...pending, state: 'sending' }), sendEmailCode: vi.fn() }
  render(<StaffEmailVerification auth={auth} onCompleted={vi.fn()} />)
  expect(await screen.findByRole('button', { name: 'Send New Code' })).toBeDisabled()
  expect(auth.sendEmailCode).not.toHaveBeenCalled()
})

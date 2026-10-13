import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { ActionConfirmationProvider } from '../../components/ActionConfirmationProvider.jsx'
import TrainerReactivationButton from './TrainerReactivationButton.jsx'

afterEach(cleanup)
const trainer = { id: 'trainer', name: 'Trainer One' }
const reviewed = { id: 'trainer', version: 2, accountId: null, accountVersion: null }
const show = props => render(<ActionConfirmationProvider><TrainerReactivationButton trainer={trainer} {...props} /></ActionConfirmationProvider>)

it('waits for account review and confirmation and prevents duplicate submissions', async () => {
  let finish
  const onReview = vi.fn().mockResolvedValue({ reviewed })
  const onReactivate = vi.fn(() => new Promise(resolve => { finish = resolve }))
  show({ onReview, onReactivate })
  fireEvent.click(screen.getByRole('button', { name: 'Reactivate Trainer' }))
  const dialog = await screen.findByRole('dialog')
  expect(onReactivate).not.toHaveBeenCalled()
  fireEvent.click(within(dialog).getByRole('button', { name: 'Reactivate Trainer' }))
  await waitFor(() => expect(onReactivate).toHaveBeenCalledWith(reviewed))
  fireEvent.click(screen.getByRole('button', { name: 'Checking Trainer…' }))
  expect(onReview).toHaveBeenCalledTimes(1)
  expect(onReactivate).toHaveBeenCalledTimes(1)
  finish()
  await waitFor(() => expect(screen.queryByRole('button')).toBeNull())
})

it('cancellation performs no write', async () => {
  const onReactivate = vi.fn()
  show({ onReview: async () => ({ reviewed }), onReactivate })
  fireEvent.click(screen.getByRole('button'))
  fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Cancel' }))
  await waitFor(() => expect(screen.getByRole('button', { name: 'Reactivate Trainer' }).disabled).toBe(false))
  expect(onReactivate).not.toHaveBeenCalled()
})

it('checks an uncertain request using the retained review without another confirmation', async () => {
  const onReview = vi.fn().mockResolvedValueOnce({ reviewed }).mockResolvedValue({ reviewed, uncertain: true })
  const onReactivate = vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValue(undefined)
  show({ onReview, onReactivate })
  fireEvent.click(screen.getByRole('button'))
  fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Reactivate Trainer' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Check Reactivation' }))
  await waitFor(() => expect(onReactivate).toHaveBeenCalledTimes(2))
  expect(onReactivate.mock.calls[1]).toEqual([reviewed])
  await waitFor(() => expect(screen.queryByRole('button')).toBeNull())
})

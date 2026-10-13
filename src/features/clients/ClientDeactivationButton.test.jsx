import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { ActionConfirmationProvider } from '../../components/ActionConfirmationProvider.jsx'
import ClientDeactivationButton from './ClientDeactivationButton.jsx'

afterEach(cleanup)
const reviewed = { id: 'client', version: 2, name: 'Client One', purchases: [{ id: 'purchase', status: 'active' }] }
const show = props => render(<ActionConfirmationProvider><ClientDeactivationButton {...props} /></ActionConfirmationProvider>)

it('waits for client/purchase review and confirmation and prevents duplicate submissions', async () => {
  let finish
  const onReview = vi.fn().mockResolvedValue({ reviewed })
  const onDeactivate = vi.fn(() => new Promise(resolve => { finish = resolve }))
  show({ onReview, onDeactivate })
  fireEvent.click(screen.getByRole('button', { name: 'Deactivate Client' }))
  const dialog = await screen.findByRole('dialog')
  expect(onDeactivate).not.toHaveBeenCalled()
  fireEvent.click(within(dialog).getByRole('button', { name: 'Deactivate Client' }))
  await waitFor(() => expect(onDeactivate).toHaveBeenCalledWith(reviewed))
  fireEvent.click(screen.getByRole('button', { name: 'Checking Client…' }))
  expect(onReview).toHaveBeenCalledTimes(1)
  expect(onDeactivate).toHaveBeenCalledTimes(1)
  finish()
  await waitFor(() => expect(screen.queryByRole('button')).toBeNull())
})

it('cancellation performs no write', async () => {
  const onDeactivate = vi.fn()
  show({ onReview: async () => ({ reviewed }), onDeactivate })
  fireEvent.click(screen.getByRole('button'))
  fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Cancel' }))
  await waitFor(() => expect(screen.getByRole('button', { name: 'Deactivate Client' }).disabled).toBe(false))
  expect(onDeactivate).not.toHaveBeenCalled()
})

it('checks an uncertain request using the retained review without another confirmation', async () => {
  const onReview = vi.fn().mockResolvedValueOnce({ reviewed }).mockResolvedValue({ reviewed, uncertain: true })
  const onDeactivate = vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValue(undefined)
  show({ onReview, onDeactivate })
  fireEvent.click(screen.getByRole('button'))
  fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Deactivate Client' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Check Deactivation' }))
  await waitFor(() => expect(onDeactivate).toHaveBeenCalledTimes(2))
  expect(onDeactivate.mock.calls[1]).toEqual([reviewed])
  await waitFor(() => expect(screen.queryByRole('button')).toBeNull())
})

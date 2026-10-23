import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import PreviousPlanDialog from './PreviousPlanDialog.jsx'

afterEach(cleanup)
const source = { date: '2026-10-01', items: [{ id: 'one', name: 'Squat', weight: '12 kg', reps: '8', rounds: '3', rest: '60s', customDetails: [{ id: 'detail', value: 'Slow descent' }] }] }
function show(onCopy = vi.fn().mockResolvedValue({}), value = { source }) {
  const onEnd = vi.fn(), onBegin = vi.fn()
  render(<PreviousPlanDialog available onPreview={async () => value} onCopy={onCopy} onBegin={onBegin} onEnd={onEnd} />)
  return { onCopy, onEnd, onBegin }
}
it('previews ordered prescriptions without writing until explicit replacement confirmation', async () => {
  const { onCopy, onEnd } = show()
  fireEvent.click(screen.getByRole('button', { name: 'Previous Plan' }))
  expect(await screen.findByText('Slow descent')).toBeVisible()
  expect(screen.getByText(/Videos remain with their original session/)).toBeVisible()
  expect(onCopy).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Replace Plan' }))
  await waitFor(() => expect(onEnd).toHaveBeenCalledTimes(1))
  expect(onCopy).toHaveBeenCalledWith({ source })
})
it('no-source preview offers no replacement action', async () => {
  const { onCopy } = show(undefined, { source: null })
  fireEvent.click(screen.getByRole('button', { name: 'Previous Plan' }))
  expect(await screen.findByText('No previous exercise plan is available.')).toBeVisible()
  expect(screen.queryByRole('button', { name: 'Replace Plan' })).toBeNull()
  expect(onCopy).not.toHaveBeenCalled()
})
it('lost copy cannot close or start a replacement and checks the same preview', async () => {
  const save = vi.fn().mockRejectedValueOnce(new Error('Lost')).mockResolvedValueOnce({})
  const { onEnd } = show(save)
  fireEvent.click(screen.getByRole('button', { name: 'Previous Plan' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Replace Plan' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Lost')
  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
  expect(onEnd).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Check original copy' }))
  await waitFor(() => expect(onEnd).toHaveBeenCalledTimes(1))
  expect(save.mock.calls[1][0].source).toEqual(save.mock.calls[0][0].source)
})

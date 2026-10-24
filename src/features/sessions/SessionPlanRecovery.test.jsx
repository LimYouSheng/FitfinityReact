import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { portalRequest } from '../../services/portalContracts.js'
import SessionPlanRecovery from './SessionPlanRecovery.jsx'

const reload = vi.fn(), runAction = vi.fn(action => action())
vi.mock('../../hooks/usePortalActions.js', () => ({ default: () => ({ reload, runAction }) }))
afterEach(() => { cleanup(); vi.clearAllMocks() })
it('copy recovery dispatches only its declared named input while retaining the displayed original items', async () => {
  const pending = { sessionId: 'target', reviewed: {}, copySource: {}, items: [{ id: 'source-item', name: 'Original squat' }] }
  const copyPreviousPlan = vi.fn(async input => portalRequest({ service: 'sessionService', operation: 'copyPreviousPlan', input }, 'api'))
  render(<SessionPlanRecovery pending={pending} services={{ sessionService: { copyPreviousPlan } }} />)
  expect(screen.getByText('Original squat')).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: 'Check original save' }))
  await waitFor(() => expect(reload).toHaveBeenCalledTimes(1))
  expect(copyPreviousPlan).toHaveBeenCalledWith({ sessionId: 'target', reviewed: {}, copySource: {} })
})

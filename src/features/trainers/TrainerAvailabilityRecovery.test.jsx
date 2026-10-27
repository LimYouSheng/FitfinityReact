import { afterEach, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import TrainerAvailabilityRecovery from './TrainerAvailabilityRecovery.jsx'
import TrainerProfileRoute from './TrainerProfileRoute.jsx'

const actions = vi.hoisted(() => ({ runAction: vi.fn(fn => fn()), reload: vi.fn(), props: null, saveAvailability: vi.fn() }))
vi.mock('../../hooks/usePortalActions.js', () => ({ default: () => actions }))
vi.mock('../../hooks/usePortalData.js', () => ({ default: () => ({ snapshot: { user: { role: 'trainer' }, data: { trainers: [], clients: [] }, policy: {}, capabilities: { apiBackedWorkflows: true, trainerAvailabilityWrites: true } }, services: { trainerService: { saveAvailability: actions.saveAvailability } } }) }))
vi.mock('./TrainerProfilePage.jsx', () => ({ default: props => { actions.props = props; return null } }))
afterEach(() => { cleanup(); vi.clearAllMocks(); actions.reload.mockReset(); actions.saveAvailability.mockReset() })
const pending = { id: 'trainer', expectedVersion: 4, blocks: [{ days: ['Monday'], from: '10:00', to: '11:00' }] }
it('coalesces explicit checks and submits the original reviewed input', async () => {
  let finish
  const saveAvailability = vi.fn(() => new Promise(resolve => { finish = resolve }))
  render(<TrainerAvailabilityRecovery pending={pending} services={{ trainerService: { saveAvailability } }} />)
  fireEvent.click(screen.getByRole('button', { name: 'Check Availability Save' }))
  fireEvent.click(screen.getByRole('button', { name: 'Checking Availability…' }))
  expect(saveAvailability).toHaveBeenCalledExactlyOnceWith(pending)
  await act(async () => finish({ outcome: 'requested' }))
  expect(actions.reload).toHaveBeenCalledTimes(1)
})
it.each([409, 503])('refreshes only a definitive rejection while preserving unknown status %i', async status => {
  const saveAvailability = vi.fn().mockRejectedValue({ status })
  render(<TrainerAvailabilityRecovery pending={pending} services={{ trainerService: { saveAvailability } }} />)
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Check Availability Save' })))
  expect(actions.reload).toHaveBeenCalledTimes(status === 409 ? 1 : 0)
  expect(screen.getByRole('button', { name: 'Check Availability Save' })).toBeEnabled()
})

it.each(['NETWORK_ERROR', 'SAVE_UNCERTAIN'])('route recovery never treats a different draft as saved after %s', async code => {
  const result = { outcome: 'requested', trainer: { id: 'trainer', version: 4 }, requestId: 'proposal' }
  actions.saveAvailability.mockRejectedValue({ code })
  actions.reload.mockResolvedValue({ trainerAvailabilityRecovered: result })
  render(<TrainerProfileRoute trainer={{ id: 'trainer' }} />)
  const attempt = actions.props.onSaveAvailability(pending.blocks, 4)
  if (code === 'SAVE_UNCERTAIN') await expect(attempt).rejects.toMatchObject({ code })
  else expect(await attempt).toEqual(result)
  expect(actions.runAction).toHaveBeenCalledTimes(code === 'SAVE_UNCERTAIN' ? 1 : 2)
})

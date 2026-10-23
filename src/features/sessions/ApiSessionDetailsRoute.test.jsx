import { afterEach, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { PortalData } from '../../hooks/usePortalData.js'
import { ActionConfirmationProvider } from '../../components/ActionConfirmationProvider.jsx'
import { EditGuardProvider } from '../../components/EditGuardProvider.jsx'
import { staff } from '../../test/api.js'
import { sessionDetailData } from '../../test/sessionReads.js'
import { directoryId } from '../../test/directory.js'
import { sessionDetail } from '../../services/apiSessionReads.js'
import ApiSessionDetailsRoute from './ApiSessionDetailsRoute.jsx'
afterEach(() => { cleanup(); vi.useRealTimers() })
function show(services, patch = {}) {
  const snapshot = { user: staff, policy: { timeZone: 'Asia/Singapore' }, sessionGeneration: 0, serverAt: '2026-10-13T06:00:00Z', data: { clients: [], trainers: [], messages: [] }, ...patch }
  const node = selectedSession => <PortalData.Provider value={{ snapshot, services, refresh: async () => snapshot, today: '2026-10-13' }}><ActionConfirmationProvider><EditGuardProvider><ApiSessionDetailsRoute selectedSession={selectedSession} navigate={vi.fn()} openClient={vi.fn()} /></EditGuardProvider></ActionConfirmationProvider></PortalData.Provider>
  const rendered = render(node({ id: directoryId(30), version: 1 }))
  return { ...rendered, update: id => rendered.rerender(node({ id, version: 1 })), refresh: () => { snapshot.serverAt = '2026-10-13T06:00:01Z'; rendered.rerender(node({ id: directoryId(30), version: 1 })) } }
}
it('shows stored plan/outcome evidence and keeps every unavailable mutation disabled', async () => {
  const services = { readSessionDetails: vi.fn().mockResolvedValue(sessionDetail(sessionDetailData(), directoryId(30), staff)) }
  show(services)
  expect(await screen.findByText('Stored instruction')).toBeVisible()
  expect(screen.getByText('Stored outcome')).toBeVisible()
  expect(screen.getByText('Stored client summary')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Postpone', exact: true })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Export Summary', exact: true })).toBeDisabled()
  for (const button of screen.queryAllByRole('button', { name: 'Edit', exact: true })) expect(button).toBeDisabled()
  expect(screen.queryByRole('button', { name: 'Client Signature', exact: true })).toBeNull()
})
it('opens only limited cover names and keeps completed cover profile access disabled', async () => {
  const value = sessionDetail(sessionDetailData(), directoryId(30), staff)
  const services = { readSessionDetails: vi.fn().mockResolvedValue(value), readSessionClient: vi.fn().mockResolvedValue({ name: 'Covered Couple', person_names: ['First', 'Second'] }) }
  const view = show(services)
  fireEvent.click(await screen.findByRole('button', { name: 'View Client' }))
  const dialog = await screen.findByRole('dialog', { name: 'Session Client' })
  expect(within(dialog).getByText('First')).toBeVisible()
  expect(within(dialog).getByText('Second')).toBeVisible()
  cleanup()
  services.readSessionDetails.mockResolvedValue({ ...value, session: { ...value.session, status: 'completed' } })
  show(services)
  expect(await screen.findByRole('button', { name: 'View Client' })).toBeDisabled()
  expect(services.readSessionClient).toHaveBeenCalledTimes(1)
  view.unmount()
})
it('ignores a late response for the previous session after navigation', async () => {
  let complete
  const first = new Promise(resolve => { complete = resolve })
  const next = sessionDetail(sessionDetailData(), directoryId(30), staff); next.session = { ...next.session, id: directoryId(31), clientSummary: 'Next session summary' }
  const services = { readSessionDetails: vi.fn().mockReturnValueOnce(first).mockResolvedValue(next) }
  const view = show(services); view.update(directoryId(31))
  expect(await screen.findByText('Next session summary')).toBeVisible()
  await act(async () => complete(sessionDetail(sessionDetailData(), directoryId(30), staff)))
  expect(screen.getByText('Next session summary')).toBeVisible()
  expect(screen.queryByText('Stored client summary')).toBeNull()
})

it('keeps the reviewed postponement dialog mounted through a background detail refresh', async () => {
  vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date('2026-10-13T06:00:00Z'))
  let complete
  const value = sessionDetail(sessionDetailData(), directoryId(30), staff)
  value.session = { ...value.session, date: '2026-10-20', status: 'scheduled' }
  const services = { readSessionDetails: vi.fn().mockResolvedValueOnce(value).mockImplementation(() => new Promise(resolve => { complete = resolve })),
    sessionService: { previewPostponement: vi.fn().mockResolvedValue({ expected: 'original-review', changes: [{ sessionId: value.session.id, before: { date: value.session.date, from: '10:00', to: '11:00' }, next: { scheduleState: 'open' } }] }) } }
  const view = show(services, { capabilities: { sessionPostponementWrites: true } })
  fireEvent.click(await screen.findByRole('button', { name: 'Postpone', exact: true }))
  const dialog = await screen.findByRole('dialog', { name: 'Postpone this session?', exact: true })
  view.refresh()
  expect(dialog).toBeInTheDocument()
  await act(async () => complete(value))
  expect(screen.getByRole('dialog', { name: 'Postpone this session?', exact: true })).toBe(dialog)
  expect(services.sessionService.previewPostponement).toHaveBeenCalledTimes(1)
})


it.each(['time', 'trainer'])('keeps the reviewed %s intent frozen after an uncertain response', async kind => {
  vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date('2026-10-13T06:00:00Z'))
  const value = sessionDetail(sessionDetailData(), directoryId(30), staff)
  value.session = { ...value.session, date: '2026-10-20', status: 'scheduled' }
  const replacement = { id: directoryId(99), name: 'Replacement', version: 1 }
  const reviewed = { trainers: [replacement] }
  const save = vi.fn().mockRejectedValueOnce(new Error('Lost committed response')).mockResolvedValue({ outcome: 'applied' })
  const services = { readSessionDetails: vi.fn().mockResolvedValue(value), reviewSessionChange: vi.fn().mockResolvedValue({ reviewed, draft: kind === 'time' ? { date: value.session.date, from: '12:00', to: '13:00' } : { replacementTrainerId: replacement.id }, uncertain: false }),
    sessionService: { requestTimeChange: save, requestTrainerChange: save } }
  show(services, { user: { ...staff, role: 'trainer', trainerId: value.session.trainerId }, capabilities: { sessionChangeWrites: true } })
  fireEvent.click(await screen.findByRole('button', { name: kind === 'time' ? 'Request Time Change' : 'Request Trainer Change', exact: true }))
  let dialog = await screen.findByRole('dialog', { name: kind === 'time' ? 'Request Time Change' : 'Request Trainer Change', exact: true })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Review Request', exact: true }))
  const confirmation = await screen.findByRole('dialog', { name: kind === 'time' ? 'Submit time-change request?' : 'Submit trainer-change request?', exact: true })
  fireEvent.click(within(confirmation).getByRole('button', { name: 'Submit Request', exact: true }))
  dialog = await screen.findByRole('dialog', { name: kind === 'time' ? 'Request Time Change' : 'Request Trainer Change', exact: true })
  expect(within(dialog).getByRole('alert')).toHaveTextContent('Lost committed response')
  expect(within(dialog).getByLabelText(kind === 'time' ? 'Requested start time' : 'Requested replacement trainer')).toBeDisabled()
  // Receipt recovery must remain possible even after the originally reviewed start passes.
  vi.setSystemTime(new Date('2026-10-21T06:00:00Z'))
  fireEvent.click(within(dialog).getByRole('button', { name: 'Check original change', exact: true }))
  await screen.findByText('Session change saved.')
  expect(save).toHaveBeenCalledTimes(2)
  expect(save.mock.calls[0]).toEqual(save.mock.calls[1])
  expect(services.reviewSessionChange).toHaveBeenCalledTimes(1)
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(screen.getByRole('button', { name: 'Export Summary', exact: true })).toBeDisabled()
})

it.each(['completed', 'cancelled'])('Trainer request capability never unlocks a %s session', async status => {
  const value = sessionDetail(sessionDetailData(), directoryId(30), staff)
  value.session = { ...value.session, status }
  const services = { readSessionDetails: vi.fn().mockResolvedValue(value) }
  show(services, { user: { ...staff, role: 'trainer', trainerId: value.session.trainerId }, capabilities: { sessionChangeWrites: true } })
  expect(await screen.findByRole('button', { name: 'Request Trainer Change', exact: true })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Request Time Change', exact: true })).toBeDisabled()
})

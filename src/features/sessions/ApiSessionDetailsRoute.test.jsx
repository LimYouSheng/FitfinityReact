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
  const node = selectedSession => <PortalData.Provider value={{ snapshot, services, today: '2026-10-13' }}><ActionConfirmationProvider><EditGuardProvider><ApiSessionDetailsRoute selectedSession={selectedSession} navigate={vi.fn()} openClient={vi.fn()} /></EditGuardProvider></ActionConfirmationProvider></PortalData.Provider>
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

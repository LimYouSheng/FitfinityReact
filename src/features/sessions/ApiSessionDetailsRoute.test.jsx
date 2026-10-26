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
function show(services, patch = {}, onChangeSaved) {
  const snapshot = { user: staff, policy: { timeZone: 'Asia/Singapore' }, sessionGeneration: 0, serverAt: '2026-10-13T06:00:00Z', data: { clients: [], trainers: [], messages: [] }, ...patch }
  const node = selectedSession => <PortalData.Provider value={{ snapshot, services, refresh: services.refresh ?? (async () => snapshot), today: '2026-10-13' }}><ActionConfirmationProvider><EditGuardProvider><ApiSessionDetailsRoute onChangeSaved={onChangeSaved} selectedSession={selectedSession} navigate={vi.fn()} openClient={vi.fn()} /></EditGuardProvider></ActionConfirmationProvider></PortalData.Provider>
  let selected = { id: directoryId(30), version: 1, ...patch.selectedSession }
  const rendered = render(node(selected))
  const select = next => { selected = next; rendered.rerender(node(selected)) }
  return { ...rendered, select, update: id => select({ id, version: 1 }), refresh: () => { snapshot.serverAt = '2026-10-13T06:00:01Z'; rendered.rerender(node(selected)) } }
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
  fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel', exact: true }))
  fireEvent.click(screen.getByRole('button', { name: 'Postpone', exact: true }))
  await screen.findByRole('dialog', { name: 'Postpone this session?', exact: true })
  expect(services.readSessionDetails).toHaveBeenCalledTimes(2)
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

it.each(['completed', 'cancelled'])('Trainer request and plan capabilities never unlock a %s session', async status => {
  const value = sessionDetail(sessionDetailData(), directoryId(30), staff)
  value.session = { ...value.session, status }
  const services = { readSessionDetails: vi.fn().mockResolvedValue(value) }
  show(services, { user: { ...staff, role: 'trainer', trainerId: value.session.trainerId }, capabilities: { sessionChangeWrites: true, sessionPlanWrites: true } })
  expect(await screen.findByRole('button', { name: 'Request Trainer Change', exact: true })).toBeDisabled()
  expect(screen.queryByRole('button', { name: 'Edit exercise plan', exact: true })).toBeNull()
  expect(screen.getByRole('button', { name: 'Request Time Change', exact: true })).toBeDisabled()
})

it('plan-only capability freezes an uncertain save and keeps media/outcome/acknowledgement unavailable', async () => {
  const value = sessionDetail(sessionDetailData(), directoryId(30), staff)
  const reviewed = { sessionId: value.session.id, version: value.session.version, expected: 'a'.repeat(64), items: value.session.exercisePlan }
  const save = vi.fn().mockRejectedValueOnce(new Error('Lost plan response')).mockResolvedValue({})
  const services = { readSessionDetails: vi.fn().mockResolvedValue(value), reviewSessionPlan: vi.fn().mockResolvedValue({ reviewed, draft: reviewed.items, uncertain: false }), sessionService: { saveExercisePlan: save } }
  show(services, { capabilities: { sessionPlanWrites: true } })
  fireEvent.click(await screen.findByRole('button', { name: 'Edit exercise plan', exact: true }))
  const weight = await screen.findByLabelText('Exercise 1 weight', { exact: true })
  fireEvent.change(weight, { target: { value: '20 kg' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save', exact: true }))
  const dialog = await screen.findByRole('dialog', { name: 'Save exercise plan?', exact: true })
  expect(dialog).not.toHaveTextContent('Videos can be filmed')
  fireEvent.click(within(dialog).getByRole('button', { name: 'Save Plan', exact: true }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Lost plan response')
  expect(weight).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Add Exercise', exact: true })).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: 'Check original save', exact: true }))
  await vi.waitFor(() => expect(save).toHaveBeenCalledTimes(2))
  expect(save.mock.calls[0]).toEqual(save.mock.calls[1])
  expect(services.reviewSessionPlan).toHaveBeenCalledTimes(1)
  await screen.findByText('Stored instruction')
  expect(screen.queryByRole('button', { name: /Manage video/ })).toBeNull()
  expect(screen.queryByRole('button', { name: 'Client Signature', exact: true })).toBeNull()
  expect(screen.getByRole('button', { name: 'Export Summary', exact: true })).toBeDisabled()
})

it('recovers an uncertain outcome with its original review and an explicit recovery confirmation', async () => {
  const value = sessionDetail(sessionDetailData(), directoryId(30), staff)
  const draft = { trainerComments: 'Measured', exerciseResults: [] }
  const reviewed = { expected: 'original-outcome' }
  const save = vi.fn().mockRejectedValueOnce(new Error('Lost outcome response')).mockResolvedValue({})
  const notice = vi.fn()
  const services = { readSessionDetails: vi.fn().mockResolvedValue(value), reviewSessionOutcome: vi.fn().mockResolvedValue({ reviewed, draft, uncertain: false }), sessionService: { saveOutcome: save } }
  show(services, { capabilities: { sessionOutcomeWrites: true } }, notice)
  await screen.findByText('Stored outcome')
  const panel = document.querySelector('.session-outcome-panel')
  fireEvent.click(within(panel).getByRole('button', { name: 'Edit', exact: true }))
  await screen.findByDisplayValue('Measured')
  fireEvent.click(within(panel).getByRole('button', { name: 'Save', exact: true }))
  const confirmation = await screen.findByRole('dialog', { name: 'Save session outcome?', exact: true })
  fireEvent.click(within(confirmation).getByRole('button', { name: 'Save Outcome', exact: true }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Lost outcome response')
  expect(within(panel).getByLabelText('Trainer comments', { exact: true })).toBeDisabled()
  fireEvent.click(within(panel).getByRole('button', { name: 'Check original outcome', exact: true }))
  await vi.waitFor(() => expect(notice).toHaveBeenCalledWith('Original session outcome confirmed.'))
  expect(save.mock.calls[0]).toEqual(save.mock.calls[1])
  expect(services.reviewSessionOutcome).toHaveBeenCalledTimes(1)
})

it.each(['completed', 'cancelled'])('outcome capability keeps terminal %s cover evidence read-only', async status => {
  const value = sessionDetail(sessionDetailData(), directoryId(30), staff)
  value.session = { ...value.session, status }
  const services = { readSessionDetails: vi.fn().mockResolvedValue(value) }
  show(services, { user: { ...staff, role: 'trainer', trainerId: value.session.trainerId }, capabilities: { sessionOutcomeWrites: true } })
  await screen.findByText('Stored outcome')
  expect(within(document.querySelector('.session-outcome-panel')).queryByRole('button', { name: 'Edit', exact: true })).toBeNull()
})

it('recovers an uncertain summary with its original review and an explicit recovery confirmation', async () => {
  const value = sessionDetail(sessionDetailData(), directoryId(30), staff)
  const draft = 'Reviewed client summary'
  const reviewed = { expected: 'original-summary' }
  const save = vi.fn().mockRejectedValueOnce(new Error('Lost summary response')).mockResolvedValue({})
  const notice = vi.fn()
  const services = { readSessionDetails: vi.fn().mockResolvedValue(value), reviewSessionSummary: vi.fn().mockResolvedValue({ reviewed, draft, uncertain: false }), sessionService: { saveClientSummary: save } }
  show(services, { capabilities: { sessionSummaryWrites: true } }, notice)
  await screen.findByText('Stored outcome')
  const panel = document.querySelector('.client-summary-panel')
  fireEvent.click(within(panel).getByRole('button', { name: 'Edit', exact: true }))
  await screen.findByDisplayValue('Reviewed client summary')
  fireEvent.click(within(panel).getByRole('button', { name: 'Save', exact: true }))
  const confirmation = await screen.findByRole('dialog', { name: 'Save client-facing summary?', exact: true })
  fireEvent.click(within(confirmation).getByRole('button', { name: 'Save Summary', exact: true }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Lost summary response')
  expect(within(panel).getByLabelText('Client-facing summary', { exact: true })).toBeDisabled()
  fireEvent.click(within(panel).getByRole('button', { name: 'Check original summary', exact: true }))
  await vi.waitFor(() => expect(notice).toHaveBeenCalledWith('Original client summary confirmed.'))
  expect(save.mock.calls[0]).toEqual(save.mock.calls[1])
  expect(services.reviewSessionSummary).toHaveBeenCalledTimes(1)
})

it.each(['completed', 'cancelled'])('summary capability keeps terminal %s cover evidence read-only', async status => {
  const value = sessionDetail(sessionDetailData(), directoryId(30), staff)
  value.session = { ...value.session, status }
  const services = { readSessionDetails: vi.fn().mockResolvedValue(value) }
  show(services, { user: { ...staff, role: 'trainer', trainerId: value.session.trainerId }, capabilities: { sessionSummaryWrites: true } })
  await screen.findByText('Stored outcome')
  expect(within(document.querySelector('.client-summary-panel')).queryByRole('button', { name: 'Edit', exact: true })).toBeNull()
})

it('acknowledgement recovery freezes the reviewed intent and never asks to confirm completion again', async () => {
  const value = sessionDetail(sessionDetailData(), directoryId(30), staff)
  value.session.date = '2026-01-01'
  const reviewed = { sessionId: value.session.id, version: value.session.version, expected: 'a'.repeat(64) }
  const save = vi.fn().mockRejectedValueOnce(new Error('Lost completion response')).mockResolvedValue({})
  const notice = vi.fn()
  const services = { readSessionDetails: vi.fn().mockResolvedValue(value), reviewSessionAcknowledgement: vi.fn().mockResolvedValue({ reviewed }), sessionService: { acknowledge: save } }
  show(services, { capabilities: { sessionAcknowledgementWrites: true } }, notice)
  fireEvent.click(await screen.findByRole('button', { name: 'Client Signature', exact: true }))
  fireEvent.click(await screen.findByRole('button', { name: 'Record late / no-show instead' }))
  fireEvent.change(screen.getByLabelText('Acknowledgement note'), { target: { value: 'Absent' } })
  fireEvent.click(screen.getByRole('button', { name: 'Review Completion', exact: true }))
  const confirmation = await screen.findByRole('dialog', { name: 'Complete this session?' })
  expect(services.readSessionDetails).toHaveBeenCalledTimes(1)
  fireEvent.click(within(confirmation).getByRole('button', { name: 'Complete Session', exact: true }))
  expect(await within(await screen.findByRole('dialog', { name: 'Trainer late / no-show' })).findByRole('alert')).toHaveTextContent('Lost completion response')
  expect(screen.getByLabelText('Acknowledgement note')).toBeDisabled()
  expect(within(screen.getByRole('dialog', { name: 'Trainer late / no-show' })).getByRole('button', { name: 'Cancel', exact: true })).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: 'Check original acknowledgement', exact: true }))
  await vi.waitFor(() => expect(notice).toHaveBeenCalledWith('Original session acknowledgement confirmed.'))
  expect(save.mock.calls[0]).toEqual(save.mock.calls[1])
  expect(services.reviewSessionAcknowledgement).toHaveBeenCalledTimes(1)
})

it.each(['completed', 'cancelled'])('acknowledgement capability cannot mutate terminal %s cover evidence', async status => {
  const value = sessionDetail(sessionDetailData(), directoryId(30), staff)
  value.session = { ...value.session, status }
  show({ readSessionDetails: vi.fn().mockResolvedValue(value) }, { user: { ...staff, role: 'trainer', trainerId: value.session.trainerId }, capabilities: { sessionAcknowledgementWrites: true } })
  await screen.findByText('Stored outcome')
  expect(screen.queryByRole('button', { name: /Client Signature/ })).toBeNull()
})


it('enables persisted summary PDF export without enabling unrelated mutations', async () => {
  const value = sessionDetail(sessionDetailData(), directoryId(30), staff)
  value.session = { ...value.session, date: '2026-10-12' }
  const services = { readSessionDetails: vi.fn().mockResolvedValue(value) }
  show(services, { capabilities: { sessionSummaryWrites: true } })
  expect(await screen.findByRole('button', { name: 'Export Summary', exact: true })).toBeEnabled()
  expect(screen.getByRole('button', { name: 'Postpone', exact: true })).toBeDisabled()
  expect(screen.queryByRole('button', { name: /WhatsApp/ })).toBeNull()
  expect(screen.queryByRole('button', { name: 'Client Signature', exact: true })).toBeNull()
  cleanup()
  services.readSessionDetails.mockResolvedValue({ ...value, client: { ...value.client, status: 'inactive' } })
  show(services, { capabilities: { sessionSummaryWrites: true } })
  expect(await screen.findByRole('button', { name: 'Export Summary', exact: true })).toBeDisabled()
  cleanup()
  services.readSessionDetails.mockResolvedValue({ ...value, session: { ...value.session, date: '2026-10-20' } })
  show(services, { capabilities: { sessionSummaryWrites: true } })
  expect(await screen.findByRole('button', { name: 'Export Summary', exact: true })).toBeDisabled()
})

it('offers historical Trainer recording playback without replacement or removal controls', async () => {
  const value = sessionDetail(sessionDetailData(), directoryId(30), staff)
  const trainer = { ...staff, role: 'trainer', trainerId: directoryId(999) }
  value.session = { ...value.session, status: 'completed', readableByTrainerId: trainer.trainerId }
  value.session.exercisePlan[0].videoAttached = true
  const item = value.session.exercisePlan[0]
  const services = {
    readSessionDetails: vi.fn().mockResolvedValue(value),
    reviewSessionMedia: vi.fn().mockResolvedValue({ reviewed: { media: { id: directoryId(998), expiresAt: '2026-10-20T00:00:00Z' } } }),
    sessionService: { loadVideo: vi.fn().mockResolvedValue(null), saveVideo: vi.fn(), removeVideo: vi.fn() },
  }
  show(services, { user: trainer, capabilities: { sessionMediaWorkflows: true } })
  fireEvent.click(await screen.findByRole('button', { name: `View video for ${item.name}`, exact: true }))
  const dialog = await screen.findByRole('dialog', { name: `Video · ${item.name}`, exact: true })
  expect(within(dialog).queryByText('Remove saved video')).toBeNull()
  expect(within(dialog).queryByRole('button', { name: 'Save Video', exact: true })).toBeNull()
  expect(within(dialog).queryByLabelText(`Attach video for ${item.name}`)).toBeNull()
  expect(services.sessionService.loadVideo).toHaveBeenCalledWith({ sessionId: value.session.id, exerciseId: item.id })
  expect(services.sessionService.saveVideo).not.toHaveBeenCalled()
  expect(services.sessionService.removeVideo).not.toHaveBeenCalled()
})

it('keeps saved session controls guarded until fresh details arrive and retries only reads after a refresh failure', async () => {
  vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date('2026-10-13T06:00:00Z'))
  const value = sessionDetail(sessionDetailData(), directoryId(30), staff)
  value.session = { ...value.session, date: '2026-10-20', status: 'scheduled' }
  let finishRead
  const read = vi.fn().mockResolvedValueOnce(value).mockRejectedValueOnce(new Error('Read failed')).mockImplementation(() => new Promise(resolve => { finishRead = resolve }))
  const save = vi.fn().mockResolvedValue({ outcome: 'applied' })
  const services = { readSessionDetails: read, sessionService: {
    previewPostponement: vi.fn().mockResolvedValue({ reviewed: {}, expected: 'review', changes: [{ sessionId: value.session.id, before: { date: value.session.date, from: '10:00', to: '11:00' }, next: { scheduleState: 'open' } }] }), postpone: save,
  } }
  show(services, { capabilities: { sessionPostponementWrites: true } })
  fireEvent.click(await screen.findByRole('button', { name: 'Postpone', exact: true }))
  fireEvent.click(await screen.findByRole('button', { name: 'Confirm Postponement', exact: true }))
  expect(await screen.findByRole('button', { name: 'Retry refreshing', exact: true })).toBeEnabled()
  expect(screen.getByRole('button', { name: 'Postpone', exact: true })).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: 'Retry refreshing', exact: true }))
  await vi.waitFor(() => expect(read).toHaveBeenCalledTimes(3))
  expect(screen.getByRole('button', { name: 'Postpone', exact: true })).toBeDisabled()
  await act(async () => finishRead({ ...value, session: { ...value.session, scheduleState: 'open', date: null, from: null, to: null, sessionNo: null } }))
  expect(await screen.findByText('Date/time not set')).toBeVisible()
  expect(screen.queryByRole('button', { name: 'Retry refreshing', exact: true })).toBeNull()
  expect(save).toHaveBeenCalledTimes(1)
})

it.each(['plan', 'outcome', 'summary'])('retains an unsaved %s through a transient background read failure and retry', async kind => {
  const value = sessionDetail(sessionDetailData(), directoryId(30), staff)
  const services = { readSessionDetails: vi.fn().mockResolvedValue(value),
    reviewSessionPlan: vi.fn().mockResolvedValue({ reviewed: {}, draft: value.session.exercisePlan }),
    reviewSessionOutcome: vi.fn().mockResolvedValue({ reviewed: {}, draft: { trainerComments: '', exerciseResults: [] } }),
    reviewSessionSummary: vi.fn().mockResolvedValue({ reviewed: {}, draft: 'Original summary' }) }
  const view = show(services, { capabilities: { sessionPlanWrites: true, sessionOutcomeWrites: true, sessionSummaryWrites: true } })
  await screen.findByText('Stored instruction')
  if (kind === 'plan') fireEvent.click(screen.getByRole('button', { name: 'Edit exercise plan', exact: true }))
  else fireEvent.click(within(document.querySelector(kind === 'outcome' ? '.session-outcome-panel' : '.client-summary-panel')).getByRole('button', { name: 'Edit', exact: true }))
  const field = await screen.findByLabelText(kind === 'plan' ? 'Exercise 1 weight' : kind === 'outcome' ? 'Trainer comments' : 'Client-facing summary', { exact: true })
  fireEvent.change(field, { target: { value: 'Unsaved independent draft' } })
  services.readSessionDetails.mockRejectedValueOnce(Object.assign(new Error('Temporary detail outage'), { status: 503 }))
  view.refresh()
  await screen.findByText('Temporary detail outage')
  expect(field).toBeInTheDocument()
  expect(field).toHaveValue('Unsaved independent draft')
  fireEvent.click(screen.getByRole('button', { name: 'Retry session', exact: true }))
  await vi.waitFor(() => expect(screen.queryByText('Temporary detail outage')).toBeNull())
  expect(field).toBeInTheDocument()
  expect(field).toHaveValue('Unsaved independent draft')
})

it.each([401, 403, 404])('retires private session details after a definitive %s background denial', async status => {
  const value = sessionDetail(sessionDetailData(), directoryId(30), staff)
  const services = { readSessionDetails: vi.fn().mockResolvedValue(value) }
  const view = show(services)
  await screen.findByText('Stored instruction')
  services.readSessionDetails.mockRejectedValueOnce(Object.assign(new Error('Access retired'), { status }))
  view.refresh()
  await screen.findByText('Access retired')
  expect(screen.queryByText('Stored instruction')).toBeNull()
  expect(screen.queryByText('Stored client summary')).toBeNull()
})

it.each(['assignment', 'completion'])('retires the active plan editor when a background read changes %s authority', async change => {
  const value = sessionDetail(sessionDetailData(), directoryId(30), staff)
  const services = { readSessionDetails: vi.fn().mockResolvedValue(value), reviewSessionPlan: vi.fn().mockResolvedValue({ reviewed: {}, draft: value.session.exercisePlan }) }
  const view = show(services, { user: { ...staff, role: 'trainer', trainerId: value.session.trainerId }, capabilities: { sessionPlanWrites: true } })
  fireEvent.click(await screen.findByRole('button', { name: 'Edit exercise plan', exact: true }))
  const field = await screen.findByLabelText('Exercise 1 weight', { exact: true })
  fireEvent.change(field, { target: { value: 'Unsaved old authority' } })
  services.readSessionDetails.mockResolvedValue({ ...value, session: { ...value.session, version: 2, ...(change === 'assignment' ? { trainerId: directoryId(99) } : { status: 'completed' }) } })
  view.refresh()
  await vi.waitFor(() => expect(screen.queryByLabelText('Exercise 1 weight', { exact: true })).toBeNull())
  expect(screen.queryByRole('button', { name: 'Edit exercise plan', exact: true })).toBeNull()
})

it('keeps reviewed booking times through an ordinary refresh, then loads the latest after Cancel', async () => {
  const value = sessionDetail(sessionDetailData(), directoryId(30), staff)
  const services = { readSessionDetails: vi.fn().mockResolvedValue(value), reviewSessionBooking: vi.fn().mockResolvedValue({ reviewed: { trainers: [] }, draft: { date: value.session.date, from: '10:00', to: '11:00', trainerId: value.session.trainerId } }) }
  const view = show(services, { capabilities: { sessionBookingWrites: true } })
  await screen.findByText('Stored instruction')
  const panel = document.querySelector('.session-overview-panel')
  fireEvent.click(within(panel).getByRole('button', { name: 'Edit', exact: true }))
  const field = await screen.findByLabelText('Session start time', { exact: true })
  fireEvent.change(field, { target: { value: '14:00' } })
  services.readSessionDetails.mockResolvedValue({ ...value, session: { ...value.session, version: 2, from: '16:00', to: '17:00' } })
  await act(async () => view.refresh())
  expect(field).toHaveValue('14:00')
  fireEvent.click(within(panel).getByRole('button', { name: 'Cancel', exact: true }))
  await vi.waitFor(() => expect(panel).toHaveTextContent('16:00–17:00'))
})

it.each(['assignment', 'completion'])('a calendar %s change hides the old editor even when its detail read fails', async change => {
  const value = sessionDetail(sessionDetailData(), directoryId(30), staff)
  const services = { readSessionDetails: vi.fn().mockResolvedValue(value), reviewSessionPlan: vi.fn().mockResolvedValue({ reviewed: {}, draft: value.session.exercisePlan }) }
  const view = show(services, { capabilities: { sessionPlanWrites: true } })
  fireEvent.click(await screen.findByRole('button', { name: 'Edit exercise plan', exact: true }))
  await screen.findByLabelText('Exercise 1 weight', { exact: true })
  services.readSessionDetails.mockRejectedValue(Object.assign(new Error('Temporary detail outage'), { status: 503 }))
  view.select({ id: value.session.id, version: 2, ...(change === 'assignment' ? { trainerId: directoryId(99) } : { status: 'completed' }) })
  expect(screen.queryByLabelText('Exercise 1 weight', { exact: true })).toBeNull()
  await screen.findByText('Temporary detail outage')
  expect(screen.queryByText('Stored client summary')).toBeNull()
})

it('retires a completed-session summary editor when permanent client assignment is lost', async () => {
  const value = sessionDetail(sessionDetailData(), directoryId(30), staff)
  value.session.status = 'completed'
  const data = { clients: [{ id: value.client.id, trainerId: value.session.trainerId, status: 'active' }], trainers: [], messages: [] }
  const services = { readSessionDetails: vi.fn().mockResolvedValue(value), reviewSessionSummary: vi.fn().mockResolvedValue({ reviewed: {}, draft: 'Private draft' }) }
  const view = show(services, { selectedSession: value.session, data, user: { ...staff, role: 'trainer', trainerId: value.session.trainerId }, capabilities: { sessionSummaryWrites: true } })
  await screen.findByText('Stored client summary')
  fireEvent.click(within(document.querySelector('.client-summary-panel')).getByRole('button', { name: 'Edit', exact: true }))
  await screen.findByDisplayValue('Private draft')
  data.clients = []
  view.refresh()
  expect(screen.queryByDisplayValue('Private draft')).toBeNull()
  await screen.findByText('Stored client summary')
  expect(within(document.querySelector('.client-summary-panel')).queryByRole('button', { name: 'Edit', exact: true })).toBeNull()
})

it('keeps committed-save refresh recovery reachable after the calendar changes scope', async () => {
  vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date('2026-10-13T06:00:00Z'))
  const value = sessionDetail(sessionDetailData(), directoryId(30), staff)
  value.session.date = '2026-10-20'
  const changed = { ...value, session: { ...value.session, version: 2, scheduleState: 'open', date: null, from: null, to: null, sessionNumber: null } }
  let finishRefresh
  const save = vi.fn().mockResolvedValue({ outcome: 'applied' })
  const services = {
    refresh: vi.fn(() => new Promise(resolve => { finishRefresh = resolve })),
    readSessionDetails: vi.fn().mockResolvedValueOnce(value).mockRejectedValueOnce(new Error('Refresh failed')).mockResolvedValue(changed),
    sessionService: { previewPostponement: vi.fn().mockResolvedValue({ reviewed: {}, expected: 'review', changes: [{ sessionId: value.session.id, before: { date: value.session.date, from: '10:00', to: '11:00' }, next: { scheduleState: 'open' } }] }), postpone: save },
  }
  const view = show(services, { selectedSession: value.session, capabilities: { sessionPostponementWrites: true } })
  fireEvent.click(await screen.findByRole('button', { name: 'Postpone', exact: true }))
  fireEvent.click(await screen.findByRole('button', { name: 'Confirm Postponement', exact: true }))
  await vi.waitFor(() => expect(services.refresh).toHaveBeenCalledTimes(1))
  await act(async () => { view.select(changed.session); finishRefresh() })
  services.refresh.mockResolvedValue(undefined)
  fireEvent.click(await screen.findByRole('button', { name: 'Retry refreshing', exact: true }))
  await screen.findByText('Date/time not set')
  expect(screen.queryByText('Saved. Updating details…')).toBeNull()
  expect(save).toHaveBeenCalledTimes(1)
})

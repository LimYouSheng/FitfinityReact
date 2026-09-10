import ReassignTrainerDialog from './ReassignTrainerDialog.jsx'
import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { seed } from '../../data/seed.js'
import { ActionConfirmationProvider } from '../../components/ActionConfirmationProvider.jsx'
import { EditGuardProvider } from '../../components/EditGuardProvider.jsx'
import { progressReportPdf } from './progressReportPdf.jsx'
import PackageProgress from './PackageProgress.jsx'
import { useState } from 'react'
import { PageState } from '../../hooks/usePageState.js'
import RenewPackageDialog from './RenewPackageDialog.jsx'
import ClientProfilePage from './ClientProfilePage.jsx'
import TrainerProfilePage from '../trainers/TrainerProfilePage.jsx'
import { GENDERS } from '../../app/contact.js'

vi.mock('./progressReportPdf.jsx', () => ({ progressReportPdf: vi.fn() }))
beforeEach(() => { Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', { configurable: true, value: vi.fn() }); vi.stubGlobal('matchMedia', () => ({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() })) })
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })
const wrapper = ({ children }) => {
  const [values, setValues] = useState({})
  return <PageState.Provider value={{ values, setValue: (key, next, initial) => setValues(current => ({ ...current,
    [key]: typeof next === 'function' ? next(current[key] ?? initial) : next })) }}>
    <ActionConfirmationProvider><EditGuardProvider>{children}</EditGuardProvider></ActionConfirmationProvider>
  </PageState.Provider>
}
const owner = seed.users.find(item => item.role === 'owner')

it('edits client details with creation controls, validates before saving and retains a failed draft', async () => {
  const onUpdate = vi.fn().mockRejectedValueOnce(new Error('Offline')).mockResolvedValueOnce()
  render(<ClientProfilePage client={seed.clients[0]} user={owner} trainer={seed.trainers[0]} trainers={seed.trainers}
    sessions={seed.sessions} policy={seed.settings} packages={seed.packages} today="2026-09-09" onUpdate={onUpdate} />, { wrapper })
  const general = within(screen.getByRole('heading', { name: 'General Information' }).closest('.panel'))
  fireEvent.click(general.getByRole('button', { name: 'Edit', exact: true }))
  expect(screen.getByRole('combobox', { name: 'Client type' })).toBeDisabled()
  expect(within(screen.getByRole('combobox', { name: 'Client gender' })).getAllByRole('option').map(item => item.value)).toEqual(['', ...GENDERS])
  expect(screen.getByRole('combobox', { name: 'Client phone country code' })).toHaveValue('+65')
  expect(screen.getByLabelText('Client birthday')).toHaveAttribute('type', 'date')
  expect(screen.getByRole('combobox', { name: 'Client emergency contact relationship' })).toBeVisible()
  const preference = screen.getByRole('combobox', { name: 'Gender preference' })
  expect(document.querySelector(`label[for="${preference.id}"]`)).toHaveClass('onboarding-label')
  fireEvent.change(screen.getByLabelText('Client name'), { target: { value: '' } })
  fireEvent.click(general.getByRole('button', { name: 'Save', exact: true }))
  expect(screen.getByLabelText('Client name')).toHaveFocus()
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(onUpdate).not.toHaveBeenCalled()
  fireEvent.change(screen.getByLabelText('Client name'), { target: { value: 'Amanda Lee' } })
  fireEvent.change(screen.getByRole('combobox', { name: 'Client gender' }), { target: { value: 'Prefer not to say' } })
  fireEvent.change(screen.getByLabelText('Client phone number', { exact: true }), { target: { value: '81234567' } })
  fireEvent.click(general.getByRole('button', { name: 'Save', exact: true }))
  fireEvent.click(within(await screen.findByRole('dialog', { name: 'Save client information?' })).getByRole('button', { name: 'Save Changes' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Offline')
  expect(screen.getByLabelText('Client name')).toHaveValue('Amanda Lee')
  fireEvent.click(general.getByRole('button', { name: 'Save', exact: true }))
  fireEvent.click(within(await screen.findByRole('dialog', { name: 'Save client information?' })).getByRole('button', { name: 'Save Changes' }))
  await waitFor(() => expect(screen.queryByLabelText('Client name')).not.toBeInTheDocument())
  expect(onUpdate).toHaveBeenCalledTimes(2)
  expect(onUpdate.mock.calls[1][0]).toMatchObject({ people: [{ name: 'Amanda Lee', gender: 'Prefer not to say', phone: { countryCode: '+65', number: '81234567' } }] })
})

it('uses creation controls and validation for trainer profile details and decimal rates', async () => {
  const onUpdate = vi.fn().mockResolvedValue()
  render(<TrainerProfilePage trainer={seed.trainers[0]} viewer={owner} trainers={seed.trainers} clients={seed.clients}
    sessions={seed.sessions} policy={seed.settings} onUpdate={onUpdate} />, { wrapper })
  const general = within(screen.getByRole('heading', { name: 'General Information' }).closest('.panel'))
  fireEvent.click(general.getByRole('button', { name: 'Edit', exact: true }))
  expect(within(screen.getByRole('combobox', { name: 'Trainer gender' })).getAllByRole('option').map(item => item.value)).toEqual(['', ...GENDERS])
  expect(screen.getByLabelText('Trainer qualifications').tagName).toBe('TEXTAREA')
  expect(screen.getByLabelText('Trainer type')).toHaveAttribute('list', 'trainer-type-options')
  expect(screen.getByLabelText('Trainer birthday')).toHaveAttribute('type', 'date')
  expect(screen.getByLabelText('Trainer phone country code')).toHaveValue('+65')
  fireEvent.change(screen.getByLabelText('Trainer gender'), { target: { value: '' } })
  fireEvent.click(general.getByRole('button', { name: 'Save', exact: true }))
  expect(screen.getByLabelText('Trainer gender')).toHaveFocus()
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('Trainer gender'), { target: { value: 'Male' } })
  fireEvent.change(screen.getByLabelText('Trainer phone country code'), { target: { value: '+60' } })
  fireEvent.change(screen.getByLabelText('Trainer phone number'), { target: { value: '123456789' } })
  fireEvent.click(general.getByRole('button', { name: 'Save', exact: true }))
  fireEvent.click(within(await screen.findByRole('dialog', { name: 'Save trainer information?' })).getByRole('button', { name: 'Save Changes' }))
  await waitFor(() => expect(onUpdate).toHaveBeenCalledWith(expect.objectContaining({ phone: '+60 123456789' })))
  await waitFor(() => expect(general.getByRole('button', { name: 'Edit', exact: true })).toBeEnabled())
  const rates = within(screen.getByRole('heading', { name: 'Training & Rates' }).closest('.panel'))
  fireEvent.click(rates.getByRole('button', { name: 'Edit', exact: true }))
  expect(screen.getByLabelText('Peak rate')).toHaveAttribute('step', '0.01')
  fireEvent.change(screen.getByLabelText('Peak rate'), { target: { value: '' } })
  fireEvent.click(rates.getByRole('button', { name: 'Save', exact: true }))
  expect(screen.getByRole('alert')).toHaveTextContent('non-negative peak rate')
  expect(onUpdate).toHaveBeenCalledTimes(1)
  fireEvent.change(screen.getByLabelText('Peak rate'), { target: { value: '80.25' } })
  fireEvent.click(rates.getByRole('button', { name: 'Save', exact: true }))
  fireEvent.click(within(await screen.findByRole('dialog', { name: 'Save trainer rates?' })).getByRole('button', { name: 'Save Rates' }))
  await waitFor(() => expect(onUpdate).toHaveBeenCalledWith({ rates: { peak: 80.25, offPeak: seed.trainers[0].rates.offPeak } }))
})

it('exports and shares only the selected package through the same PDF renderer while preserving compact charts', async () => {
  vi.mocked(progressReportPdf).mockResolvedValue(new Blob(['%PDF-1.4'], { type: 'application/pdf' }))
  vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:report')
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  const share = vi.fn().mockResolvedValue()
  vi.stubGlobal('navigator', { share, canShare: () => true })
  const source = { ...seed.clients[0], package: { ...seed.clients[0].package, id: 'new', used: 9 },
    packageHistory: [{ id: 'old', total: 12, startDate: '2026-01-01', endDate: '2026-04-01' }],
    strengthProgress: [{ id: 'row', name: 'Row', points: [
      { id: 'a', sessionId: 'a', date: '2026-03-01', load: 15, packageId: 'old' },
      { id: 'b', sessionId: 'b', date: '2026-09-01', load: 25, packageId: 'new' },
      { id: 'c', date: '2025-01-01', load: 5, packageId: null },
    ] }] }
  const sessions = [
    { id: 'a', clientId: source.id, packageId: 'old', date: '2026-03-01', status: 'completed', exerciseResults: [{ id: 'row', name: 'Row', loadKg: 15, reps: 10, sets: 3 }] },
    ...['b', 'missing-2', 'missing-3', 'missing-4', 'no-show'].map(id => ({ id, clientId: source.id, packageId: 'new', status: 'completed', ...(id === 'no-show' ? { acknowledgement: { method: 'late_no_show' } } : {}) })),
    { id: 'planned', clientId: source.id, packageId: 'new', status: 'planned' },
    { id: 'cancelled', clientId: source.id, packageId: 'new', status: 'cancelled' },
  ]
  Object.assign(sessions.find(item => item.id === 'b'), { date: '2026-09-01', exerciseResults: [{ id: 'row', name: 'Row', loadKg: 25, reps: 10, sets: 3 }] })
  source.strengthProgress[0].points[0].load = 999 // A stale aggregate must not change the report.
  const save = vi.fn().mockResolvedValue(), history = vi.fn().mockResolvedValue([])
  function Report() {
    const [packageId, setPackageId] = useState()
    return <><button onClick={() => setPackageId(undefined)}>Packages</button><PackageProgress client={source} sessions={sessions} user={owner} packageId={packageId}
      onOpenPackage={setPackageId} onRecordAction={save} onLoadHistory={history} /></>
  }
  render(<Report />)
  expect(screen.queryByRole('button', { name: 'Export Progress Report' })).not.toBeInTheDocument()
  expect(document.querySelector('[data-package-id="new"]')).toHaveTextContent('5 / 12')
  fireEvent.click(within(screen.getByLabelText('Progress packages')).getAllByRole('button', { name: 'View' })[0])
  expect(screen.getByRole('button', { name: 'Show Row progress chart' })).toHaveTextContent('25 kg')
  expect(screen.getByLabelText('Package progress summary')).toHaveTextContent('Completed: 5 · With exercise records: 1')
  expect(screen.queryByText('Unassigned Historical Records')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Packages' }))
  fireEvent.click(within(screen.getByLabelText('Progress packages')).getAllByRole('button', { name: 'View' })[1])
  expect(screen.getByRole('button', { name: 'Show Row progress chart' })).toHaveTextContent('15 kg')
  expect(screen.getByLabelText('Package progress summary')).toHaveTextContent('Completed: 1 · With exercise records: 1')
  fireEvent.click(screen.getByRole('button', { name: 'Export Progress Report' }))
  await waitFor(() => expect(save).toHaveBeenCalledTimes(1))
  expect(progressReportPdf.mock.calls[0][0].strengthProgress[0].points).toEqual([{ id: 'result-a-row', sessionId: 'a', packageId: 'old', date: '2026-03-01', load: 15, reps: 10, sets: 3 }])
  expect(save.mock.calls[0][0]).toMatchObject({ packageId: 'old', kind: 'pdf_export' })
  fireEvent.click(screen.getByRole('button', { name: 'View Export/WhatsApp History' }))
  await waitFor(() => expect(history).toHaveBeenCalledWith('old'))
  fireEvent.click(screen.getByRole('button', { name: 'Share Progress Report via WhatsApp' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Share PDF' }))
  await waitFor(() => expect(save).toHaveBeenCalledTimes(2))
  expect(share).toHaveBeenCalledTimes(1)
  expect(progressReportPdf.mock.calls[1][0].strengthProgress).toEqual(progressReportPdf.mock.calls[0][0].strengthProgress)
  expect(save.mock.calls[1][0]).toMatchObject({ packageId: 'old', kind: 'pdf_share_opened' })
})

it('paginates current and past packages for both roles, excludes queued purchases and rejects an unavailable detail', () => {
  // Reproduce five History records: three current-purchase workouts and two past.
  const amanda = structuredClone(seed.clients[0])
  const completed = seed.sessions.filter(item => item.clientId === amanda.id && item.status === 'completed')
  const history = [...completed, ...['2026-08-03', '2026-08-10'].map((date, index) => ({ ...completed[0],
    id: `past-amanda-${index}`, packageId: amanda.packageHistory[0].id, date }))]
  amanda.strengthProgress = amanda.strengthProgress.map(exercise => ({ ...exercise, points: exercise.points.slice(-1) }))
  render(<ClientProfilePage client={amanda} user={owner} trainer={seed.trainers[0]} trainers={seed.trainers}
    sessions={history} policy={seed.settings} today="2026-09-09" />, { wrapper })
  fireEvent.click(screen.getByRole('button', { name: 'Session History', exact: true }))
  expect(within(screen.getByLabelText('Session History')).getAllByRole('article')).toHaveLength(5)
  expect(screen.queryByLabelText('Session History summary')).not.toBeInTheDocument()
  cleanup()
  render(<PackageProgress client={amanda} sessions={history} user={owner} packageId={amanda.package.id} />)
  expect(screen.getByLabelText('Package progress summary')).toHaveTextContent('Completed: 3 · With exercise records: 3')
  const rows = document.querySelectorAll('.strength-progress-row')
  expect(rows).toHaveLength(6)
  for (const row of rows) expect(row.children[3]).toHaveTextContent(/^3$/)
  cleanup()

  const source = { ...seed.clients[0], packageHistory: Array.from({ length: 10 }, (_, index) => ({
    id: `past-${index}`, total: 12, used: 12, startDate: `20${10 + index}-01-01`, endDate: `20${10 + index}-04-01`,
  })), additionalPackages: [
    { id: 'queued', name: 'Future purchase', startDate: '2027-01-01', endDate: '2027-04-01' },
    { id: 'stopped', name: 'Stopped purchase', total: 12, status: 'inactive', startDate: '2026-05-01', endDate: '2026-08-01' },
  ] }
  for (const user of [owner, seed.users.find(item => item.role === 'trainer')]) {
    const onOpen = vi.fn()
    const view = render(<PackageProgress client={source} user={user} onOpenPackage={onOpen} />)
    const list = screen.getByLabelText('Progress packages')
    expect(within(list).getAllByRole('article')).toHaveLength(10)
    expect(list).toHaveTextContent('Current')
    expect(list).toHaveTextContent('Past · Inactive')
    expect(screen.queryByText('Future purchase')).not.toBeInTheDocument()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(within(list).getAllByRole('article')).toHaveLength(2)
    fireEvent.click(within(list).getAllByRole('button', { name: 'View' })[1])
    expect(onOpen).toHaveBeenCalledWith('past-0')
    view.rerender(<PackageProgress client={source} user={user} packageId="removed" />)
    expect(screen.getByText('This package is unavailable.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Export Progress Report' })).not.toBeInTheDocument()
    cleanup()
  }
})

it('filters and paginates client history and upcoming sessions independently with inclusive dates', () => {
  const client = seed.clients[0]
  const sessions = ['history', 'upcoming'].flatMap(kind => Array.from({ length: 22 }, (_, index) => ({
    id: `${kind}-${index}`, clientId: client.id, trainerId: client.trainerId, packageId: client.package.id,
    date: `2026-${kind === 'history' ? '08' : '10'}-${String(index + 1).padStart(2, '0')}`, from: '18:00', to: '19:00',
    sessionNumber: index + 1, packageTotal: 24, status: kind === 'history' ? 'completed' : 'planned',
  })))
  render(<ClientProfilePage client={client} user={owner} trainer={seed.trainers[0]} trainers={seed.trainers}
    sessions={sessions} policy={seed.settings} today="2026-09-09" />, { wrapper })
  fireEvent.click(screen.getByRole('button', { name: 'Session History', exact: true }))
  fireEvent.change(screen.getByLabelText('Session History from'), { target: { value: '2026-08-05' } })
  fireEvent.change(screen.getByLabelText('Session History to'), { target: { value: '2026-08-18' } })
  expect(within(screen.getByLabelText('Session History')).getAllByRole('article')).toHaveLength(10)
  expect(screen.getByLabelText('Session History')).toHaveTextContent('18 Aug 2026')
  expect(screen.queryByLabelText('Session History summary')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Next' }))
  expect(within(screen.getByLabelText('Session History')).getAllByRole('article')).toHaveLength(4)
  expect(screen.getByLabelText('Session History')).toHaveTextContent('05 Aug 2026')
  fireEvent.click(screen.getByRole('button', { name: 'Upcoming Sessions', exact: true }))
  expect(screen.getByLabelText('Upcoming Sessions from')).toHaveValue('')
  expect(within(screen.getByLabelText('Upcoming Sessions')).getAllByRole('article')).toHaveLength(10)
  fireEvent.change(screen.getByLabelText('Upcoming Sessions from'), { target: { value: '2026-10-12' } })
  fireEvent.change(screen.getByLabelText('Upcoming Sessions to'), { target: { value: '2026-10-12' } })
  expect(within(screen.getByLabelText('Upcoming Sessions')).getAllByRole('article')).toHaveLength(1)
  fireEvent.click(screen.getByRole('button', { name: 'Session History', exact: true }))
  expect(screen.getByLabelText('Session History from')).toHaveValue('2026-08-05')
  expect(screen.getByLabelText('List pages')).toHaveTextContent('Page 2 of 2')
  fireEvent.change(screen.getByLabelText('Session History from'), { target: { value: '2026-08-18' } })
  expect(within(screen.getByLabelText('Session History')).getAllByRole('article')).toHaveLength(1)
})

it('hides Additional Packages when empty or entirely inactive and shows an active additional purchase', () => {
  const source = seed.clients[0]
  const extra = { ...source.package, id: 'additional', name: 'Extra purchase', status: 'active' }
  for (const additionalPackages of [undefined, [], [{ ...extra, status: 'inactive' }], [extra]]) {
    render(<ClientProfilePage client={{ ...source, additionalPackages }} user={owner} trainer={seed.trainers[0]}
      trainers={seed.trainers} sessions={seed.sessions} policy={seed.settings} packages={seed.packages} today="2026-09-09" />, { wrapper })
    fireEvent.click(screen.getByRole('button', { name: 'Package', exact: true }))
    if (additionalPackages?.some(item => item.status === 'active')) expect(screen.getByRole('heading', { name: 'Additional Packages' })).toBeInTheDocument()
    else expect(screen.queryByRole('heading', { name: 'Additional Packages' })).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Current Package' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Past Packages' })).toBeInTheDocument()
    cleanup()
  }
})

it('prefills steps two to five, retains the saved schedule and submits once after review', async () => {
  const client = seed.clients[0], onSave = vi.fn().mockResolvedValue(), onClose = vi.fn()
  render(<RenewPackageDialog client={client} trainers={seed.trainers} sessions={seed.sessions} packages={seed.packages}
    policy={seed.settings} today="2026-09-09" onSave={onSave} onClose={onClose} />, { wrapper })
  expect(screen.getByLabelText('Start date')).toHaveValue('2026-11-16')
  expect(screen.queryByLabelText('Client name')).not.toBeInTheDocument()
  expect(screen.queryByLabelText('Matched trainer')).not.toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('PT Package'), { target: { value: 'package-24' } })
  fireEvent.click(screen.getByRole('button', { name: 'Continue to Client Availability' }))
  expect(screen.getByLabelText('Client availability blocks')).toHaveTextContent('Monday')
  fireEvent.click(screen.getByRole('button', { name: 'Continue to Trainer Matching' }))
  expect(screen.getByLabelText('Matched trainer')).toHaveValue(client.trainerId)
  expect(screen.getByLabelText('Fixed Weekly Schedule')).toHaveTextContent('18:00–19:00')
  fireEvent.click(screen.getByRole('button', { name: 'Continue to Review & Confirm' }))
  fireEvent.click(screen.getByRole('button', { name: 'Add Package', exact: true }))
  const confirm = await screen.findByRole('dialog', { name: `Add package for ${client.name}?` })
  expect(onSave).not.toHaveBeenCalled()
  expect(confirm).toHaveTextContent('24 sessions')
  fireEvent.click(within(confirm).getByRole('button', { name: 'Add Package', exact: true }))
  await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1))
  expect(onSave.mock.calls[0][0]).toMatchObject({ packageId: 'package-24', packageVersion: 1,
    expectedPackageId: client.package.id, expectedSchedule: client.fixedWeeklySchedule, expectedTrainerId: client.trainerId, trainerId: client.trainerId, fixedWeeklySchedule: client.fixedWeeklySchedule })
  await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1))
})

it('retains the renewal draft after a service rejection and guards cancellation of unsaved changes', async () => {
  const client = seed.clients[0], onClose = vi.fn()
  render(<RenewPackageDialog client={client} trainers={seed.trainers} sessions={seed.sessions} packages={seed.packages}
    policy={seed.settings} today="2026-09-09" onSave={vi.fn().mockRejectedValue(new Error('The renewal conflicts with another session.'))} onClose={onClose} />, { wrapper })
  fireEvent.change(screen.getByLabelText('Start date'), { target: { value: '2026-11-23' } })
  fireEvent.click(screen.getByRole('button', { name: 'Continue to Client Availability' }))
  expect(screen.getByLabelText('Client availability blocks')).toHaveTextContent('Monday')
  fireEvent.click(screen.getByRole('button', { name: 'Continue to Trainer Matching' }))
  expect(screen.getByLabelText('Matched trainer')).toHaveValue(client.trainerId)
  expect(screen.getByLabelText('Fixed Weekly Schedule')).toHaveTextContent('18:00–19:00')
  fireEvent.click(screen.getByRole('button', { name: 'Continue to Review & Confirm' }))
  fireEvent.click(screen.getByRole('button', { name: 'Add Package', exact: true }))
  const confirm = await screen.findByRole('dialog', { name: `Add package for ${client.name}?` })
  fireEvent.click(within(confirm).getByRole('button', { name: 'Add Package', exact: true }))
  await screen.findByText('The renewal conflicts with another session.')
  fireEvent.click(screen.getByRole('button', { name: 'Edit Package & Preferences' }))
  expect(screen.getByLabelText('Start date')).toHaveValue('2026-11-23')
  fireEvent.click(screen.getByRole('button', { name: 'Cancel', exact: true }))
  const leave = await screen.findByRole('dialog', { name: 'Leave this edit?' })
  expect(onClose).not.toHaveBeenCalled()
  fireEvent.click(within(leave).getByRole('button', { name: 'Leave Without Saving' }))
  await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1))
})

it('gives both roles read-only inactive profiles and reserves reactivation for the owner', () => {
  for (const user of [owner, seed.users.find(item => item.role === 'trainer')]) {
    const client = { ...seed.clients[0], status: 'inactive' }
    render(<ClientProfilePage client={client} user={user} trainer={seed.trainers[0]} trainers={seed.trainers}
      sessions={seed.sessions} policy={seed.settings} packages={seed.packages} today="2026-09-09" />, { wrapper })
    expect(screen.queryByRole('button', { name: 'Edit', exact: true })).not.toBeInTheDocument()
    expect(screen.queryAllByRole('button', { name: 'Reactivate Client' })).toHaveLength(user.role === 'owner' ? 1 : 0)
    fireEvent.click(screen.getByRole('button', { name: 'Package', exact: true }))
    expect(screen.queryByRole('button', { name: 'Add Package' })).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Past Packages' })).toBeVisible()
    cleanup()
  }
})

it('lets the owner edit prefilled availability and trainer in the shared package wizard', async () => {
  const client = seed.clients[0], onSave = vi.fn().mockResolvedValue(client)
  render(<RenewPackageDialog client={client} trainers={seed.trainers} sessions={seed.sessions} packages={seed.packages}
    policy={seed.settings} today="2026-09-09" onSave={onSave} onClose={vi.fn()} />, { wrapper })
  fireEvent.click(screen.getByRole('button', { name: 'Continue to Client Availability' }))
  fireEvent.click(screen.getByRole('button', { name: 'Reset Availability' }))
  const trainer = seed.trainers.find(item => item.id !== client.trainerId && item.status === 'active' && item.availability.Monday?.length)
  const [from, to] = trainer.availability.Monday[0]
  fireEvent.click(screen.getByRole('button', { name: 'Monday', exact: true }))
  fireEvent.change(screen.getByLabelText('Availability from'), { target: { value: from } })
  fireEvent.change(screen.getByLabelText('Availability to'), { target: { value: to } })
  fireEvent.click(screen.getByRole('button', { name: 'Add Time' }))
  fireEvent.click(screen.getByRole('button', { name: 'Continue to Trainer Matching' }))
  fireEvent.change(screen.getByLabelText('Matched trainer'), { target: { value: trainer.id } })
  fireEvent.click(screen.getByRole('button', { name: 'Continue to Review & Confirm' }))
  expect(screen.getByLabelText('Form summary')).toHaveTextContent(trainer.name)
  fireEvent.click(screen.getByRole('button', { name: 'Add Package', exact: true }))
  fireEvent.click(within(await screen.findByRole('dialog', { name: `Add package for ${client.name}?` })).getByRole('button', { name: 'Add Package' }))
  await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1))
  expect(onSave.mock.calls[0][0]).toMatchObject({ trainerId: trainer.id, fixedWeeklySchedule: [{ day: 'Monday', from, to }] })
})

it('offers late session cleanup to the owner on an inactive client and shows its timestamped history', async () => {
  const client = { ...seed.clients[0], status: 'inactive', package: { ...seed.clients[0].package, status: 'inactive',
    deactivatedAt: '2026-09-09T04:00:00Z', deactivatedBy: owner,
    sessionDeletionHistory: [{ at: '2026-09-09T05:00:00Z', by: owner, sessionIds: ['removed'] }] } }
  const onDelete = vi.fn().mockResolvedValue(client)
  const sessions = [{ id: 'future', packageId: client.package.id, clientId: client.id, date: '2099-09-09', from: '18:00', to: '19:00', status: 'planned' }]
  for (const user of [owner, seed.users.find(item => item.role === 'trainer')]) {
    render(<ClientProfilePage client={client} user={user} trainer={seed.trainers[0]} trainers={seed.trainers}
      sessions={sessions} policy={seed.settings} packages={seed.packages} today="2026-09-09" onDeletePackageSessions={onDelete} />, { wrapper })
    fireEvent.click(screen.getByRole('button', { name: 'Package', exact: true }))
    expect(screen.getByText(/1 upcoming sessions deleted/)).toHaveTextContent(owner.name)
    if (user.role === 'owner') {
      fireEvent.click(screen.getByRole('button', { name: 'Delete Upcoming Sessions (1)' }))
      const dialog = screen.getByRole('dialog', { name: 'Delete Upcoming Package Sessions?' })
      expect(onDelete).not.toHaveBeenCalled()
      fireEvent.click(within(dialog).getByRole('button', { name: 'Delete Sessions' }))
      await waitFor(() => expect(onDelete).toHaveBeenCalledWith({ packageId: client.package.id }))
    } else expect(screen.queryByRole('button', { name: /Delete Upcoming Sessions/ })).not.toBeInTheDocument()
    cleanup()
  }
})

it('prefills a legacy 24-session purchase and keeps unavailable templates unselected for explicit review', () => {
  const client = seed.clients.find(item => item.package.total === 24)
  const renderPackage = packages => render(<RenewPackageDialog client={client} trainers={seed.trainers} sessions={seed.sessions}
    packages={packages} policy={seed.settings} today="2026-09-09" onSave={vi.fn()} onClose={vi.fn()} />, { wrapper })
  renderPackage(seed.packages)
  expect(screen.getByLabelText('PT Package')).toHaveValue('package-24')
  expect(screen.getByLabelText('Weekly frequency')).toHaveValue(String(client.package.sessionsPerWeek))
  expect(screen.getByLabelText('Trainer preference')).toHaveValue(client.genderPreference)
  cleanup()
  renderPackage(seed.packages.filter(item => item.total !== 24))
  expect(screen.getByLabelText('PT Package')).toHaveValue('')
  fireEvent.click(screen.getByRole('button', { name: 'Continue to Client Availability' }))
  expect(screen.getByRole('alert')).toHaveTextContent('Choose an active PT package.')
})

it('reviews a permanent reassignment before saving the selected trainer and original assignment snapshot once', async () => {
  const client = seed.clients[0], onSave = vi.fn().mockResolvedValue(client), onClose = vi.fn()
  render(<ReassignTrainerDialog client={client} trainers={seed.trainers} sessions={seed.sessions} timeZone={seed.settings.timeZone}
    onSave={onSave} onClose={onClose} />, { wrapper })
  expect(screen.getByRole('button', { name: 'Review Reassignment' })).toBeDisabled()
  expect(screen.getByRole('option', { name: 'Priya Nair — Unavailable' })).toBeDisabled()
  expect(screen.getByText(/Priya Nair:.*Monday, 18:00–19:00/)).toBeVisible()
  fireEvent.change(screen.getByLabelText('New trainer'), { target: { value: 't2' } })
  fireEvent.click(screen.getByRole('button', { name: 'Review Reassignment' }))
  const confirm = await screen.findByRole('dialog', { name: 'Reassign trainer for Amanda Lim?' })
  expect(confirm).toHaveTextContent('current/additional packages')
  expect(onSave).not.toHaveBeenCalled()
  fireEvent.click(within(confirm).getByRole('button', { name: 'Reassign Trainer', exact: true }))
  await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1))
  expect(onSave.mock.calls[0][0]).toMatchObject({ trainerId: 't2', expected: { trainerId: 't1', fixedWeeklySchedule: client.fixedWeeklySchedule } })
  expect(onSave.mock.calls[0][0].requestId).toBeTruthy()
  await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1))
})

it('keeps reassignment selection after cancelled confirmation and a failed save', async () => {
  const onSave = vi.fn().mockRejectedValue(new Error('The selected trainer has a booking conflict.')), onClose = vi.fn()
  render(<ReassignTrainerDialog client={seed.clients[0]} trainers={seed.trainers} sessions={seed.sessions} timeZone={seed.settings.timeZone}
    onSave={onSave} onClose={onClose} />, { wrapper })
  fireEvent.change(screen.getByLabelText('New trainer'), { target: { value: 't2' } })
  fireEvent.click(screen.getByRole('button', { name: 'Review Reassignment' }))
  let confirm = await screen.findByRole('dialog', { name: 'Reassign trainer for Amanda Lim?' })
  fireEvent.click(within(confirm).getByRole('button', { name: 'Cancel', exact: true }))
  await waitFor(() => expect(screen.getByRole('button', { name: 'Review Reassignment' })).toBeEnabled())
  expect(onSave).not.toHaveBeenCalled()
  expect(screen.getByLabelText('New trainer')).toHaveValue('t2')
  fireEvent.click(screen.getByRole('button', { name: 'Review Reassignment' }))
  confirm = await screen.findByRole('dialog', { name: 'Reassign trainer for Amanda Lim?' })
  fireEvent.click(within(confirm).getByRole('button', { name: 'Reassign Trainer', exact: true }))
  expect(await screen.findByRole('alert')).toHaveTextContent('booking conflict')
  expect(screen.getByLabelText('New trainer')).toHaveValue('t2')
  expect(onClose).not.toHaveBeenCalled()
})

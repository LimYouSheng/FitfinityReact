import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import DashboardPage from './DashboardPage.jsx'
import { seed } from '../../data/seed.js'
import { withBusyCalendar } from '../../test/fixtures/calendar.js'

afterEach(cleanup)

it.each(['owner', 'trainer'])('%s calendar shows counts or every weekly session, and day popups preserve all scoped records', role => {
  const data = withBusyCalendar(seed)
  for (const session of data.sessions) session.status = ['not_planned', 'planned', 'completed'][(Number(session.from.slice(0, 2)) - 8) % 3]
  const statusLabels = ['Not Planned', 'Planned', 'Completed', 'Not Planned', 'Planned', 'Completed', 'Not Planned', 'Planned']
  const expectStatuses = (surface, labels) => {
    const badges = [...surface.querySelectorAll('.calendar-event-status')]
    expect(badges.map(badge => badge.textContent)).toEqual(labels)
    for (const [index, badge] of badges.entries()) {
      expect(badge).toHaveClass('status-badge', { 'Not Planned': 'amber', Planned: 'blue', Completed: 'green' }[labels[index]])
      expect(badge.closest('button')).toHaveAccessibleName(new RegExp(`, ${labels[index]}$`))
    }
  }
  const sessions = data.sessions.filter(session => role === 'owner' || session.trainerId === 't1')
  sessions.push({ ...sessions[0], id: 'single-session', date: '2026-09-05', trainerId: 't1' })
  const count = role === 'owner' ? 14 : 8
  const props = {
    user: { role }, sessions, clients: data.clients, trainers: data.trainers, today: '2026-09-03',
    state: { mode: 'week', date: '2026-09-02' }, onState: vi.fn(), onOpenSession: vi.fn(),
    onOpenDay: vi.fn(), onCloseDay: vi.fn(),
  }
  const view = render(<DashboardPage {...props} />)
  const day = date => document.querySelector(`.calendar-day[data-date="${date}"]`)
  for (const mode of ['week', 'month']) {
    props.state = { ...props.state, mode }
    view.rerender(<DashboardPage {...props} />)
    const busy = day('2026-09-02')
    const empty = day('2026-09-04')
    expect(screen.queryByLabelText('Calendar date')).toBeNull()
    expect(within(empty).queryByRole('button')).toBeNull()
    expect(within(empty).queryByText(/View day/)).toBeNull()
    const trainerWeek = role === 'trainer' && mode === 'week'
    if (trainerWeek) {
      expect(busy.querySelectorAll('.calendar-event')).toHaveLength(8)
      expect([...busy.querySelectorAll('.calendar-event strong')].map(item => item.textContent)).toEqual(['08:00–09:00', '09:00–10:00', '10:00–11:00', '11:00–12:00', '12:00–13:00', '13:00–14:00', '14:00–15:00', '15:00–16:00'])
      expectStatuses(busy, statusLabels)
      expect(day('2026-09-03').querySelectorAll('.calendar-event')).toHaveLength(5)
      expect(empty).toHaveTextContent('No sessions')
      fireEvent.click(busy.querySelectorAll('.calendar-event')[7])
      expect(props.onOpenSession).toHaveBeenLastCalledWith('busy-7')
    } else {
      expect(busy.querySelector('.calendar-date strong')).toHaveTextContent(new RegExp(`^${count}$`))
      expect(day('2026-09-03').querySelector('.calendar-date strong')).toHaveTextContent(/^5$/)
      expect(empty.querySelector('.calendar-date strong')).toBeNull()
      expect(document.querySelector('.calendar-grid .calendar-event')).toBeNull()
      expect(busy.querySelector('.calendar-count-label')).toHaveTextContent(/^sessions$/)
      expect(empty.querySelector('.calendar-count-label')).toBeNull()
      expect(empty.querySelector('.calendar-date')).toBeNull()
      expect(day('2026-09-05').querySelector('.calendar-count-label')).toHaveTextContent(/^session$/)
    }
    expect(busy.querySelector('.calendar-more')).toBeNull()
    expect(empty.querySelector('.calendar-event')).toBeNull()
    const date = within(busy).getByRole('button', { name: 'Show sessions for 2026-09-02', exact: true })
    expect(busy).toHaveClass('calendar-past')
    expect(date).not.toHaveAttribute('aria-current')
    expect(date).toBeEnabled()
    expect(day('2026-09-03')).not.toHaveClass('calendar-past')
    expect(day('2026-09-03')).toHaveClass('calendar-today')
    expect(within(day('2026-09-03')).getByText('Today', { exact: true })).toBeVisible()
    expect(within(day('2026-09-03')).getByRole('button', { name: 'Show sessions for 2026-09-03', exact: true })).toHaveAttribute('aria-current', 'date')
    expect(empty).not.toHaveClass('calendar-past')
    if (mode === 'week') {
      expect([...document.querySelectorAll('.calendar-day')].map(element => element.dataset.date)).toEqual([
        '2026-09-02', '2026-09-03', '2026-09-04', '2026-09-05', '2026-09-06', '2026-09-07', '2026-09-08',
      ])
    } else {
      expect(within(empty).queryByRole('button')).toBeNull()
      expect(within(empty).queryByText(/View day/)).toBeNull()
      expect(empty.querySelector('time')).toHaveAttribute('datetime', '2026-09-04')
      expect(empty.children).toHaveLength(1)
      expect(document.querySelectorAll('.calendar-day')).toHaveLength(30)
      expect(day('2026-08-31')).toBeNull()
      expect(day('2026-10-01')).toBeNull()
      expect(day('2026-09-01').style.gridColumnStart).toBe('2')
    }
    expect(within(date).getByText(/View day/)).toBeVisible()
    fireEvent.click(date)
    expect(props.onOpenDay).toHaveBeenLastCalledWith('2026-09-02')
    view.rerender(<DashboardPage {...props} selectedDay="2026-09-02" />)
    const dialog = screen.getByRole('dialog', { name: 'Calendar sessions' })
    expect(dialog.querySelectorAll('.calendar-event')).toHaveLength(count)
    expect(dialog.closest('.calendar-past')).toBeNull()
    if (role === 'owner') {
      const groups = dialog.querySelectorAll('.calendar-trainer-group')
      expect(groups).toHaveLength(2)
      expect(groups[0]).toHaveTextContent(data.trainers.find(trainer => trainer.id === 't1').name)
      expect(groups[0].querySelectorAll('.calendar-event')).toHaveLength(8)
      expect(groups[1].querySelectorAll('.calendar-event')).toHaveLength(6)
      expectStatuses(groups[0], statusLabels)
      expectStatuses(groups[1], statusLabels.slice(0, 6))
      expect(groups[0].querySelector('.calendar-event:last-child')).toHaveTextContent('15:00–16:00')
    } else {
      expect(dialog.querySelector('.calendar-trainer-group')).toBeNull()
      expectStatuses(dialog, statusLabels)
      expect(dialog.querySelector('.calendar-event:last-child')).toHaveTextContent('15:00–16:00')
    }
    view.rerender(<DashboardPage {...props} selectedDay="2026-09-04" />)
    expect(screen.getByRole('dialog')).toHaveTextContent('No sessions for this day.')
    view.rerender(<DashboardPage {...props} />)
  }
  props.today = '2026-09-04'
  view.rerender(<DashboardPage {...props} />)
  expect(day('2026-09-03')).toHaveClass('calendar-past')
  expect(within(day('2026-09-03')).queryByText('Today', { exact: true })).toBeNull()
  expect(day('2026-09-04')).not.toHaveClass('calendar-past')
  expect(day('2026-09-04')).toHaveClass('calendar-today')
  expect(day('2026-09-04')).toHaveAttribute('aria-current', 'date')
  expect(within(day('2026-09-04')).getByText('Today', { exact: true })).toBeVisible()
  expect(day('2026-09-04').querySelector('.calendar-date strong')).toBeNull()
  expect(within(day('2026-09-04')).queryByRole('button')).toBeNull()
  props.today = '2027-01-01'
  props.state = { mode: 'month', date: '2027-01-01' }
  view.rerender(<DashboardPage {...props} />)
  expect(day('2026-12-31')).toBeNull()
  expect(day('2027-01-01')).not.toHaveClass('calendar-past')
  expect(day('2027-01-02')).not.toHaveClass('calendar-past')
  expect(day('2027-01-01').style.gridColumnStart).toBe('5')
  expect(document.querySelectorAll('.calendar-day')).toHaveLength(31)
  expect(day('2027-02-01')).toBeNull()
  expect(props.onState).not.toHaveBeenCalled()
  expect(screen.getByLabelText('Calendar month').querySelectorAll('option')).toHaveLength(12)
  expect(screen.getByRole('button', { name: 'Previous calendar period' })).toBeDisabled()
  fireEvent.change(screen.getByLabelText('Calendar month'), { target: { value: '2027-12-01' } })
  expect(props.onState).toHaveBeenLastCalledWith({ mode: 'month', date: '2027-12-01' })
  props.state = { mode: 'month', date: '2027-12-01' }
  view.rerender(<DashboardPage {...props} />)
  expect(screen.getByRole('button', { name: 'Next calendar period' })).toBeDisabled()
  for (const [date, weeks] of [['2027-02-01', 4], ['2028-02-01', 5], ['2027-09-01', 5]]) {
    props.state = { mode: 'week', date }; props.today = date
    view.rerender(<DashboardPage {...props} />)
    const select = screen.getByLabelText('Calendar week')
    expect(select.querySelectorAll('option:not([hidden])')).toHaveLength(weeks)
    const last = select.options[select.options.length - 1].value
    fireEvent.change(select, { target: { value: last } })
    expect(props.onState).toHaveBeenLastCalledWith({ mode: 'week', date: last })
  }
  expect(screen.queryByLabelText('Calendar date')).toBeNull()
})

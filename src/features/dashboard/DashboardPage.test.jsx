import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import DashboardPage from './DashboardPage.jsx'
import { seed } from '../../data/seed.js'
import { withBusyCalendar } from '../../test/fixtures/calendar.js'

afterEach(cleanup)

it.each(['owner', 'trainer'])('%s calendar shows counts or every weekly session, and day popups preserve all scoped records', role => {
  const data = withBusyCalendar(seed)
  const sessions = data.sessions.filter(session => role === 'owner' || session.trainerId === 't1')
  const count = role === 'owner' ? 14 : 8
  const props = {
    user: { role }, sessions, clients: data.clients, trainers: data.trainers, today: '2026-09-02',
    state: { mode: 'week', date: '2026-09-02' }, onState: vi.fn(), onOpenSession: vi.fn(),
    onOpenDay: vi.fn(), onCloseDay: vi.fn(),
  }
  const view = render(<DashboardPage {...props} />)
  const day = date => screen.getByRole('button', { name: `Show sessions for ${date}`, exact: true }).closest('.calendar-day')
  for (const mode of ['week', 'month']) {
    props.state = { ...props.state, mode }
    view.rerender(<DashboardPage {...props} />)
    const busy = day('2026-09-02')
    const empty = day('2026-09-04')
    const trainerWeek = role === 'trainer' && mode === 'week'
    if (trainerWeek) {
      expect(busy.querySelectorAll('.calendar-event')).toHaveLength(8)
      expect([...busy.querySelectorAll('.calendar-event strong')].map(item => item.textContent)).toEqual(['08:00–09:00', '09:00–10:00', '10:00–11:00', '11:00–12:00', '12:00–13:00', '13:00–14:00', '14:00–15:00', '15:00–16:00'])
      expect(day('2026-09-03').querySelectorAll('.calendar-event')).toHaveLength(5)
      expect(empty).toHaveTextContent('No sessions')
      fireEvent.click(busy.querySelectorAll('.calendar-event')[7])
      expect(props.onOpenSession).toHaveBeenLastCalledWith('busy-7')
    } else {
      expect(busy.querySelector('.calendar-date')).toHaveTextContent(new RegExp(`^${count}$`))
      expect(day('2026-09-03').querySelector('.calendar-date')).toHaveTextContent(/^5$/)
      expect(empty.querySelector('.calendar-date')).toHaveTextContent(/^0$/)
      expect(document.querySelector('.calendar-grid .calendar-event')).toBeNull()
    }
    expect(busy.querySelector('.calendar-more')).toBeNull()
    expect(empty.querySelector('.calendar-event')).toBeNull()
    const date = within(busy).getByRole('button', { name: 'Show sessions for 2026-09-02', exact: true })
    expect(date).toHaveAttribute('aria-current', 'date')
    fireEvent.click(date)
    expect(props.onOpenDay).toHaveBeenLastCalledWith('2026-09-02')
    view.rerender(<DashboardPage {...props} selectedDay="2026-09-02" />)
    const dialog = screen.getByRole('dialog', { name: 'Calendar sessions' })
    expect(dialog.querySelectorAll('.calendar-event')).toHaveLength(count)
    if (role === 'owner') {
      const groups = dialog.querySelectorAll('.calendar-trainer-group')
      expect(groups).toHaveLength(2)
      expect(groups[0]).toHaveTextContent(data.trainers.find(trainer => trainer.id === 't1').name)
      expect(groups[0].querySelectorAll('.calendar-event')).toHaveLength(8)
      expect(groups[1].querySelectorAll('.calendar-event')).toHaveLength(6)
      expect(groups[0].querySelector('.calendar-event:last-child')).toHaveTextContent('15:00–16:00')
    } else {
      expect(dialog.querySelector('.calendar-trainer-group')).toBeNull()
      expect(dialog.querySelector('.calendar-event:last-child')).toHaveTextContent('15:00–16:00')
    }
    view.rerender(<DashboardPage {...props} selectedDay="2026-09-04" />)
    expect(screen.getByRole('dialog')).toHaveTextContent('No sessions for this day.')
    view.rerender(<DashboardPage {...props} />)
  }
  expect(props.onState).not.toHaveBeenCalled()
  expect(screen.getByLabelText('Calendar date')).toHaveValue('2026-09-02')
})

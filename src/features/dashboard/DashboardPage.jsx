import Panel from '../../components/Panel.jsx'

const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

export default function DashboardPage({ user }) {
  return (
    <>
      <div className="page-head">
        <div>
          <span className="eyebrow">Operations</span>
          <h1>{user.role === 'owner' ? 'Owner Dashboard' : 'Trainer Dashboard'}</h1>
        </div>
      </div>

      <Panel>
        <div className="section-head">
          <h2>Calendar</h2>
          <div className="calendar-mode-scaffold">
            <button type="button" disabled>Weekly</button>
            <button type="button" disabled>Monthly</button>
          </div>
        </div>

        <div className="calendar-scaffold" aria-label="Calendar scaffold">
          {DAYS.map(day => (
            <div key={day} className="calendar-day-scaffold">
              <strong>{day.slice(0, 3)}</strong>
              <span>—</span>
            </div>
          ))}
        </div>
      </Panel>
    </>
  )
}

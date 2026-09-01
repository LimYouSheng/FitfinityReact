import { OWNER_NAV, TRAINER_NAV } from '../app/constants.js'
import RoleSwitcher from './RoleSwitcher.jsx'

export default function AppShell({ user, users, userId, route, onRoute, onUserChange, onReset, children }) {
  const nav = user.role === 'owner' ? OWNER_NAV : TRAINER_NAV
  return (
    <div className="portal-shell">
      <aside className="sidebar">
        <button className="brand" type="button" onClick={() => onRoute('dashboard')} aria-label="Dashboard">
          <img src="/assets/images/fitfinity-logo.jpg" alt="Fitfinity" />
        </button>
        <div className="identity-copy"><strong>{user.name}</strong><span>{user.role === 'owner' ? 'Owner' : 'Trainer'}</span></div>
        <nav aria-label="Portal navigation">
          {nav.map(([key, label]) => (
            <button key={key} className={route === key ? 'active' : ''} type="button" onClick={() => onRoute(key)}>{label}</button>
          ))}
        </nav>
        <div className="sidebar-footer">
          <button type="button" className="secondary-action" onClick={onReset}>Reset Demo Data</button>
        </div>
      </aside>
      <div className="portal-main">
        <header className="topbar">
          <div><span className="eyebrow">Canonical React migration</span><strong>M1 vertical slice</strong></div>
          <RoleSwitcher users={users} userId={userId} onChange={onUserChange} />
        </header>
        <main className="content">{children}</main>
      </div>
    </div>
  )
}

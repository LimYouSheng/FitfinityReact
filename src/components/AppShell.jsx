import { useEffect, useMemo, useRef, useState } from 'react'
import { OWNER_NAV, TRAINER_NAV } from '../app/constants.js'
import RoleSwitcher from './RoleSwitcher.jsx'

const initials = name => name
  .split(/\s+/)
  .filter(Boolean)
  .slice(0, 2)
  .map(part => part[0])
  .join('')
  .toUpperCase()

export default function AppShell({
  user,
  users,
  userId,
  route,
  canGoBack = false,
  onBack,
  messages,
  onRoute,
  onUserChange,
  onReset,
  children,
}) {
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [profileOpen, setProfileOpen] = useState(false)
  const profileRef = useRef(null)

  const nav = user.role === 'owner' ? OWNER_NAV : TRAINER_NAV

  useEffect(() => {
    setDrawerOpen(false)
    setProfileOpen(false)

    document
      .querySelectorAll('details.profile-menu[open]')
      .forEach(element => element.removeAttribute('open'))
  }, [route, userId])

  useEffect(() => {
    const onPointerDown = event => {
      if (profileRef.current && !profileRef.current.contains(event.target)) {
        setProfileOpen(false)
      }

      document
        .querySelectorAll('details.profile-menu[open]')
        .forEach(element => {
          if (!element.contains(event.target)) {
            element.removeAttribute('open')
          }
        })
    }

    document.addEventListener('pointerdown', onPointerDown, true)
    return () => document.removeEventListener('pointerdown', onPointerDown, true)
  }, [])

  const groups = useMemo(() => {
    const result = []

    for (const item of nav) {
      let group = result.find(entry => entry.name === item.group)

      if (!group) {
        group = { name: item.group, items: [] }
        result.push(group)
      }

      group.items.push(item)
    }

    return result
  }, [nav])

  const visibleMessages = messages.filter(message => {
    if (message.recipientRole === user.role) return true
    if (user.role === 'trainer' && message.recipientTrainerId === user.trainerId) return true
    if (message.recipientUserId === user.id) return true
    return false
  })

  const unread = visibleMessages.filter(message => !message.read).length

  return (
    <div className="portal-shell">
      <button
        type="button"
        className={`drawer-scrim ${drawerOpen ? 'show' : ''}`}
        aria-label="Close navigation"
        onClick={() => setDrawerOpen(false)}
      />

      <aside className={`sidebar ${drawerOpen ? 'mobile-open' : ''}`}>
        <button
          className="brand"
          type="button"
          onClick={() => onRoute('dashboard')}
          aria-label="Fitfinity dashboard"
        >
          <img src="/assets/images/fitfinity-logo.jpg" alt="Fitfinity" />
        </button>

        <div className="role-chip">
          {user.role === 'owner' ? 'OWNER / SITE ADMIN' : 'PERSONAL TRAINER'}
        </div>

        <nav aria-label="Portal navigation">
          {groups.map(group => (
            <div className="nav-group" key={group.name}>
              <div className="nav-group-label">{group.name}</div>

              {group.items.map(item => (
                <button
                  key={item.key}
                  aria-label={item.label}
                  className={`${route === item.key ? 'active' : ''} ${item.disabled ? 'nav-disabled' : ''}`.trim()}
                  type="button"
                  disabled={item.disabled}
                  title={item.disabled ? 'Scaffolded — feature migration pending' : undefined}
                  onClick={() => onRoute(item.key)}
                >
                  <span className="nav-dot" aria-hidden="true" />
                  <span className="nav-text">{item.label}</span>
                  {item.key === 'messages' && unread > 0 && <span className="nav-count">{unread}</span>}
                  {item.disabled && <span className="nav-soon">Soon</span>}
                </button>
              ))}
            </div>
          ))}
        </nav>

        <div className="sidebar-footer">
          <RoleSwitcher users={users} userId={userId} onChange={onUserChange} />
          <button type="button" className="secondary-action" onClick={onReset}>
            Reset Demo Data
          </button>
        </div>
      </aside>

      <div className="portal-main">
        <header className="topbar">
          <div className="topbar-left">
            {canGoBack && (
              <button
                type="button"
                className="topbar-back-button"
                aria-label="Back"
                onClick={onBack}
              >
                <span aria-hidden="true">‹</span>
              </button>
            )}

            <button
              type="button"
              className="menu-toggle"
              aria-label="Open navigation"
              onClick={() => setDrawerOpen(true)}
            >
              ☰
            </button>

            <button
              type="button"
              className="home-button"
              aria-label="Home"
              onClick={() => onRoute('dashboard')}
            >
              <svg
                className="home-icon"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <path
                  d="M4 10.8 12 4l8 6.8v8.7a.5.5 0 0 1-.5.5H15v-6H9v6H4.5a.5.5 0 0 1-.5-.5v-8.7Z"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinejoin="round"
                  strokeLinecap="round"
                />
              </svg>
            </button>

            <div className="topbar-title">
              <strong>Fitfinity Staff</strong>
              <span>{user.role === 'owner' ? 'Owner portal' : 'Trainer portal'}</span>
            </div>
          </div>

          <div className="topbar-user">
            <button
              type="button"
              className="message-button"
              aria-label="Messages"
              onClick={() => onRoute('messages')}
            >
              Messages
              {unread > 0 && <span>{unread}</span>}
            </button>

            <div className="profile-menu-wrap" ref={profileRef}>
              <button
                type="button"
                className="profile-trigger"
                aria-label="Open profile menu"
                aria-expanded={profileOpen}
                onClick={() => setProfileOpen(current => !current)}
              >
                <span className="user-avatar" aria-hidden="true">
                  {initials(user.name)}
                </span>
              </button>

              {profileOpen && (
                <div className="profile-popover" role="menu" aria-label="Profile menu">
                  <div className="profile-popover-head">
                    <strong>{user.name}</strong>
                    <span>
                      {user.role === 'owner' ? 'Owner / Site Admin' : 'Personal Trainer'}
                    </span>
                  </div>

                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => onRoute(user.role === 'owner' ? 'owner-profile' : 'my-profile')}
                  >
                    My Profile
                  </button>

                  <button type="button" role="menuitem" disabled>
                    Change Password
                    <span>Soon</span>
                  </button>

                  <button type="button" role="menuitem" disabled>
                    Sign Out
                    <span>Mock mode</span>
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>

        <main className="content">{children}</main>
      </div>
    </div>
  )
}

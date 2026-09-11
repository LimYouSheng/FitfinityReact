import { useEffect, useMemo, useRef, useState } from 'react'
import { OWNER_NAV, TRAINER_NAV } from '../app/constants.js'
import { useActionConfirmation } from './ActionConfirmationProvider.jsx'
import { useEditGuard } from './EditGuardProvider.jsx'
import RoleSwitcher from './RoleSwitcher.jsx'

const initials = name => (name ?? '')
  .split(/\s+/)
  .filter(Boolean)
  .slice(0, 2)
  .map(part => part[0])
  .join('')
  .toUpperCase()

function closeProfileDropdowns(outsideTarget = null) {
  document
    .querySelectorAll('details.profile-menu[open]')
    .forEach(element => {
      const summary = element.querySelector(':scope > summary')
      const isDropdown = summary && getComputedStyle(summary).display !== 'none'
      if (isDropdown && (!outsideTarget || !element.contains(outsideTarget))) {
        element.removeAttribute('open')
      }
    })
}

export default function AppShell({
  user,
  demoControls = false,
  users,
  userId,
  route,
  routePath = route,
  accountBusy = false,
  canGoBack = false,
  onBack,
  messages,
  onRoute,
  onUserChange,
  onReset,
  onSignOut,
  children,
}) {
  const confirmAction = useActionConfirmation()
  const { activeEdit } = useEditGuard()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [profileOpen, setProfileOpen] = useState(false)
  const [expandedGroup, setExpandedGroup] = useState(null)
  const previousLocation = useRef({ userId, routePath })
  const profileRef = useRef(null)

  const nav = user.role === 'owner' ? OWNER_NAV : TRAINER_NAV

  useEffect(() => {
    const previous = previousLocation.current
    if (previous.userId !== userId) setExpandedGroup(null)
    else if (previous.routePath !== routePath) {
      const group = nav.find(item => item.key === route)?.group
      if (group) setExpandedGroup(group)
    }
    previousLocation.current = { userId, routePath }
  }, [nav, route, routePath, userId])

  useEffect(() => {
    setDrawerOpen(false)
    setProfileOpen(false)

    closeProfileDropdowns()
  }, [route, userId])

  useEffect(() => {
    const onPointerDown = event => {
      if (profileRef.current && !profileRef.current.contains(event.target)) {
        setProfileOpen(false)
      }

      closeProfileDropdowns(event.target)
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
    <div className="portal-shell" data-user-id={userId} aria-busy={accountBusy}>
      {accountBusy && <div className="portal-account-progress" role="status">Switching account…</div>}
      <button
        type="button"
        className={`drawer-scrim ${drawerOpen ? 'show' : ''}`}
        aria-label="Close navigation"
        onClick={() => setDrawerOpen(false)}
      />

      <aside className={`sidebar ${drawerOpen ? 'mobile-open' : ''}`} inert={accountBusy}>
        <button
          className="brand"
          type="button"
          onClick={() => onRoute('dashboard')}
          aria-label="Fitfinity dashboard"
        >
          <img src={`${import.meta.env.BASE_URL}assets/images/fitfinity-logo.jpg`} alt="Fitfinity" />
        </button>

        <div className="role-chip">
          {user.role === 'owner' ? 'OWNER / SITE ADMIN' : 'PERSONAL TRAINER'}
        </div>

        <nav aria-label="Portal navigation">
          {groups.map(group => {
            const collapsed = expandedGroup !== group.name
            const id = `portal-nav-${group.name.toLowerCase().replaceAll(' ', '-')}`
            return <div className="nav-group" key={group.name}>
              <button
                type="button"
                className="nav-group-label nav-group-toggle"
                aria-label={`${group.name} section`}
                aria-expanded={!collapsed}
                aria-controls={id}
                onClick={() => setExpandedGroup(current => current === group.name ? null : group.name)}
              >
                <span>{group.name}</span>
                <svg viewBox="0 0 16 16" aria-hidden="true"><path d="m4 6 4 4 4-4" /></svg>
              </button>

              <div className="nav-group-items" id={id} hidden={collapsed}>
              {group.items.map(item => (
                <button
                  key={item.key}
                  aria-label={item.label}
                  className={`nav-link ${route === item.key ? 'active' : ''} ${item.disabled ? 'nav-disabled' : ''}`.trim()}
                  type="button"
                  disabled={item.disabled}
                  title={item.disabled ? 'Not available yet' : undefined}
                  onClick={() => {
                    setDrawerOpen(false)
                    onRoute(item.key)
                  }}
                >
                  <span className="nav-dot" aria-hidden="true" />
                  <span className="nav-text">{item.label}</span>
                  {item.key === 'messages' && unread > 0 && (
                    <span className="nav-count" aria-label={`${unread} unread messages`}>{unread}</span>
                  )}
                  {item.disabled && <span className="nav-soon">Soon</span>}
                </button>
              ))}
              </div>
            </div>
          })}
        </nav>

        {demoControls && <div className="sidebar-footer">
          <RoleSwitcher users={users} userId={userId} onChange={onUserChange} />
          <button type="button" className="secondary-action" onClick={async () => {
            const confirmed = await confirmAction({
              title: 'Reset all demo data?',
              message: 'This will discard every demo change and restore the original trainers, clients, sessions and messages.',
              confirmLabel: 'Reset Demo Data',
              danger: true,
            })
            if (confirmed) onReset()
          }}>
            Reset Demo Data
          </button>
        </div>}
      </aside>

      <div className="portal-main" inert={accountBusy}>
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

          </div>

          <div className="topbar-user">
            <button
              type="button"
              className="message-button"
              aria-label="Messages"
              onClick={() => onRoute('messages')}
            >
              <svg
                className="message-icon"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <path
                  d="M4.5 6.5h15v11h-15z"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.7"
                  strokeLinejoin="round"
                />
                <path
                  d="m5.2 7.2 6.8 5.4 6.8-5.4"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.7"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              {unread > 0 && <span className="message-count">{unread}</span>}
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

                  <button type="button" role="menuitem" onClick={() => onRoute('change-password')}>
                    Change Password
                  </button>

                  <button type="button" role="menuitem" onClick={onSignOut}>
                    Sign Out
                  </button>
                </div>
              )}
            </div>
          </div>

        </header>

        <main
          className={`content ${activeEdit ? 'edit-active' : ''}`.trim()}
          onClickCapture={event => {
            if (activeEdit && !event.target.closest('.editing-section, .modal-backdrop')) {
              event.preventDefault()
              event.stopPropagation()
            }
          }}
        >
          {children}
        </main>
      </div>
    </div>
  )
}

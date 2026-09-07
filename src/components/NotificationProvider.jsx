import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

const NotificationContext = createContext(null)
const tones = {
  success: { icon: '✓' },
  info: { icon: 'i' },
  warning: { icon: '!' },
  error: { icon: '!' },
}

function NotificationBanner({ notification, onDismiss }) {
  const [hovered, setHovered] = useState(false)
  const [focused, setFocused] = useState(false)
  const { tone, message } = notification
  const presentation = tones[tone]

  useEffect(() => {
    if (hovered || focused || tone === 'error') return undefined
    const timer = setTimeout(onDismiss, 6000)
    return () => clearTimeout(timer)
  }, [focused, hovered, onDismiss, tone])

  return <div className={`notification-banner notification-${tone}`} data-tone={tone}
    onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}
    onFocus={() => setFocused(true)} onBlur={event => {
      if (!event.currentTarget.contains(event.relatedTarget)) setFocused(false)
    }}>
    <span className="notification-icon" aria-hidden="true">{presentation.icon}</span>
    <p role={tone === 'error' ? 'alert' : 'status'} aria-atomic="true">{message}</p>
    <button type="button" aria-label="Dismiss notification" onClick={onDismiss}>×</button>
  </div>
}

export function NotificationProvider({ children }) {
  const [notification, setNotification] = useState(null)
  const sequence = useRef(0)
  const scope = useRef(0)
  const dismiss = useCallback(() => setNotification(null), [])
  const clear = useCallback(() => { scope.current += 1; setNotification(null) }, [])
  const notify = useCallback(({ message, tone = 'success' }) => {
    setNotification({ id: ++sequence.current, message, tone: tones[tone] ? tone : 'info' })
  }, [])

  // Call only after confirmation and validation. A rejected operation never emits success.
  const runAction = useCallback(async (operation, outcome) => {
    const startedIn = scope.current
    let result
    try {
      result = await operation()
    } catch (error) {
      if (scope.current === startedIn) notify({ tone: 'error', message: error?.message || 'Could not complete this action. Try again.' })
      throw error
    }
    if (scope.current === startedIn && outcome) notify(typeof outcome === 'function' ? outcome(result) : outcome)
    return result
  }, [notify])

  useEffect(() => () => { scope.current += 1 }, [])
  const value = useMemo(() => ({ notify, runAction, clear }), [clear, notify, runAction])
  return <NotificationContext.Provider value={value}>
    {children}
    {notification && createPortal(<div className="notification-region">
      <NotificationBanner key={notification.id} notification={notification} onDismiss={dismiss} />
    </div>, document.body)}
  </NotificationContext.Provider>
}

export function useNotifications() {
  const context = useContext(NotificationContext)
  if (!context) throw new Error('useNotifications must be used inside NotificationProvider.')
  return context
}

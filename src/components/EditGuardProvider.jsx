import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { PORTAL_DRAFT_DISCARDED } from '../hooks/usePortalData.js'
import { useActionConfirmation } from './ActionConfirmationProvider.jsx'

const EditGuardContext = createContext(null)

export function EditGuardProvider({ children }) {
  const confirmAction = useActionConfirmation()
  const [activeEdit, setActiveEdit] = useState(null)
  const navigationPending = useRef(null)

  useEffect(() => {
    if (navigationPending.current && navigationPending.current.edit !== activeEdit) navigationPending.current.controller.abort()
  }, [activeEdit])

  useEffect(() => {
    const warnBeforeUnload = event => {
      if (!activeEdit) return
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', warnBeforeUnload)
    return () => window.removeEventListener('beforeunload', warnBeforeUnload)
  }, [activeEdit])

  const guardNavigation = useCallback(async action => {
    if (!activeEdit) {
      await action()
      return true
    }

    if (navigationPending.current) return false
    const pending = { controller: new AbortController(), edit: activeEdit }
    navigationPending.current = pending

    try {
      const confirmed = await confirmAction({
        title: 'Leave this edit?',
        message: `${activeEdit} is currently being edited. Leaving now will discard the unsaved changes.`,
        confirmLabel: 'Leave Without Saving',
        danger: true,
        signal: pending.controller.signal,
      })
      if (!confirmed) return false

      window.dispatchEvent(new Event(PORTAL_DRAFT_DISCARDED))
      setActiveEdit(null)
      await action()
      return true
    } finally {
      if (navigationPending.current === pending) navigationPending.current = null
    }
  }, [activeEdit, confirmAction])

  const value = useMemo(() => ({ activeEdit, setActiveEdit, guardNavigation }), [activeEdit, guardNavigation])

  return <EditGuardContext.Provider value={value}>{children}</EditGuardContext.Provider>
}

export function useEditGuard() {
  const context = useContext(EditGuardContext)
  if (!context) throw new Error('useEditGuard must be used inside EditGuardProvider.')
  return context
}

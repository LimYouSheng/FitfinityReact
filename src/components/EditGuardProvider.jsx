import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { useActionConfirmation } from './ActionConfirmationProvider.jsx'

const EditGuardContext = createContext(null)

export function EditGuardProvider({ children }) {
  const confirmAction = useActionConfirmation()
  const [activeEdit, setActiveEdit] = useState(null)
  const navigationPending = useRef(false)

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
    navigationPending.current = true

    try {
      const confirmed = await confirmAction({
        title: 'Leave this edit?',
        message: `${activeEdit} is currently being edited. Leaving now will discard the unsaved changes.`,
        confirmLabel: 'Leave Without Saving',
        danger: true,
      })
      if (!confirmed) return false

      setActiveEdit(null)
      await action()
      return true
    } finally {
      navigationPending.current = false
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

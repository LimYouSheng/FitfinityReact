import { createContext, useCallback, useContext, useRef, useState } from 'react'
import ConfirmDialog from './ConfirmDialog.jsx'

const ActionConfirmationContext = createContext(null)

export function ActionConfirmationProvider({ children }) {
  const [request, setRequest] = useState(null)
  const resolver = useRef(null)

  const finish = useCallback(confirmed => {
    resolver.current?.(confirmed)
    resolver.current = null
    setRequest(null)
  }, [])

  const confirmAction = useCallback(options => new Promise(resolve => {
    resolver.current?.(false)
    resolver.current = resolve
    setRequest(options)
  }), [])

  return (
    <ActionConfirmationContext.Provider value={confirmAction}>
      {children}
      <ConfirmDialog
        open={Boolean(request)}
        title={request?.title ?? 'Confirm action'}
        confirmLabel={request?.confirmLabel ?? 'Confirm'}
        cancelLabel={request?.cancelLabel ?? 'Cancel'}
        danger={request?.danger}
        onCancel={() => finish(false)}
        onConfirm={() => finish(true)}
      >
        <p>{request?.message}</p>
      </ConfirmDialog>
    </ActionConfirmationContext.Provider>
  )
}

export function useActionConfirmation() {
  const confirmAction = useContext(ActionConfirmationContext)
  if (!confirmAction) throw new Error('useActionConfirmation must be used inside ActionConfirmationProvider.')
  return confirmAction
}

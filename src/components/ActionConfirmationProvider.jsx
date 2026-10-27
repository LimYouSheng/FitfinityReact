import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import ConfirmDialog from './ConfirmDialog.jsx'
import { PORTAL_SESSION_ENDED } from '../hooks/usePortalData.js'

const ActionConfirmationContext = createContext(null)

export function ActionConfirmationProvider({ children }) {
  const [request, setRequest] = useState(null)
  const pending = useRef(null)

  // A retired caller, replaced request or old abort signal cannot decide a newer action.
  const finish = useCallback((confirmed, expected = pending.current) => {
    if (!expected || pending.current !== expected) return
    pending.current = null
    expected.cleanup?.()
    expected.resolve(confirmed)
    setRequest(null)
  }, [])
  const cancel = useCallback(owner => {
    if (pending.current?.owner === owner) finish(false)
  }, [finish])
  const confirm = useCallback((options, owner) => {
    if (options.signal?.aborted) return Promise.resolve(false)
    return new Promise(resolve => {
      finish(false)
      const next = { options, owner, resolve }
      const abort = () => finish(false, next)
      next.cleanup = () => options.signal?.removeEventListener('abort', abort)
      options.signal?.addEventListener('abort', abort, { once: true })
      pending.current = next
      setRequest(next)
    })
  }, [finish])
  useEffect(() => {
    const endSession = () => finish(false)
    window.addEventListener(PORTAL_SESSION_ENDED, endSession)
    return () => {
      window.removeEventListener(PORTAL_SESSION_ENDED, endSession)
      const previous = pending.current
      pending.current = null
      previous?.cleanup?.()
      previous?.resolve(false)
    }
  }, [finish])
  const actions = useMemo(() => ({ confirm, cancel }), [confirm, cancel])
  const options = request?.options

  return (
    <ActionConfirmationContext.Provider value={actions}>
      {children}
      <ConfirmDialog
        open={Boolean(request)}
        title={options?.title ?? 'Confirm action'}
        confirmLabel={options?.confirmLabel ?? 'Confirm'}
        cancelLabel={options?.cancelLabel ?? 'Cancel'}
        danger={options?.danger}
        onCancel={() => finish(false, request)}
        onConfirm={() => finish(true, request)}
      >
        <p>{options?.message}</p>
        {options?.detail}
      </ConfirmDialog>
    </ActionConfirmationContext.Provider>
  )
}

/** Confirmations belong to the screen that requested them, including late callbacks. */
export function useActionConfirmation() {
  const actions = useContext(ActionConfirmationContext)
  if (!actions) throw new Error('useActionConfirmation must be used inside ActionConfirmationProvider.')
  const { confirm, cancel } = actions
  const owner = useRef({}), mounted = useRef(false)
  useEffect(() => {
    const identity = owner.current
    mounted.current = true
    return () => { mounted.current = false; cancel(identity) }
  }, [cancel])
  return useCallback(options => mounted.current ? confirm(options, owner.current) : Promise.resolve(false), [confirm])
}

import { useLayoutEffect, useSyncExternalStore } from 'react'
import { useEditGuard } from '../../components/EditGuardProvider.jsx'

export default function ClientCreationRecovery({ creation }) {
  const { form } = useSyncExternalStore(creation.subscribe, creation.getSnapshot)
  const { setActiveEdit } = useEditGuard()
  const dirty = Boolean(form && !form.created && (form.submitted || form.saving || JSON.stringify(form.draft) !== JSON.stringify(form.initialDraft)))
  useLayoutEffect(() => {
    setActiveEdit(dirty ? 'New client' : null)
    return () => setActiveEdit(null)
  }, [dirty, setActiveEdit])
  return form ? <p role="status">Your client creation progress is retained in this tab. Retry loading to verify your account and resume.</p> : null
}

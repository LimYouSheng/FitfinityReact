import { useLayoutEffect, useSyncExternalStore } from 'react'
import { useEditGuard } from './EditGuardProvider.jsx'

export default function CreationRecovery({ creation, noun = 'client' }) {
  const { form } = useSyncExternalStore(creation.subscribe, creation.getSnapshot)
  const { setActiveEdit } = useEditGuard()
  const dirty = Boolean(form && !form.created && (form.submitted || form.saving || JSON.stringify(form.draft) !== JSON.stringify(form.initialDraft)))
  useLayoutEffect(() => {
    setActiveEdit(dirty ? `New ${noun}` : null)
    return () => setActiveEdit(null)
  }, [dirty, noun, setActiveEdit])
  return form ? <p role="status">Your {noun} creation progress is retained in this tab. Retry loading to verify your account and resume.</p> : null
}

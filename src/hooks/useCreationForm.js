import { useCallback, useState, useSyncExternalStore } from 'react'

const empty = Object.freeze({})
const subscribe = () => () => {}
const snapshot = () => empty

// The same form object survives a temporary directory unmount. Late save responses
// update only the original workflow version; retirement cannot revive a prior login.
export default function useCreationForm(recovery, initial) {
  const [local, setLocal] = useState(initial)
  const stored = useSyncExternalStore(recovery?.subscribe ?? subscribe, recovery?.getSnapshot ?? snapshot)
  const form = recovery ? stored.form ?? local : local
  const update = useCallback((patch, expectedVersion) => {
    if (recovery) {
      const current = recovery.getSnapshot().form ?? local
      return recovery.update({ form: { ...current, ...(typeof patch === 'function' ? patch(current) : patch) } }, expectedVersion)
    }
    setLocal(current => ({ ...current, ...(typeof patch === 'function' ? patch(current) : patch) }))
    return true
  }, [recovery, local])
  const setter = key => value => update(current => ({ [key]: typeof value === 'function' ? value(current[key]) : value }))
  return { form, update, setter }
}

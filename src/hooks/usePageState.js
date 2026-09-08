import { createContext, useCallback, useContext, useRef, useState } from 'react'

export const PageState = createContext(null)
const resolve = value => typeof value === 'function' ? value() : value

// Only navigation state belongs here. Editable drafts remain local and guarded.
export default function usePageState(key, initial) {
  const context = useContext(PageState)
  const initialValue = useRef(initial)
  const [local, setLocal] = useState(() => ({ key, value: resolve(initial) }))
  const value = context
    ? (Object.hasOwn(context.values, key) ? context.values[key] : resolve(initialValue.current))
    : local.key === key ? local.value : resolve(initialValue.current)
  const update = context?.setValue
  const setValue = useCallback(next => {
    if (update) update(key, next, resolve(initialValue.current))
    else setLocal(current => ({ key, value: typeof next === 'function'
      ? next(current.key === key ? current.value : resolve(initialValue.current)) : next }))
  }, [key, update])
  return [value, setValue]
}

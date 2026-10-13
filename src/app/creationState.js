// Private creation state is owned by one verified login, never browser storage.
export function createCreationState(ownerId, empty = () => ({})) {
  let state = empty(), version = 0, retired = false
  const listeners = new Set()
  const publish = () => listeners.forEach(listener => listener())
  return {
    ownerId, getSnapshot: () => state,
    subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener) },
    version: () => version,
    update(patch, expected = version) {
      if (retired || expected !== version) return false
      state = { ...state, ...patch }; publish(); return true
    },
    reset() { version++; state = empty(); publish() },
    retire() { retired = true; version++; state = empty(); publish() },
  }
}

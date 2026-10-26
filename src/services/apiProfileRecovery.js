import { ApiError } from './apiClient.js'

/** Recover simple form commands independently of their cancelled/unmounted editors. */
export function profileRecoveryCommands(entries) {
  return {
    async read(generation, selectedKind) {
      if (selectedKind !== undefined && !Object.hasOwn(entries, selectedKind)) throw new ApiError('INVALID_REQUEST', 'Choose an existing save to recover.')
      const pending = []
      let recovered = false
      for (const [kind, { label, command }] of Object.entries(entries)) {
        if (!command.pendingInput(generation)) continue
        if (selectedKind !== kind) { pending.push({ kind, label }); continue }
        try {
          if (await command.reconcile(generation)) recovered = true
          if (command.pendingInput(generation)) pending.push({ kind, label })
        } catch (error) {
          if (['SESSION_CHANGED', 'SESSION_EXPIRED', 'SESSION_RECHECK'].includes(error.code)) throw error
          pending.push({ kind, label, error: error.message })
        }
      }
      return { pending, recovered }
    },
    async resume(kind, generation) {
      if (!Object.hasOwn(entries, kind)) throw new ApiError('INVALID_REQUEST', 'Choose an existing save to recover.')
      const command = entries[kind].command
      const original = command.pendingInput(generation)
      return original ? command(original, generation) : null
    },
  }
}

import { describe, expect, it } from 'vitest'
import { sessionSummaryWhatsAppText } from './sessionExport.js'

describe('session summary export', () => {
  it('includes selected video captions from the planned exercise details', () => {
    expect(sessionSummaryWhatsAppText(
      { name: 'Amanda Lim' },
      { sessionNumber: 4, packageTotal: 12 },
      'Strong session.',
      [{ name: 'Romanian Deadlift', weight: '40 kg', reps: '8', rounds: '2', rest: '60 sec' }],
    )).toContain('• Romanian Deadlift — 40 kg · 8 reps · 2 rounds · 1 minute rest interval')
    const withoutSummary = sessionSummaryWhatsAppText({ name: 'Amanda' }, { sessionNumber: 4, packageTotal: 12 }, '', [{ name: 'Squat' }])
    expect(withoutSummary).toBe('Amanda — Session Summary\n\nExercise videos (1)\n• Squat\n\nSession 4 / 12')
  })
})

import { describe, expect, it } from 'vitest'
import { progressReportCsv, progressReportFilename, progressReportWhatsAppText } from './progressReport.js'

describe('progress report export', () => {
  it('exports every recorded load with inherited exercise details', () => {
    const client = {
      name: 'Amanda Lim',
      strengthProgress: [{
        name: 'Smith back squat',
        sets: 3,
        reps: 8,
        points: [
          { date: '2026-07-10', load: 20 },
          { date: '2026-07-20', load: 25, reps: 10 },
        ],
      }],
    }

    expect(progressReportFilename(client)).toBe('amanda-lim-progress-report.csv')
    expect(progressReportCsv(client)).toBe([
      '"Client","Exercise","Date","Sets","Reps","Load (kg)"',
      '"Amanda Lim","Smith back squat","2026-07-10","3","8","20"',
      '"Amanda Lim","Smith back squat","2026-07-20","3","10","25"',
    ].join('\n'))
    expect(progressReportWhatsAppText(client)).toContain('10 Jul 2026 · 20 kg · 3 sets · 8 reps')
    expect(progressReportWhatsAppText(client)).toContain('20 Jul 2026 · 25 kg · 3 sets · 10 reps')
  })
})

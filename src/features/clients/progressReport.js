function csvCell(value) {
  return `"${String(value ?? '').replaceAll('"', '""')}"`
}

export function progressReportCsv(client) {
  const rows = [['Client', 'Exercise', 'Date', 'Sets', 'Reps', 'Load (kg)']]

  for (const exercise of client.strengthProgress ?? []) {
    for (const point of exercise.points ?? []) {
      rows.push([
        client.name,
        exercise.name,
        point.date,
        point.sets ?? exercise.sets,
        point.reps ?? exercise.reps,
        point.load,
      ])
    }
  }

  return rows.map(row => row.map(csvCell).join(',')).join('\n')
}

export function progressReportFilename(client) {
  const clientSlug = client.name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)/g, '')

  return `${clientSlug || 'client'}-progress-report.csv`
}

export function progressReportWhatsAppText(client) {
  const lines = [`${client.name} — Progress Report`]

  for (const exercise of client.strengthProgress ?? []) {
    lines.push('', exercise.name)
    for (const point of exercise.points ?? []) {
      lines.push([
        formatDate(point.date),
        `${point.load} kg`,
        `${point.sets ?? exercise.sets ?? '—'} sets`,
        `${point.reps ?? exercise.reps ?? '—'} reps`,
      ].join(' · '))
    }
  }

  return lines.join('\n')
}
import { formatDate } from '../../utils/date.js'

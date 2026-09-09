export const CHART = { left: 58, right: 870, top: 30, bottom: 232 }
export const PROGRESS_FONT = 'Aptos, "Segoe UI", Arial, sans-serif'

export function progressNumber(value) {
  return Number.isInteger(value) ? String(value) : String(value).replace(/\.0$/, '')
}

export function progressSummary(exercise) {
  const first = exercise.points[0]?.load ?? 0
  const latest = exercise.points.at(-1)?.load ?? 0
  return { first, latest, change: latest - first }
}

export function progressChange(value) {
  return `${value >= 0 ? '+' : ''}${progressNumber(value)}`
}

export function chartPoints(exercise) {
  const values = exercise.points.map(point => point.load)
  const maximum = Math.max(...values, 1)
  const minimum = Math.min(...values, 0)
  const padding = Math.max(5, (maximum - minimum) * 0.25)
  const low = Math.max(0, minimum - padding)
  const high = maximum + padding
  const width = CHART.right - CHART.left
  const height = CHART.bottom - CHART.top

  return exercise.points.map((point, index) => ({
    ...point,
    x: CHART.left + (exercise.points.length === 1 ? width / 2 : (index / (exercise.points.length - 1)) * width),
    y: CHART.bottom - ((point.load - low) / (high - low || 1)) * height,
  }))
}

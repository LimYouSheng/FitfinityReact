import { useId } from 'react'
import { formatDate } from '../../utils/date.js'
import { CHART, PROGRESS_FONT, chartPoints, progressNumber } from './progressChart.js'

// The app and PDF render this same SVG, including its geometry and visual styles.
export default function StrengthProgressChart({ exercise, ...placement }) {
  const id = useId().replace(/[^a-zA-Z0-9_-]/g, '')
  const lineId = `strength-line-${id}`, areaId = `strength-area-${id}`
  const points = chartPoints(exercise)
  const line = points.map(point => `${point.x},${point.y}`).join(' ')
  const area = `${CHART.left},${CHART.bottom} ${line} ${CHART.right},${CHART.bottom}`
  const labelVisible = (index, maximum) => {
    const last = points.length - 1
    const stride = Math.max(1, Math.ceil(last / maximum))
    return index === 0 || index === last || (index % stride === 0 && index < last - stride / 2)
  }

  return <svg xmlns="http://www.w3.org/2000/svg" className="strength-chart" viewBox="0 0 900 280"
    fontFamily={PROGRESS_FONT} role="img" aria-label={`${exercise.name} load progress chart`} {...placement}>
    <defs>
      <linearGradient id={lineId} x1="0" x2="1">
        <stop offset="0" stopColor="#ff3e9c" /><stop offset="1" stopColor="#6676ff" />
      </linearGradient>
      <linearGradient id={areaId} x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stopColor="#6676ff" stopOpacity=".25" /><stop offset="1" stopColor="#6676ff" stopOpacity="0" />
      </linearGradient>
    </defs>
    {[0, 1, 2, 3, 4].map(index => {
      const y = CHART.top + ((CHART.bottom - CHART.top) / 4) * index
      return <line key={index} x1={CHART.left} x2={CHART.right} y1={y} y2={y} stroke="#292f39" strokeWidth="1" />
    })}
    <text x="18" y="142" fill="#747d8d" fontSize="9" transform="rotate(-90 18 142)">Load (kg)</text>
    {points.length > 1 && <>
      <polygon points={area} fill={`url(#${areaId})`} />
      <polyline points={line} fill="none" stroke={`url(#${lineId})`} strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
    </>}
    {points.map((point, index) => {
      const latest = index === points.length - 1
      return <g key={point.id}>
        <title>{`${formatDate(point.date)}: ${progressNumber(point.load)} kg`}</title>
        <circle cx={point.x} cy={point.y} r={latest ? 7 : 5} fill={latest ? '#ff3e9c' : '#11141a'}
          stroke={latest ? '#ffe0ef' : '#6676ff'} strokeWidth="3" />
        {labelVisible(index, 20) && <text x={point.x} y={point.y - 13} textAnchor="middle" fill="#c8ced8" fontSize="9" fontWeight="800">{progressNumber(point.load)}</text>}
        {labelVisible(index, 12) && <text x={point.x} y="258" textAnchor="middle" fill="#747d8d" fontSize="9">{formatDate(point.date).replace(/ \d{4}$/, '')}</text>}
      </g>
    })}
  </svg>
}

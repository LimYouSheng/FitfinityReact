import { DAYS } from '../../app/constants.js'
import { formatTime } from './trainerTime.js'

export default function TrainerAvailabilityGrid({ availability }) {
  return (
    <div className="availability-grid">
      {DAYS.map(day => {
        const blocks = availability?.[day] ?? []
        return (
          <div className="availability-day" key={day}>
            <strong>{day.slice(0, 3).toUpperCase()}</strong>
            {blocks.length
              ? blocks.map(([from, to], index) => (
                  <span className="availability-block" key={`${day}-${index}`}>
                    {formatTime(from)}–{formatTime(to)}
                  </span>
                ))
              : <span className="availability-empty">Unavailable</span>}
          </div>
        )
      })}
    </div>
  )
}


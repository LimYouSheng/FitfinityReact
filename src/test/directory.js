import { staff } from './api.js'
export const directoryId = n => `10000000-0000-4000-8000-${String(n).padStart(12, '0')}`
export function directoryData() {
  const trainer = { id: directoryId(1), version: 1, name: 'API Trainer', status: 'active', email: 'trainer@fixture.test', phone_country_code: '+65', phone_number: '91234567', birthday: '1985-01-01', gender: 'Male', trainer_type: 'Strength', qualifications: 'Coach', public_profile: true, peak_rate_cents: 8000, off_peak_rate_cents: 5500, approve_availability: true, approve_session_time: true, approve_session_trainer: true, approve_weekly_schedule: true, availability: [{ id: directoryId(2), weekday: 0, starts_at: '10:00:00', ends_at: '11:00:00' }] }
  const person = { id: directoryId(3), version: 1, position: 1, name: 'API Client', email: 'client@fixture.test', phone_country_code: '+65', phone_number: '91234568', birthday: '1990-01-01', gender: 'Female', emergency_name: 'Contact', emergency_relationship: 'Friend', emergency_country_code: '+65', emergency_number: '91234569' }
  const purchased = { id: directoryId(4), version: 1, template_id: directoryId(5), template_revision: 1, name: 'Purchased Twelve', total_sessions: 12, validity_days: 90, sessions_per_week: 1, free_gym: false, start_date: '2026-09-01', end_date: '2026-11-29', purchased_trainer_id: trainer.id, trainer_id: trainer.id, trainer_name: trainer.name, status: 'active', stage: 'current', used: 3, schedule: [{ id: directoryId(6), weekday: 0, starts_at: '10:00:00', ends_at: '11:00:00' }] }
  return { schemaVersion: 1, viewerId: staff.id, serverAt: '2026-09-22T06:00:00Z', businessDate: '2026-09-22', timeZone: 'Asia/Singapore',
    clients: [{ id: directoryId(7), version: 2, name: person.name, kind: 'individual', status: 'active', trainer_id: trainer.id, gender_preference: 'any', remarks: 'Morning preference', people: [person], purchases: [purchased] }], trainers: [trainer],
    packages: [{ id: directoryId(5), version: 1, revision: 2, name: 'Current Template', total_sessions: 24, validity_days: 180, status: 'active' }] }
}
export const emptyDirectory = () => ({ ...directoryData(), clients: [], trainers: [], packages: [] })

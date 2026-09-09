import { createContext, useContext } from 'react'

export const PortalData = createContext(null)
export const PORTAL_SESSION_ENDED = 'fitfinity:session-ended'

export default function usePortalData() {
  const value = useContext(PortalData)
  if (!value) throw new Error('Portal data provider is required.')
  return value
}

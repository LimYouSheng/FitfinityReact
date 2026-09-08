import { mockPolicy } from './mockPolicy.js'
export const PACKAGE_VALIDITY = mockPolicy.packageValidity
export const WEEKLY_FREQUENCIES = mockPolicy.weeklyFrequencies
export const DEFAULT_PACKAGES = Object.keys(PACKAGE_VALIDITY).map(value => ({
  id: `package-${value}`, name: `${value} sessions`, total: Number(value),
  validityDays: PACKAGE_VALIDITY[value], status: 'active', version: 1,
}))

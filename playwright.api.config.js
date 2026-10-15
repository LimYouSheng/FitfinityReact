import { defineConfig } from '@playwright/test'
import prototype from './playwright.config.js'

// A separate suite: no demo seed, route fulfillment or Node API simulator.
export default defineConfig({
  testDir: './tests-api',
  use: { baseURL: 'http://127.0.0.1:4180', trace: 'retain-on-failure' },
  projects: prototype.projects,
  outputDir: 'test-results-api',
})

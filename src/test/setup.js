import '@testing-library/jest-dom/vitest'
import { beforeEach, vi } from 'vitest'

// jsdom has no media-query engine; layout-specific suites override this boundary.
beforeEach(() => {
  vi.stubGlobal('matchMedia', () => ({ matches: false, addEventListener() {}, removeEventListener() {} }))
})

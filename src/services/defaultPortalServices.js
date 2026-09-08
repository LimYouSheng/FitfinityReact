import { createPortalServices } from './portalService.js'
import { mockPortalAdapter } from './mockPortalAdapter.js'

export const portalServices = createPortalServices(mockPortalAdapter)

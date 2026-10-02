import usePortalData from './usePortalData.js'
import { useNotifications } from '../components/NotificationProvider.jsx'

// A committed write stays successful if only the follow-up refresh fails.
// PortalDataProvider retains the retry banner so callers never repeat the write.
export default function usePortalActions() {
  const { refresh } = usePortalData()
  const { runAction } = useNotifications()
  return { runAction, reload: () => refresh().catch(() => null) }
}

import { useContext } from 'react'
import { PortalData } from './usePortalData.js'
import { browserReportService } from '../services/reportService.js'

export default function useReportService() {
  return useContext(PortalData)?.services.reportService ?? browserReportService
}

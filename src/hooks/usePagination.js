import { useEffect, useMemo, useState } from 'react'
import { paginate } from '../app/pagination.js'

export default function usePagination(items, resetKey = '') {
  const [page, setPage] = useState(1)

  useEffect(() => setPage(1), [resetKey])

  const result = useMemo(() => paginate(items, page), [items, page])

  useEffect(() => {
    if (page !== result.currentPage) setPage(result.currentPage)
  }, [page, result.currentPage])

  return { ...result, setPage }
}

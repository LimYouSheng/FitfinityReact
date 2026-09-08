import { useEffect, useMemo } from 'react'
import { paginate } from '../app/pagination.js'
import usePageState from './usePageState.js'

export default function usePagination(items, resetKey = '', stateKey = 'pagination') {
  const [saved, setSaved] = usePageState(stateKey, () => ({ resetKey, page: 1 }))
  const page = saved.resetKey === resetKey ? saved.page : 1
  const setPage = next => setSaved({ resetKey, page: typeof next === 'function' ? next(page) : next })

  useEffect(() => {
    if (saved.resetKey !== resetKey) setSaved({ resetKey, page: 1 })
  }, [resetKey, saved.resetKey, setSaved])

  const result = useMemo(() => paginate(items, page), [items, page])

  useEffect(() => {
    if (page !== result.currentPage) setPage(result.currentPage)
  }, [page, result.currentPage])

  return { ...result, setPage }
}

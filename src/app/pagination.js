export const LIST_PAGE_SIZE = 10

export function paginate(items, page, pageSize = LIST_PAGE_SIZE) {
  const pageCount = Math.max(1, Math.ceil(items.length / pageSize))
  const currentPage = Math.min(Math.max(1, page), pageCount)
  const start = (currentPage - 1) * pageSize

  return {
    currentPage,
    pageCount,
    items: items.slice(start, start + pageSize),
  }
}

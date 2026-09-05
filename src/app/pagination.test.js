import { describe, expect, it } from 'vitest'
import { LIST_PAGE_SIZE, paginate } from './pagination.js'

describe('list pagination', () => {
  it('shows no more than ten items and clamps page requests', () => {
    const items = Array.from({ length: 23 }, (_, index) => index + 1)
    expect(LIST_PAGE_SIZE).toBe(10)
    expect(paginate(items, 1).items).toEqual(items.slice(0, 10))
    expect(paginate(items, 2).items).toEqual(items.slice(10, 20))
    expect(paginate(items, 99)).toMatchObject({ currentPage: 3, pageCount: 3, items: [21, 22, 23] })
  })
})

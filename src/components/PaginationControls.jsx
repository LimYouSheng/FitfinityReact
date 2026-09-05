export default function PaginationControls({ currentPage, pageCount, onPage }) {
  if (pageCount <= 1) return null

  return (
    <nav className="pagination-controls" aria-label="List pages">
      <button
        type="button"
        className="secondary-button"
        disabled={currentPage === 1}
        onClick={() => onPage(currentPage - 1)}
      >
        Previous
      </button>
      <span>Page {currentPage} of {pageCount}</span>
      <button
        type="button"
        className="secondary-button"
        disabled={currentPage === pageCount}
        onClick={() => onPage(currentPage + 1)}
      >
        Next
      </button>
    </nav>
  )
}

interface Props {
  total: number
  limit: number
  offset: number
  onChange: (offset: number) => void
}

/**
 * Prev / Next pager for a server-paginated list. Renders nothing when
 * everything fits on one page.
 */
export default function Pagination({ total, limit, offset, onChange }: Props) {
  if (total <= limit) return null

  const from = offset + 1
  const to = Math.min(offset + limit, total)
  const page = Math.floor(offset / limit) + 1
  const pageCount = Math.ceil(total / limit)

  return (
    <div
      className="spread"
      style={{ marginTop: 16, alignItems: 'center', flexWrap: 'wrap', gap: 8 }}
    >
      <span className="muted">
        {from}–{to} of {total}
      </span>
      <div className="row" style={{ gap: 8, alignItems: 'center' }}>
        <button
          disabled={offset === 0}
          onClick={() => onChange(Math.max(0, offset - limit))}
        >
          Previous
        </button>
        <span className="muted">
          Page {page} of {pageCount}
        </span>
        <button
          disabled={offset + limit >= total}
          onClick={() => onChange(offset + limit)}
        >
          Next
        </button>
      </div>
    </div>
  )
}

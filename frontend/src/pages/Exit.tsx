import TabBar from '../components/TabBar'

const REVIEWS = [
  { symbol: 'HDFCLIFE', note: 'Target zone hit', urgency: 'High' },
  { symbol: 'DIXON', note: 'Day 20 of 21, no target yet', urgency: 'High' },
  { symbol: 'PERSISTENT', note: 'Trailing stop tightened', urgency: 'Normal' },
]

export default function Exit() {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        minHeight: '100vh',
        background: 'var(--surface-1)',
      }}
    >
      <div style={{ height: '4px', background: 'var(--brand-teal)' }} />

      <div
        style={{
          padding: '16px',
          background: 'var(--surface-2)',
          borderBottom: '0.5px solid var(--border-strong)',
        }}
      >
        <p style={{ fontSize: '18px', fontWeight: 500, margin: 0, color: 'var(--text-primary)' }}>
          Exit review
        </p>
        <p style={{ fontSize: '13px', color: 'var(--text-secondary)', margin: '3px 0 0' }}>
          Sorted by priority · {REVIEWS.length} pending
        </p>
      </div>

      <div style={{ flex: 1 }}>
        {REVIEWS.map((item, i) => (
          <div
            key={item.symbol}
            style={{
              padding: '12px 16px',
              borderBottom: i < REVIEWS.length - 1 ? '0.5px solid var(--border)' : 'none',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}
          >
            <div>
              <p style={{ fontSize: '15px', fontWeight: 500, margin: 0, color: 'var(--text-primary)' }}>
                {item.symbol}
              </p>
              <p style={{ fontSize: '12px', color: 'var(--text-secondary)', margin: '2px 0 0' }}>
                {item.note}
              </p>
            </div>
            <span
              style={{
                background: item.urgency === 'High' ? 'var(--coral-bg)' : 'var(--surface-1)',
                color: item.urgency === 'High' ? 'var(--coral-text)' : 'var(--text-muted)',
                fontSize: '11px',
                padding: '3px 10px',
                borderRadius: '20px',
              }}
            >
              {item.urgency}
            </span>
          </div>
        ))}
      </div>

      <TabBar />
    </div>
  )
}
import TabBar from '../components/TabBar'

const QUEUE = [
  {
    symbol: 'TATASTEEL',
    price: 149.3,
    qty: 335,
    capital: 50035,
    stop: 143.8,
    firedMinsAgo: 8,
    badge: 'PRE cleared',
    fresh: true,
  },
  {
    symbol: 'CUMMINSIND',
    price: 3412,
    qty: 15,
    capital: 51180,
    stop: 3260,
    firedMinsAgo: 22,
    badge: 'PRE cleared',
    fresh: true,
  },
  {
    symbol: 'COFORGE',
    price: 8120,
    qty: 6,
    capital: 48720,
    stop: 7690,
    firedMinsAgo: 1140,
    badge: 'ENG watch',
    fresh: false,
  },
]

function formatINR(n: number) {
  return `₹${n.toLocaleString('en-IN')}`
}

function formatFired(mins: number) {
  if (mins < 60) return `Fired ${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `Fired ${hrs}h ago`
  return 'Fired yesterday'
}

export default function Buy() {
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
          Buy queue
        </p>
        <p style={{ fontSize: '13px', color: 'var(--text-secondary)', margin: '3px 0 0' }}>
          {QUEUE.length} signals · sorted by freshness
        </p>
      </div>

      <div style={{ padding: '16px', flex: 1 }}>
        {QUEUE.map((item) => (
          <div
            key={item.symbol}
            style={{
              borderRadius: '12px',
              padding: '12px',
              marginBottom: '10px',
              border: '0.5px solid var(--border)',
              background: 'var(--surface-2)',
              opacity: item.fresh ? 1 : 0.7,
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
              <span style={{ fontSize: '15px', fontWeight: 500, color: 'var(--text-primary)' }}>
                {item.symbol}
              </span>
              <span
                style={{
                  fontSize: '11px',
                  fontWeight: item.fresh ? 500 : 400,
                  padding: '3px 10px',
                  borderRadius: '20px',
                  background: item.fresh ? 'var(--brand-teal)' : 'var(--surface-1)',
                  color: item.fresh ? '#fff' : 'var(--text-muted)',
                }}
              >
                {item.badge}
              </span>
            </div>

            <p style={{ fontSize: '12px', color: 'var(--text-secondary)', margin: '4px 0 10px' }}>
              {formatFired(item.firedMinsAgo)} · {formatINR(item.price)}
            </p>

            <div
              style={{
                display: 'grid',
                gridTemplateColumns: '1fr 1fr 1fr',
                gap: '8px',
                marginBottom: '10px',
                fontSize: '12px',
              }}
            >
              <div>
                <p style={{ color: 'var(--text-muted)', margin: 0 }}>Qty</p>
                <p style={{ color: 'var(--text-primary)', margin: '2px 0 0', fontWeight: 500 }}>
                  {item.qty}
                </p>
              </div>
              <div>
                <p style={{ color: 'var(--text-muted)', margin: 0 }}>Capital</p>
                <p style={{ color: 'var(--text-primary)', margin: '2px 0 0', fontWeight: 500 }}>
                  {formatINR(item.capital)}
                </p>
              </div>
              <div>
                <p style={{ color: 'var(--text-muted)', margin: 0 }}>Initial stop</p>
                <p style={{ color: 'var(--text-primary)', margin: '2px 0 0', fontWeight: 500 }}>
                  {formatINR(item.stop)}
                </p>
              </div>
            </div>

            <button
              style={{
                width: '100%',
                padding: '10px',
                borderRadius: '8px',
                border: item.fresh ? 'none' : '0.5px solid var(--border-strong)',
                background: item.fresh ? 'var(--brand-teal)' : 'transparent',
                color: item.fresh ? '#fff' : 'var(--text-primary)',
                fontSize: '14px',
                fontWeight: 500,
                cursor: 'pointer',
              }}
            >
              Review and execute ↗
            </button>
          </div>
        ))}
      </div>

      <TabBar />
    </div>
  )
}
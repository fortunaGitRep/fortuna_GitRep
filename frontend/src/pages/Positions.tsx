import TabBar from '../components/TabBar'

const POSITIONS = [
  {
    symbol: 'HDFCLIFE',
    entry: 612.4,
    current: 648.9,
    day: 14,
    maxDay: 21,
    stop: 631.0,
    status: 'Near target',
  },
  {
    symbol: 'COFORGE',
    entry: 7840.0,
    current: 8120.0,
    day: 6,
    maxDay: 21,
    stop: 7690.0,
    status: 'On track',
  },
  {
    symbol: 'DIXON',
    entry: 15200.0,
    current: 14980.0,
    day: 20,
    maxDay: 21,
    stop: 14850.0,
    status: 'Time exit near',
  },
]

function formatINR(n: number) {
  return `₹${n.toLocaleString('en-IN')}`
}

export default function Positions() {
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
          Positions
        </p>
        <p style={{ fontSize: '13px', color: 'var(--text-secondary)', margin: '3px 0 0' }}>
          {POSITIONS.length} open
        </p>
      </div>

      <div style={{ flex: 1 }}>
        {POSITIONS.map((p, i) => {
          const pnl = p.current - p.entry
          const pnlPct = (pnl / p.entry) * 100
          const isUp = pnl >= 0

          return (
            <div
              key={p.symbol}
              style={{
                padding: '12px 16px',
                borderBottom: i < POSITIONS.length - 1 ? '0.5px solid var(--border)' : 'none',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                <span style={{ fontSize: '15px', fontWeight: 500, color: 'var(--text-primary)' }}>
                  {p.symbol}
                </span>
                <span
                  style={{
                    fontSize: '13px',
                    fontWeight: 500,
                    color: isUp ? '#2E7D32' : '#C62828',
                  }}
                >
                  {isUp ? '+' : ''}
                  {pnlPct.toFixed(1)}%
                </span>
              </div>

              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  fontSize: '12px',
                  color: 'var(--text-secondary)',
                  margin: '4px 0 8px',
                }}
              >
                <span>
                  {formatINR(p.entry)} → {formatINR(p.current)}
                </span>
                <span>
                  Day {p.day} of {p.maxDay}
                </span>
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                  Stop {formatINR(p.stop)}
                </span>
                <span
                  style={{
                    fontSize: '11px',
                    padding: '3px 10px',
                    borderRadius: '20px',
                    background: 'var(--surface-1)',
                    color: 'var(--text-secondary)',
                  }}
                >
                  {p.status}
                </span>
              </div>
            </div>
          )
        })}
      </div>

      <TabBar />
    </div>
  )
}
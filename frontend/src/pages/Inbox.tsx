import TabBar from '../components/TabBar'

const ACTIONS = [
  {
    type: 'BUY',
    symbol: 'TATASTEEL',
    meta: '₹149.30',
    note: 'Trigger: breakout node, gate PRE passed',
    cta: 'Review and execute',
    primary: true,
  },
  {
    type: 'EXIT REVIEW',
    symbol: 'HDFCLIFE',
    meta: 'Day 14 of 21',
    note: 'Trigger: tracking node, target zone hit',
    cta: 'Review hold or exit',
    primary: false,
  },
]

export default function Inbox() {
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
          padding: '14px 16px',
          background: 'var(--surface-2)',
          borderBottom: '0.5px solid var(--border-strong)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <div>
          <p style={{ fontSize: '13px', color: 'var(--text-secondary)', margin: 0 }}>
            Swing sleeve
          </p>
          <p style={{ fontSize: '16px', fontWeight: 500, margin: '2px 0 0', color: 'var(--text-primary)' }}>
            ₹4.2L / ₹6L deployed
          </p>
        </div>
        <span
          style={{
            background: 'var(--brand-teal)',
            color: '#fff',
            fontSize: '12px',
            padding: '4px 10px',
            borderRadius: '20px',
          }}
        >
          CAP-P2
        </span>
      </div>

      <div style={{ padding: '16px', flex: 1 }}>
        <p
          style={{
            fontSize: '13px',
            fontWeight: 500,
            color: 'var(--text-secondary)',
            margin: '0 0 10px',
          }}
        >
          Action required · {ACTIONS.length}
        </p>

        {ACTIONS.map((a) => (
          <div
            key={a.symbol}
            style={{
              borderRadius: '12px',
              padding: '12px',
              marginBottom: '10px',
              border: '0.5px solid var(--border)',
              background: 'var(--surface-2)',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
              <span style={{ fontSize: '15px', fontWeight: 500, color: 'var(--text-primary)' }}>
                {a.type} · {a.symbol}
              </span>
              <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{a.meta}</span>
            </div>
            <p style={{ fontSize: '13px', color: 'var(--text-secondary)', margin: '4px 0 10px' }}>
              {a.note}
            </p>
            <button
              style={{
                width: '100%',
                padding: '10px',
                borderRadius: '8px',
                border: a.primary ? 'none' : '0.5px solid var(--border-strong)',
                background: a.primary ? 'var(--brand-teal)' : 'transparent',
                color: a.primary ? '#fff' : 'var(--text-primary)',
                fontSize: '14px',
                fontWeight: 500,
                cursor: 'pointer',
              }}
            >
              {a.cta} ↗
            </button>
          </div>
        ))}
      </div>

      <TabBar />
    </div>
  )
}
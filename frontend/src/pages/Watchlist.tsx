import { IconBook } from '@tabler/icons-react'
import TabBar from '../components/TabBar'

const GATES = ['MAC', 'NAT', 'FLO', 'PRE', 'ENG'] as const

const UNIVERSE = [
  { symbol: 'COFORGE', passed: 5 },
  { symbol: 'KEI', passed: 4 },
  { symbol: 'TRENT', passed: 3 },
  { symbol: 'BLUESTARCO', passed: 2 },
]

export default function Watchlist() {
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
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
        }}
      >
        <div>
          <p style={{ fontSize: '18px', fontWeight: 500, margin: 0, color: 'var(--text-primary)' }}>
            Watchlist
          </p>
          <p style={{ fontSize: '13px', color: 'var(--text-secondary)', margin: '3px 0 0' }}>
            Universe · gate status
          </p>
        </div>
        <button
          onClick={() => alert('Glossary — coming soon')}
          aria-label="Glossary"
          style={{
            width: '32px',
            height: '32px',
            padding: 0,
            borderRadius: '50%',
            border: '0.5px solid var(--border)',
            background: 'var(--surface-1)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer',
            flexShrink: 0,
          }}
        >
          <IconBook size={16} stroke={1.75} color="var(--text-secondary)" />
        </button>
      </div>

      <div style={{ flex: 1 }}>
        {UNIVERSE.map((stock, i) => (
          <div
            key={stock.symbol}
            style={{
              padding: '12px 16px',
              borderBottom: i < UNIVERSE.length - 1 ? '0.5px solid var(--border)' : 'none',
            }}
          >
            <p style={{ fontSize: '15px', fontWeight: 500, margin: '0 0 8px', color: 'var(--text-primary)' }}>
              {stock.symbol}
            </p>
            <div style={{ display: 'flex', gap: '4px' }}>
              {GATES.map((gate, idx) => {
                const cleared = idx < stock.passed
                return (
                  <div key={gate} style={{ flex: 1, textAlign: 'center' }}>
                    <div
                      style={{
                        height: '5px',
                        borderRadius: '3px',
                        background: cleared ? 'var(--brand-teal)' : 'var(--border)',
                      }}
                    />
                    <p
                      style={{
                        fontSize: '10px',
                        margin: '3px 0 0',
                        fontWeight: cleared ? 500 : 400,
                        color: cleared ? 'var(--brand-teal)' : 'var(--text-muted)',
                      }}
                    >
                      {gate}
                    </p>
                  </div>
                )
              })}
            </div>
          </div>
        ))}
      </div>

      <TabBar />
    </div>
  )
}
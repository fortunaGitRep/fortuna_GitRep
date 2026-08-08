import { useState } from 'react'
import { NavLink } from 'react-router-dom'
import {
  IconBell,
  IconArrowUpCircle,
  IconArrowDownCircle,
  IconChartBar,
  IconList,
  IconLogout,
} from '@tabler/icons-react'
import { supabase } from '../supabaseClient'

const TABS = [
  { to: '/inbox', label: 'Inbox', Icon: IconBell },
  { to: '/buy', label: 'Buy', Icon: IconArrowUpCircle },
  { to: '/exit', label: 'Exit', Icon: IconArrowDownCircle },
  { to: '/positions', label: 'Positions', Icon: IconChartBar },
  { to: '/watchlist', label: 'Watchlist', Icon: IconList },
]

export default function TabBar() {
  const [confirmOpen, setConfirmOpen] = useState(false)

  return (
    <>
      <div
        style={{
          display: 'flex',
          borderTop: '0.5px solid var(--border)',
          background: 'var(--surface-2)',
        }}
      >
        {TABS.map(({ to, label, Icon }) => (
          <NavLink
            key={to}
            to={to}
            style={{ flex: 1, textDecoration: 'none' }}
          >
            {({ isActive }) => (
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '2px',
                  margin: isActive ? '6px 4px' : '0',
                  padding: isActive ? '4px 0' : '10px 0',
                  borderRadius: isActive ? '14px' : '0',
                  background: isActive ? 'var(--brand-teal)' : 'transparent',
                  color: isActive ? '#fff' : 'var(--text-secondary)',
                }}
              >
                <Icon size={19} stroke={1.75} />
                <span style={{ fontSize: '10px' }}>{label}</span>
              </div>
            )}
          </NavLink>
        ))}

        <button
          onClick={() => setConfirmOpen(true)}
          aria-label="Log out"
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '0 12px',
            background: 'transparent',
            border: 'none',
            color: 'var(--text-muted)',
            cursor: 'pointer',
          }}
        >
          <IconLogout size={18} stroke={1.75} />
        </button>
      </div>

      {confirmOpen && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.4)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 100,
          }}
          onClick={() => setConfirmOpen(false)}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              background: 'var(--surface-2)',
              borderRadius: '14px',
              padding: '20px',
              width: '260px',
              boxShadow: '0 8px 24px rgba(0,0,0,0.15)',
            }}
          >
            <p style={{ fontSize: '15px', fontWeight: 500, margin: '0 0 6px', color: 'var(--text-primary)' }}>
              Log out of Fortuna?
            </p>
            <p style={{ fontSize: '13px', color: 'var(--text-secondary)', margin: '0 0 16px' }}>
              You'll need to sign in again to see your positions and signals.
            </p>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                onClick={() => setConfirmOpen(false)}
                style={{
                  flex: 1,
                  padding: '10px',
                  borderRadius: '8px',
                  border: '0.5px solid var(--border-strong)',
                  background: 'transparent',
                  color: 'var(--text-primary)',
                  fontSize: '14px',
                  cursor: 'pointer',
                }}
              >
                Cancel
              </button>
              <button
                onClick={() => supabase.auth.signOut()}
                style={{
                  flex: 1,
                  padding: '10px',
                  borderRadius: '8px',
                  border: 'none',
                  background: 'var(--brand-teal)',
                  color: '#fff',
                  fontSize: '14px',
                  fontWeight: 500,
                  cursor: 'pointer',
                }}
              >
                Log out
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
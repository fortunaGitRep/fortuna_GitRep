# Fortuna — Tech Stack

**What this doc is:** A single-page reference of every technology, service, and tool used to build Fortuna — what it is, what layer it belongs to, and its current status. For the *why* behind each choice, see `Fortuna-Learning-Concepts.md`. For session-by-session progress, see `Fortuna-Build-Log.md`. This doc is the quick "what are we even using" snapshot.

**Status key:** 🟢 Live/in use · 🟡 Installed, not yet wired up · ⚪ Planned, not started

---

## Frontend

| Tech | What it is | Status |
|---|---|---|
| React | UI library — component-based JavaScript framework | 🟢 |
| TypeScript | JavaScript with static types, catches errors before runtime | 🟢 |
| Vite | Build tool + dev server for the frontend | 🟢 |
| React Router (`react-router-dom`) | In-app navigation/routing without full page reloads | 🟢 |
| `@supabase/supabase-js` | Client library — talks to Supabase (auth, database) from the browser | 🟢 |
| `@tabler/icons-react` | Icon set, as React components | 🟢 |
| CSS custom properties (`theme.css`) | Hand-defined color palette/design tokens, no CSS framework | 🟢 |
| PWA (manifest + service worker) | Installable home-screen app, push notifications | ⚪ |
| `vite-plugin-pwa` | Vite plugin that generates the manifest/service worker for PWA support | ⚪ |

---

## Backend

| Tech | What it is | Status |
|---|---|---|
| Python 3.11 | Backend language | 🟢 |
| FastAPI | Python web framework — now serves a live authenticated Dhan route (`/dhan/funds`) alongside health check | 🟢 |
| Uvicorn | ASGI server that actually runs the FastAPI app | 🟢 |
| `python-dotenv` | Loads `.env` config into Python — wired up via `load_dotenv()` in `dhan_client.py` | 🟢 |
| VectorBT | Backtesting engine (NumPy/Numba-based) | ⚪ |
| TA-Lib | Technical indicator library (VWAP, ADX, Supertrend, Bollinger Bands, etc.) | ⚪ |
| pandas-ta-classic | Additional technical indicators on top of pandas | ⚪ |
| `dhanhq` (Python SDK) | Official Dhan client — constructs `DhanContext` + `dhanhq` instance, wraps all API calls | 🟢 |
| `pyotp` | Generates the live 6-digit TOTP code for headless token generation | 🟢 |
| `requests` | HTTP client — calls Dhan's `generateAccessToken` endpoint for the TOTP flow | 🟢 |
| Dhan API — Trading/Auth | Broker API — order execution, funds, positions (free tier). Auth via TOTP flow, tested live (`/dhan/funds` returns real account data) | 🟢 |
| Dhan API — Data | Historical OHLCV + live market feed. Requires paid Data API subscription (~₹499/mo), currently **Inactive** on account | ⚪ subscription pending |
| Direction Funnel logic (MAC→NAT→FLO→PRE→ENG gates) | Fortuna's own signal-generation logic | ⚪ |

---

## Database

| Tech | What it is | Status |
|---|---|---|
| Supabase Postgres | Cloud-hosted relational database (Supabase Cloud, no local Docker) | 🟢 |
| Row Level Security (RLS) | Postgres-level per-user data access enforcement | 🟢 (enabled by default on new tables; policies not yet written) |
| Supabase CLI | Pushes schema migrations/edge functions from the terminal to the cloud project | 🟢 |
| Data architecture (storage vs compute split) | What actually gets persisted vs recomputed on demand | ⚪ open decision |

---

## Security / Auth

| Tech | What it is | Status |
|---|---|---|
| Supabase Auth | Manages sessions, tokens, sign-in providers | 🟢 |
| Google OAuth | "Continue with Google" sign-in | 🟢 tested live |
| Magic link (passwordless email) | One-time email login link | 🟢 tested live |
| Google Cloud OAuth client | Credentials backing the Google sign-in flow | 🟢 |
| Email allowlist | Restrict sign-in to your own email only | ⚪ |
| 6-digit PIN login | Server-verified (hashed) credential, cross-device | ⚪ |
| Session expiry tuning | Currently Supabase default (1hr token, silent refresh) | ⚪ decision pending |
| Dhan TOTP token generation | Headless access-token generation via PIN + TOTP secret (`generate_fresh_token()`), tested live. Currently runs at startup only | 🟢 (startup only; scheduled refresh not yet built) |

---

## Infrastructure / DevOps

| Tech | What it is | Status |
|---|---|---|
| VS Code | Code editor | 🟢 |
| Claude Code (VS Code extension) | AI coding assistant with repo context | 🟢 |
| Git | Version control | 🟢 |
| GitHub (`fortunaGitRep/fortuna_GitRep`) | Remote repo host | 🟢 |
| Scoop | Windows package manager (installs git, Node, Supabase CLI) | 🟢 |
| Node.js (LTS) | JavaScript runtime, runs the frontend build tooling | 🟢 |
| npm | Node package manager | 🟢 |
| Render | Hosting for the FastAPI backend (Free tier) | 🟡 backend deployed, unused beyond health check |
| Frontend deployment (Render or similar) | Real URL for the frontend, needed for mobile/PWA use | ⚪ |
| Docker | Deliberately not used — see `Fortuna-Learning-Concepts.md` §4 | ❌ rejected |

---

<!-- Update status column and add new rows as tech gets added or wired up. -->

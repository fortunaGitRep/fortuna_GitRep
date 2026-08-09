# Fortuna — Build Log

**What this doc is:** The ongoing, session-by-session record of actual feature work on Fortuna — what got built, what's still open, decisions made along the way. Environment/tooling setup lives in `Fortuna-Environment-Setup.md` (stays stable, rarely touched). The reasoning behind architectural choices lives in `Fortuna-Learning-Concepts.md`. This doc is where "what's done" and "what's next" live.

Repo root: `D:\Takara\Fortuna\_Repository`

---

## Open items (current)

- [ ] Fix leftover default styling/behavior as five-tab shell gets built (Vite starter `App.css` still present, unused, not deleted)
- [ ] Move from placeholder `/` page to the real five-tab shell (Inbox, Buy, Exit, Positions, Watchlist), using the six existing HTML mockups as the visual reference (`fortuna_cash_inbox_correct_teal.html`, `fortuna_cash_buy_tab_correct_teal.html`, `fortuna_cash_exit_correct_teal.html`, `fortuna_cash_watchlist_correct_teal.html`, `fortuna_cash_watchlist_labeled_stages.html`, `fortuna_cash_glossary_corner_icon.html`)
- [ ] Email allowlist — restrict Google OAuth sign-in to your own email only (currently any Google account can get a valid session)
- [ ] Session length/expiry decision — currently Supabase default (1-hour access token, silent indefinite refresh, no forced re-login). Needs a deliberate call given this sits behind live trading data.
- [ ] Multi-device 6-digit PIN login — decided this must be a real Supabase-verified credential (hashed server-side), not a local on-device unlock, since it needs to work identically across phone + laptop. Design not started.
- [ ] Custom-branded auth emails — magic link currently uses Supabase's generic default template. Could restyle in Authentication → Emails, or route through Brevo (already used for EliteRoadMaps transactional email).
- [ ] Deploy the frontend somewhere with a real URL — prerequisite for real day-to-day mobile access (not tied to home wifi) and for PWA home-screen install.
- [ ] PWA install button (home-screen icon) — needs `vite-plugin-pwa`, manifest, icons, service worker; also needs HTTPS on a real device, which depends on the deployment step above.
- [ ] **Data architecture decision** — what Fortuna actually persists in Supabase Postgres vs computes on demand in Python. Not yet decided: "outputs only" (gate results, positions, watchlist, signal history — small, fine on free tier) vs "bulk historical OHLCV cached in Postgres" (wrong tool for that volume — flat files or a time-series store would fit better). Shapes the whole backend/signal-engine build, so worth deciding before that starts. See `Fortuna-Learning-Concepts.md` §6.
- [ ] Connect Dhan API — needs to happen before any signal engine work, since indicators/gates have nothing to compute on without real price data flowing in
- [ ] Signal engine itself — Direction Funnel logic (MAC→NAT→FLO→PRE→ENG), gates, indicators — still only exists as research PDFs, not code. Depends on Dhan API connection above.

---

## Session log

### 2026-08-08 — Auth wiring, end to end

**Goal for the session:** finish scaffold + wire up auth.

**What was done:**
- Confirmed Vite React+TS scaffold (`frontend/`) already existed from a prior session — no re-scaffold needed
- Installed `@supabase/supabase-js` and `react-router-dom`
- Created `frontend/.env.local` with `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY` (hit a Windows dotfile gotcha — Explorer silently saved it as `.env.local.txt`; fixed via `ren` in terminal)
- Created `frontend/src/supabaseClient.ts`
- Moved hand-written `LoginPage.tsx` and `AuthCallback.tsx` from the `frontend/` root into `frontend/src/` so their relative import of `supabaseClient` resolves
- Replaced Vite's default `App.tsx` demo content with `BrowserRouter` + session-aware routing (`/login`, `/auth/callback`, `/` placeholder)
- Created a new Google Cloud project (`Fortuna Login Auth`), completed the Google Auth Platform consent screen (External audience — only option on a personal account), created a Web application OAuth client with the Supabase callback URL as the authorized redirect URI
- Configured Supabase Dashboard: enabled Google provider with the Client ID/Secret, set Site URL and Redirect URLs to localhost for dev
- **Tested live, both working end to end:** Google OAuth (including the expected "unverified app" warning screen) and magic link, both landing correctly on the placeholder `/` page showing the real logged-in email
- Fixed the leftover `frontend-temp` browser tab title in `index.html`
- Committed and pushed: `Wire up Supabase auth: Google OAuth + magic link, routing, tested end-to-end`

**Decisions made:**
- Auth-only scope for today (Option A) — deferred building the real five-tab shell to a future session rather than combining it with auth wiring
- Multi-device PIN clarified as a server-verified credential, not a local app-lock, since it needs to work identically across phone and laptop
- Doc structure split three ways going forward (Environment Setup / Learning Concepts / this Build Log) to stop setup-doc bloat as feature work ramps up

**Carried to next session:** see Open Items above — most immediately relevant next steps are either the five-tab shell or starting to turn Direction Funnel research into backend code.

---

<!-- Next session entries append below, most recent last -->

### 2026-08-08 (cont'd) — Five-tab UI shell

**Goal for the session:** build the real Inbox/Buy/Exit/Positions/Watchlist shell, replacing the auth placeholder page.

**What was done:**
- Installed `@tabler/icons-react` (logged as Entry #1 in `Fortuna-Frontend-Concepts.md`)
- Defined the color palette as real CSS variables in `frontend/src/theme.css` (imported globally via `main.tsx`), replacing the placeholder `var(--surface-1)` etc. tokens the mockups used — light mode only, no dark mode
- Built `components/TabBar.tsx` — shared nav bar using `react-router-dom`'s `NavLink` for active-state styling, used by all five tab pages
- Built all five tab pages in `pages/`: `Inbox.tsx`, `Buy.tsx`, `Exit.tsx`, `Positions.tsx`, `Watchlist.tsx` — all with hardcoded dummy data, no Supabase/backend calls yet
- Wired `/inbox`, `/buy`, `/exit`, `/positions`, `/watchlist` routes into `App.tsx` behind a shared `ProtectedRoute` wrapper; `/` now redirects to `/inbox`
- Positions tab fields were designed from scratch (no mockup existed) by reasoning from what the other tabs already implied Fortuna tracks: entry→current price with P&L%, day count against the max hold window, current trailing stop, and a status badge
- Buy tab was redesigned once, after noticing the first pass had just reused Exit's row layout rather than being designed for what a *buy* decision specifically needs: qty, capital required, and initial stop shown per signal (pre-trade sizing info that Exit/Positions don't need since those are for trades already in motion), plus a "Review and execute ↗" button per card instead of one button for only the top signal
- Watchlist built using the labeled gate-stage-bars mockup variant, with a working (but non-functional placeholder) glossary icon button in the header
- Tested visually in-browser — tab bar active-state highlighting, layouts, and badges all confirmed matching intent

**Decisions made:**
- P&L color (green gain / red loss) intentionally breaks from the locked palette — universal enough convention that it didn't need to fit the teal/coral system
- Glossary content itself is deferred — button exists and is positioned correctly, but does nothing yet

**Not yet done / carried forward:**
- Glossary page/content — button is a placeholder
- All five tabs run on hardcoded dummy data — real Supabase-backed data, and the data architecture question (`Fortuna-Learning-Concepts.md` §6), still need deciding before this becomes real

**Decided and built this session (not open items):**
- Logout — `TabBar.tsx` icon opening a custom styled confirm modal (dark overlay, Cancel/Log out card matching the app palette)
- Mobile-width container — fixed ~480px shell on all screen sizes, no responsive desktop redesign (`Fortuna-Frontend-Concepts.md` §2)

Committed and pushed: `Build five-tab UI shell: Inbox, Buy, Exit, Positions, Watchlist with TabBar, theme, and logout confirm`

**Carried to next session:** connect the Dhan API before any signal engine work — indicators/gates have nothing to compute on without real price data flowing in.


# Fortuna — Build Log

**What this doc is:** The ongoing, session-by-session record of actual feature work on Fortuna — what got built, what's still open, decisions made along the way. Environment/tooling setup lives in `Fortuna-Environment-Setup.md` (stays stable, rarely touched). The reasoning behind architectural choices lives in `Fortuna-Learning-Concepts.md`. This doc is where "what's done" and "what's next" live.

Repo root: `D:\Takara\Fortuna\_Repository`

**Last updated:** 2026-08-23 (Upstox data pipeline — instrument catalogue layer built & populated: 2,643 stocks + 139 indices live in Supabase)

---

## Git hygiene (reference — set once, don't re-derive)

**`.gitignore` lives at the REPO ROOT** (`D:\Takara\Fortuna\_Repository\.gitignore`), not inside `backend/` — it must cover both backend (Python) and frontend (Vite/node) paths.

Current `.gitignore` content:

```gitignore
# --- Environment / secrets ---
.env
.env.*
!.env.example
*.pem
*.key

# --- Python (backend) ---
__pycache__/
*.py[cod]
*.egg-info/
.venv/
venv/
env/
.pytest_cache/
.mypy_cache/
.ipynb_checkpoints/

# --- Node / Vite (frontend) ---
node_modules/
dist/
dist-ssr/
.vite/
*.local
npm-debug.log*
yarn-debug.log*
yarn-error.log*

# --- Supabase local runtime ---
supabase/.temp/
supabase/.branches/

# --- Editor / OS ---
.vscode/*
!.vscode/extensions.json
.DS_Store
Thumbs.db

# --- Build / misc ---
*.log
.cache/
```

**Never committed:** `.env` (holds Dhan secrets, `F_ANTHROPIC_API_KEY`, Supabase service-role key). Only `env.example` / `.env.example` is safe to commit. A `.gitignore` only stops *untracked* files — if `.env` or `__pycache__` were ever committed before, they stay tracked until `git rm --cached <path>` untracks them. Verify before any commit: `git status` (no `.env`/`__pycache__` staged) and `git ls-files | findstr ".env"` (should show only the example file).

**Pre-commit checklist:** (1) `.gitignore` at root, (2) no double extensions in `db/migrations/` (e.g. the `001_...sql.sql` slip — should be single `.sql`), (3) `market_data/__init__.py` exists, (4) `git status` clean of secrets/pycache.

---

## Open items (current) — as of 2026-08-16

**Folder-structure convention (decided 2026-08-15):** `db/` and `modules/market_data/` are **shared foundation layers** common to both Fortuna Index (the funnel) and the future Fortuna Cash scanner — NOT owned by any single feature. `market_data/` currently sits inside `modules/` for historical reasons; the more expressive placement would be top-level beside `db/` (features in `modules/`, shared layers at top level), but moving it was deferred — the cost is the same now or when Cash arrives, so no churn right after committing. **Going forward:** create new logical folders per the shared-vs-feature distinction — shared infrastructure (used by both Index and Cash) as top-level/peer layers, actual product features under `modules/`. Do NOT nest shared layers inside one consuming feature (would force the other consumer to reach into its internals).

- [ ] Fix leftover default styling/behavior as five-tab shell gets built (Vite starter `App.css` still present, unused, not deleted)
- [ ] Move from placeholder `/` page to the real five-tab shell (Inbox, Buy, Exit, Positions, Watchlist), using the six existing HTML mockups as the visual reference (`fortuna_cash_inbox_correct_teal.html`, `fortuna_cash_buy_tab_correct_teal.html`, `fortuna_cash_exit_correct_teal.html`, `fortuna_cash_watchlist_correct_teal.html`, `fortuna_cash_watchlist_labeled_stages.html`, `fortuna_cash_glossary_corner_icon.html`)
- [ ] Email allowlist — restrict Google OAuth sign-in to your own email only (currently any Google account can get a valid session)
- [ ] Session length/expiry decision — currently Supabase default (1-hour access token, silent indefinite refresh, no forced re-login). Needs a deliberate call given this sits behind live trading data.
- [ ] Multi-device 6-digit PIN login — decided this must be a real Supabase-verified credential (hashed server-side), not a local on-device unlock, since it needs to work identically across phone + laptop. Design not started.
- [ ] Custom-branded auth emails — magic link currently uses Supabase's generic default template. Could restyle in Authentication → Emails, or route through Brevo (already used for EliteRoadMaps transactional email).
- [ ] Deploy the frontend somewhere with a real URL — prerequisite for real day-to-day mobile access (not tied to home wifi) and for PWA home-screen install.
- [ ] PWA install button (home-screen icon) — needs `vite-plugin-pwa`, manifest, icons, service worker; also needs HTTPS on a real device, which depends on the deployment step above.
- [ ] **Data architecture decision** — what Fortuna actually persists in Supabase Postgres vs computes on demand in Python. Not yet decided: "outputs only" (gate results, positions, watchlist, signal history — small, fine on free tier) vs "bulk historical OHLCV cached in Postgres" (wrong tool for that volume — flat files or a time-series store would fit better). Shapes the whole backend/signal-engine build, so worth deciding before that starts. See `Fortuna-Learning-Concepts.md` §6.
- [x] ~~Connect Dhan API~~ — **done 2026-08-09.** Trading/auth APIs live via TOTP flow, `/dhan/funds` smoke test returns real account data.
- [x] ~~Subscribe to Dhan Data API~~ — **done 2026-08-15.** ₹499/mo Data API active (single subscription covers live feed, quotes, historical, intraday). Daily historical = back to inception; intraday minute = last 5 years, 90-day-per-call cap.
- [x] ~~Module_F_Global_Gate_Funnel (Stage 1-4)~~ — **built + live-tested 2026-08-14.** AI (Claude+web_search) for data extraction + judgment only; all math in deterministic Python. Lives in `backend/modules/Module_F_Foundation_Gate_Funnel/`.
- [x] ~~Deploy + harden `sync.py`~~ — **done 2026-08-15.** Deployed, backfill run, integrity-hardened (calendar cross-check + coverage-floor clamp). Two entry points: `backfill_and_verify` (once) + `sync_daily` (every trading day).
- [x] ~~VIX percentile calc~~ — **done 2026-08-15.** Built as `vix_regime.py` (252+63 day percentile, regime bands, PRE-1 decision verdict), unit-tested, live result verified (VIX 11.31 → LOW regime).
- [x] ~~Run the index backfill~~ — **done 2026-08-15.** All 3 indices backfilled + integrity-verified (VIX/Nifty 246 rows, GIFT 274). GIFT-Nifty verification RESOLVED — Dhan genuinely serves security_id 5024.
- [ ] **Verify `sync_daily` on the first live trading day** — after Tue 2026-08-18 (Mon 17th is a normal trading day; Sat 15th = Independence Day holiday). Run `sync_daily_all()`, confirm it detects the gap since 2026-08-14, fetches only the new trading day(s), and verifies them clean (no duplicates, integrity_ok). First real test of the incremental path.
- [x] ~~Wire real Dhan VIX/OHLC into the orchestrator~~ — **done 2026-08-16.** Full data-source cleanup: orchestrator pulls VIX/Nifty/GIFT from the store, AI keeps only FII-DII/macro/news/judgment. Pre-market awareness added (PRE-3/PRE-4-location report pending). First full real Stage 1-4 verdict produced. Also fixed the AI-gateway JSON-extraction bug (prose-wrapped fenced JSON).
- [ ] **Frontend — Global Gate display** — build UI to show each module's individual verdict (MAC/NAT/FLO/PRE-1..5) and the rolled-up final decision + direction verdict. Consumes `/funnel/global-gate/run`. Stack: React + Vite + TypeScript (matches existing frontend). **STATUS (paused 2026-08-16, design phase — samples built, NOT yet wired to real .tsx):**
  - ✅ **Main dashboard sample APPROVED** (`global_gate_ui_v2.jsx`) — dark instrument-panel aesthetic, all 11 gates grouped (Macro/National/Flows/Pre-market), verdict stat blocks (tradeable/direction/trap-risk/confidence×), pending/open banner, extraction + judgment panels. Authoritative gate labels pulled from the v0.9 spec sit under each acronym. Weights shown "Style B": each of Direction/Context/Confidence = label(left) — bar(middle) — word+number(right), inline. "Reading the weights" legend included. Responsive (cards minmax 260px, stack on mobile — fixes the earlier too-thin problem). Auto-load + manual refresh planned.
  - ✅ **MAC-1 detail-page sample built** (`mac1_detail_samples.jsx`) — opens as a separate detail view on gate click (breadcrumb ← Global Gate / MAC-1, gate name + signal + weights header). **Decision: KEEP 3 SWITCHABLE TABS.** Tab 1 "Current data only" (judgment flags + overhang text + decision logic + sources — works today, no backend). Tab 2 "Full evidence trail" (per-news items tagged geopolitical/commodity/fed + rule trail — NEEDS BACKEND). Tab 3 "Hybrid" (live-now data + marked "needs backend" placeholders).
  - ⏸ **ON HOLD — finalize the COMPLETE UI design first, then convert all to real wired .tsx together.** Readability review of the detail page flagged issues (see below).
  - **Remaining to wire (after design finalised):** fetch `/funnel/global-gate/run` (auto-load on mount + refresh button); make gate cards clickable → route to detail page; build detail page as a reusable component for all 11 gates (not just MAC-1); match frontend file/routing conventions.
- [ ] **Frontend readability redesign (detail page + dashboard)** — the MAC-1 detail page readability was judged weak. Researched data-dense financial-dashboard design best practices; concrete fixes to apply: (1) stronger visual hierarchy — priority data larger/bolder, secondary smaller/lighter (page is currently too flat); (2) fix "none0.0" spacing bug — word+number collide, need a space; (3) the three top weights are cramped, DIRECTION/CONTEXT/CONFIDENCE labels too tiny/faint; (4) reserve color strictly for meaning (state), not decoration — currently violet/cyan/amber used decoratively; (5) body/faint text contrast likely below 4.5:1 — raise it; (6) more vertical breathing room between sections. Density itself is correct (Ash is a Bloomberg-terminal-type user who wants every gate daily) — the fix is hierarchy + whitespace + contrast, not less data. Apply the same design language to both the dashboard and detail page before wiring.
- [ ] **Backend — per-gate evidence trail** (for detail-page Tabs 2 & 3) — the funnel must attach, per gate, the individual news items that fed it (tagged geopolitical/fed/commodity, mapped shock-vs-overhang) and the rule-trail of checks each gate ran. Currently only the aggregated `judgment` + `extraction` exist; per-gate evidence is not captured. Until built, detail Tabs 2 & 3 render the honest "needs backend" placeholder state.
- [ ] **Test document + Excel test cases** — create a testing doc: research/write how testing is done (unit/integration/e2e, what a good test case is), how to run Fortuna's tests, and an Excel sheet of test cases (input values → expected output → actual output) for the funnel modules and market_data. Formalises verification beyond the current ad-hoc route-hitting.
- [ ] **Dhan connection fails on first server start** — `generate_fresh_token()` frequently fails on the FIRST `uvicorn` start (seen repeatedly: `KeyError: 'accessToken'` / `Invalid TOTP`), then succeeds on the second start. Likely TOTP timing/clock or a token-rate quirk. Related to the startup-blocking item below but distinct — the *first-attempt* failure pattern needs its own diagnosis (retry-with-fresh-TOTP, or a brief wait+retry inside `generate_fresh_token`).
- [ ] **Weekend/holiday integrity check for index data** — the calendar (`fortuna_nse_calendar`) now exists; use it to verify the index tables have every expected trading day (no silent gaps). Closes the autonomous-trading "no loopholes" concern.
- [ ] **Scheduling / trigger mechanism (deferred to deploy time)** — decoupled from the functions themselves (backfill/sync/calendar all run correctly regardless of trigger). Options to decide later: **Render Cron Jobs** (preferred — managed, survives restarts, one mechanism for daily market-data sync + yearly calendar refresh + eventually the funnel run) vs a **frontend button** for manual runs (e.g. a "refresh calendar" button pushed each January). Can't schedule until the backend is deployed to Render (localhost can't be cron-triggered) — so this is a go-live task. For now everything is manual via routes.
- [ ] **Annual calendar refresh** — `ensure_calendar()` must run once a year (late Dec/early Jan) to load the next year's NSE holidays before the daily sync starts adding that year's dates. Handled by whatever trigger mechanism above. The integrity-check coverage-floor clamp (added 2026-08-15) makes a late refresh fail-safe rather than broken — pre-calendar dates are stored/used but not calendar-verified.
- [ ] **Live market-status check before trading** — the REAL trade gate (calendar is only a sync-time optimization). Dhan's `dhanhq` library exposes a market-status capability; wire this as the pre-trade "is the market actually open right now?" check.
- [ ] Move Dhan token generation off startup-blocking — `generate_fresh_token()` runs at import time, so a failed TOTP call stops the server booting. Hit this repeatedly on 2026-08-14/15 (TOTP rate-limit on `--reload` restarts; clock-drift "Invalid TOTP"). Workaround: run `uvicorn main:app` without `--reload`. Needs lazy/scheduled refresh.
- [ ] GIFT Nifty carry-premium is a static estimate (`GIFT_CARRY_PREMIUM_POINTS_DEFAULT = 75.0`) — v0.9/v3 docs want a real interest-rate-differential calc. Needs computed cost-of-carry or a backtested fixed value.
- [ ] FLO-1 rolling FII/DII trend + FLO-2 retail-vs-FII divergence — currently manual params, no rolling-window logic. Needs a small Supabase table of daily FII/DII net figures.
- [ ] PRE-3 gap classifier needs Stage-5 inputs (ATR/trend) it won't have until `Module_F_Tech_Indicators_Funnel` exists — degrades to "uncertain" gracefully for now.
- [ ] No persistence for `Module_F_Global_Gate_Funnel` runs yet — returns a `Stage1To4Result` object, nothing written to Supabase. A `fortuna_global_gate_runs` audit table makes sense (whole point of the Corrections Log is auditing wrong calls).
- [ ] Model string in `ai_gateway.py` (`claude-sonnet-4-5`) not verified against the live API account.
- [ ] **VIX regime thresholds (25/75/90 percentile) need India-VIX backtesting** — currently sensible defaults, but should be validated/tuned against India VIX's own history before fully trusting the regime bands for live sizing.
- [ ] **True VIX acceleration flag** — `recent_volatility_stress` is cross-sectional (value unusual recently vs annually), not a time-change. A genuine "VIX rising over N days" flag (multi-day % change) would be a stronger stress signal — future enhancement.
- [ ] **Signal engine Stage 5 (`Module_F_Tech_Indicators_Funnel`, ENG-1..11)** — empty placeholder package only. Depends on real Nifty OHLC (now available). Combining Stage 1-4 + Stage 5 = the `Module_F_Foundation_Gate_Funnel` combiner (parent `__init__.py`, currently a placeholder comment).

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

---

### 2026-08-09 — Dhan API connection (auth + smoke test)

**Goal for the session:** connect the Dhan API and prove real account data flows into the backend.

**What was done:**
- Reviewed Dhan's full offering before building (Trading APIs free; Data APIs paid ~₹499/mo; Dhan Cloud; MCP; Conditional Orders; Postback) and confirmed Fortuna's Direction Funnel is *not* replaceable by Dhan's off-the-shelf conditional-order triggers — the multi-gate sequential pipeline is genuinely custom logic
- Decided **direct API over MCP** for order placement — MCP needs an interactive client in the loop and bakes in confirmation guardrails aimed at conversational trading; Fortuna's automated pipeline calls the SDK directly instead. (MCP still useful as a personal dev tool, separate from the product.)
- Decided **not** to route Fortuna's FastAPI backend through Dhan Cloud — that runtime is for standalone scheduled strategy scripts, not an always-on request/response server. Dhan Cloud reconsidered later as one option for *just* the signal-engine job, not the backend.
- Generated the Dhan access token ("Fortuna" app, Access Token mode — not API Key mode, since this is a personal single-account build)
- Set up **TOTP** for headless token generation, so the backend can mint fresh 24h tokens without manual daily regeneration
- Installed `dhanhq`, `pyotp`; wired `python-dotenv` via `load_dotenv()`
- Built `dhan_client.py`: reads `DHAN_CLIENT_ID` / `DHAN_PIN` / `DHAN_TOTP_SECRET` from `.env`, `generate_fresh_token()` calls Dhan's `generateAccessToken` endpoint with a live TOTP code, then constructs the `dhanhq` client with that fresh token
- Added `/dhan/funds` smoke-test route to `main.py` calling `dhan.get_fund_limits()`
- **Tested live:** `/dhan/funds` returned `"status":"success"` with the real `dhanClientId` and account balance fields — full chain confirmed end to end (`.env` → TOTP token generation → authenticated Dhan call → real data)

**Decisions made:**
- Client ID is required by *both* the token-generation call and every API call — it's the account identifier, separate from the token; not something the TOTP flow removes
- Token currently generates **at import/startup time** — deliberately, so a failed TOTP call fails loudly during the smoke test. Flagged as needing a lazy/scheduled refresh before real use (now an open item)
- `.env` for the backend holds three keys: `DHAN_CLIENT_ID`, `DHAN_PIN`, `DHAN_TOTP_SECRET` — no static access token stored, since it's minted at runtime

**Gotchas hit:**
- `python-dotenv` doesn't auto-load — needed an explicit `load_dotenv()` call before reading `os.environ`
- Editor "import dhanhq could not be resolved" was a Pylance interpreter mismatch (cosmetic), not a real missing-module error — the package was installed to the system Python 3.11

**Not yet done / carried forward:**
- Data API subscription (~₹499/mo) is the real next blocker — no historical/live price data until it's active
- Scheduled/lazy token refresh (off startup-blocking)
- Signal engine still depends on the above

**Carried to next session:** subscribe to the Dhan Data API, then begin turning Direction Funnel research into backend code against real OHLCV.

---

### 2026-08-14 — Module_F_Global_Gate_Funnel (Stage 1-4) built + live-tested

**Goal:** build the first piece of the signal engine — Stage 1-4 of the Direction Funnel (MAC-1..3, NAT-1, FLO-1..2, PRE-1..5), using AI only where genuinely needed.

**Core architecture decision (confirmed before building):** AI (Claude) does exactly two things — (1) fetch pre-market data via `web_search` that no clean API provides, and (2) make qualitative judgment calls a formula can't (event-shock vs stale-overhang; surprise vs expected). **Every arithmetic operation stays in deterministic Python.** This directly targets the 12-Aug-2026 Corrections Log root cause (a raw-number-subtraction error, not a judgment error) — keep math out of the model's hands.

**Data sourcing, researched not assumed:** India VIX + Nifty OHLC → Dhan. GIFT Nifty → NOT via Dhan originally believed (trades on NSE IFSC, different exchange) → later found in Dhan scrip master, unverified. FII/DII → not Dhan (NSE/NSDL EOD reports). Global macro/news → Claude+web_search.

**Built** — package at `backend/modules/Module_F_Foundation_Gate_Funnel/`, with `Module_F_Global_Gate_Funnel/` (Stage 1-4) as first child and empty `Module_F_Tech_Indicators_Funnel/` placeholder (Stage 5). Parent `__init__.py` = placeholder comment (combiner logic comes later).
- `schemas.py` — Pydantic: `ModuleOutput`, AI extraction/judgment shapes, `Stage1To4Result`
- `deterministic_modules.py` — every MAC/NAT/FLO/PRE function ported from v3 pseudocode, CPR calc, GIFT basis-adjustment fix, calendar helper — pure Python, no AI, no network
- `ai_gateway.py` — the ONE Claude call (web_search tool), data extraction + judgment only, never math. Reads `F_ANTHROPIC_API_KEY`
- `orchestrator.py` — `run_stage1_to_4()`, wires Dhan + AI + calendar inputs through deterministic funcs into a partial (Stage 1-4 only) result
- `test_sanity.py` — runs without any API key (mocks AI); reproduces the 12-Aug Corrections Log worked example (-0.29% gap-down) as a regression check

**Env/billing:** `F_ANTHROPIC_API_KEY` in backend `.env` — separate Anthropic console account with its own pay-as-you-go billing (Claude Pro does NOT include API access). Verified cost: Sonnet 5 $2/$10 per MTok + web_search $10/1k searches ≈ 8-9¢ per daily run (~$1.50-2/month).

**Live end-to-end test (2026-08-14, 12:46 IST):** real GIFT Nifty (cross-checked 3 sources), real FII/DII, real US/Asia close, all extracted with sources. Judgment layer correctly classified the US-Iran Strait of Hormuz situation as a **live overhang, not a fresh shock** (exactly the MAC-1 distinction the v0.9 Corrections Log was built around), kept trap_risk "moderate". Decay logic confirmed: past 10:00 IST cutoff → PRE-2/MAC-2 direction_weight correctly zeroed. Route: `/funnel/global-gate/run` (mock VIX/OHLC still, Dhan Data API not active this day).

**Gotchas:** missing `__init__.py` at `modules/` and `modules/Module_F_Foundation_Gate_Funnel/` levels (ModuleNotFoundError); parent init accidentally had child's import code; `anthropic` package not installed; Dhan TOTP rate-limit + clock-drift crashes on `--reload` (import-time token gen). Workaround: `uvicorn main:app` no `--reload`.

**Not committed** — decided to hold the git commit until tested against real Dhan data, not mocks.

---

### 2026-08-15 — Dhan Data API live, market_data layer, db/ layer, NSE calendar

**Goal:** subscribe to Dhan Data API, then build the shared market-data + storage foundation the signal engine needs.

**Dhan Data API subscribed + confirmed.** One ₹499/mo subscription covers live feed + quotes + historical + intraday. Daily historical goes back to inception; intraday minute up to 5 years with a 90-day-per-call cap (validates flat-file plan for the 500-stock scanner later). Corporate-action adjusted.

**Security IDs confirmed from Dhan scrip master CSV** (`images.dhan.co/api-data/api-scrip-master.csv`) — NOT guessed: NIFTY 50 = 13, India VIX = 21, GIFT Nifty = 5024, all `IDX_I` / `INDEX`. GIFT still unverified (listed ≠ served — test on first fetch). FII/DII confirmed NOT available from Dhan (not in their Data API list) — stays on Claude+web_search.

**New folder structure added (all additive, nothing moved):**
```
backend/
├── db/                                    ← NEW shared DB infra
│   ├── supabase_client.py                 ← lazy-singleton service-role client (reads F_SUPABASE_URL, F_SUPABASE_SERVICE_KEY)
│   └── migrations/                        ← versioned SQL, source-of-truth (run manually in Supabase)
│       ├── 001_fortuna_index_tables.sql
│       └── 002_fortuna_nse_calendar.sql
└── modules/
    └── market_data/                       ← NEW shared Dhan data-fetch + storage layer
        ├── indices.py                     ← Dhan fetch: VIX/Nifty/GIFT daily, IST-correct dates
        ├── index_store.py                 ← read/write the 3 index tables
        ├── sync.py                        ← ensure-current (backfill/gap-fill/skip) — WRITTEN, NOT DEPLOYED
        └── nse_calendar.py                ← NSE holiday fetch + weekend gen
```

**Supabase tables created + verified:**
- `fortuna_vix_daily` (date + close), `fortuna_nifty_daily` / `fortuna_gift_daily` (date + OHLC). Service-role RLS. Smoke-tested reachable (empty — backfill not run yet).
- `fortuna_nse_calendar` (trade_date PK, day_type: trading_holiday/clearing_holiday/weekend, description, year). **Populated + verified:** 20 trading + 20 clearing holidays (from NSE API), 104 weekends (generated). Both skip-guards confirmed (re-run does zero work).

**CRITICAL correctness fix — IST timestamp handling.** Dhan returns candle timestamps as epoch SECONDS stamped at midnight IST. Naive `fromtimestamp()` uses the server's local zone → on Render (UTC) every date shifts back one day, silently corrupting CPR/gap/percentile. Fixed: `epoch_to_ist_date()` pins IST explicitly. **Verified against real data:** close 24,471.70 → 2026-08-11 (matches the build-log/Corrections-Log reference), weekends correctly excluded.

**NSE calendar decisions:** Dhan-returned-dates = source of truth for *data integrity* (backward-looking gap check). NSE `holiday-master` API = source for the *forward* calendar (holidays known in advance). Live **market-status check = the real trade gate**; calendar is only a sync-time optimization + future expiry logic. Fail-loud philosophy: missing calendar → "don't assume", never guess. Republished holiday lists conflict on dates (Holi shown as both Mar 3 and Mar 14) → only NSE's own API is trusted. NSE API works on browser headers ALONE (no cookie-priming needed — confirmed by live test). CM segment (= FO in India). Clearing holidays are TRADEABLE (market open, no settlement); trading holidays are not. Independence Day 2026 (Sat) correctly landed as `weekend` not holiday — the two sources dovetailed with no gap/double-count.

**Coding standards** captured to memory and applied throughout market_data/db (error handling, retry+backoff, timeouts-where-possible, structured logging no-secrets, defensive parsing, idempotent upserts, deferred-standards noted in docstrings).

**Rules added this stretch:** #14 Baby Steps, #15 Small Fixes Small Diffs.

**Not committed yet** — same reason: commit when tested against real end-to-end index data (backfill run).

**Carried to next session:** run the index backfill (populates the 3 empty index tables, resolves GIFT verification), then harden `sync.py` with the Dhan-dates + calendar integrity check, then build the VIX percentile calc, then wire real VIX/OHLC into the Global Gate orchestrator (replacing mocks).

---

### 2026-08-15 (cont'd) — sync.py deployed, backfill run + verified, all 3 indices live

**Goal:** deploy `sync.py`, run the one-time backfill, get all three index tables populated + integrity-verified against real data.

**sync.py finalised with a two-entry-point design (Ash's requirement):**
- `backfill_and_verify(index)` — run ONCE per index. Pulls ~365 days, then does a FULL calendar integrity check (stored dates == expected trading days). After it passes, that history is trusted and frozen — never re-checked.
- `sync_daily(index)` — run EVERY trading day. Cheap max-date read, fetches only missing days, verifies ONLY the newly-added days. Never re-scans backfilled history. Refuses to run on an empty table (fail-loud: "run backfill first"). "Nothing newer to fetch" (weekend/holiday) = success, not failure.
- Plus `backfill_and_verify_all()` / `sync_daily_all()` with per-index isolation (one index failing doesn't abort the others).

**Two supporting helpers added:** `nse_calendar.get_expected_trading_days(from,to)` (the integrity oracle — weekdays minus trading_holidays/weekends; clearing holidays count as trading) and `index_store.get_stored_dates(index,from,to)`. Integrity check = `expected − stored = missing`.

**First backfill surfaced a real subtlety (good catch by the integrity check):** VIX/Nifty came back with 5 "missing" dates, GIFT with 1 — all 2025 weekdays (Gandhi Jayanti, Christmas, festival days). Root cause: the ~365-day backfill reaches into **2025**, but the calendar only holds **2026** (NSE's `holiday-master` API only serves the current year — confirmed: historical years aren't available from that endpoint). So the check flagged real 2025 holidays as "missing data" — the *data was correct*, the *calendar coverage* was incomplete for that range.

**Also learned — GIFT trades on a DIFFERENT calendar.** GIFT Nifty (NSE IX / IFSC / GIFT City) follows a more international schedule, so it trades through domestic Indian festival holidays. That's why GIFT has MORE bars (274 vs VIX/Nifty's 246) and fewer "missing" days — it's genuinely open when domestic NSE is closed. Consequence: GIFT can't be cleanly validated against the *domestic* NSE calendar; noted for later (may need its own IFSC calendar or a stored==Dhan-returned check).

**Fix chosen (no new dependency):** clamp the integrity check to the calendar's coverage floor. Added `nse_calendar.get_calendar_coverage_start()` (min trade_date in calendar); `sync._integrity_check` now only validates dates >= that floor. 2025 data is still stored and used (the percentile just needs closes), it's simply not calendar-verified for a year the calendar doesn't cover. A range entirely below the floor returns clean (nothing checkable). Rejected: sourcing 2025 from a third-party API (adds a dependency) or hardcoding a 2025 list (real work purely to validate already-correct data).

**Re-ran backfill — all three clean:** VIX `ok:true integrity_ok:true` 246 rows; Nifty same 246; GIFT `ok:true integrity_ok:true` 274 rows; zero missing dates across the board. Idempotency confirmed (re-run re-upserted without duplicating). **GIFT's long-standing "unverified" flag is now RESOLVED** — Dhan genuinely serves GIFT daily data.

**Why this problem won't recur:** the backfill-into-an-uncovered-year issue is a one-time initial-setup artifact. `sync_daily` never reaches backward (only adds today's bar, always in a covered year). Year-rollover is fail-safe via the coverage-floor clamp: if the annual calendar refresh is late, next-year dates are stored/used but just not calendar-verified until the calendar catches up — never broken.

**Scheduling deferred to deploy time** (logged in Open Items): Render Cron preferred (one mechanism for daily sync + yearly calendar refresh + funnel) vs a frontend manual button. Key principle: the functions run correctly regardless of trigger, so the trigger choice is low-stakes and later. Can't schedule until deployed (localhost can't be cron-triggered).

**State now:** entire market_data foundation live + verified end-to-end — 3 indices backfilled with ~1yr of IST-correct data, integrity-checked, in Supabase. THIS is a real commit point (working, tested, real data — not mocks).

**Carried to next session:** VIX percentile calc (reads the stored closes), then wire real VIX/OHLC into the Global Gate orchestrator (replacing the hardcoded mocks in `/funnel/global-gate/run`).

---

### 2026-08-15 (cont'd) — VIX percentile + PRE-1 decision verdict (first live funnel component)

**Goal:** build the VIX percentile calc and PRE-1's decision verdict, running on the real backfilled VIX data.

**Major design decision — VIX now used in BOTH modules (reversing the earlier 1-4 / Stage-5 separation):** The original separation was based on an assumption that later proved wrong — that Stage 1-4 would only use Claude+web_search (no Dhan data), so it was "the AI layer" and Stage 5 was "the technical layer." Now that Stage 1-4 also pulls Dhan data (VIX, OHLC), that dividing line dissolved. New design: **VIX serves decision in this module (regime/size/GO-NO-GO) AND direction in Stage 5 (as a confirmation-only `vix_direction` input alongside price).** The safety principle from the v0.9 Corrections Log is preserved automatically — VIX's directional contribution only ever lives in Stage 5 *among* the price/technical signals, so it structurally can't vote on direction from pre-market data alone. Overarching architecture: every gate/filter emits its own individual verdict, then the system rolls all individual verdicts into two high-probability rollups — one for decision, one for direction.

**Built `modules/market_data/vix_regime.py`:**
- `calculate_percentile(current, priors)` — pure, unit-tested. Mid-rank tie handling `(below + 0.5*equal)/N`. Ranks against PRIOR observations only (excludes the current value — the "prior observations only" rule).
- Two windows: 252-day (primary regime) + 63-day (recent stress). Standard, fact-checked against the Perplexity VIX brief.
- Regime bands on the 252 PERCENTILE not raw VIX (>=90 extreme, >=75 high, <=25 low, else normal) — self-calibrates to India VIX's own history, avoiding US-VIX absolute thresholds that don't transfer.
- `evaluate_vix_decision()` — emits PRE-1's individual DECISION verdict: regime, GO/NO-GO, size guidance, confidence multiplier. `direction_weight = 0.0` structurally (v0.9/v3 PRE-1 rule).

**VIX conceptual grounding (from Perplexity research, fact-checked):** VIX is a risk/regime/size gate, NOT a direction signal — rising VIX = fear/hedging but can rise before/during/after a move, so never standalone directional. Percentile answers "how unusual is today's VIX vs its own history" (regime-relative); raw value answers "how big might moves be". Use India VIX for Nifty (not Cboe VIX). 252-day primary + 63-day recent is the standard window pair.

**Perplexity code-review round (caught real issues, all fixed):**
- BUG: thin history still emitted a confident regime (10 priors + 95th pctl → false EXTREME). Fixed: regime → UNKNOWN when priors < MIN_PRIORS_FOR_CONFIDENCE (40).
- Added finite/positive value validation (drop None/NaN/<=0 before ranking).
- Renamed `recent_acceleration` → `recent_volatility_stress` — honest: it's cross-sectional (value unusual recently vs annually), NOT a time-change. True multi-day-change acceleration flagged as a future enhancement.
- Relabeled `current_vix` → `latest_close_vix` — it's the latest COMPLETED close (pre-market ~08:45 IST run), not a live "today" value. Decided: **live intraday VIX mode dropped entirely** — other gates handle in-session decisions; live VIX would add noise not decision quality (Ash's call).

**Testing:** `test_vix_regime.py` — 7 unit tests (percentile math, regime-relativity, thin-history→UNKNOWN, validation, empty-data, calm/extreme branches). Runs without DB (monkeypatches the store read). 7/7 pass locally.

**Live result on real data (246 backfilled VIX closes):** VIX 11.31 → 252-pctl 24.5 → regime LOW → GO, normal size, confidence 1.2, direction_weight 0. `priors_252_used: 245` (just under full window, handled gracefully). First fully-real, tested, fact-checked funnel component producing a live decision.

**Carried to next session:** wire `evaluate_vix_decision()` into PRE-1 inside the Global Gate orchestrator (replacing the mock VIX percentile), then wire real Nifty OHLC for CPR/gap (replacing the other mocks). Then Stage 5 build (incl. `vix_direction`).

---

### 2026-08-16 — Orchestrator wired to real data: first full Stage 1-4 verdict, no mocks

**Goal:** wire everything built (VIX regime, index store, calendar) into the Global Gate orchestrator, replacing all hardcoded mock VIX/OHLC, so `/funnel/global-gate/run` produces a Stage 1-4 verdict on fully real data.

**Design decisions settled first (before code):**
- **Dropped the `unknown`/thin-history regime** in `vix_regime.py` — it existed only for <40 days of VIX history, which can't recur post-backfill (246 days stored, only grows). Renamed `UNKNOWN` → `NO_DATA`, now meaning ONLY genuine infra failure (empty/invalid store read), not thin history.
- **`vix_regime` is the single source of VIX-decision truth; `PRE_1` became a thin adapter** — takes a `VixDecision`, maps it to `ModuleOutput` (regime→signal, confidence passes through, direction_weight=0). Removed the duplicated 25/75/90 thresholds that previously lived in BOTH `vix_regime` and `PRE_1` (a real drift-bug waiting to happen). PRE_1 stays pure; the orchestrator does the DB read.
- **`vix_direction` remains future Stage-5 work** — this file is VIX-for-decision only. Confirmed the "VIX in both modules" v1.0 design: decision here, direction (confirmation-only, alongside price) in Stage 5.
- **NO restructure** — considered moving `market_data` up beside `db/` or into the Foundation module; decided the architecture is sound and a full restructure would be over-engineering. `market_data` stays in `modules/` (folder-convention note already logged).

**Full data-source cleanup (the "we have live data now" change):**
- Orchestrator now pulls **VIX** (via `evaluate_vix_decision()`), **Nifty prev-day OHLC**, and **GIFT level** all from the **store** (`get_latest_bar()`), not from injected params or the AI.
- **AI gateway no longer fetches GIFT** — removed from its prompt + JSON schema. It now does only what genuinely needs it: FII/DII, US/Asia close, macro levels, news + judgment (shock/surprise/overhang). `gift_nifty` made optional/deprecated in `schemas.py`.
- Added `index_store.get_latest_bar(index_key)` — returns the latest full OHLC bar (handles VIX's close-only table too). Needed because CPR/gap need OHLC, not just closes.

**Pre-market awareness (Ash's principle: "say not-available-yet, don't fake it"):**
- Today's Nifty OPEN doesn't exist at a pre-market (~08:45 IST) run. Gates needing it now report a pending state instead of a fake verdict, and the rollup uses only available verdicts.
- Mapping (all five PRE gates explained/confirmed): PRE-1 (VIX regime) available ✓; PRE-2 (GIFT overnight gap) available ✓ (GIFT trades overnight); PRE-3 (gap behaviour) → `not_available_yet:pre_market` (needs today's open) ✗; PRE-4 → width available ✓, location → `location_pending` ✗; PRE-5 (calendar) available ✓.
- `nifty_today_open` is now an OPTIONAL param (None = pre-market). Pass `?nifty_today_open=<price>` after 9:15 to fill in PRE-3 + PRE-4 location. `run_stage1_to_4()` signature simplified — no more mock VIX/OHLC objects.

**Bug found + fixed live — AI gateway JSON extraction.** First real end-to-end run 500'd on `json.decoder.JSONDecodeError: Expecting value: line 1 column 1`. Added debug logging → root cause: Claude (with web_search) returns **reasoning prose + a ```json fenced block** (2070 chars of valid data), but `_extract_json_block` only stripped fences when the string STARTED with ```. Prose-before-fence broke it. Fixed: robustly find the JSON — regex for a ```json fenced block anywhere, else first-`{`-to-last-`}`, else fail loud with a preview (not a bare JSONDecodeError). Verified against the real response. Debug prints reduced to a quiet `logger.debug`.

**MILESTONE — first complete real Stage 1-4 verdict (2026-08-16 run):** All 11 modules ran on real data. PRE-1 `calm`/conf 1.2 (real VIX 11.31 @ 24th pctl), PRE-2 `small_gap_noise` (real stored GIFT), PRE-4 `narrow_trend_possible | location_pending` (real Nifty CPR width), PRE-3 `not_available_yet` + PRE-4 location pending (pre-market, correct). Real FII/DII (+508.1/+356.4), US close down, crude 88.52, gold 4376. `gift_nifty: null` in extraction (AI-drops-GIFT confirmed). Judgment correctly flagged Strait-of-Hormuz as `live_overhang` not fresh shock → `trap_risk: moderate`. Note: PRE-5 = `non_trading_day` (Sat Aug 16 = Independence Day weekend) correctly zeroed the confidence product — right behaviour, won't zero on a real trading day.

**Files changed:** `vix_regime.py`, `test_vix_regime.py`, `index_store.py`, `deterministic_modules.py` (PRE_1/PRE_3/PRE_4), `orchestrator.py` (rewritten), `ai_gateway.py` (GIFT removed + JSON fix), `schemas.py` (gift optional), `main.py` (cleaned imports, route simplified, added `/market-data/sync-daily`).

**Carried to next session:** frontend to display Global Gate individual verdicts + final verdict; test document + Excel test cases (how-to-test + input/expected/actual); then Stage 5 direction engine. `sync_daily` live test still pending Monday EOD.

---

### 2026-08-23 — Upstox data pipeline: instrument catalogue layer (Step 1) built & populated

**Context / strategic shift:** Decided to source **all market data FREE from Upstox** (Analytics Token) and keep **Dhan for execution only** — reverses the v0.4 spec's "Dhan Data API ₹499/mo" plan. Upstox's Analytics Token (1-yr, read-only, no static IP, free) confirmed to cover everything Fortuna needs: historical candles, quotes, option chain, **fundamentals**, market info, news. Only trading/account-state APIs need a static IP (irrelevant — Fortuna never trades via Upstox). Cost of the whole data layer drops to ₹0.

**Bigger scope decision — cross-market regime thesis.** Fortuna's data breadth is now driven by a cross-market regime-rotation vision: scan ALL markets/submarkets (index, stocks, non-index-correlated stocks, options, sectors, themes, commodities, bonds), find where the trend/opportunity is, rotate there; learn regime patterns from history (e.g. flight-to-safety → gold/oil in a war) and apply forward over a multi-year horizon. Consequence: fetch EVERYTHING Upstox offers (full ~2,643-stock universe, all 139 indices, full fundamentals) — not a fixed Nifty 500 — because you can't discover rotations in markets you didn't capture. Honest ceiling logged: Upstox = Indian data only, daily back to ~2000 (intraday 2022); not global, not multi-century. Captured in new `fortuna_strategy_thesis.md`.

**Three data domains defined:** (1) universe stocks (~2,643 EQ) — fundamentals + OHLCV; (2) all NSE indices (~139, minus Nifty 50) — OHLCV only; (3) Nifty 50 separate — OHLCV all timeframes + near-future options data for index-options trading.

**Design decisions settled first (before code):**
- **Auth = raw pre-authenticated `requests.Session`, NOT the official upstox-python-sdk.** The SDK is a heavyweight OpenAPI-generated client built around the OAuth/trading surface (~95% order-placement code this read-only token can't use); a plain Bearer header keeps the hand-rolled retry/backoff/throttle control the backfill needs and matches the "client owns auth, data modules import it" pattern (`dhan_client` ↔ `upstox_auth_client`). Verified an SDK exists but chose against it deliberately.
- **Trading path deferred (Rule #16, added this session):** never let current broker cost/pricing decisions hardcode the architecture. `get_trading_client()` is a stub raising NotImplementedError with a pointer; `.env` gets commented placeholder trading vars. Broker choice may change after Fortuna is complete.
- **Data-fetch build discipline = per-script Phase 1 / Phase 2.** Phase 1 = download+parse+filter+PRINT summary, NO DB write (verify the data is sane first). Phase 2 = add the DB write once verified. This caught a real bug (below).
- **DB naming convention:** lowercase `f_` prefix (Postgres folds unquoted identifiers to lowercase; capital `F_` would force quoting in every query forever). Python files verb-explicit (`fetch_*`, `read_*`, `track_*`). Parquet filenames = instrument_key suffix (ISIN for stocks, slugified index name for indices). Audit timestamps in IST via a shared `now_ist()` SQL helper.
- **Storage split (resolves the Learning-doc §6 open question):** reference/output data → Supabase Postgres (catalogues, fundamentals, watchlists, fetch-status); bulk historical OHLCV → Parquet in Supabase Storage. Broker-namespaced folders (`dhan/`, `upstox/`) for swappability.
- **Soft-delete, never hard delete:** delisted/vanished instruments get `is_active=false` (skipped by fetchers) but keep their row + history — the regime-research thesis actively wants delisted names. Storage cost is negligible.

**What got built + verified:**
- `upstox_auth_client.py` — Analytics Token auth, `get_analytics_client()` (cached authed Session), stubbed `get_trading_client()`, `smoke_test()` (Market Status call), JWT-exp expiry warning. **Smoke test PASSED** (HTTP 200, status=success).
- Migration `003_fortuna_universe_instruments.sql` → `f_universe_instruments` (stocks). Live.
- Migration `004_fortuna_index_instruments.sql` → `f_all_nse_index_instruments` (indices). Live. (Both reuse shared `now_ist()` + `touch_updated_at_ist()` + RLS service-role-only.)
- `fetch_universe_instrument_list.py` — downloads `NSE.json.gz` (public, ~83,844 records), filters `segment=NSE_EQ AND instrument_type=EQ`, cross-refs `NSE_FO` underlyings for F&O flag. Verify-then-`--sync` modes.
- `fetch_index_instrument_list.py` — same shape, `segment=NSE_INDEX`.
- `instrument_store.py` — config-driven store for BOTH catalogue tables (mirrors `index_store.py`'s `TABLE_CONFIG` pattern): chunked upsert on `instrument_key` PK (500/batch) + `reconcile_active()` soft-delete + `sync_catalog()` orchestration + `connection_smoke_test()`.

**KEY DATA FINDING (caught by Phase-1 verify-first):** filtering `segment=NSE_EQ` alone returns **9,687** records — but only **2,643** are actual company equities (`instrument_type=EQ`). The other ~7,000 are govt securities / bonds / debt (SG=4,301, GS, TB, GB, N*/Y*/Z* series). Must filter `instrument_type=EQ` too. ETFs are typed `EQ` (e.g. SMALLIETF) so captured automatically; ETF-specific research deferred. This is exactly why Phase-1-print-before-DB-write exists — a blind write would have polluted the universe with 7,000 non-stocks.

**Bug found + fixed live — `.env` not loaded in the fetch→store chain.** First `--sync` failed: `Missing required environment variable 'F_SUPABASE_URL'` even though it existed in `.env`. Root cause: `db/supabase_client.py` reads `os.environ` but nothing in the fetch→store→supabase_client import chain called `load_dotenv()` (only `upstox_auth_client` self-loads, and this path doesn't import it). Fix: `load_dotenv()` at the top of each fetch script's `__main__` block (idempotent, localized). Did NOT modify shared `supabase_client.py` (Rule #7 — the Dhan pipeline depends on it; consolidating the load into that file is logged as an optional future refactor).

**MILESTONE — Step 1 (instrument catalogue layer) complete & populated:**
- `f_universe_instruments`: **2,643 stocks** (208 F&O-eligible), verified in DB.
- `f_all_nse_index_instruments`: **139 indices**, verified in DB.
- **Idempotency proven:** re-running `--sync` returned HTTP 200 (update) not 201 (insert), row counts unchanged (2,643 / 139), zero duplicates — the property the future scheduler depends on.
- Full chain proven end-to-end: auth → public download → parse → filter → verify → chunked upsert → paginated soft-delete reconcile → Supabase (service-role, RLS bypassed).

**Docs updated this session:** `fortuna_multi_strategy_roadmap.md` (build-status header, EQ-only finding, scheduler open-item §10, Postgres-vs-Parquet resolution §11); new `fortuna_code_flow.md` (auth→fetch→store→DB flow, per-file responsibilities, DB layer, Step-1-vs-Step-2 distinction); new `fortuna_strategy_thesis.md` (cross-market regime thesis); new `fortuna_spec_increment_2026-08-23.md` (scope + v0.4 corrections, to merge at next spec bump); `Fortuna-Learning-Concepts.md` (`__init__.py` note).

**Open items surfaced:**
- **Scheduler (important):** all fetches are manual `--sync` runs. Production needs an unattended, ordered, resumable scheduler (daily instrument refresh → daily OHLCV → fundamentals staleness check; weekly 1W; monthly 1Mo). Can't finalize until the OHLCV/fundamentals jobs exist. Options: APScheduler / Render Cron / task queue.
- **Dhan → `dhan/` migration** still deferred (files loose in `market_data/`; move + fix imports + re-test as its own task). `market_data/` and `upstox/` now have `__init__.py`.
- **Index data source migration** (Foundation Funnel's VIX/Nifty/GIFT from Dhan → Upstox) — separate future task; don't cancel Dhan Data API subscription until done.

**Carried to next session — Step 2: OHLCV fetching.** Build `_ohlcv_engine.py` (shared fetch core) + `fetch_universe_ohlcv.py` / `fetch_index_ohlcv.py` (thin per-domain callers) + `read_ohlcv.py` (single read accessor) + `f_fetch_status` table + `track_fetch_status.py` (resumability). Priority order: (1) all indices, (2) Nifty 50 separate (own Parquet, intraday), (3) EQ stocks. Confirm Upstox V3 historical per-call date-range caps on first real call.

### 2026-08-25/26 — Upstox data pipeline: OHLCV backfill + full Fundamentals layer (Steps 2 & 3) complete

**Milestone summary.** The entire data foundation is now built and populated: OHLCV price history for the full universe in R2, and company fundamentals (screening Tier-1 + archival Tier-2) in Supabase. First fundamental watchlist screen ran successfully. This closes Steps 2 and 3 from the previous session.

**STORAGE CHANGE (supersedes last session's plan): Supabase Storage → Cloudflare R2 for OHLCV.** Last session logged "bulk OHLCV → Parquet in Supabase Storage." Superseded: bulk OHLCV Parquet now lives in **Cloudflare R2** (bucket `fortuna-ohlcv`, S3-compatible, **zero egress fees** — decisive for repeated backtesting reads). Access via `db/r2_client.py` (`get_r2()`, `get_r2_settings()`). Supabase Postgres remains for all relational data. Rule of thumb settled: **per-entity files (R2/Parquet) when data is big-per-entity and read one-at-a-time** (OHLCV — load one stock's long series, compute); **relational rows (Postgres) when small-per-entity and filtered-across-all** (fundamentals screening — `WHERE pe<20 AND roe>12` across all stocks).

**Step 2 — OHLCV pipeline (DONE).**
- Built: `_ohlcv_engine.py` (fetch core — `fetch_candles`, `fetch_full_history` with decade-chunk pagination for the V3 daily span cap, `fetch_all_timeframes`), `ohlcv_store.py` (Parquet↔R2 — `backfill_instrument`, `update_instrument` merge-dedup, `_write_df`), `ohlcv_fetch_progress.py` (resumability ledger), shared `_ohlcv_backfill_runner.py` (`run_backfill(cfg)`, `cli_main(cfg)`, `DomainConfig`) with thin callers `fetch_index_ohlcv.py` / `fetch_universe_ohlcv.py`.
- One Parquet per instrument, all three timeframes stacked (`timeframe` col: 1d/1w/1mo). Keys `upstox/universe/<ISIN>.parquet`, `upstox/indices/<slug>.parquet`.
- Migration `005_fortuna_ohlcv_fetch_progress.sql` → `f_ohlcv_fetch_progress` (resumable per-instrument ledger).
- **Result:** 135 indices + 2,638 stocks done, ~287 MB in R2, content-verified against live values. (4 BHARATBOND indices + 2 illiquid stocks fail candles — genuinely not available.)

**Step 3 — Fundamentals pipeline (DONE).** Upstox Company Fundamentals API: 8 endpoints, keyed by ISIN except `competitors` (needs `instrument_key`). Split into Tier-1 (screening) and Tier-2 (archive).
- **3 tables** (Migration `006_fortuna_fundamentals.sql`): `f_fundamentals_profile` (descriptive), `f_fundamentals_metrics` (screening workhorse — all numeric, one row/stock), `f_fundamentals_statements` (Tier-2 JSONB archive).
- **Store:** `fundamentals_store.py` — `store_fundamentals(screening_only=)` (Tier-1: profile+metrics), `store_tier2_statements()` (Tier-2: the 4 archive endpoints → statements). Parsers strip `%` conditionally, compute growth/CAGR from core Revenue, sort periods newest-first.
- **Orchestrators:** `fetch_universe_fundamentals.py` (Tier-1 screening backfill, ledger `f_fundamentals_fetch_progress` / Migration 007); `backfill_universe_fundamentals_onetime.py` (Tier-2 one-time archival, ledger `f_fundamentals_tier2_progress` / Migration 009, auto-cooldown).
- **Result:** Tier-1 2,296 stocks done; Tier-2 2,290 archived, 0 failed.

**ETF SPLIT (Migration `008_fortuna_split_etf_instruments.sql`).** ISIN-prefix analysis of the catalogue: INE=2,295 (companies), INF=347 (ETFs/MF units), IN9=1 (JAIN DVR — a real stock, kept). ETFs have no fundamentals and are a different KIND of instrument, so — matching the indices-table precedent (own table, not a per-row flag) — moved the 347 INF rows to new `f_etf_instruments`. `f_universe_instruments` is now **2,296 pure stocks**. ETFs preserved (not deleted) for a future regime-rotation/exposure layer. Staged migration (create→copy→verify→delete).

**Gap analysis vs Ash's 15-criteria screener → Path A (reserve, fill later).** ~10 criteria Upstox serves directly (ROCE, ROE, P/E, P/B, 1Y+3Y sales/profit growth). 5 gaps left as reserved NULL columns in `f_fundamentals_metrics`, filled by later jobs: `market_cap_cr`/`shares_outstanding`/`face_value` (NSE quote-equity, issuedSize×price — Upstox has no reliable share count), `pledge_pct` (NSE disclosure feed), `debt_to_equity`/`interest_coverage`/`revenue_growth_5y`/`net_profit_growth_5y` (external Screener/Yahoo — borrowings/interest not broken out, only 4yr history).

**Real bugs found + fixed (all caught by verify-first / the bulk run itself):**
1. **CAGR complex-number bug** — `(negative)**(1/3)` yields a Python `complex`, which isn't JSON-serialisable → 107 loss-year stocks failed the DB write. Fix: `_cagr` returns `None` unless BOTH endpoints > 0 (CAGR through a loss is mathematically undefined anyway).
2. **Bank revenue = NULL** — banks/NBFCs (SBI, HDFC, ICICI… ~260 major financials) have no "Revenue" line-item, only "Total Revenue" → all got NULL revenue. Fix: `_parse_income` falls back to "Total Revenue" when core "Revenue" is absent. Verified SBI (rev ₹712,643cr, 1Y +7.4%, 3Y CAGR +14.6%). Manufacturers unchanged (they keep core Revenue).
3. **Array-ordering latent bug** — growth/CAGR trusted API array order; fixed with explicit newest-first sort (`_period_key` parses "Mar 2026" → sortable).
4. **Partial-429 archive bug (Tier-2)** — if some of the 4 endpoints 429'd but others succeeded, a partial row got stored + marked done (permanently incomplete). Fix: if ANY endpoint is rate-limited, whole stock stays retryable (no partial write). Critical for an archival run.

**RATE-LIMIT strategy (the defining constraint).** Upstox limits are FLAT (not raised by the Plus plan — verified): 25/sec, 250/min, **1000 / 30-min rolling** (the binding one). Fundamentals = 4 calls/stock, so ~250 stocks exhausts a window; a full run is inherently multi-hour. Defence layers: (1) `request_get` 1s/2s/4s retry; (2) proactive throttle; (3) **rate-limited ≠ failed** — a 429'd stock stays `pending` (retried), so the `failed` list stays meaningful (genuine no-data/ETFs only); (4) **auto-cooldown** in the Tier-2 backfill — per-stock 2 attempts 10s apart, and if the 2nd is still rate-limited, **sleep 30 min** then resume the SAME stock. The Tier-2 run finished 2,290/2,290 fully unattended (4 auto-sleeps navigated).

**First watchlist screen ran** (not yet persisted): the ~10 available criteria as SQL against `f_fundamentals_metrics` → ~98–137 quality stocks (banks now included via the revenue fix). This is "Watchlist 1"; persistence design (criteria + materialized members, `f_watchlists` + `f_watchlist_members`, source flag) is an OPEN item.

**Data verification.** Eyeballed all 3 fundamentals tables for representative ISINs (KRBL, Godrej, SBI, etc.) — values sane and cross-table consistent. Quirks documented (per-stock period vintage; Tier-2 lags Tier-1 ~1yr; two by-design NULL statements columns; negative CAGR valid). Decided to trust the data rather than exhaustively cross-check Screener now (breadth cross-check via Chartink list-comparison is the future method if needed).

**Docs updated this session:** new `fortuna_data_pipeline_flow.md` (deep pipeline reference — 5-layer pattern, OHLCV+fundamentals call-trees, walk-throughs, rate-limit playbook, verification quirks + join SQL, run/argparse mechanics). This Build-Log entry. `fortuna_code_flow.md`, `Fortuna-Tech-Stack.md`, `Fortuna-Learning-Concepts.md`, `fortuna_multi_strategy_roadmap.md`, `fortuna_spec_increment_2026-08-23.md`, `fortuna_strategy_thesis.md` reconciled to current reality (R2 storage, 2,296 stocks + ETF split, fundamentals done).

**Open items surfaced / carried forward:**
- **Watchlist persistence** — build `f_watchlists` + `f_watchlist_members`; the 3 planned lists (fundamentals-swing, fundamentals-longterm, options/F&O). Next milestone.
- **`update_universe_fundamentals_qtrly.py`** — recurring APPEND job (vs the one-time backfills); cadence TBD. Deferred until something consumes fresh data.
- **NSE market-cap/shares fill job** — separate; fills the reserved gap columns (issuedSize×price).
- **DuckDB analytical layer** + `read_ohlcv.py` accessor — deferred until bulk research reads begin.
- **Scheduler / Render cloud runs** — for unattended recurring jobs, once they exist.

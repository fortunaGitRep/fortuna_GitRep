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
- [x] ~~Connect Dhan API~~ — **done 2026-08-09.** Trading/auth APIs live via TOTP flow, `/dhan/funds` smoke test returns real account data.
- [x] ~~Subscribe to Dhan Data API~~ — **done 2026-08-15.** ₹499/mo Data API active (single subscription covers live feed, quotes, historical, intraday). Daily historical = back to inception; intraday minute = last 5 years, 90-day-per-call cap.
- [x] ~~Module_F_Global_Gate_Funnel (Stage 1-4)~~ — **built + live-tested 2026-08-14.** AI (Claude+web_search) for data extraction + judgment only; all math in deterministic Python. Lives in `backend/modules/Module_F_Foundation_Gate_Funnel/`.
- [ ] **Deploy + harden `sync.py`** — written 2026-08-14, NEVER deployed/run yet. Needs the data-integrity hardening discussed 2026-08-15 (verify stored dates == Dhan's returned dates for the range; treat "no fresh data" as "don't trade") before it's trusted for autonomous use.
- [ ] **VIX percentile calc** — not built yet. Reads `get_recent_closes("INDIA_VIX", window)` from the store, ranks today's VIX. Blocked only on running the backfill (below).
- [ ] **Run the index backfill** — `sync.py` will pull ~365 days for VIX/Nifty/GIFT into the (currently empty) `fortuna_*_daily` tables on first run. Not done yet. Also resolves the GIFT-Nifty verification (does Dhan actually serve security_id 5024?).
- [ ] **Wire real Dhan VIX/OHLC into the orchestrator** — `Module_F_Global_Gate_Funnel`'s `/funnel/global-gate/run` still uses hardcoded mock VIX/OHLC. Swap for real `market_data` fetches once backfill + percentile are done.
- [ ] **Weekend/holiday integrity check for index data** — the calendar (`fortuna_nse_calendar`) now exists; use it to verify the index tables have every expected trading day (no silent gaps). Closes the autonomous-trading "no loopholes" concern.
- [ ] **Annual calendar refresh scheduling** — `ensure_calendar()` works and is loaded for 2026; needs a scheduled once-a-year run (+ `force_holidays=True` path for mid-year NSE circular updates). Currently manual via `/market-data/nse-calendar/sync`.
- [ ] **Live market-status check before trading** — the REAL trade gate (calendar is only a sync-time optimization). Dhan's `dhanhq` library exposes a market-status capability; wire this as the pre-trade "is the market actually open right now?" check.
- [ ] Move Dhan token generation off startup-blocking — `generate_fresh_token()` runs at import time, so a failed TOTP call stops the server booting. Hit this repeatedly on 2026-08-14/15 (TOTP rate-limit on `--reload` restarts; clock-drift "Invalid TOTP"). Workaround: run `uvicorn main:app` without `--reload`. Needs lazy/scheduled refresh.
- [ ] GIFT Nifty carry-premium is a static estimate (`GIFT_CARRY_PREMIUM_POINTS_DEFAULT = 75.0`) — v0.9/v3 docs want a real interest-rate-differential calc. Needs computed cost-of-carry or a backtested fixed value.
- [ ] FLO-1 rolling FII/DII trend + FLO-2 retail-vs-FII divergence — currently manual params, no rolling-window logic. Needs a small Supabase table of daily FII/DII net figures.
- [ ] PRE-3 gap classifier needs Stage-5 inputs (ATR/trend) it won't have until `Module_F_Tech_Indicators_Funnel` exists — degrades to "uncertain" gracefully for now.
- [ ] No persistence for `Module_F_Global_Gate_Funnel` runs yet — returns a `Stage1To4Result` object, nothing written to Supabase. A `fortuna_global_gate_runs` audit table makes sense (whole point of the Corrections Log is auditing wrong calls).
- [ ] Model string in `ai_gateway.py` (`claude-sonnet-4-5`) not verified against the live API account.
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

# Fortuna — Learning & Concept Log

A running record of the technical concepts applied while building Fortuna, in the order they were actually decided — not a generic reference, but *why this project specifically needed this choice*. Purpose: build depth as I go, and have a real, defensible system to walk through later (interviews, portfolio, whatever comes up).

Each entry: what the concept is → why Fortuna needed it → what I considered and rejected, and why.

---

## 1. PWA (Progressive Web App) for the frontend

**What it is:**
A web app that behaves like a native app — installable to a home screen, works offline-capable, can receive push notifications — while still being a normal website under the hood (one codebase, no app store).

**Why Fortuna needed it:**
Fortuna's cash-swing UI (Inbox/Buy/Exit/Positions/Watchlist) needs to alert me the moment a buy/exit trigger fires — trading is time-sensitive, so in-app-only checking isn't good enough. But building two separate native apps (iOS + Android) for a personal tool is disproportionate effort for a single user. A PWA gets push notifications (Android natively, iOS 16.4+ if added to home screen) and installability from one React codebase, no App Store review, no separate mobile build pipeline.

**What I rejected, and why:**
- *Native app (Swift/Kotlin):* Two codebases to maintain, app store approval overhead, massive overkill for a single-user tool. Rejected on cost/benefit.
- *Plain website, no PWA features:* No push notifications, no home-screen presence — would mean checking manually, which defeats the point of a decision-inbox system built for speed-to-action.

---

## 2. Auth strategy — Google OAuth (primary) + magic link (fallback)

**What it is:**
Two passwordless login paths: "Continue with Google" (OAuth — Google vouches for identity) and email magic link (Supabase sends a one-time login link, no password stored anywhere).

**Why Fortuna needed it:**
No password means no password to leak, phish, or brute-force. But I also wanted this to be fast/frictionless, not security theater that's annoying to use daily. Google OAuth is mature, battle-tested infrastructure I don't have to trust myself to build correctly. Magic link exists as a fallback with zero dependency on Google, in case that account or service has an issue — never rely on a single point of failure for the only way into a system holding trading data.

**What I rejected, and why:**
- *Native Supabase Passkey/WebAuthn (fingerprint login):* Genuinely the ideal UX (Face ID/Touch ID, phishing-resistant by design) — but Supabase's implementation is currently beta/experimental, with open bugs like "browser does not support WebAuthn" showing up in their own GitHub discussions. If this were my *only* login method and it broke, I'd be locked out of my own trading data with no way in. Revisiting once it's GA (out of beta) — not rejected forever, just not yet.
- *Traditional email + password:* Passwords are the single most-attacked credential type (reuse, breaches, phishing). Skipping entirely rather than managing that risk.
- *SMS OTP:* Real cost per message, added infra (Twilio/MSG91), and a phone-number dependency — decided email magic link covers the "simple fallback" need without the recurring cost.

---

## 3. Row Level Security (RLS) on Supabase tables

**What it is:**
A Postgres-level enforcement rule: which rows of a table a given request is allowed to see or modify, decided by the database itself based on who's authenticated — not by trusting the frontend to behave.

**Why Fortuna needed it:**
The React PWA calls Supabase *directly from the browser* — there's no backend server sitting in between to gatekeep requests. That means the public "anon key" is visible in my app's JS bundle by design (this is normal for Supabase apps). Without RLS, that key alone would be enough for anyone to query tables like `fortuna_positions` directly. RLS makes the database itself the security boundary: even if the key leaks, a request can only touch rows belonging to the authenticated user's own `auth.uid()` — there's no session that resolves to anyone else's data.

**What I rejected, and why:**
- *No RLS, rely on obscurity (key not being found):* Security through "no one will find it" isn't real security, and this is trading position data, not a public blog. Rejected outright.
- *"Automatically expose new tables" left on:* Would grant API access to every new table by default. Turned off — new tables stay unreachable until I explicitly write a policy, so nothing is exposed by accident.
- *Building a backend API layer to gatekeep instead of RLS:* Legitimate alternative pattern (backend validates every request before touching the DB) — but adds a whole service to build/host/maintain for a single-user app. RLS gets the same guarantee at the database layer for free, given I'm already on Supabase. Revisit only if Fortuna's needs get complex enough to justify a real backend (e.g. the signal engine itself, which likely will need one).

---

## 4. Supabase Cloud-only, no local Docker stack

**What it is:**
Supabase offers `supabase start` — a full local Postgres/Auth/Storage stack running in Docker, mirroring the cloud project for local development and testing. The alternative is developing directly against the real Supabase Cloud project, with the CLI used only for pushing schema migrations and edge functions.

**Why Fortuna needed it (cloud-only):**
Running the local stack requires Docker Desktop, which on this machine needed BIOS-level virtualization, WSL2, and Virtual Machine Platform all correctly configured first — real setup cost before writing a single line of app code. At this stage, that cost buys a feature (an offline/local copy of the database for testing) that isn't actually needed yet — there's no team to isolate from, no risk of touching production data by accident with a single user, and no migration volume high enough to justify the safety net. Cloud-only keeps one source of truth and removes an entire layer of environment complexity.

**What I rejected, and why:**
- *Local Docker-based Supabase stack (`supabase start`):* Tried first, then abandoned after hitting the Docker/BIOS/WSL2 configuration chain. Docker Desktop was uninstalled entirely rather than pushed through — the setup cost wasn't worth it for a single-user project with no local-testing requirement yet.
- *Half-measure (Docker installed but stack unused):* No reason to keep Docker Desktop installed at all if it's not being used — removed cleanly rather than left as dead weight.

**What I chose instead:**
Develop directly against the real Supabase Cloud project. The Supabase CLI (`supabase link`, `supabase login`) connects the terminal to the cloud project for pushing schema migrations and edge functions — no local database process runs at all. One source of truth, zero Docker/virtualization dependency, browsing tables happens in the Supabase web dashboard instead of a local Studio instance.

**Revisit when:** schema/migration iteration gets heavy enough that testing directly against production-linked Cloud becomes risky or slow — at that point the local stack's safety net becomes worth its setup cost.

---

## 5. Multi-device PIN — server-verified, not a local app-lock

**What it is:**
A 6-digit PIN as a second way into Fortuna, alongside Google OAuth and magic link. Two fundamentally different ways to build this: a **local app-lock** (a PIN that unlocks a session already sitting on that specific device, checked entirely client-side, no server round-trip) versus a **server-verified credential** (the PIN itself is hashed and stored in Supabase, checked against the backend, so it works as a real login method from any device).

**Why Fortuna needed it (server-verified):**
The initial ask was a PIN that's fast to unlock with, but that ask also required the *same* PIN to work identically from both phone and laptop — including a device that's never been logged into before. A local app-lock can't do that by definition: it only ever unlocks a session that already exists on that device. Since the requirement was genuinely cross-device, the PIN has to be a real, independently-checkable credential Supabase can verify — otherwise a second device with no prior session would have no way to use it at all.

**What I rejected, and why:**
- *Local on-device PIN unlock:* This was the first instinct — feels lighter, no server round-trip, common pattern in banking/trading apps for quick re-entry. Rejected once the actual requirement (any device, not just "my usual device") was made explicit, since a local gate structurally cannot satisfy that.
- *SMS OTP as the "fast" option instead of a PIN:* Already rejected earlier in Entry #2 for the primary/fallback auth pair — same cost and deliverability issues apply here, and it doesn't solve for "fast unlock" anyway since it still needs network + waiting for a text every time.

**What I chose instead:**
A PIN checked server-side against Supabase, the same way a password would be (hashed at rest, verified via a dedicated endpoint/RPC rather than Supabase's built-in OAuth/magic-link providers, since PIN-as-credential isn't a native Supabase auth method). This makes it a real, portable login path — works the same from a brand new device as from a familiar one — at the cost of a network round-trip a pure local unlock wouldn't need.

**Status:** Decision made, not yet built.

---

## 6. Storage vs compute — what actually lives in Supabase Postgres (open question)

**What it is:**
Two different things that got conflated at first: *where the dev database runs* (Entry #4 — local Docker vs Supabase Cloud) versus *what data Fortuna actually persists in that database at all*. These sound related but are independent — the cloud-vs-local choice is about the database's location, not its size or shape.

**The confusion, as it actually happened:**
The question came up: does going Cloud-only (no local Docker) limit how much stock/indicator data Fortuna can work with — a whole NSE F&O universe of historical prices plus computed indicators (VWAP, ADX, Supertrend, RSI, etc.)? The honest answer: **the Docker decision barely matters for this.** The reason is that VectorBT/TA-Lib/pandas-ta don't operate through Postgres at all — they pull historical price data from Dhan's API into pandas DataFrames and compute indicators in-memory, in Python. That's a compute task, not a database task, and it's identical whether Supabase happens to be local or cloud.

**What actually matters instead:**
Whether Supabase Postgres is used to *store* bulk historical market data, or only to store the *outputs* of processing it:
- **Outputs only** (which stocks passed which gate, current positions, watchlist state, signal history) — small, relational, fits comfortably on Supabase's free tier (500MB). Cloud-only Postgres is a fine fit for this, no scale concern.
- **Bulk historical OHLCV for a full stock universe, years deep** — a fundamentally different amount of data, and a relational row-store isn't really the right tool for it regardless of local or cloud. That pattern usually wants flat files (Parquet/CSV, cached to disk or Render's storage) or a dedicated time-series store, fetched/refreshed from the broker API rather than held permanently in Postgres.

**Status:** Not yet decided which pattern Fortuna uses. This directly shapes the backend/signal-engine architecture, so it's worth deciding deliberately before that gets built, rather than defaulting into "put everything in Supabase" by momentum. Tracked as open in `Fortuna-Build-Log.md`.

---

## 7. `@tabler/icons-react` for the tab bar and UI icons

**What it is:**
A React component library shipping the Tabler icon set as individual importable components (`IconBell`, `IconArrowUpCircle`, etc.) — versus an icon *font*, where icons are characters in a custom font file rendered via a CSS class (e.g. `<i class="ti ti-bell">`).

**Why Fortuna needed it:**
The UI mockups (built via the Visualizer widget tool for design review) already used Tabler icons through the CSS-class font pattern, since that's how the mockup tool renders them. But that pattern isn't how a real Vite/React app consumes icons — there's no icon font wired into the project, and pulling one in would mean self-hosting font files or a CDN dependency for something React already handles more directly. `@tabler/icons-react` keeps the exact same icon set and visual look as the approved mockups, just delivered as tree-shakeable React components instead of a font — the standard pattern for icons in a modern React app.

**What I rejected, and why:**
- *Self-hosting the Tabler icon font and using CSS classes (matching the mockup markup literally):* Would work, but adds a font-loading dependency and doesn't fit how the rest of the React app is built (component-based, not class-based). No real upside over the React-native package for a from-scratch build.
- *A different icon set entirely:* Would break visual continuity with the already-approved mockups for no reason — Tabler's icon selection was already chosen and looked right in the design review.

---

## 8. Fixed mobile-width shell on all screen sizes, no responsive desktop layout

**What it is:**
The app renders inside a fixed ~480px-wide container, centered on the page, regardless of viewport width — versus a fully responsive layout that reflows content (e.g. sidebar nav, multi-column content) to use extra space on wider screens.

**Why Fortuna needed it:**
Fortuna's whole reason for being a PWA (see Entry #1) is the phone-alert-to-action loop — a trigger fires, you get notified, you act fast, on your phone. Desktop is real but secondary: something that needs to work when opened, not a primary surface worth its own layout design. A fixed mobile-width shell gets the actual target experience (phone) exactly right and costs nothing extra on desktop beyond unused side margins.

**What I rejected, and why:**
- *Full responsive redesign (sidebar nav on wide screens, multi-column content, table views for Positions/Watchlist on desktop):* Real, structural extra work — different nav pattern, different content density decisions per breakpoint — for a secondary use case. Rejected for now as effort disproportionate to how Fortuna is actually meant to be used.

**Revisit when:** desktop becomes a genuinely primary way you use Fortuna (e.g. active research/backtesting sessions where more screen real estate would actually help) rather than an occasional fallback.

---

<!-- Next entries append below as concepts get added, in the order they're decided. -->


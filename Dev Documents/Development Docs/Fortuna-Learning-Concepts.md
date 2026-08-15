# Fortuna — Software Engineering Concepts & Learning Log

**What this doc is:** A running record of the software engineering concepts behind Fortuna — written so it works two ways at once. First, as *why this project specifically needed this choice*, in the order decisions were actually made. Second, as genuine interview preparation: each entry starts with the underlying fundamental — the thing a computer science grad or bootcamp grad would already know cold — before getting into Fortuna's specific decision. The goal is to close that gap, not just document Fortuna.

**Format per entry:** *Fundamentals* (what the underlying tech/concept actually is, taught from scratch) → *Why Fortuna needed it* → *What I considered and rejected, and why*.

**Sections:** Frontend · Backend · Database · Security · Infrastructure

---

# Frontend

## 1. PWA (Progressive Web App)

**Fundamentals:**
A normal website is HTML/CSS/JS served from a server, rendered fresh in a browser tab each time you visit — it has no presence on your device beyond a bookmark, and it stops working the instant you lose internet. A **native app** (built with Swift for iOS, Kotlin for Android) is the opposite extreme: compiled code installed directly on the device, with full access to OS features (push notifications, home-screen icon, background processing), but requiring a separate codebase per platform and going through an app store's review process to ship.

A **PWA** sits in between. It's still a website — same HTML/CSS/JS, one codebase — but two browser technologies let it behave like a native app:
- A **service worker**: a JavaScript file that runs in the background, separate from your page, even when the tab is closed. It can intercept network requests (enabling offline behavior by serving cached content) and receive **push notifications** from a server.
- A **web app manifest** (`manifest.json`): a small config file listing the app's name, icons, and colors. Browsers use it to let a user "install" the site — meaning it gets a real home-screen icon and opens in its own window, no browser address bar, indistinguishable at a glance from a native app.

**Why Fortuna needed it:**
Trading is time-sensitive — a buy/exit trigger firing needs to reach you fast, and "check the app manually" isn't good enough. Push notifications require either a native app or a PWA; a plain website can't send them. But building two separate native codebases (iOS + Android) for a single-user personal tool is disproportionate effort. A PWA gets push notifications (Android natively; iOS 16.4+ once added to the home screen) and installability from the one React codebase already being built, with no App Store review and no separate mobile build pipeline.

**What I rejected, and why:**
- *Native app (Swift/Kotlin):* Two codebases, app store approval overhead — massive overkill for a single-user tool. Rejected on cost/benefit.
- *Plain website, no PWA features:* No push notifications, no home-screen presence — would mean checking manually, defeating the point of a decision-inbox system built for speed-to-action.

---

## 7. `@tabler/icons-react` for the tab bar and UI icons

**Fundamentals:**
In web development there are two common ways to ship icons. An **icon font**: icons are drawn as characters in a custom font file, and you display one by writing `<i class="ti ti-bell">` — the browser renders it like a letter, just from a font where "letter X" happens to be a bell shape. A **component icon library**: each icon is its own small piece of reusable UI code (in React, a **component** — a function that returns markup), imported and used directly as e.g. `<IconBell />`. This is the standard modern pattern in component-based frameworks like React, where **npm** (Node's package manager) is used to pull in third-party code — `npm install <package>` downloads it into `node_modules/` and records it in `package.json` so anyone re-running `npm install` gets the exact same dependencies.

**Why Fortuna needed it:**
The UI mockups (built via a design-preview tool) already used the Tabler icon set through the CSS-class font pattern, since that's how the mockup tool renders icons. But that pattern isn't how a real Vite/React app is typically built — there's no icon font wired in, and adding one means self-hosting font files for something React already handles more directly as components. `@tabler/icons-react` keeps the exact same icon set and visual look as the approved mockups, just delivered as components instead of a font.

**What I rejected, and why:**
- *Self-hosting the Tabler icon font, using CSS classes matching the mockup markup literally:* Would work, but adds a font-loading dependency and doesn't fit how the rest of the app is built (component-based). No real upside for a from-scratch build.
- *A different icon set entirely:* Would break visual continuity with the already-approved mockups for no reason.

---

## 8. Fixed mobile-width shell on all screen sizes, no responsive desktop layout

**Fundamentals:**
**Responsive design** is the practice of writing CSS that adapts a layout to whatever screen size it's viewed on — commonly done with **media queries** (CSS rules that apply only above/below a certain width) or flexible layout systems (CSS Grid, Flexbox) that reflow content automatically. **Mobile-first** is a specific responsive philosophy: design for the smallest screen first, then progressively add layout complexity for wider screens, rather than designing for desktop and cramming it down to mobile as an afterthought. The alternative to responsive design is a **fixed-width layout** — the content stays the same size regardless of viewport, and on a much wider screen than intended, you just see extra blank space on the sides.

**Why Fortuna needed it:**
Fortuna's whole reason for being a PWA (Entry #1) is the phone-alert-to-action loop — a trigger fires, you get notified, you act fast, on your phone. Desktop is real but secondary: something that needs to work when opened, not a primary surface worth its own responsive layout design. A fixed mobile-width shell gets the actual target experience (phone) exactly right and costs nothing extra on desktop beyond unused side margins.

**What I rejected, and why:**
- *Full responsive redesign (sidebar nav on wide screens, multi-column content, table views for Positions/Watchlist on desktop):* Real, structural extra work — different nav pattern, different content-density decisions per breakpoint — for a secondary use case. Rejected for now as effort disproportionate to how Fortuna is actually meant to be used.

**Revisit when:** desktop becomes a genuinely primary way you use Fortuna (e.g. active research/backtesting sessions where more screen real estate would help) rather than an occasional fallback.

---

# Backend

## 9. Timezone-correct epoch handling (Unix timestamps, UTC vs local, IST pinning)

**Fundamentals:**
A **Unix timestamp** (a.k.a. epoch time) is a single number: the count of seconds since 1970-01-01 00:00:00 UTC. It represents an absolute *instant* — the same number everywhere on Earth, with no timezone baked in. A timezone only matters when you convert that instant back into a human calendar date/time. The trap: `datetime.fromtimestamp(ts)` in Python, called *without* a timezone argument, converts using **the machine's local timezone**. So the same epoch number produces a different wall-clock date depending on what server it runs on. The fix is to convert with an *explicit* timezone (`datetime.fromtimestamp(ts, tz=SOME_ZONE)`), never relying on the machine's local setting.

**Why Fortuna needed it:**
Dhan returns each daily candle's timestamp as epoch seconds, stamped at **midnight IST** of that trading day. Midnight IST = 18:30 UTC the *previous* day. So a naive `fromtimestamp()` on a UTC server (like Render, where the app will deploy) would convert that instant to the previous calendar date — every single trading day silently shifted back by one. That date is the anchor for the CPR calc (which prior day's high/low/close), the gap calc, and the VIX percentile. A one-day drift wouldn't crash anything — it would just quietly compute the wrong direction verdict on a live trade. This is the most dangerous kind of bug: silent, correct-looking, and only wrong in production. Fixed with an explicit `IST = timezone(timedelta(hours=5, minutes=30))` and an `epoch_to_ist_date()` helper, then **verified against known real data** (Dhan's close of 24,471.70 had to map to 2026-08-11, the date already referenced in the build log — and it did).

**What I rejected, and why:**
- *Relying on `fromtimestamp()` with no timezone:* Works by luck on the dev laptop (which happens to be set to IST), fails silently on a UTC production server. The definition of a latent bug — rejected precisely because it *looks* fine locally.
- *Storing the raw epoch and converting at read time everywhere:* Pushes the same timezone trap onto every future caller instead of solving it once at the fetch boundary. Converting to a real IST `date` immediately, at the single point data enters the system, is the clean fix.

---

## 10. Idempotency & upserts (safe retries, no duplicates)

**Fundamentals:**
An operation is **idempotent** if doing it multiple times has the same effect as doing it once. Turning a light switch to "on" is idempotent (flip it on twice, still on); pressing a "+1" button is not (each press changes the result). In data systems this matters enormously because networks and jobs fail and get retried — if a retry double-charges a card or double-inserts a row, that's a real bug. An **upsert** ("update or insert") is the database primitive for idempotent writes: given a key, if a row with that key exists, update it; otherwise insert it. Combined with a **primary key** (a column whose value must be unique per row), an upsert keyed on that PK can never create a duplicate no matter how many times it runs.

**Why Fortuna needed it:**
Fortuna's data jobs run on schedules and can be re-run (a crashed sync, a manual re-trigger, an overlapping fetch window). If the daily VIX write or the calendar populate created duplicate rows on every re-run, the history feeding the percentile would be corrupt. Every write in the `market_data`/calendar layer is an upsert on a `trade_date` primary key — so re-running is always safe, and the "skip if already done" guards are purely an *efficiency* optimization (avoid pointless network/DB work), not a correctness one. That separation matters: correctness comes from the PK+upsert, so even if a skip-guard has a bug, data can't be duplicated.

**What I rejected, and why:**
- *Plain `INSERT`:* Would throw a duplicate-key error (or worse, silently duplicate without a PK) on any re-run. Makes every job a one-shot that can't be safely retried — the opposite of what an autonomous system needs.
- *"Check if exists, then insert" in application code:* Two round-trips, and a race condition between the check and the insert (two runs could both check "not there" then both insert). The database's atomic upsert does it correctly in one operation.

---

## 11. Resilient external calls — timeouts, bounded retries, exponential backoff

**Fundamentals:**
Any call to an external service (a broker API, a data feed) can fail or hang — that's not an edge case, it's the normal state of networks. Three standard defenses: a **timeout** (never wait indefinitely — cap how long a single call can block, so one hung request can't freeze the whole system); **bounded retries** (on failure, try again, but a *fixed* number of times — infinite retries just turn one failure into an infinite hang); and **exponential backoff** (wait longer between each retry — 1s, then 2s, then 4s — rather than hammering a struggling service with instant retries, which often makes the overload worse). Together these turn a transient network blip into a self-healing non-event instead of a crash.

**Why Fortuna needed it:**
Fortuna is meant to run autonomously and place real trades — "the Dhan call failed and the whole job died" is not acceptable for something that must be reliable unattended. The `market_data` fetch layer wraps every Dhan call in bounded retry (3 attempts) with exponential backoff, so a momentary network hiccup retries and succeeds instead of aborting the run. An honest gap was flagged and *not* faked: a true per-call timeout needs the `dhanhq` SDK to expose one (unverified), so rather than claim a timeout the code doesn't have, the retry *ceiling* bounds total failure time and the limitation is documented in the module docstring — better to state a known gap than pretend robustness.

**What I rejected, and why:**
- *A single call with no retry:* Any transient failure = whole job fails. Too brittle for unattended operation.
- *Infinite retries:* Turns a persistently-down service into an infinitely-hanging job — worse than failing fast, because nothing alerts and nothing proceeds.
- *Instant retries with no backoff:* Hammering a rate-limited or struggling API with back-to-back retries often trips *more* blocking (we literally hit Dhan's "once every 2 minutes" TOTP limit this way via auto-reload). Backoff is what makes retries help rather than hurt.

---

# Database

## 3. Row Level Security (RLS) on Supabase tables

**Fundamentals:**
A **relational database** (like **Postgres**, the database Supabase is built on) stores data in **tables** — rows and columns, like a spreadsheet, with **SQL** (Structured Query Language) as the language used to read and write that data (`SELECT`, `INSERT`, `UPDATE`, `DELETE`). In a typical web app, the frontend never talks to the database directly — a backend server sits in between, receiving requests, deciding what a given user is allowed to see, then querying the database on their behalf. That backend-side check is called **authorization** (distinct from **authentication**, which just confirms *who* someone is — authorization decides *what they're allowed to do*).

**Row Level Security (RLS)** is a Postgres feature that moves authorization *into the database itself*: you write a policy (e.g. "a row is only visible if its `user_id` column matches the currently authenticated user's ID") and Postgres enforces it on every single query, automatically, no matter what asked for the data. This matters specifically for apps like Supabase's, where the frontend *does* talk to the database directly from the browser using a public API key — there's no backend server as a gatekeeper, so the database has to do that job itself.

**Why Fortuna needed it:**
The React PWA calls Supabase directly from the browser — there's no backend server sitting in between to gatekeep requests. That means the public "anon key" is visible in the app's JS bundle by design (normal for Supabase apps). Without RLS, that key alone would be enough for anyone to query tables like `fortuna_positions` directly. RLS makes the database itself the security boundary: even if the key leaks, a request can only touch rows belonging to the authenticated user's own `auth.uid()`.

**What I rejected, and why:**
- *No RLS, rely on obscurity (key not being found):* Security through "no one will find it" isn't real security, and this is trading position data, not a public blog. Rejected outright.
- *"Automatically expose new tables" left on:* Would grant API access to every new table by default. Turned off — new tables stay unreachable until a policy is explicitly written, so nothing is exposed by accident.
- *Building a backend API layer to gatekeep instead of RLS:* A legitimate alternative pattern — but adds a whole service to build/host/maintain for a single-user app. RLS gets the same guarantee at the database layer for free, given already being on Supabase. Revisit only if Fortuna's needs get complex enough to justify a real backend (e.g. the signal engine itself, which likely will need one anyway).

---

## 6. Storage vs compute — what actually lives in Supabase Postgres (open question)

**Fundamentals:**
Not all data belongs in a relational database. Postgres (and SQL databases generally) are optimized for structured, relatively small, frequently-updated records with relationships between them — a user, their positions, their watchlist. They're a poor fit for large volumes of **time-series data** (e.g. years of minute-by-minute stock prices for hundreds of symbols) — that kind of data is typically stored instead in flat files (**Parquet**, a compressed columnar file format built for exactly this: fast to read large chunks of, much smaller on disk than CSV) or a dedicated time-series database. Separately, **compute** (actually calculating something, like a technical indicator from price history) doesn't need a database at all — it can happen entirely in memory, in a programming language like Python, using data pulled fresh from an API.

**The confusion, as it actually happened:**
The question came up: does going Cloud-only on Supabase (no local Docker, see Entry #4) limit how much stock/indicator data Fortuna can work with? The honest answer: that decision barely matters here, because VectorBT/TA-Lib/pandas-ta (Fortuna's planned indicator/backtesting tools) don't operate through Postgres at all — they pull historical price data from Dhan's API into pandas DataFrames and compute indicators in-memory, in Python. That's a compute task, not a database task, and identical whether Supabase is local or cloud.

**What actually matters instead:**
Whether Supabase Postgres is used to store bulk historical market data, or only the *outputs* of processing it:
- **Outputs only** (which stocks passed which gate, current positions, watchlist state, signal history) — small, relational, fits comfortably on Supabase's free tier (500MB). Fine fit, no scale concern.
- **Bulk historical OHLCV for a full stock universe, years deep** — a fundamentally different volume, and a relational row-store isn't the right tool for it regardless of local or cloud. That pattern wants flat files (Parquet) or a time-series store instead.

**Status:** Not yet decided which pattern Fortuna uses. This directly shapes the backend/signal-engine architecture — worth deciding deliberately before that gets built, rather than defaulting into "put everything in Supabase" by momentum. Tracked as open in `Fortuna-Build-Log.md`.

---

## 12. Source of truth, and using the authoritative source for integrity checks

**Fundamentals:**
When the same fact is available from multiple places, the **source of truth** is the one authoritative origin you treat as correct when they disagree — everything else is a copy that can be stale or wrong. A recurring engineering mistake is validating data against a *derived* or *republished* copy instead of the origin. Two related ideas: an **idempotency/integrity check** verifies stored data actually matches what it should be (not just "did the write return success", but "is the data really all there and correct"); and **data provenance** — knowing *where* each piece of data came from — is what lets you trust it. For any autonomous system, "the write said OK" is not the same as "the data is correct and complete" — those must be checked separately.

**Why Fortuna needed it:**
Two concrete cases hit this on the same day. First, NSE trading-holiday dates: the republished finance sites (Groww, ClearTax, etc.) openly *contradicted each other* — Holi was listed as both March 3 and March 14 across sources. Hardcoding from any of them would have silently gated live trades on a wrong calendar. Only NSE's own `holiday-master` API is authoritative, so that became the single source and the republished lists were discarded entirely. Second, for verifying the stored index history has no gaps: the cleanest check isn't "does our data match some external calendar" but "does our stored set of dates exactly equal the set of dates **Dhan itself returns**" — because Dhan's own feed is the authoritative source for what trading days *its* data covers. Checking data against the same source that produced it is a provably tight integrity check, with no third-party calendar to drift out of sync.

**What I rejected, and why:**
- *Hardcoding the holiday list from republished finance blogs:* They conflict with each other and go stale — fatal for something gating real trades. Rejected the moment the date contradictions showed up.
- *Building an independent NSE trading calendar purely to validate Dhan's data gaps:* Over-engineered — it introduces a *second* source that can disagree with Dhan, when the tightest check is simply comparing Dhan's stored dates against Dhan's returned dates. The calendar earns its place for the *forward-looking* "is today a holiday, skip the fetch" job, not for backward integrity.
- *Trusting "write returned success" as proof the data is correct:* An upsert reporting OK doesn't prove every expected row is present and contiguous. For autonomous trading, integrity is verified separately (post-write date/count checks), not assumed from a success response.

**Design note — layered gate for "no loopholes":** because Fortuna trades unattended, the guiding principle became belt-and-suspenders: the NSE calendar is only a sync-time *optimization*, and the real pre-trade gate is a **live market-status check** against the broker. A missing/wrong calendar can then never *cause* a bad trade — worst case it wastes a fetch — because the live check is the actual authority. Failure mode is bounded to "fail safe" (don't trade on absent/stale data) rather than "fail dangerous" (trade on a wrong assumption).

**Real-world refinement — only validate what your reference actually covers.** The first index backfill (pulling ~1 year of history) flagged 5 "missing" trading days. They turned out to be real 2025 holidays — the *data* was correct; the *validator* (a 2026-only calendar) just couldn't speak to 2025, because NSE's API only serves the current year. The wrong fix would be to force the check to pass by sourcing a whole extra year of holidays (real work, new dependency) purely to validate data already known to be correct. The right fix: **clamp the integrity check to the range your reference actually covers** — validate 2026-onward (where the calendar is authoritative), store-and-use the 2025 data without calendar-verifying it. Lesson: an integrity check should only assert over the range its oracle can vouch for; beyond that it should stay silent, not manufacture false positives. A check that flags correct data as broken is worse than no check — it trains you to ignore it. (Related discovery the same day: GIFT Nifty trades on the IFSC/international calendar, not the domestic NSE one — so it legitimately has *more* trading days than Nifty/VIX, and can't be validated against the domestic calendar at all. Same principle: don't validate against the wrong reference.)

---

# Security

## 2. Auth strategy — Google OAuth (primary) + magic link (fallback)

**Fundamentals:**
**Authentication** answers "who is this?" — as opposed to authorization (Entry #3), which answers "what are they allowed to do?" The traditional approach is a password: the app stores a (hashed, never plaintext) password and compares it at login. This has a well-known weakness — people reuse passwords across sites, and any breach of *any* site they use puts every other account at risk.

**OAuth** is a different pattern: **delegated authentication**. Instead of your app managing its own password, the user proves their identity to a third party they already trust (Google, in this case) and that third party vouches for them back to your app, without your app ever seeing their Google password. This is the "Continue with Google" button pattern seen everywhere. **Magic link** (a.k.a. **passwordless email login**) is a different no-password approach: the app emails a unique, single-use, time-limited link; clicking it proves you control that email address, which the app accepts as sufficient identity — no password exists anywhere to leak.

Both of these rely on the concept of a **session** — once identity is confirmed, the server issues a token (Supabase uses a **JWT**, JSON Web Token — a signed piece of data proving "this is user X, issued at time Y") that the browser stores and sends with future requests, so the user doesn't have to re-authenticate on every single action.

**Why Fortuna needed it:**
No password means no password to leak, phish, or brute-force. But it also needed to be fast/frictionless daily, not security theater that's annoying to use. Google OAuth is mature, battle-tested infrastructure that doesn't need to be trusted to build correctly from scratch. Magic link exists as a fallback with zero dependency on Google, in case that account or service has an issue — never rely on a single point of failure for the only way into a system holding trading data.

**What I rejected, and why:**
- *Native Supabase Passkey/WebAuthn (fingerprint login):* Genuinely the ideal UX (Face ID/Touch ID, phishing-resistant by design) — but Supabase's implementation is currently beta/experimental, with open bugs like "browser does not support WebAuthn" in their own GitHub discussions. If this were the *only* login method and it broke, that's a lockout from your own trading data with no way in. Revisiting once it's GA — not rejected forever, just not yet.
- *Traditional email + password:* Passwords are the single most-attacked credential type (reuse, breaches, phishing). Skipped entirely rather than managing that risk.
- *SMS OTP:* Real per-message cost, added infra (Twilio/MSG91), and a phone-number dependency — email magic link covers the "simple fallback" need without the recurring cost.

---

## 5. Multi-device PIN — server-verified, not a local app-lock

**Fundamentals:**
There are two fundamentally different ways to build "unlock with a PIN." A **local app-lock**: the PIN is checked entirely on-device, client-side, with no network call — it's just gating access to a session that's *already* authenticated and sitting on that phone/laptop. This is fast and works offline, but it's inherently tied to one specific device — a phone that's never logged in before has no local session to unlock. A **server-verified credential**: the PIN itself is a real login method, like a password — stored **hashed** (run through a one-way cryptographic function like bcrypt, so even if the database leaks, the actual PIN can't be recovered from what's stored) and checked against the server on every login attempt, working identically from any device since nothing device-specific is involved.

**Why Fortuna needed it:**
The initial ask was a PIN that's fast to unlock with, but that ask also required the *same* PIN to work identically from both phone and laptop — including a device never logged into before. A local app-lock can't do that by definition: it only ever unlocks a session that already exists on that device. Since the requirement was genuinely cross-device, the PIN has to be a real, independently-checkable credential Supabase can verify.

**What I rejected, and why:**
- *Local on-device PIN unlock:* First instinct — feels lighter, no server round-trip, common in banking/trading apps for quick re-entry. Rejected once the actual requirement (any device, not just "my usual device") was made explicit, since a local gate structurally can't satisfy that.
- *SMS OTP as the "fast" option instead of a PIN:* Already rejected in Entry #2 for the same cost/deliverability reasons, and it doesn't solve for "fast unlock" anyway since it still needs network + waiting for a text every time.

**What I chose instead:**
A PIN checked server-side against Supabase, the same way a password would be (hashed at rest, verified via a dedicated endpoint/RPC rather than Supabase's built-in OAuth/magic-link providers, since PIN-as-credential isn't a native Supabase auth method). This makes it a real, portable login path — works the same from a brand new device as from a familiar one — at the cost of a network round-trip a pure local unlock wouldn't need.

**Status:** Decision made, not yet built.

---

# Infrastructure

## 4. Supabase Cloud-only, no local Docker stack

**Fundamentals:**
**Docker** packages an application together with everything it needs to run (system libraries, exact versions) into a **container** — a lightweight, isolated environment that runs the same way on any machine, avoiding "works on my machine" problems. Supabase offers a full local stack (`supabase start`) that runs Postgres, Auth, and Storage as Docker containers on your own machine — a local mirror of the cloud project, useful for offline development or testing risky schema changes without touching production. The alternative is developing directly against the real **cloud-hosted** project, using the CLI only to push schema changes and functions up to it — one source of truth, no local database process at all.

**Why Fortuna needed it (cloud-only):**
Running the local stack requires Docker Desktop, which on this machine needed BIOS-level virtualization, WSL2, and Virtual Machine Platform all correctly configured first — real setup cost before writing a single line of app code. At this stage, that cost buys a feature (an offline/local copy of the database) that isn't actually needed — no team to isolate from, no risk of touching production data by accident with a single user, and no migration volume high enough to justify the safety net.

**What I rejected, and why:**
- *Local Docker-based Supabase stack (`supabase start`):* Tried first, then abandoned after hitting the Docker/BIOS/WSL2 configuration chain. Docker Desktop was uninstalled entirely rather than pushed through — not worth the setup cost for a single-user project with no local-testing requirement yet.
- *Half-measure (Docker installed but stack unused):* No reason to keep Docker Desktop installed if it's not being used — removed cleanly rather than left as dead weight.

**What I chose instead:**
Develop directly against the real Supabase Cloud project. The Supabase CLI (`supabase link`, `supabase login`) connects the terminal to the cloud project for pushing schema migrations and edge functions — no local database process runs at all. Browsing tables happens in the Supabase web dashboard instead of a local Studio instance.

**Revisit when:** schema/migration iteration gets heavy enough that testing directly against production-linked Cloud becomes risky or slow.

---

<!-- Next entries append below, filed under the correct section, in the order they're decided. -->

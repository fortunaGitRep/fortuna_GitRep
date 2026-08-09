# Fortuna — Environment Setup

**What this doc is:** A start-from-nothing guide to setting up everything needed to build Fortuna on a Windows machine — editor, languages, tooling, and cloud service connections (Supabase, Google Cloud) — going straight to **Supabase Cloud** (no local Docker-based Supabase stack). Follow it top to bottom on a brand new laptop and you'll end up exactly where the current setup stands.

**This doc stays mechanical and stable** — the *how*, not the *why*, and not ongoing feature work. Two companion docs:
- `Fortuna-Learning-Concepts.md` — the *why* behind each architectural decision, rejected alternatives, reasoning to revisit later.
- `Fortuna-Build-Log.md` — the ongoing, session-by-session record of feature work and open items. This is where "what's left to do" lives now, not here.

Repo root used throughout: `D:\Takara\Fortuna\_Repository`

---

## Step 1 — Install VS Code

**What it is:** A code editor — the program you write and run all your code in.

**Why Fortuna needs it:** Every piece of Fortuna (FastAPI backend, React frontend, Supabase config) gets written and tested here before it ships.

Download from code.visualstudio.com and run the installer. Confirm:
```
code --version
```

---

## Step 2 — Install Python

**What it is:** A programming language runtime.

**Why Fortuna needs it:** Runs the FastAPI backend, and all the quant/backtesting work — VectorBT, TA-Lib, pandas-ta-classic.

Download the installer from python.org (version 3.11). **During install, tick "Add python.exe to PATH."**

Verify:
```
python --version
```

**If that fails** with a message about installing from the Microsoft Store: Windows ships fake placeholder programs for `python.exe`/`python3.exe`. Fix: **Settings → Apps → Advanced app settings → App execution aliases** — turn OFF both toggles. Open a **new** terminal window afterward (PATH changes never apply to an already-open terminal).

**Note:** Windows Python doesn't ship a separate `python3.exe` — always use plain `python` on Windows.

---

## Step 3 — Upgrade pip

```
python -m pip install --upgrade pip
```
**Why:** A current pip resolves dependency conflicts better — matters for the next install.

---

## Step 4 — Install Fortuna's core Python packages

```
python -m pip install vectorbt
python -m pip install TA-Lib
```
- **VectorBT** — backtesting engine, tests strategies against historical data fast (NumPy/Numba-based).
- **TA-Lib** — the technical indicator library behind VWAP, ADX, Supertrend, Bollinger Bands, etc.

---

## Step 5 — Install VS Code extensions

```
code --install-extension ms-python.python
code --install-extension ms-python.vscode-pylance
code --install-extension dbaeumer.vscode-eslint
code --install-extension esbenp.prettier-vscode
code --install-extension rangav.vscode-thunder-client
```

| Extension | What it does | Why Fortuna needs it |
|---|---|---|
| Python | Base Python support — run/debug code | Editing/debugging the FastAPI backend |
| Pylance | Smart autocomplete + type-checking | Catches bugs before you run the code |
| ESLint | Flags JS/TS code quality issues | Keeps React frontend code clean |
| Prettier | Auto-formats code consistently | No manual formatting debates with yourself |
| Thunder Client | Sends test API requests from inside VS Code | Test FastAPI endpoints without Postman |

**Note — no Supabase extension:** There is an official "Supabase" VS Code extension, but it's built specifically to integrate a **local, Docker-based** Supabase instance into the editor. Since Fortuna connects straight to Supabase Cloud (see Step 10), that extension doesn't apply here and isn't installed. Browsing tables/schema happens in the Supabase Dashboard (in your browser) instead — see Step 10.

VS Code will likely pull in a few supporting extensions automatically — `debugpy` and `vscode-python-envs` (Pylance's plumbing), a **Jupyter** suite (worth keeping — good for running VectorBT backtests interactively), and `rainbow-csv` (colors CSV columns, handy for raw NSE data).

---

## Step 6 — Connect Claude in VS Code

**Status: done and confirmed working.**

Install the official **"Claude Code"** extension by Anthropic (extension ID `anthropic.claude-code`) from the marketplace — watch for unofficial lookalikes with similar names.

1. `Ctrl+Shift+X` → search "Claude Code" → confirm publisher is **Anthropic** → Install.
2. Open your Fortuna repo folder in VS Code.
3. In the **Claude Code** panel (left sidebar), click **+ New session**, keep **Local** selected.
4. First run triggers a browser OAuth sign-in — approve access with your Claude Pro account. (If the authorization page loads as garbled/corrupted text instead of the sign-in screen, this is typically HTTPS-scanning interference from network/security software — retrying on a different network, e.g. a mobile hotspot, isolates and usually resolves it.)
5. Verified working by asking it to read the actual repo structure — it correctly listed real files across `frontend/`, `backend/`, and `supabase/`.

**Why this over GitHub Copilot:** Copilot starts with zero knowledge of Fortuna's architecture or your rule book. Claude Code can read and reason about the actual repo directly.

**Cost:** Draws from your existing Claude Pro subscription — no separate bill.

---

## Step 7 — Install Scoop

**What it is:** A package manager for Windows — like `pip`, but for command-line tools instead of code libraries.

**Why it matters:** Installs tools with PATH wired up automatically, avoiding the manual PATH mess from Step 2.

```
irm get.scoop.sh | iex
```

---

## Step 8 — Install Git

**What it is:** Version control — tracks every change to your code over time.

```
scoop install git
```

Set your identity (required before your first commit):
```
git config --global user.name "Your Name"
git config --global user.email "your@email.com"
```
Use the same email as your GitHub account (Step 9), so commits show as verified once pushed.

---

## Step 9 — Create a GitHub account

**What it is:** A cloud host for git repositories.

**Why Fortuna needs it:** Backup of your code off your laptop, and where Render pulls from to deploy.

Use the same email as `git config --global user.email` above.

---

## Step 10 — Install Node.js

**What it is:** A JavaScript runtime — runs the tools that build and serve the React frontend.

```
scoop install nodejs-lts
```
**Why LTS:** Most stable release line, matches what Render and most hosting expects.

Verify:
```
node --version
npm --version
```

---

## Step 11 — Create the repo folder structure

```
mkdir D:\Takara\Fortuna\_Repository
cd D:\Takara\Fortuna\_Repository
mkdir frontend backend
```
**Why separate `frontend/` and `backend/`:** Different runtimes (Node vs Python), deployed as separate services on Render.

---

## Step 12 — Initialize git and make the first commit

```
cd D:\Takara\Fortuna\_Repository
git init
git branch -m main
```
**Why `main`:** Modern convention, matches GitHub's default — avoids friction when pushing later.

Add a `.gitignore` **before** anything else — it tells git to never track `.env` files (Supabase keys, Dhan API keys). Committing secrets is hard to fully undo later.

```
git add .gitignore
git commit -m "Initial repo setup: gitignore"
```

---

## Step 13 — Install the Supabase CLI

**What it is:** A command-line tool for Supabase — separate from the project you create in the web dashboard.

**Why Fortuna needs it (cloud-only workflow):** Pushes schema migrations and deploys edge functions to your real cloud project directly from the terminal — no local database, no Docker involved.

```
scoop bucket add supabase https://github.com/supabase/scoop-bucket.git
scoop install supabase
```
Verify:
```
supabase --version
```

---

## Step 14 — Connect the CLI to Supabase Cloud

```
supabase login
```
Opens a browser to authorize the CLI with your Supabase account.

```
supabase link --project-ref <your-project-ref>
```
Find your project ref in the Supabase dashboard — it's the subdomain of your project URL, e.g. for `https://bymauhxwfzlzwlvtpxzd.supabase.co`, the ref is `bymauhxwfzlzwlvtpxzd`.

Verify the link:
```
supabase projects list
```
Should show your Fortuna project marked `LINKED`.

**Browsing tables/schema:** Use the Supabase Dashboard in your browser (supabase.com/dashboard → Fortuna project) — this is the visual tool, no VS Code extension needed.

**A note on what we deliberately skipped:** `supabase start` (running a full local Postgres/Auth/Storage stack via Docker) was tried and then abandoned. It required Docker Desktop, which needed BIOS virtualization + WSL2 + Virtual Machine Platform all correctly configured — real setup cost for a feature (local testing DB) that isn't needed while working directly against Supabase Cloud. **Docker Desktop has been uninstalled and is not part of this setup.** If local testing becomes genuinely necessary later (e.g. heavy schema/migration iteration), it can be revisited then.

---

## Step 15 — Scaffold the React frontend with Vite

**What Vite is:** A frontend build tool. "Scaffolding" generates the base React project skeleton — `package.json`, `index.html`, `src/`, dev server config.

If `frontend/` is empty:
```
cd D:\Takara\Fortuna\_Repository
npm create vite@latest frontend -- --template react-ts
```

If `frontend/` already has files in it (e.g. hand-written auth files), scaffold into a throwaway folder first, then merge:
```
npm create vite@latest frontend-temp -- --template react-ts
```
Copy everything Vite generated into `frontend/`, delete `frontend-temp/`. Check `package.json`'s `"name"` field says `"frontend"`, not `"frontend-temp"`.

**Known leftover from this step:** the browser tab title still reads "frontend-temp" — this comes from `<title>` in `frontend/index.html`, copied over from the throwaway scaffold folder and never renamed. Cosmetic only; fix is a one-line edit to `<title>frontend-temp</title>` → `<title>Fortuna</title>`. Not yet applied as of this doc's last update — do it next session.

Install and run:
```
cd frontend
npm install
npm run dev
```
Confirm it serves at `http://localhost:5173/`.

**Note:** `npm run dev` is only needed while actively working on the frontend. Stop it with `Ctrl+C` when done for the day — nothing is lost, no external service depends on it staying up.

**Testing from your phone on the same wifi:** `npm run dev -- --host` exposes the dev server on your local network (e.g. `http://192.168.x.x:5173`). Note: if auth is involved, that local IP needs to be added to Supabase's Redirect URLs for OAuth to work from the phone this way — see Step 20. This is a quick local test only, not how real day-to-day mobile access will work (see Step 20's note on real deployment).

---

## Step 16 — Connecting your app code to Supabase

This is the actual "connection" that matters for Fortuna functioning — not a VS Code integration, but your backend code talking to Supabase Cloud directly.

```
pip install supabase
```
In FastAPI backend code:
```python
from supabase import create_client
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
```
`SUPABASE_URL` and `SUPABASE_KEY` come from the dashboard (Settings → API), stored in a `.env` file — never hardcoded, never committed (already protected by `.gitignore` from Step 12).

---

## Step 17 — Push to GitHub

GitHub repo created: `https://github.com/fortunaGitRep/fortuna_GitRep`

```
git add .
git commit -m "Add frontend scaffold, supabase config, backend folder"
git remote add origin https://github.com/fortunaGitRep/fortuna_GitRep.git
git push -u origin main
```

**Why `-u`:** Sets `main` to track `origin/main`, so every future push/pull is just `git push` / `git pull` with no extra flags needed.

**Auth note:** GitHub no longer accepts your account password for CLI pushes — it uses a browser-based OAuth prompt instead (same pattern as Claude Code's sign-in). If a plain password prompt appears in the terminal instead, that means a Personal Access Token is needed — a separate one-time setup.

---

## Step 18 — Scaffold the FastAPI backend

**What "scaffolding" means here:** Same idea as the Vite frontend scaffold (Step 15) — generating the minimal skeleton that makes `backend/` a real, runnable application instead of an empty folder: a starter server file, a dependency list, and a config template.

**What FastAPI does, concretely:** It's the framework that lets Python code respond to web requests. When the React frontend eventually asks "give me my Positions tab data," FastAPI is what receives that request, runs the Python logic, and sends back JSON.

Create these three files inside `backend/`:

**`main.py`** — the actual server, with a health check and CORS enabled so the frontend (`localhost:5173`) can call it during local development:
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Fortuna API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"status": "Fortuna API is running"}

@app.get("/health")
def health():
    return {"status": "ok"}
```

**`requirements.txt`** — what to install:
```
fastapi
uvicorn[standard]
supabase
python-dotenv
```

**`.env.example`** — template only, no real secrets (real `.env` is git-ignored):
```
SUPABASE_URL=
SUPABASE_KEY=
```

Install and run:
```
cd D:\Takara\Fortuna\_Repository\backend
python -m pip install -r requirements.txt
uvicorn main:app --reload
```

**What `uvicorn main:app --reload` means:** `uvicorn` is the actual server program that runs a FastAPI app (FastAPI itself is just the framework/code, not a server). `main:app` tells it to look inside `main.py` for the variable named `app`. `--reload` auto-restarts the server whenever you save a code change — same live-reload idea as Vite's dev server, just for the backend.

Confirm it's working: open `http://127.0.0.1:8000` in a browser — should show `{"status": "Fortuna API is running"}`.

**Running both sides at once for local dev:** frontend and backend run as two separate processes in two separate terminals — `npm run dev` (Step 15) in one, `uvicorn main:app --reload` in another. Both need to be running simultaneously for the full app to work locally.

---

## Step 19 — Frontend dependencies for auth

```
cd D:\Takara\Fortuna\_Repository\frontend
npm install @supabase/supabase-js react-router-dom
```
- **`@supabase/supabase-js`** — the client library the frontend uses to talk to Supabase directly from the browser (auth, and later, database queries).
- **`react-router-dom`** — handles in-app navigation/routes (`/login`, `/auth/callback`, `/`, and eventually the five tab routes) without full page reloads.

---

## Step 20 — Wire up Google OAuth + magic link auth

**Status: done and confirmed working end-to-end (Google OAuth and magic link both tested live).**

### 20.1 — Frontend env file

Create `frontend\.env.local` (git-ignored, never committed):
```
VITE_SUPABASE_URL=https://<your-project-ref>.supabase.co
VITE_SUPABASE_ANON_KEY=<your-anon-key>
```
**Why the `VITE_` prefix is mandatory:** Vite only exposes env variables to browser code if they start with `VITE_` — anything else stays server-side-only and `import.meta.env` won't see it.

**Windows gotcha hit during setup:** creating a dotfile like `.env.local` via Explorer's "New → Text Document" can silently save it as `.env.local.txt` (Windows hides known extensions by default). Verify with:
```
dir /a .env*
```
If it shows the `.txt` suffix, fix with:
```
ren ".env.local.txt" ".env.local"
```

**Also learned:** if `npm run dev` is already running when you create/edit `.env.local`, Vite won't pick up the new values — restart the dev server (`Ctrl+C`, then `npm run dev` again) after any env file change.

### 20.2 — `src/supabaseClient.ts`

```typescript
import { createClient } from '@supabase/supabase-js'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY

if (!supabaseUrl || !supabaseAnonKey) {
  throw new Error('Missing Supabase environment variables — check frontend/.env.local')
}

export const supabase = createClient(supabaseUrl, supabaseAnonKey)
```

This is the single initialized client the whole app imports from.

### 20.3 — `LoginPage.tsx` and `AuthCallback.tsx` location

Both files must live in `src/` (same folder as `supabaseClient.ts`) since they import it via a relative path (`./supabaseClient`). They were originally hand-written sitting in the `frontend/` root — moved into `src/` as part of this step:
```
move LoginPage.tsx src\
move AuthCallback.tsx src\
```

`LoginPage.tsx` — Google OAuth as the primary CTA (brand teal `#083F41`), magic link as a fallback. *Why this combination and not passkeys or SMS OTP — see `Fortuna-Learning-Concepts.md` §2.*

`AuthCallback.tsx` — handles the redirect after both Google and magic-link sign-in; listens for the Supabase session to resolve, then routes into the app root.

### 20.4 — Routing (`App.tsx`)

Replaced Vite's default demo content in `frontend/src/App.tsx` with:
- `BrowserRouter` wrapping the app (kept inside `App.tsx` rather than `main.tsx`, which was left untouched)
- A session check on load (`supabase.auth.getSession()`) plus a live listener (`onAuthStateChange`) so login/logout state updates the UI automatically
- Routes:
  - `/login` → `LoginPage` (redirects to `/` if already logged in)
  - `/auth/callback` → `AuthCallback`
  - `/` → a bare placeholder ("Logged in" + email + Log out button) if authenticated, redirects to `/login` if not

This placeholder root page is intentionally throwaway — it exists only to prove the auth flow works end-to-end. It gets replaced by the real five-tab shell (Inbox / Buy / Exit / Positions / Watchlist) in a future step, using the existing HTML mockups (`fortuna_cash_*_correct_teal.html` etc.) as the visual reference.

`App.css` is no longer imported by the new `App.tsx` but was left in place, unused, rather than deleted.

### 20.5 — Google Cloud OAuth client

Google Cloud project created: `Fortuna Login Auth` (console.cloud.google.com).

1. Went through the **Google Auth Platform** consent screen setup (Google's current flow, previously called "OAuth consent screen"):
   - App name: `Fortuna`
   - Audience: **External** — the only option available on a personal (non-Workspace) Google account; this only controls which Google accounts can appear on the consent screen, not who gets access to the app itself. See note below on access control.
   - Support/contact email: your email
2. **Clients → + Create Client**:
   - Application type: **Web application** (correct even for what will eventually be a PWA — the OAuth redirect flow itself is browser-based regardless of device)
   - Name: `Fortuna Web client for LoginAuth`
   - Authorized redirect URI: `https://<your-project-ref>.supabase.co/auth/v1/callback`
3. Client ID + Client Secret generated — copied into Supabase (next step).

**Expected warning, not a bug:** because this app isn't submitted for Google's verification review (unnecessary for a personal single-user app), Google shows an interstitial "Google hasn't verified this app" screen during sign-in. Click **Advanced → Go to Fortuna (unsafe)** to proceed. This is normal and doesn't indicate a misconfiguration.

**Access control note:** any Google account can currently complete sign-in and get a valid session — an allowlist restricting this to your own email is tracked as open work in `Fortuna-Build-Log.md`, not done yet.

### 20.6 — Supabase Dashboard config

**Authentication → Sign In / Providers → Google:**
- Toggled on
- Client ID + Client Secret from 20.5 pasted in

**Authentication → URL Configuration:**
- Site URL: `http://localhost:5173`
- Redirect URLs: `http://localhost:5173/auth/callback`

(Note: the left-sidebar item is labeled **Sign In / Providers**, not "Providers" — this changed from what earlier notes assumed.)

### 20.7 — Testing

Both flows tested live and confirmed working:
- **Google OAuth:** Continue with Google → account picker → "unverified app" warning → Advanced → Go to Fortuna (unsafe) → redirected through `/auth/callback` → landed on `/` showing the real logged-in email and a working Log out button.
- **Magic link:** "Use email instead" → link received in inbox from `Supabase Auth <noreply@mail.app.supabase.io>` → clicking it signs in the same way.

Session default: 1-hour access token, auto-refreshed indefinitely via refresh token, no forced re-login. Open decisions (allowlist, session tightening, multi-device PIN, email branding) are tracked in `Fortuna-Build-Log.md`, not repeated here.

---

## Quick command glossary

| Command | What it does |
|---|---|
| `python --version` | Shows which Python is active |
| `pip install X` | Installs a Python package |
| `npm install` | Installs all JS packages listed in `package.json` |
| `npm run dev` | Starts the Vite dev server (live-reloading frontend) |
| `npm run dev -- --host` | Same, but exposed on your local network (e.g. for phone testing) |
| `git init` | Turns a folder into a git repository |
| `git add <file>` | Stages a file to be committed |
| `git commit -m "message"` | Saves a snapshot of staged changes |
| `git branch` | Shows which branch you're on |
| `git status` | Shows staged/unstaged/untracked files — always check before committing |
| `supabase login` | Authorizes the CLI with your Supabase account |
| `supabase link --project-ref X` | Connects the CLI to your cloud project |
| `supabase projects list` | Shows linked projects |
| `uvicorn main:app --reload` | Starts the FastAPI dev server with live-reload |
| `scoop install X` | Installs a command-line tool on Windows |
| `code .` | Opens the current folder in VS Code |
| `dir /a .env*` | Shows real filenames of dotfiles (catches hidden `.txt` extensions on Windows) |

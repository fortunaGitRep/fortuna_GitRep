# Fortuna Login — Setup Checklist

Two files: `LoginPage.tsx` (screen) and `AuthCallback.tsx` (handles the redirect after login).
Both assume you already have a `supabaseClient.ts` exporting `supabase` — adjust the import path if yours lives elsewhere.

## 0. Supabase project creation — security settings
When creating the project (Project Settings shown at setup time), set:
- **Enable Data API:** ON — required for supabase-js to talk to the DB.
- **Automatically expose new tables:** OFF — new tables stay unreachable via API until access is explicitly granted. Supabase's own recommended default.
- **Enable automatic RLS:** ON — auto-enables Row Level Security on every new table, so nothing is accidentally open.

**Practical consequence:** tables like `fortuna_positions` will be locked down by default. Before the app can read/write them, you'll need an RLS policy — e.g. "user can only see rows where `user_id = auth.uid()`" — otherwise queries will just return empty, not an error. Expected behavior for single-user-with-auth, not a bug.

## 1. Google Cloud Console
1. Create (or reuse) a project at console.cloud.google.com
2. APIs & Services → Credentials → Create OAuth Client ID → Web application
3. Authorized redirect URI: `https://<your-supabase-project-ref>.supabase.co/auth/v1/callback`
4. Copy the **Client ID** and **Client Secret**

## 2. Supabase Dashboard
1. Authentication → Providers → Google → toggle on
2. Paste Client ID + Client Secret from step 1
3. Authentication → URL Configuration:
   - Site URL: your production domain (e.g. `https://fortuna.yourdomain.com`)
   - Redirect URLs: add `http://localhost:5173/auth/callback` (dev) and your prod equivalent
4. Magic link is on by default under Authentication → Providers → Email — no extra setup needed.

## 3. Routing
Add a route for `/auth/callback` pointing at `AuthCallback.tsx` — this is where both Google and magic-link redirects land.

## 4. Local testing
- `npm run dev`, hit the login page, click "Continue with Google" — should redirect out to Google, back to `/auth/callback`, then into the app root.
- Test magic link by using "Use email instead" — check inbox, click link, same callback path fires.

## Not included (deliberately)
- Native Supabase passkey/WebAuthn — still beta, skipping per the earlier lockout-risk discussion. Revisit once it's GA.
- Session length/expiry config — Supabase defaults to a rolling refresh token; flag if you want this tightened given trading data is behind it.

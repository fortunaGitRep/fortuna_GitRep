import { useState } from "react";
import { supabase } from "./supabaseClient"; // adjust path to your existing client

/**
 * Fortuna — Login
 *
 * Design system sync (per Fortuna UI spec):
 * - Brand color: #083F41 (exact, pixel-sampled — do not approximate)
 * - Philosophy: zero noise, one actionable thing at a time
 * - This screen: logo + one primary CTA. Magic link is a fallback,
 *   kept visually subordinate (small text link, not a second button).
 *
 * Auth flow:
 * - Primary: Google OAuth (mature, no lockout risk from beta features)
 * - Fallback: Email magic link (zero-cost, no Google dependency)
 * - Deliberately NOT using Supabase native passkeys yet — still beta,
 *   see conversation notes on WebAuthn reliability.
 */

const BRAND = "#083F41";

export default function LoginPage() {
  const [showMagicLink, setShowMagicLink] = useState(false);
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [errorMsg, setErrorMsg] = useState("");

  async function handleGoogleLogin() {
    setStatus("sending");
    setErrorMsg("");
    const { error } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: {
        redirectTo: `${window.location.origin}/auth/callback`,
      },
    });
    if (error) {
      setStatus("error");
      setErrorMsg("Couldn't reach Google. Check connection and try again.");
    }
    // On success, browser redirects away — no further state needed here.
  }

  async function handleMagicLink(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim()) return;
    setStatus("sending");
    setErrorMsg("");
    const { error } = await supabase.auth.signInWithOtp({
      email: email.trim(),
      options: {
        emailRedirectTo: `${window.location.origin}/auth/callback`,
      },
    });
    if (error) {
      setStatus("error");
      setErrorMsg("Couldn't send the link. Check the address and try again.");
    } else {
      setStatus("sent");
    }
  }

  return (
    <div
      style={{
        width: "100%",
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        background: BRAND,
        padding: "24px",
        boxSizing: "border-box",
      }}
    >
      {/* Logo mark — wordmark only, no decoration */}
      <div
        style={{
          fontFamily: "Georgia, 'Times New Roman', serif",
          fontSize: "32px",
          letterSpacing: "0.04em",
          color: "#F4F1EA",
          marginBottom: "64px",
          fontWeight: 400,
        }}
      >
        Fortuna
      </div>

      {/* Primary CTA */}
      {status !== "sent" && (
        <button
          onClick={handleGoogleLogin}
          disabled={status === "sending"}
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: "10px",
            width: "100%",
            maxWidth: "320px",
            padding: "14px 20px",
            background: "#F4F1EA",
            color: BRAND,
            border: "none",
            borderRadius: "6px",
            fontSize: "15px",
            fontWeight: 600,
            fontFamily: "system-ui, -apple-system, sans-serif",
            cursor: status === "sending" ? "default" : "pointer",
            opacity: status === "sending" ? 0.7 : 1,
            transition: "opacity 0.15s ease",
          }}
        >
          <GoogleIcon />
          {status === "sending" ? "Connecting…" : "Continue with Google"}
        </button>
      )}

      {/* Magic link fallback — deliberately subordinate: text link, not a button */}
      {!showMagicLink && status !== "sent" && (
        <button
          onClick={() => setShowMagicLink(true)}
          style={{
            background: "none",
            border: "none",
            color: "rgba(244,241,234,0.6)",
            fontSize: "13px",
            fontFamily: "system-ui, -apple-system, sans-serif",
            marginTop: "20px",
            cursor: "pointer",
            textDecoration: "underline",
            textUnderlineOffset: "3px",
          }}
        >
          Use email instead
        </button>
      )}

      {showMagicLink && status !== "sent" && (
        <form
          onSubmit={handleMagicLink}
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "10px",
            width: "100%",
            maxWidth: "320px",
            marginTop: "20px",
          }}
        >
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@email.com"
            required
            style={{
              padding: "12px 14px",
              borderRadius: "6px",
              border: "1px solid rgba(244,241,234,0.25)",
              background: "rgba(244,241,234,0.08)",
              color: "#F4F1EA",
              fontSize: "14px",
              fontFamily: "system-ui, -apple-system, sans-serif",
              outline: "none",
            }}
          />
          <button
            type="submit"
            disabled={status === "sending"}
            style={{
              padding: "12px 14px",
              borderRadius: "6px",
              border: "1px solid rgba(244,241,234,0.4)",
              background: "transparent",
              color: "#F4F1EA",
              fontSize: "14px",
              fontWeight: 600,
              fontFamily: "system-ui, -apple-system, sans-serif",
              cursor: status === "sending" ? "default" : "pointer",
              opacity: status === "sending" ? 0.6 : 1,
            }}
          >
            {status === "sending" ? "Sending…" : "Send login link"}
          </button>
        </form>
      )}

      {status === "sent" && (
        <div
          style={{
            color: "#F4F1EA",
            fontSize: "14px",
            fontFamily: "system-ui, -apple-system, sans-serif",
            textAlign: "center",
            maxWidth: "280px",
            lineHeight: 1.5,
          }}
        >
          Link sent to {email}. Open it on this device to sign in.
        </div>
      )}

      {status === "error" && (
        <div
          style={{
            color: "#E8A87C",
            fontSize: "13px",
            fontFamily: "system-ui, -apple-system, sans-serif",
            marginTop: "16px",
            textAlign: "center",
            maxWidth: "280px",
          }}
        >
          {errorMsg}
        </div>
      )}
    </div>
  );
}

function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" xmlns="http://www.w3.org/2000/svg">
      <path
        fill="#4285F4"
        d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.9c1.7-1.57 2.7-3.88 2.7-6.62z"
      />
      <path
        fill="#34A853"
        d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.9-2.26c-.8.54-1.84.86-3.06.86-2.35 0-4.34-1.59-5.05-3.72H.96v2.33A9 9 0 0 0 9 18z"
      />
      <path
        fill="#FBBC05"
        d="M3.95 10.7A5.4 5.4 0 0 1 3.67 9c0-.59.1-1.17.28-1.7V4.97H.96A9 9 0 0 0 0 9c0 1.45.35 2.83.96 4.03l2.99-2.33z"
      />
      <path
        fill="#EA4335"
        d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.58C13.46.89 11.43 0 9 0A9 9 0 0 0 .96 4.97l2.99 2.33C4.66 5.17 6.65 3.58 9 3.58z"
      />
    </svg>
  );
}

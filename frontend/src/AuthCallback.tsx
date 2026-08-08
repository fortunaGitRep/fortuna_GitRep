import { useEffect } from "react";
import { useNavigate } from "react-router-dom"; // swap for your router if different
import { supabase } from "./supabaseClient";

/**
 * Fortuna — /auth/callback
 * Handles the redirect after both Google OAuth and magic link.
 * Supabase JS auto-parses the URL fragment/query on load if
 * detectSessionInUrl is on (default true) — this just waits for
 * the session to land, then routes into the app.
 */
export default function AuthCallback() {
  const navigate = useNavigate();

  useEffect(() => {
    const { data: listener } = supabase.auth.onAuthStateChange((event, session) => {
      if (session) {
        navigate("/", { replace: true }); // → your Inbox tab / app root
      }
    });

    // Handle case where session is already resolved by the time this mounts
    supabase.auth.getSession().then(({ data }) => {
      if (data.session) navigate("/", { replace: true });
    });

    return () => listener.subscription.unsubscribe();
  }, [navigate]);

  return (
    <div
      style={{
        width: "100%",
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "#083F41",
        color: "#F4F1EA",
        fontFamily: "system-ui, -apple-system, sans-serif",
        fontSize: "14px",
      }}
    >
      Signing you in…
    </div>
  );
}

import { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import type { Session } from "@supabase/supabase-js";
import { supabase } from "./supabaseClient";
import LoginPage from "./LoginPage";
import AuthCallback from "./AuthCallback";
import Inbox from "./pages/Inbox";
import Buy from "./pages/Buy";
import Exit from "./pages/Exit";
import Positions from "./pages/Positions";
import Watchlist from "./pages/Watchlist";

function ProtectedRoute({
  session,
  children,
}: {
  session: Session | null;
  children: React.ReactNode;
}) {
  if (!session) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}

function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setLoading(false);
    });

    const { data: listener } = supabase.auth.onAuthStateChange(
      (_event, session) => {
        setSession(session);
      },
    );

    return () => listener.subscription.unsubscribe();
  }, []);

  if (loading) return null;

  return (
    <BrowserRouter>
      <div
        style={{
          maxWidth: "480px",
          margin: "0 auto",
          minHeight: "100vh",
          boxShadow: "0 0 0 0.5px var(--border)",
        }}
      >
        <Routes>
          <Route
            path="/login"
            element={session ? <Navigate to="/inbox" replace /> : <LoginPage />}
          />
          <Route path="/auth/callback" element={<AuthCallback />} />

          <Route
            path="/inbox"
            element={
              <ProtectedRoute session={session}>
                <Inbox />
              </ProtectedRoute>
            }
          />
          <Route
            path="/buy"
            element={
              <ProtectedRoute session={session}>
                <Buy />
              </ProtectedRoute>
            }
          />
          <Route
            path="/exit"
            element={
              <ProtectedRoute session={session}>
                <Exit />
              </ProtectedRoute>
            }
          />
          <Route
            path="/positions"
            element={
              <ProtectedRoute session={session}>
                <Positions />
              </ProtectedRoute>
            }
          />
          <Route
            path="/watchlist"
            element={
              <ProtectedRoute session={session}>
                <Watchlist />
              </ProtectedRoute>
            }
          />

          <Route path="/" element={<Navigate to="/inbox" replace />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}

export default App;

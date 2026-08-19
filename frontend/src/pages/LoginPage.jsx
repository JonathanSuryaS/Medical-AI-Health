  // LoginPage.jsx — the two-column login screen.
//
// On successful login, saves the token (inside api.login) and navigates to /chat.
// useNavigate is React Router's way to move between pages in code (vs a link).

import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { login } from "../api.js";
import AuthShell from "../components/AuthShell.jsx";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(email, password);
      navigate("/chat");            // logged in -> go to the app
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell title="Welcome back" subtitle="Sign in to your health assistant.">
      <form onSubmit={handleSubmit} className="auth-form">
        <label>Email
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                 placeholder="you@email.com" required />
        </label>
        <label>Password
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                 placeholder="••••••••" required />
        </label>
        {error && <p className="auth-error">{error}</p>}
        <button type="submit" disabled={busy}>{busy ? "Signing in…" : "Log in"}</button>
      </form>
      <p className="auth-switch">
        Don't have an account? <Link to="/signup">Sign up</Link>
      </p>
    </AuthShell>
  );
}

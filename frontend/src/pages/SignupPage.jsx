// SignupPage.jsx — near-identical to login, but calls signup and enforces the
// 8-char minimum the backend requires (so the user sees the rule before the
// server rejects them).

import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { signup } from "../api.js";
import AuthShell from "../components/AuthShell.jsx";

export default function SignupPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    setBusy(true);
    try {
      await signup(email, password);
      navigate("/chat");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell title="Create account" subtitle="Start asking grounded health questions.">
      <form onSubmit={handleSubmit} className="auth-form">
        <label>Email
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                 placeholder="you@email.com" required />
        </label>
        <label>Password
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                 placeholder="at least 8 characters" required />
        </label>
        {error && <p className="auth-error">{error}</p>}
        <button type="submit" disabled={busy}>{busy ? "Creating…" : "Sign up"}</button>
      </form>
      <p className="auth-switch">
        Already have an account? <Link to="/login">Log in</Link>
      </p>
    </AuthShell>
  );
}

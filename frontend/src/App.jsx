// App.jsx — the route map. This is the "table of contents" for the whole app:
// which URL shows which page.
//
// The important concept here is ProtectedRoute: /chat is wrapped in it, so a
// logged-out visitor gets redirected to /login. This is the frontend mirror of
// the backend's get_current_user gate -- same "must be logged in" idea, enforced
// on the client so users never even see the chat screen without a token.

import { Routes, Route, Navigate } from "react-router-dom";
import { isLoggedIn } from "./api.js";
  import LoginPage from "./pages/LoginPage.jsx";
  import SignupPage from "./pages/SignupPage.jsx";
  import ChatPage from "./pages/ChatPage.jsx";

// The guard: render the page if logged in, otherwise bounce to /login.
function ProtectedRoute({ children }) {
  return isLoggedIn() ? children : <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <Routes>
      {/* default: send people to the chat (which itself redirects to login if needed) */}
      <Route path="/" element={<Navigate to="/chat" replace />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/signup" element={<SignupPage />} />
      <Route
        path="/chat"
        element={
          <ProtectedRoute>
            <ChatPage />
          </ProtectedRoute>
        }
      />
      {/* anything unknown -> chat */}
      <Route path="*" element={<Navigate to="/chat" replace />} />
    </Routes>
  );
}

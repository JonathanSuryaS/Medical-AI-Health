// api.js — the single point of contact with the backend.
//
// Now handles auth too. The token is kept in localStorage so it survives page
// refreshes (that's what "staying logged in" means). Every protected call reads
// the token and sends it in the Authorization header — mirroring what you did by
// hand with the Authorize button in /docs.

const TOKEN_KEY = "medai_token";

// --- token storage (the browser's memory of "who am I") ---
export function saveToken(token) {
  localStorage.setItem(TOKEN_KEY, token);
}
export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}
export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}
export function isLoggedIn() {
  return !!getToken();
}

 
async function request(path, { method = "GET", body = null, auth = false } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (auth) {
    const token = getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`/api${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : null,
  });

  if (!res.ok) {
    // 401 on a protected call means the token is missing/expired -> force re-login.
    if (res.status === 401) {
      clearToken();
    }
    let detail = `Request failed (${res.status})`;
    try {
      const data = await res.json();
      if (data.detail) detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
    } catch { /* not json */ }
    throw new Error(detail);
  }
  return res.json();
}

// --- auth ---
export async function signup(email, password) {
  const data = await request("/auth/signup", { method: "POST", body: { email, password } });
  saveToken(data.access_token);
  return data;
}
export async function login(email, password) {
  const data = await request("/auth/login", { method: "POST", body: { email, password } });
  saveToken(data.access_token);
  return data;
}
export function logout() {
  clearToken();
}

// --- app ---
export async function askQuestion(question, k = null) {
  return request("/ask", { method: "POST", auth: true, body: k ? { question, k } : { question } });
}
export async function getHistory() {
  return request("/history", { method: "GET", auth: true });
}

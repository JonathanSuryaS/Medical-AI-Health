// api.js — the single point of contact with the FastAPI backend.
//
// Everything the UI knows about the server lives here. If the endpoint shape
// changes, this is the only file that changes. The component just awaits
// askQuestion() and renders the result -- it never touches fetch, URLs, or
// status codes. That separation is what keeps a React app maintainable.

// "/api/ask" is rewritten to "http://localhost:8000/ask" by the Vite proxy
// (see vite.config.js). In production you'd point this at your deployed URL.
const ENDPOINT = "/api/ask";

export async function askQuestion(question, k = null) {
  const res = await fetch(ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(k ? { question, k } : { question }),
  });

  if (!res.ok) {
    // Surface a real message instead of letting the UI show a blank failure.
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (body.detail) detail = body.detail;
    } catch {
      /* response wasn't JSON; keep the status message */
    }
    throw new Error(detail);
  }

  // Shape: { answer, abstained, citations: [{n, source, url}], provider }
  return res.json();
}

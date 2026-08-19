// ChatPage.jsx — the logged-in app. Two columns: history sidebar on the left,
// ask panel on the right. This is the ChatGPT-style layout.
//
// On mount it loads the user's history (useEffect runs once). After each answer
// it refreshes history so the new question appears in the sidebar immediately.

import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { askQuestion, getHistory, logout } from "../api.js";

export default function ChatPage() {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const navigate = useNavigate();

  // Load history once when the page opens.
  useEffect(() => { refreshHistory(); }, []);

  async function refreshHistory() {
    try {
      setHistory(await getHistory());
    } catch (err) {
      // 401 here means the token expired; api.js already cleared it -> go log in.
      if (err.message.includes("401") || err.message.toLowerCase().includes("auth")) {
        navigate("/login");
      }
    }
  }

  async function handleAsk() {
    const q = question.trim();
    if (!q || loading) return;
    setLoading(true);
    setError(null);
    setAnswer(null);
    try {
      const result = await askQuestion(q);
      setAnswer(result);
      setQuestion("");
      refreshHistory();               // new Q appears in the sidebar
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function handleLogout() {
    logout();
    navigate("/login");
  }

  return (
    <div className="chat-layout">
      <aside className="sidebar">
        <div className="sidebar-head">
          <span className="pulse" aria-hidden="true" />
          <span>History</span>
        </div>
        <div className="history-list">
          {history.length === 0 && <p className="history-empty">No questions yet.</p>}
          {history.map((h) => (
            <button key={h.id} className="history-item"
                    onClick={() => setAnswer({ answer: h.answer, citations: [], abstained: false, provider: "" })}>
              {h.question}
            </button>
          ))}
        </div>
        <button className="logout-btn" onClick={handleLogout}>Log out</button>
      </aside>

      <main className="chat-main">
        <h1>Medical AI Health Assistant</h1>
        <div className="ask-row">
          <textarea value={question} onChange={(e) => setQuestion(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleAsk(); } }}
                    placeholder="Ask a medical question…" rows={3} />
          <button onClick={handleAsk} disabled={loading || !question.trim()}>
            {loading ? "Consulting…" : "Ask"}
          </button>
        </div>

        {error && <div className="chat-error">{error}</div>}

        {answer && (
          <article className={`answer-card ${answer.abstained ? "abstained" : ""}`}>
            <p className="answer-text">{answer.answer}</p>
            {answer.citations?.length > 0 && (
              <div className="sources">
                <h2>Sources</h2>
                <ol>
                  {answer.citations.map((c) => (
                    <li key={c.n}>
                      <span className="src-name">{c.source}</span>
                      {c.url && <a href={c.url} target="_blank" rel="noopener noreferrer">{c.url}</a>}
                    </li>
                  ))}
                </ol>
              </div>
            )}
          </article>
        )}
      </main>
    </div>
  );
}

// App.jsx — the whole UI. One component, deliberately, so the data flow is easy
// to follow while you learn: state at the top, an async handler, and the render.
//
// The four pieces of React state map exactly to the four things the UI can be:
//   question  -- what's in the text box (controlled input)
//   answer    -- the result to show (null until we have one)
//   loading   -- true while the request is in flight (disables the button, shows status)
//   error     -- a message if the request failed
// Every UI state below is derived from these four. That's the core React idea:
// state drives the view, you never touch the DOM by hand.

import { useState } from "react";
import { askQuestion } from "./api.js";

export default function App() {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function handleAsk() {
    const q = question.trim();
    if (!q || loading) return;

    setLoading(true);
    setError(null);
    setAnswer(null);
    try {
      const result = await askQuestion(q);
      setAnswer(result);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  // Enter to submit; Shift+Enter for a newline.
  function handleKey(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleAsk();
    }
  }

  return (
    <div className="page">
      <header className="masthead">
        <div className="pulse" aria-hidden="true" />
        <div>
          <h1>Medical AI Health Assistant</h1>
          <p className="tagline">
            Answers grounded in NIH sources — with citations, or an honest refusal.
          </p>
        </div>
      </header>

      <section className="ask">
        <textarea
          className="input"
          placeholder="Ask a medical question — e.g. What are the symptoms of type 2 diabetes?"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={handleKey}
          rows={3}
        />
        <button className="submit" onClick={handleAsk} disabled={loading || !question.trim()}>
          {loading ? "Consulting sources…" : "Ask"}
        </button>
      </section>

      {error && (
        <div className="notice error">
          <strong>Something went wrong.</strong> {error}
          <div className="hint">Is the backend running on port 8000?</div>
        </div>
      )}

      {answer && <AnswerCard answer={answer} />}

      {!answer && !error && !loading && (
        <p className="empty">
          Ask a question to see a sourced answer. Out-of-scope questions are
          declined rather than guessed at.
        </p>
      )}
    </div>
  );
}

// A separate component for the answer keeps App readable and shows the other
// core React idea: compose the UI from small pieces that each render one thing.
function AnswerCard({ answer }) {
  return (
    <article className={`answer-card ${answer.abstained ? "abstained" : ""}`}>
      {answer.abstained && <div className="badge">No grounded answer — referred out</div>}

      <p className="answer-text">{answer.answer}</p>

      {answer.citations?.length > 0 && (
        <div className="sources">
          <h2>Sources</h2>
          <ol>
            {answer.citations.map((c) => (
              <li key={c.n}>
                <span className="src-name">{c.source}</span>
                {c.url && (
                  <a href={c.url} target="_blank" rel="noopener noreferrer">
                    {c.url}
                  </a>
                )}
              </li>
            ))}
          </ol>
        </div>
      )}

      <footer className="meta">answered by {answer.provider || "unknown"}</footer>
    </article>
  );
}

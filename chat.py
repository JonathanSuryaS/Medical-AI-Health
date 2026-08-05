"""
chat.py — interactive REPL around the pipeline. Ask many questions in one run.

    py -m src.chat

Why this exists separately from pipeline.py: pipeline.py runs one question and
exits, which is what the eval harness and the API want. This file is for *you* --
a loop that keeps the model resident in VRAM (so every answer after the first is
fast) and lets you eyeball retrieval + grounding while tuning, without paying the
model-load cost on every question.

It calls Pipeline().ask() and nothing else -- same object the API serves, so what
you see here is exactly what a user would get. Type a question and press enter.
Commands: /quit or /exit to leave, /k N to change how many passages are retrieved.
"""

from __future__ import annotations

from config import settings
from src.pipeline import Pipeline


def _print_answer(ans) -> None:
    tag = "ABSTAINED" if ans.abstained else "answered"
    print(f"\n[{tag}]  provider={ans.provider}  backend={settings.vector_backend}\n")
    print(ans.text)
    if ans.citations:
        print("\nSources:")
        for c in ans.citations:
            print(f"  [{c.n}] {c.source} — {c.url or '(no url)'}")
    print()


def main() -> None:
    print("Loading pipeline (first question warms up the model)...")
    pipe = Pipeline()                 # build once, reuse for every question
    k = settings.top_k

    print("\nMedical RAG — ask a question. /quit to exit, /k N to set passage count.\n")
    while True:
        try:
            q = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nbye.")
            break

        if not q:
            continue
        if q in ("/quit", "/exit"):
            print("bye.")
            break
        if q.startswith("/k "):
            try:
                k = int(q.split()[1])
                print(f"(now retrieving {k} passages)\n")
            except (IndexError, ValueError):
                print("usage: /k 6\n")
            continue

        try:
            ans = pipe.ask(q, k=k)
            _print_answer(ans)
        except Exception as e:
            # Don't let one bad call kill the session -- print and keep going.
            print(f"\n[error] {type(e).__name__}: {e}\n")


if __name__ == "__main__":
    main()
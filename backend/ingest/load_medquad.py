# load_medquad -> turn raw corpus into clean, chunked records.
# canonical medQuAD removed 3 subsets (ADAM, Encyclopedia, MedlinePlusDrugs)
# This loader drops rows with empty / whitespace answers so incomplete corpus can never inflate or deflate your recall numbers unnoticed

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from config import settings

@dataclass
class DocChunk:
    id: str
    text: str
    question: str
    source: str
    url: str = ""


def _chunk(text: str, size: int, overlap: int) -> list[str]:
    text = text.strip()
    if len(text) <= size:
        return [text]
    out, start = [], 0
    while start < len(text):
        end = start + size
        out.append(text[start:end])
        start = end - overlap
    return out


def load_corpus(csv_path: Path) -> list[DocChunk]:
    if not csv_path.exists():
        raise FileNotFoundError(
            f"{csv_path} not found. See the DATA NOTE in this file and the README — "
            f"download a MedQuAD CSV that includes answers and place it there."
        )

    chunks: list[DocChunk] = []
    dropped = 0
    with csv_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            answer = (row.get("answer") or "").strip()
            question = (row.get("question") or "").strip()
            if not answer:                      # answer-less row -> skip, count it
                dropped += 1
                continue
            source = (row.get("source") or row.get("focus_area") or "MedQuAD/NIH").strip()
            url = (row.get("url") or "").strip()
            for j, piece in enumerate(_chunk(answer, settings.chunk_chars, settings.chunk_overlap)):
                chunks.append(
                    DocChunk(
                        id=f"row{i}_chunk{j}",
                        text=piece,
                        question=question,
                        source=source,
                        url=url,
                    )
                )

    print(f"[load_corpus] kept {len(chunks)} chunks; dropped {dropped} answer-less rows")
    if dropped > len(chunks):
        print("[load_corpus] WARNING: more rows dropped than kept — wrong corpus version?")
    return chunks


if __name__ == "__main__":
    docs = load_corpus(settings.RAW_CORPUS if hasattr(settings, "RAW_CORPUS") else __import__("config").RAW_CORPUS)
    print(docs[0] if docs else "empty")
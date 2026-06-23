"""
medquad_xml_to_csv.py — one-time preprocessing: MedQuAD XML -> flat CSV.

Reads the raw MedQuAD download from EITHER:
  - the GitHub .zip directly (no extraction needed), or
  - an already-extracted folder.
Default source path comes from config.MEDQUAD_SRC; override with argv.

DATA NOTE:
The canonical abachaa/MedQuAD repo has ANSWERS REMOVED from 3 subsets
(A.D.A.M., MedlinePlus Drugs, MedlinePlus Herbs) for copyright. Those pairs
have empty <Answer> tags; this script drops and counts them so an incomplete
corpus can never silently poison retrieval.

Usage:
    # uses config.MEDQUAD_SRC
    python -m src.ingest.medquad_xml_to_csv
    # or point at a download explicitly (zip or folder)
    python -m src.ingest.medquad_xml_to_csv ~/Downloads/MedQuAD-master.zip data/medquad.csv
"""
from __future__ import annotations

import csv
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

from config import MEDQUAD_SRC, RAW_CORPUS


def _clean(text: str) -> str:
    """Strip scrape noise: collapse intra-line whitespace, drop indentation and
    blank lines, but KEEP single newlines so list/section structure survives."""
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    return "\n".join(lines).strip()


def parse_xml(data: bytes) -> list[dict]:
    """Parse one MedQuAD XML document (bytes) into QA-pair dicts."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return []

    source = root.attrib.get("source", "")
    url = root.attrib.get("url", "")
    focus_el = root.find("Focus")
    focus = (focus_el.text or "").strip() if focus_el is not None else ""

    rows = []
    for qa in root.iterfind(".//QAPair"):
        q_el, a_el = qa.find("Question"), qa.find("Answer")
        question = _clean(q_el.text or "") if q_el is not None else ""
        answer = _clean(a_el.text or "") if a_el is not None else ""
        qtype = q_el.attrib.get("qtype", "") if q_el is not None else ""
        rows.append({
            "question": question, "answer": answer,
            "source": source, "url": url,
            "focus_area": focus, "qtype": qtype,
        })
    return rows


def iter_documents(src: Path):
    """Yield (subset_name, xml_bytes) from a .zip OR a directory.

    `subset_name` is the immediate parent folder (e.g. '3_GHR_QA'), which works
    the same whether the zip has a top-level 'MedQuAD-master/' prefix or not.
    """
    if src.suffix.lower() == ".zip":
        with zipfile.ZipFile(src) as zf:
            for name in zf.namelist():
                if name.lower().endswith(".xml"):
                    parts = name.split("/")
                    subset = parts[-2] if len(parts) >= 2 else "root"
                    yield subset, zf.read(name)
    elif src.is_dir():
        for xf in sorted(src.rglob("*.xml")):
            yield xf.parent.name, xf.read_bytes()
    else:
        raise SystemExit(
            f"{src} is neither a .zip nor a folder.\n"
            f"Download MedQuAD from https://github.com/abachaa/MedQuAD (Code > Download ZIP) "
            f"and put it at {src}, or pass a path as the first argument."
        )


def convert(src: Path, out_csv: Path) -> None:
    if not src.exists():
        raise SystemExit(
            f"Source not found: {src}\n"
            f"Download the MedQuAD ZIP from GitHub and drop it there "
            f"(or pass a path/folder as the first argument)."
        )

    kept, dropped = [], 0
    per_kept: Counter = Counter()
    per_dropped: Counter = Counter()

    for subset, data in iter_documents(src):
        for row in parse_xml(data):
            if not row["question"] or not row["answer"]:
                dropped += 1
                per_dropped[subset] += 1
                continue
            kept.append(row)
            per_kept[subset] += 1

    if not kept:
        raise SystemExit("No answered pairs found — wrong source contents?")

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f, fieldnames=["question", "answer", "source", "url", "focus_area", "qtype"]
        )
        w.writeheader()
        w.writerows(kept)

    print(f"\nSource: {src}")
    print(f"Wrote {len(kept):,} answered pairs to {out_csv}")
    print(f"Dropped {dropped:,} answer-less pairs (copyright-removed subsets)\n")
    print(f"{'subset':<32}{'kept':>8}{'dropped':>10}")
    print("-" * 50)
    for subset in sorted(set(per_kept) | set(per_dropped)):
        print(f"{subset:<32}{per_kept[subset]:>8}{per_dropped[subset]:>10}")


if __name__ == "__main__":
    # Canonical source is config.MEDQUAD_SRC (set it once there).
    # An optional CLI arg overrides it for one-off runs.
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else MEDQUAD_SRC
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else RAW_CORPUS
    if len(sys.argv) <= 1:
        print(f"Reading MedQuAD from config.MEDQUAD_SRC: {src}")
    convert(src, out)
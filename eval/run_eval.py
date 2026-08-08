"""
run_eval.py — sample questions, run them through the pipeline, judge the answers,
report the numbers you'll defend.

    py -m eval.run_eval                 # default: 50 questions
    py -m eval.run_eval --n 20          # quick pass
    py -m eval.run_eval --n 100 --seed 7

WHAT IT MEASURES
  faithfulness  -- fraction of the answer's claims supported by retrieved passages
  relevancy     -- did the answer address the question at all
  abstain rate  -- how often it refused (context: these questions ARE in the index,
                   so a high abstain rate here would signal the threshold is too high)

TWO HONEST CAVEATS, stated so you state them too:
  1. The questions are sampled from medquad.csv, which is what you indexed. So
     retrieval plays on easy mode -- the target passage is always present. This
     makes RETRIEVAL look better than it would on unseen questions. FAITHFULNESS
     is still valid (a hallucination is a hallucination regardless of whether the
     source was easy to find). Do not report this as a held-out number.
  2. The judge is a local 9B model -- good enough to catch problems and iterate,
     noisier than a frontier judge. For the figure that goes in the submission,
     re-run the judge against a hosted model; the code doesn't change, only
     config.judge_* does.

FLOW IS TWO-PHASE ON PURPOSE
  Generate all answers first (llama in VRAM), THEN judge all of them (qwen in
  VRAM). On 8GB you can't hold both comfortably; phasing keeps one resident at a
  time and, as a bonus, lets you re-judge without re-generating.
"""

from __future__ import annotations

import argparse
import csv
import random
import statistics
import time
from dataclasses import dataclass

from config import RAW_CORPUS, settings
from backend.pipeline import Pipeline
from eval.judge import FaithfulnessJudge, FaithfulnessResult


@dataclass
class Sample:
    question: str
    reference_answer: str          # the MedQuAD answer, kept for eyeballing
    # filled in phase 1:
    generated: str = ""
    passages: list = None
    abstained: bool = False
    provider: str = ""


def load_samples(n: int, seed: int) -> list[Sample]:
    with open(RAW_CORPUS, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    random.seed(seed)
    picked = random.sample(rows, min(n, len(rows)))
    return [Sample(question=r["question"], reference_answer=r["answer"]) for r in picked]


def phase1_generate(samples: list[Sample]) -> None:
    print(f"\n[phase 1] generating {len(samples)} answers "
          f"(provider={settings.llm_provider})...")
    pipe = Pipeline()
    t0 = time.time()
    for i, s in enumerate(samples, 1):
        ans = pipe.ask(s.question)
        s.generated = ans.text
        s.passages = ans.passages
        s.abstained = ans.abstained
        s.provider = ans.provider
        print(f"  {i:>3}/{len(samples)}  "
              f"{'ABSTAIN' if ans.abstained else 'ok':<7}  {s.question[:60]}")
    print(f"[phase 1] done in {(time.time()-t0)/60:.1f} min")


def phase2_judge(samples: list[Sample]) -> list[FaithfulnessResult]:
    print(f"\n[phase 2] judging (judge={settings.judge_model})...")
    print("  NOTE: if the generator and judge are different Ollama models, the")
    print("  first judge call will pause while Ollama swaps models in VRAM.\n")
    judge = FaithfulnessJudge()
    results = []
    t0 = time.time()
    for i, s in enumerate(samples, 1):
        r = judge.score(s.question, s.generated, s.passages or [], abstained=s.abstained)
        results.append(r)
        if r.status == "scored":
            verdict = f"faith={r.faithfulness:.2f} ({r.n_supported}/{r.n_claims})"
        else:
            verdict = r.status
        print(f"  {i:>3}/{len(samples)}  {verdict}")
    print(f"[phase 2] done in {(time.time()-t0)/60:.1f} min")
    return results


def report(results: list[FaithfulnessResult]) -> None:
    scored     = [r for r in results if r.status == "scored"]
    abstained  = [r for r in results if r.status == "abstained"]
    no_claims  = [r for r in results if r.status == "no_claims"]
    parse_fail = [r for r in results if r.status == "parse_fail"]

    print("\n" + "=" * 62)
    print("EVAL SUMMARY")
    print("=" * 62)
    print(f"  total questions      {len(results)}")
    print(f"  scored               {len(scored)}")
    print(f"  abstained (gate)     {len(abstained)}")
    print(f"  no-claims (refused   {len(no_claims)}   "
          f"in prose — correct, not a failure)")
    # parse_fail is an EVAL bug, not a system result. If it's above ~0 the
    # reported mean is computed on a biased subset -- fix the judge before trusting it.
    flag = "  <-- judge parse bug, investigate" if parse_fail else ""
    print(f"  parse-fail (judge)   {len(parse_fail)}{flag}")

    if scored:
        faith = [r.faithfulness for r in scored]
        rel = [r.relevancy for r in scored]
        mean_f = statistics.mean(faith)
        print(f"\n  faithfulness  mean   {mean_f:.3f}   "
              f"(target {settings.faithfulness_target})  "
              f"{'PASS' if mean_f >= settings.faithfulness_target else 'BELOW'}")
        print(f"  faithfulness  median {statistics.median(faith):.3f}")
        print(f"  perfect (1.0)        {sum(1 for x in faith if x == 1.0)}/{len(faith)}")
        print(f"  relevancy     mean   {statistics.mean(rel):.3f}")

        worst = sorted(scored, key=lambda r: r.faithfulness)[:5]
        print("\n  lowest-faithfulness questions (look here first):")
        for r in worst:
            print(f"    {r.faithfulness:.2f}  {r.question[:64]}")
            for uc in r.unsupported_claims[:2]:
                print(f"          unsupported: {uc[:70]}")
    print("=" * 62)


def write_csv(samples: list[Sample], results: list[FaithfulnessResult], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["question", "status", "faithfulness", "relevancy", "n_claims",
                    "n_supported", "unsupported_claims", "generated"])
        for s, r in zip(samples, results):
            w.writerow([
                s.question, r.status,
                "" if r.faithfulness < 0 else f"{r.faithfulness:.3f}",
                r.relevancy, r.n_claims, r.n_supported,
                " | ".join(r.unsupported_claims), s.generated,
            ])
    print(f"\nper-question results -> {path}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=50, help="number of questions to sample")
    ap.add_argument("--seed", type=int, default=42, help="sampling seed (reproducible)")
    ap.add_argument("--out", default="eval/results.csv")
    args = ap.parse_args()

    samples = load_samples(args.n, args.seed)
    phase1_generate(samples)
    results = phase2_judge(samples)
    report(results)
    write_csv(samples, results, args.out)


if __name__ == "__main__":
    main()
#(the scorer + report)
"""Task 3 — evaluation harness.

Run:  python -m evals.run_evals

Scoring is a hybrid by design:

  * Rule-based checks (deterministic, free, fast) cover everything objectively
    verifiable: enum validity, urgency band, routing, structure, grounding,
    determinism, error handling. These are the quality gates — they either hold
    or the build is broken.

  * An LLM-as-judge scores the two things rules cannot: whether the draft
    response is actually usable by an agent, and whether the TAM talking points
    are specific rather than generic. The judge is advisory: it contributes to
    the quality score but never decides pass/fail on its own, because a judge
    that gates CI is a non-deterministic gate.

Each case yields pass/fail plus a 0-1 quality score (the fraction of its checks
that passed). Reports are written to eval_report.json and eval_report.md.
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from evals.test_cases import BRIEF_CASES, TRIAGE_CASES
from src.account_brief import generate_account_brief
from src.config import CATEGORIES, RESPONDER_TEAMS, URGENCIES
from src.data_loader import AccountNotFoundError
from src.llm import LLMError, ask_llm_json
from src.prompts import JUDGE_PROMPT_VERSION
from src.triage import triage_ticket

ROOT = Path(__file__).resolve().parent.parent

JUDGE_PROMPT = """You are a strict QA reviewer for an internal support AI tool.
Score the output below on the given criterion. Be sceptical: generic, vague or
padded output scores low. Reply with ONLY valid JSON.

## Criterion
{criterion}

## Output under review
{output}

{{"score": 0.0, "justification": "one sentence"}}"""


def _sentence_count(text: str) -> int:
    return len([s for s in re.split(r"[.!?]+", text or "") if s.strip()])


def _judge(criterion: str, output: str) -> tuple[float, str]:
    """LLM-as-judge. Failures degrade to a neutral score — never crash the suite."""
    try:
        verdict = ask_llm_json(JUDGE_PROMPT.format(criterion=criterion, output=output))
        score = min(max(float(verdict.get("score", 0.5)), 0.0), 1.0)
        return score, str(verdict.get("justification", ""))
    except (LLMError, TypeError, ValueError) as exc:
        return 0.5, f"judge unavailable ({exc}); neutral score applied"


# --------------------------------------------------------------------------- #
# Task 1 scoring
# --------------------------------------------------------------------------- #

def score_triage_case(case: dict) -> dict:
    checks: list[tuple[str, bool]] = []
    started = time.perf_counter()

    try:
        result = triage_ticket(**case["input"])
    except Exception as exc:  # noqa: BLE001 — any crash is a hard fail
        return {
            "id": case["id"], "task": "task1", "adversarial": case["adversarial"],
            "description": case["description"], "passed": False, "quality_score": 0.0,
            "checks": [{"check": "pipeline_runs", "passed": False}],
            "error": f"{type(exc).__name__}: {exc}",
            "latency_ms": round((time.perf_counter() - started) * 1000),
        }

    exp = case["expect"]

    # Schema gates — these apply to every case.
    checks.append(("category_is_valid_enum", result["category"] in CATEGORIES))
    checks.append(("urgency_is_valid_enum", result["urgency"] in URGENCIES))
    checks.append(("responder_team_is_valid_enum", result["responder_team"] in RESPONDER_TEAMS))
    checks.append(("reasoning_present", len(result["reasoning"]) > 20))

    # Case-specific expectations.
    if "urgency_in" in exp:
        checks.append((f"urgency in {exp['urgency_in']}", result["urgency"] in exp["urgency_in"]))
    if "category_in" in exp:
        checks.append((f"category in {exp['category_in']}", result["category"] in exp["category_in"]))
    if "product" in exp:
        checks.append((f"product == {exp['product']}", result["product"] == exp["product"]))
    if "responder_team_in" in exp:
        checks.append((f"team in {exp['responder_team_in']}",
                       result["responder_team"] in exp["responder_team_in"]))
    if "min_confidence" in exp:
        checks.append((f"confidence >= {exp['min_confidence']}",
                       result["confidence"] >= exp["min_confidence"]))
    if "max_confidence" in exp:
        checks.append((f"confidence <= {exp['max_confidence']}",
                       result["confidence"] <= exp["max_confidence"]))
    if exp.get("requires_human_review"):
        checks.append(("flagged for human review", result["needs_human_review"] is True))
    if "min_clarifying_questions" in exp:
        checks.append((f"asks >= {exp['min_clarifying_questions']} clarifying question(s)",
                       len(result["clarifying_questions"]) >= exp["min_clarifying_questions"]))
    if exp.get("requires_kb_match"):
        checks.append(("cites a knowledge-base doc", result["matched_kb_doc"] is not None))
    if exp.get("forbid_kb_match"):
        checks.append(("refuses to cite a KB doc it cannot support",
                       result["matched_kb_doc"] is None))
    if "draft_response_min_chars" in exp:
        checks.append((f"draft response >= {exp['draft_response_min_chars']} chars",
                       len(result["draft_response"]) >= exp["draft_response_min_chars"]))

    # Grounding gate: a cited doc must have actually been retrieved.
    retrieved = {d["doc_path"] for d in result["retrieved_docs"]}
    checks.append(("cited doc was actually retrieved (no hallucination)",
                   result["matched_kb_doc"] is None or result["matched_kb_doc"] in retrieved))

    # LLM-as-judge: is the draft reply genuinely sendable?
    judge_score, judge_note = _judge(
        "Is this draft first-response something a support agent could send to the customer "
        "with only minor edits? It must acknowledge the specific issue, state a concrete next "
        "step, invent no facts, and promise no fix date. Score 0.0-1.0.",
        result["draft_response"],
    )

    rule_score = sum(1 for _, ok in checks if ok) / len(checks)
    quality = round(0.75 * rule_score + 0.25 * judge_score, 3)

    return {
        "id": case["id"], "task": "task1", "adversarial": case["adversarial"],
        "description": case["description"],
        "passed": all(ok for _, ok in checks),
        "quality_score": quality,
        "checks": [{"check": name, "passed": ok} for name, ok in checks],
        "judge": {"score": round(judge_score, 3), "justification": judge_note},
        "observed": {
            "category": result["category"], "urgency": result["urgency"],
            "product": result["product"], "responder_team": result["responder_team"],
            "confidence": result["confidence"], "matched_kb_doc": result["matched_kb_doc"],
        },
        "latency_ms": result["latency_ms"],
    }


# --------------------------------------------------------------------------- #
# Task 2 scoring
# --------------------------------------------------------------------------- #

def score_brief_case(case: dict) -> dict:
    checks: list[tuple[str, bool]] = []
    started = time.perf_counter()
    exp = case["expect"]

    # Adversarial: unknown account must raise cleanly, not fabricate a brief.
    if exp.get("raises_account_not_found"):
        try:
            generate_account_brief(case["account_id"])
            checks.append(("raises AccountNotFoundError for unknown id", False))
        except AccountNotFoundError:
            checks.append(("raises AccountNotFoundError for unknown id", True))
        except Exception as exc:  # noqa: BLE001
            checks.append((f"raises AccountNotFoundError (got {type(exc).__name__})", False))

        rule_score = sum(1 for _, ok in checks if ok) / len(checks)
        return {
            "id": case["id"], "task": "task2", "adversarial": case["adversarial"],
            "description": case["description"],
            "passed": all(ok for _, ok in checks), "quality_score": round(rule_score, 3),
            "checks": [{"check": n, "passed": ok} for n, ok in checks],
            "latency_ms": round((time.perf_counter() - started) * 1000),
        }

    try:
        brief = generate_account_brief(case["account_id"])
    except Exception as exc:  # noqa: BLE001
        return {
            "id": case["id"], "task": "task2", "adversarial": case["adversarial"],
            "description": case["description"], "passed": False, "quality_score": 0.0,
            "checks": [{"check": "pipeline_runs", "passed": False}],
            "error": f"{type(exc).__name__}: {exc}",
            "latency_ms": round((time.perf_counter() - started) * 1000),
        }

    # Structure gates.
    checks.append(("executive_summary present", bool(brief["executive_summary"].strip())))
    checks.append(("talking_points present", len(brief["talking_points"]) > 0))
    checks.append(("risk section present (may be empty list)", "flagged_signals" in brief))

    if exp.get("has_all_three_sections"):
        checks.append(("all three required sections present", all([
            bool(brief["executive_summary"].strip()),
            "flagged_signals" in brief,
            len(brief["talking_points"]) > 0,
        ])))
    if "min_tickets_analysed" in exp:
        checks.append((f"analysed >= {exp['min_tickets_analysed']} tickets",
                       brief["tickets_analysed"] >= exp["min_tickets_analysed"]))
    if "min_summary_sentences" in exp:
        n = _sentence_count(brief["executive_summary"])
        lo = exp["min_summary_sentences"]
        hi = exp.get("max_summary_sentences", 99)
        checks.append((f"summary is {lo}-{hi} sentences (got {n})", lo <= n <= hi))
    if "min_talking_points" in exp:
        n = len(brief["talking_points"])
        lo = exp["min_talking_points"]
        hi = exp.get("max_talking_points", 99)
        checks.append((f"{lo}-{hi} talking points (got {n})", lo <= n <= hi))
    if exp.get("all_quotes_verified"):
        # Any risk that survives into flagged_signals has already been verified
        # verbatim against source text by account_brief._verify_risks.
        checks.append(("every flagged risk carries a verified verbatim quote",
                       all(r.get("evidence_quote") for r in brief["flagged_signals"])))
    if exp.get("no_fabricated_sources"):
        valid = all(
            r["source"] == "escalation_note" or r["source"].startswith("TKT-")
            for r in brief["flagged_signals"]
        )
        checks.append(("every risk source is a real ticket id or escalation_note", valid))
    if exp.get("deterministic"):
        second = generate_account_brief(case["account_id"])
        checks.append(("identical output on re-run (determinism)",
                       brief["executive_summary"] == second["executive_summary"]
                       and brief["flagged_signals"] == second["flagged_signals"]))

    judge_score, judge_note = _judge(
        "Are these TAM talking points specific and actionable — do they reference concrete "
        "tickets, numbers or events? Generic filler such as 'discuss satisfaction' or 'review "
        "the roadmap' must score below 0.4. Score 0.0-1.0.",
        json.dumps(brief["talking_points"], indent=2),
    )

    rule_score = sum(1 for _, ok in checks if ok) / len(checks)
    quality = round(0.75 * rule_score + 0.25 * judge_score, 3)

    return {
        "id": case["id"], "task": "task2", "adversarial": case["adversarial"],
        "description": case["description"],
        "passed": all(ok for _, ok in checks), "quality_score": quality,
        "checks": [{"check": n, "passed": ok} for n, ok in checks],
        "judge": {"score": round(judge_score, 3), "justification": judge_note},
        "observed": {
            "tickets_analysed": brief["tickets_analysed"],
            "join_key_used": brief["join_key_used"],
            "risks_flagged": len(brief["flagged_signals"]),
            "risks_rejected_unverified": len(brief["rejected_signals"]),
        },
        "latency_ms": brief["latency_ms"],
    }


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #

def render_report_md(results: list[dict], summary: dict) -> str:
    lines = [
        "# Evaluation Report",
        "",
        f"Generated: {summary['generated_at']}",
        f"Prompt versions: `{summary['prompt_versions']}`  |  Judge: `{JUDGE_PROMPT_VERSION}`",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Total cases | {summary['total']} |",
        f"| Passed | {summary['passed']} |",
        f"| Failed | {summary['failed']} |",
        f"| Pass rate | {summary['pass_rate']:.0%} |",
        f"| Mean quality score | {summary['mean_quality']:.3f} |",
        f"| Adversarial cases | {summary['adversarial_total']} (passed: {summary['adversarial_passed']}) |",
        "",
        "## Results",
        "",
        "| Case | Task | Adversarial | Result | Quality | Latency |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| `{r['id']}` | {r['task']} | {'yes' if r['adversarial'] else 'no'} | "
            f"{'PASS' if r['passed'] else 'FAIL'} | {r['quality_score']:.2f} | {r['latency_ms']} ms |"
        )

    lines += ["", "## Failed checks", ""]
    failures = [
        (r["id"], c["check"]) for r in results for c in r["checks"] if not c["passed"]
    ]
    if failures:
        lines += [f"- `{cid}` — {check}" for cid, check in failures]
    else:
        lines.append("_None. All checks passed._")

    lines += ["", "## Case detail", ""]
    for r in results:
        lines += [f"### `{r['id']}` — {'PASS' if r['passed'] else 'FAIL'}", "", r["description"], ""]
        if r.get("error"):
            lines += [f"**Error:** `{r['error']}`", ""]
        for c in r["checks"]:
            lines.append(f"- {'x' if c['passed'] else ' '} {c['check']}".replace("- x", "- [x]").replace("-  ", "- [ ] "))
        if r.get("judge"):
            lines += ["", f"**Judge ({r['judge']['score']:.2f}):** {r['judge']['justification']}"]
        if r.get("observed"):
            lines += ["", f"**Observed:** `{json.dumps(r['observed'])}`"]
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    print("Running evaluation harness...\n")
    results: list[dict] = []

    for case in TRIAGE_CASES:
        print(f"  [task1] {case['id']} ...", end=" ", flush=True)
        r = score_triage_case(case)
        print(f"{'PASS' if r['passed'] else 'FAIL'}  (quality {r['quality_score']:.2f})")
        results.append(r)

    for case in BRIEF_CASES:
        print(f"  [task2] {case['id']} ...", end=" ", flush=True)
        r = score_brief_case(case)
        print(f"{'PASS' if r['passed'] else 'FAIL'}  (quality {r['quality_score']:.2f})")
        results.append(r)

    passed = sum(1 for r in results if r["passed"])
    adversarial = [r for r in results if r["adversarial"]]
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "prompt_versions": "triage/v1.0.0, risk/v1.0.0, brief/v1.0.0",
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "pass_rate": passed / len(results) if results else 0.0,
        "mean_quality": sum(r["quality_score"] for r in results) / len(results) if results else 0.0,
        "adversarial_total": len(adversarial),
        "adversarial_passed": sum(1 for r in adversarial if r["passed"]),
    }

    (ROOT / "eval_report.json").write_text(
        json.dumps({"summary": summary, "results": results}, indent=2), encoding="utf-8"
    )
    (ROOT / "eval_report.md").write_text(
        render_report_md(results, summary), encoding="utf-8"
    )

    print(
        f"\n{summary['passed']}/{summary['total']} passed "
        f"({summary['pass_rate']:.0%})  |  mean quality {summary['mean_quality']:.3f}"
    )
    print("Wrote eval_report.json and eval_report.md")

    # Non-zero exit on failure so CI can gate on this.
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
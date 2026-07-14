"""Task 1 — Intelligent ticket triage agent.

Pipeline:  raw ticket -> KB retrieval -> LLM classification -> schema validation
                                                             -> structured triage result

The LLM's output is never trusted directly. Every field is validated against the
enums in config.py and coerced to a safe default if the model returns something
outside the allowed set. Any correction is recorded in `validation_warnings` so
that model drift is visible rather than silent.
"""
from __future__ import annotations

import time
from typing import Optional

from src.config import CATEGORIES, URGENCIES, PRODUCTS, RESPONDER_TEAMS
from src.llm import ask_llm_json, LLMError
from src.prompts import TRIAGE_PROMPT, TRIAGE_PROMPT_VERSION
from src.retriever import build_context, search

# Category -> default team, used when the model returns an unknown team.
_TEAM_FALLBACK = {
    "Bug": "Tier-2 Support",
    "Feature Request": "Product Team",
    "How-To": "Tier-1 Support",
    "Performance": "Tier-2 Support",
    "Billing": "Billing Team",
    "Integration": "Integrations Team",
    "Onboarding": "Onboarding Team",
    "Data Loss": "Data Recovery Team",
}


def _coerce(value, allowed: list[str], default: str, field: str, warnings: list[str]) -> str:
    """Force a model-supplied value into the allowed enum, recording any correction."""
    if isinstance(value, str):
        for option in allowed:
            if value.strip().lower() == option.lower():
                return option
    warnings.append(f"{field}: model returned {value!r}, coerced to {default!r}")
    return default


def triage_ticket(subject: str, body: str, ticket_id: Optional[str] = None) -> dict:
    """Triage a single ticket. This is the callable entry point for Task 1."""
    if not (subject or "").strip() and not (body or "").strip():
        raise ValueError("Ticket must have a subject or a body.")

    started = time.perf_counter()

    # 1. Retrieve — find KB sections relevant to this ticket.
    query = f"{subject}\n{body}"
    kb_hits = search(query, top_k=3)
    kb_context = build_context(query, top_k=3)

    # 2. Generate — ask the model to classify, grounded in the retrieved context.
    prompt = TRIAGE_PROMPT.format(
        products=" | ".join(f'"{p}"' for p in PRODUCTS),
        categories=" | ".join(f'"{c}"' for c in CATEGORIES),
        urgencies=" | ".join(f'"{u}"' for u in URGENCIES),
        teams=" | ".join(f'"{t}"' for t in RESPONDER_TEAMS),
        kb_context=kb_context,
        subject=subject or "(no subject)",
        body=body or "(no body)",
    )
    raw = ask_llm_json(prompt)

    # 3. Validate — never trust the model's field values.
    warnings: list[str] = []
    category = _coerce(raw.get("category"), CATEGORIES, "How-To", "category", warnings)
    urgency = _coerce(raw.get("urgency"), URGENCIES, "P3", "urgency", warnings)
    product = _coerce(raw.get("product"), PRODUCTS + ["Unknown"], "Unknown", "product", warnings)
    team = _coerce(
        raw.get("responder_team"), RESPONDER_TEAMS,
        _TEAM_FALLBACK.get(category, "Tier-1 Support"), "responder_team", warnings,
    )

    # Anti-hallucination: the cited KB doc must be one we actually retrieved.
    matched_doc = raw.get("matched_kb_doc")
    retrieved_paths = {h["doc_path"] for h in kb_hits}
    if matched_doc and matched_doc not in retrieved_paths:
        warnings.append(f"matched_kb_doc: model cited {matched_doc!r}, not in retrieved set — dropped")
        matched_doc = None

    try:
        confidence = min(max(float(raw.get("confidence", 0.5)), 0.0), 1.0)
    except (TypeError, ValueError):
        confidence = 0.5
        warnings.append("confidence: unparseable, defaulted to 0.5")

    questions = raw.get("clarifying_questions") or []
    if not isinstance(questions, list):
        questions = []

    return {
        "ticket_id": ticket_id,
        "product": product,
        "product_area": str(raw.get("product_area") or "Unknown"),
        "category": category,
        "urgency": urgency,
        "reasoning": str(raw.get("reasoning") or ""),
        "matched_kb_doc": matched_doc,
        "kb_match_reason": raw.get("kb_match_reason") if matched_doc else None,
        "retrieved_docs": [
            {"doc_path": h["doc_path"], "heading": h["heading"], "score": h["score"]}
            for h in kb_hits
        ],
        "responder_team": team,
        "draft_response": str(raw.get("draft_response") or ""),
        "confidence": round(confidence, 2),
        "needs_human_review": confidence < 0.5,
        "clarifying_questions": [str(q) for q in questions][:4],
        "validation_warnings": warnings,
        "prompt_version": TRIAGE_PROMPT_VERSION,
        "latency_ms": round((time.perf_counter() - started) * 1000),
    }


def triage_from_dict(ticket: dict) -> dict:
    """Convenience wrapper: accepts a raw ticket dict (e.g. from tickets.json)."""
    return triage_ticket(
        subject=ticket.get("subject", ""),
        body=ticket.get("body", ""),
        ticket_id=ticket.get("ticket_id"),
    )
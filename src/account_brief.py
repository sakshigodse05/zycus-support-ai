"""Task 2 — TAM account health summariser.

Two-stage prompt chain:
  stage 1 (risk)   account signals + tickets -> churn/escalation risks, each quoted
  stage 2 (brief)  account + tickets + verified risks -> 3-section TAM brief

Determinism (a hard requirement of the task) is enforced on three levels:
  1. temperature = 0 and a fixed seed on the provider call;
  2. the 90-day window is anchored to the dataset, not to wall-clock time;
  3. tickets are sorted deterministically before being rendered into the prompt.

Every quoted risk is verified against the source text before it reaches the TAM.
An LLM that cannot be caught fabricating a quote will eventually fabricate one.
"""
from __future__ import annotations

import re
import time
from typing import List

from src.data_loader import AccountNotFoundError, get_account, get_account_tickets
from src.llm import ask_llm_json
from src.prompts import (
    BRIEF_PROMPT, BRIEF_PROMPT_VERSION,
    RISK_PROMPT, RISK_PROMPT_VERSION,
)

_SEVERITY_ORDER = {"High": 0, "Medium": 1, "Low": 2}


def _normalise(text: str) -> str:
    """Lowercase, collapse whitespace — so quote verification tolerates formatting only."""
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def _ticket_digest(tickets: List[dict], max_body_chars: int = 400) -> str:
    """Render tickets into a compact, stable block of prompt context."""
    if not tickets:
        return "(no tickets in the last 90 days)"

    lines = []
    for t in tickets:
        body = " ".join((t.get("body") or "").split())
        if len(body) > max_body_chars:
            body = body[:max_body_chars].rstrip() + "…"
        lines.append(
            f"- {t.get('ticket_id')} | {t.get('created_at', '')[:10]} | "
            f"{t.get('urgency')} | {t.get('category')} | {t.get('status')} | "
            f"CSAT: {t.get('satisfaction_score') if t.get('satisfaction_score') is not None else 'n/a'}\n"
            f"  Subject: {t.get('subject')}\n"
            f"  Body: {body}"
        )
    return "\n".join(lines)


def _verify_risks(risks: List[dict], account: dict, tickets: List[dict]) -> tuple[list, list]:
    """Drop any risk whose quote does not literally appear in the source text.

    This is the guard that makes 'justify each flag with a direct quote' real
    rather than aspirational. A quote the model invented is worse than no flag:
    a TAM would repeat it to the customer.
    """
    haystack = _normalise(
        " ".join(account.get("escalation_notes") or [])
        + " "
        + " ".join(f"{t.get('subject', '')} {t.get('body', '')}" for t in tickets)
    )

    verified, rejected = [], []
    for risk in risks:
        quote = str(risk.get("evidence_quote") or "").strip()
        if quote and _normalise(quote) in haystack:
            severity = risk.get("severity")
            verified.append({
                "signal": str(risk.get("signal") or "").strip(),
                "severity": severity if severity in _SEVERITY_ORDER else "Medium",
                "evidence_quote": quote,
                "source": str(risk.get("source") or "unknown"),
                "why_it_matters": str(risk.get("why_it_matters") or "").strip(),
            })
        else:
            rejected.append({
                "signal": risk.get("signal"),
                "unverified_quote": quote,
                "reason": "quote not found verbatim in account notes or ticket text",
            })

    verified.sort(key=lambda r: (_SEVERITY_ORDER[r["severity"]], r["signal"]))
    return verified, rejected


def generate_account_brief(account_id: str, days: int = 90) -> dict:
    """Generate a QBR-ready brief for one account. Entry point for Task 2."""
    started = time.perf_counter()

    account = get_account(account_id)              # raises AccountNotFoundError
    tickets = get_account_tickets(account_id, days=days)
    digest = _ticket_digest(tickets)

    # --- Stage 1: risk detection (quote-grounded) ---
    risk_raw = ask_llm_json(RISK_PROMPT.format(
        health_status=account.get("health_status", "Unknown"),
        usage_trend=account.get("usage_trend", "Unknown"),
        nps_score=account.get("nps_score", "not submitted"),
        renewal_date=account.get("renewal_date", "Unknown"),
        last_login_days_ago=account.get("last_login_days_ago", "Unknown"),
        seats_licensed=account.get("seats_licensed", 0),
        seats_active=account.get("seats_active", 0),
        escalation_notes="\n".join(
            f"- {n}" for n in (account.get("escalation_notes") or [])
        ) or "(none recorded)",
        ticket_digest=digest,
    ))
    risks, rejected = _verify_risks(risk_raw.get("risks") or [], account, tickets)

    # --- Stage 2: brief synthesis (grounded in verified risks only) ---
    risk_summary = "\n".join(
        f"- [{r['severity']}] {r['signal']} — evidence ({r['source']}): \"{r['evidence_quote']}\""
        for r in risks
    ) or "(no verified risk signals)"

    contact = account.get("primary_contact") or {}
    brief_raw = ask_llm_json(BRIEF_PROMPT.format(
        company=account.get("company", "Unknown"),
        account_id=account_id,
        tam=account.get("tam", "Unassigned"),
        plan_tier=account.get("plan_tier", "Unknown"),
        arr_usd=account.get("arr_usd", 0),
        industry=account.get("industry", "Unknown"),
        region=account.get("region", "Unknown"),
        health_status=account.get("health_status", "Unknown"),
        usage_trend=account.get("usage_trend", "Unknown"),
        nps_score=account.get("nps_score", "not submitted"),
        seats_active=account.get("seats_active", 0),
        seats_licensed=account.get("seats_licensed", 0),
        products=", ".join(account.get("products") or []) or "None recorded",
        customer_since=account.get("customer_since", "Unknown"),
        renewal_date=account.get("renewal_date", "Unknown"),
        last_qbr_date=account.get("last_qbr_date", "Unknown"),
        primary_contact=f"{contact.get('name', 'Unknown')} ({contact.get('title', 'Unknown')})",
        open_tickets=account.get("open_tickets", 0),
        p1_tickets_last_30d=account.get("p1_tickets_last_30d", 0),
        ticket_digest=digest,
        risk_summary=risk_summary,
    ))

    return {
        "account_id": account_id,
        "company": account.get("company"),
        "tam": account.get("tam"),
        "health_status": account.get("health_status"),
        "renewal_date": account.get("renewal_date"),
        "arr_usd": account.get("arr_usd"),
        "tickets_analysed": len(tickets),
        "join_key_used": tickets[0]["_join_key"] if tickets else "none",
        "executive_summary": str(brief_raw.get("executive_summary") or "").strip(),
        "open_risks": [str(r) for r in (brief_raw.get("open_risks") or [])],
        "flagged_signals": risks,
        "rejected_signals": rejected,
        "talking_points": [str(p) for p in (brief_raw.get("talking_points") or [])],
        "prompt_versions": {
            "risk": RISK_PROMPT_VERSION,
            "brief": BRIEF_PROMPT_VERSION,
        },
        "latency_ms": round((time.perf_counter() - started) * 1000),
    }


def render_markdown(brief: dict) -> str:
    """Human-readable brief — what the TAM actually reads."""
    lines = [
        f"# Account Brief — {brief['company']} ({brief['account_id']})",
        "",
        f"**TAM:** {brief['tam']}  |  **Health:** {brief['health_status']}  |  "
        f"**ARR:** ${brief['arr_usd']:,}  |  **Renewal:** {brief['renewal_date']}",
        f"*Based on {brief['tickets_analysed']} tickets from the last 90 days.*",
        "",
        "## 1. Executive Summary",
        brief["executive_summary"] or "_Not available._",
        "",
        "## 2. Open Risks & Flagged Issues",
    ]

    if brief["flagged_signals"]:
        for r in brief["flagged_signals"]:
            lines += [
                f"- **[{r['severity']}] {r['signal']}**",
                f"  - Evidence ({r['source']}): \"{r['evidence_quote']}\"",
                f"  - Why it matters: {r['why_it_matters']}",
            ]
    else:
        lines.append("- No verified risk signals in the last 90 days.")

    if brief["rejected_signals"]:
        lines += ["", f"> {len(brief['rejected_signals'])} signal(s) were discarded "
                      "because the supporting quote could not be verified against the source text."]

    lines += ["", "## 3. Recommended Talking Points"]
    lines += [f"{i}. {p}" for i, p in enumerate(brief["talking_points"], 1)] or ["_None generated._"]

    return "\n".join(lines)
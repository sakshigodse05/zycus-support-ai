"""Test cases for the evaluation harness.

Each case declares acceptance criteria rather than a single golden string —
LLM output is not byte-stable, so asserting on exact text produces a brittle
suite that fails for the wrong reasons. We assert on the things that must hold:
enum validity, urgency band, routing, grounding, and refusal-to-guess.

Every task includes an adversarial case (marked `adversarial: True`).
"""

# --------------------------------------------------------------------------- #
# TASK 1 — triage
# --------------------------------------------------------------------------- #
TRIAGE_CASES = [
    {
        "id": "T1-01-p1-outage",
        "description": "Production outage, no workaround, many users blocked -> must be P1.",
        "input": {
            "subject": "CRITICAL: DataBridge Pro Connectors pipeline down in production",
            "body": (
                "Our production Connectors pipeline has been completely down since 03:00 UTC. "
                "Error: 'ERR_CONNECTION_TIMEOUT after 30s'. All 200 engineers are blocked and "
                "no data is flowing. We have no workaround. Business is stopped."
            ),
        },
        "expect": {
            "urgency_in": ["P1"],
            "category_in": ["Bug", "Performance", "Integration"],
            "product": "DataBridge Pro",
            "min_confidence": 0.6,
            "requires_kb_match": True,
            "draft_response_min_chars": 80,
        },
        "adversarial": False,
    },
    {
        "id": "T1-02-billing-invoice",
        "description": "Invoice question -> Billing category, Billing Team, low urgency.",
        "input": {
            "subject": "Question about our latest invoice",
            "body": (
                "We received invoice INV-2291 and the seat count looks higher than what we "
                "agreed. Could someone from billing explain how seats are counted? "
                "Not urgent, no one is blocked."
            ),
        },
        "expect": {
            "urgency_in": ["P3", "P4"],
            "category_in": ["Billing"],
            "responder_team_in": ["Billing Team"],
            "min_confidence": 0.6,
        },
        "adversarial": False,
    },
    {
        "id": "T1-03-feature-request",
        "description": "Missing functionality with a workaround -> Feature Request, Product Team.",
        "input": {
            "subject": "Request: bulk export in AnalyticsHub",
            "body": (
                "AnalyticsHub only lets us export one dashboard at a time. We'd like to select "
                "several and export them together. We can do it manually for now, it's just slow."
            ),
        },
        "expect": {
            "urgency_in": ["P3", "P4"],
            "category_in": ["Feature Request"],
            "responder_team_in": ["Product Team"],
        },
        "adversarial": False,
    },
    {
        "id": "T1-04-howto-sso",
        "description": "Guidance request -> How-To, low urgency, should ground in the SSO doc.",
        "input": {
            "subject": "How do I configure SAML SSO for SecureVault?",
            "body": (
                "We're planning our SSO rollout next month and want to understand the setup steps "
                "for SAML with SecureVault. Nothing is broken — we just need the documentation."
            ),
        },
        "expect": {
            "urgency_in": ["P3", "P4"],
            "category_in": ["How-To", "Onboarding"],
            "requires_kb_match": True,
        },
        "adversarial": False,
    },
    {
        "id": "T1-05-data-loss",
        "description": "Missing records -> Data Loss, high urgency, Data Recovery Team.",
        "input": {
            "subject": "URGENT: records missing from SecureVault after sync",
            "body": (
                "After last night's sync roughly 4,000 records are missing from SecureVault. "
                "We cannot recover them and our operations team is at a standstill. "
                "Please escalate immediately."
            ),
        },
        "expect": {
            "urgency_in": ["P1", "P2"],
            "category_in": ["Data Loss", "Bug"],
            "responder_team_in": ["Data Recovery Team", "Tier-2 Support"],
        },
        "adversarial": False,
    },
    {
        "id": "T1-06-ADVERSARIAL-vague",
        "description": (
            "ADVERSARIAL — near-empty, ambiguous ticket. The system must NOT invent a "
            "confident classification. It must lower confidence, flag for human review, "
            "ask clarifying questions, and refuse to cite a KB doc it cannot support."
        ),
        "input": {
            "subject": "it's broken",
            "body": "doesn't work. pls fix asap!!!",
        },
        "expect": {
            "max_confidence": 0.5,
            "requires_human_review": True,
            "min_clarifying_questions": 1,
            "forbid_kb_match": True,
        },
        "adversarial": True,
    },
]

# --------------------------------------------------------------------------- #
# TASK 2 — account brief
# --------------------------------------------------------------------------- #
BRIEF_CASES = [
    {
        "id": "T2-01-high-volume-account",
        "description": "Account with 17 tickets in 90d -> substantive brief, all quotes verified.",
        "account_id": "ACC-3033",
        "expect": {
            "min_tickets_analysed": 5,
            "min_summary_sentences": 3,
            "max_summary_sentences": 6,
            "min_talking_points": 3,
            "max_talking_points": 5,
            "all_quotes_verified": True,
        },
        "adversarial": False,
    },
    {
        "id": "T2-02-at-risk-account",
        "description": "At Risk account -> must surface at least one risk signal with a quote.",
        "account_id": "ACC-3336",
        "expect": {
            "min_summary_sentences": 3,
            "min_talking_points": 3,
            "all_quotes_verified": True,
        },
        "adversarial": False,
    },
    {
        "id": "T2-03-determinism",
        "description": "Same account run twice -> byte-identical brief (hard task requirement).",
        "account_id": "ACC-3033",
        "expect": {"deterministic": True},
        "adversarial": False,
    },
    {
        "id": "T2-04-quote-grounding",
        "description": "Every flagged risk quote must appear verbatim in the source text.",
        "account_id": "ACC-3033",
        "expect": {"all_quotes_verified": True, "no_fabricated_sources": True},
        "adversarial": False,
    },
    {
        "id": "T2-05-structure",
        "description": "Output must always carry all three required sections.",
        "account_id": "ACC-3336",
        "expect": {"has_all_three_sections": True},
        "adversarial": False,
    },
    {
        "id": "T2-06-ADVERSARIAL-unknown-account",
        "description": (
            "ADVERSARIAL — account id that does not exist in accounts.json. The system must "
            "raise AccountNotFoundError cleanly, not hallucinate a brief for a fictional customer."
        ),
        "account_id": "ACC-0000",
        "expect": {"raises_account_not_found": True},
        "adversarial": True,
    },
]
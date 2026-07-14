# Evaluation Report

Generated: 2026-07-14T07:11:28+00:00
Prompt versions: `triage/v1.0.0, risk/v1.0.0, brief/v1.0.0`  |  Judge: `judge/v1.0.0`

## Summary

| Metric | Value |
|---|---|
| Total cases | 12 |
| Passed | 12 |
| Failed | 0 |
| Pass rate | 100% |
| Mean quality score | 0.919 |
| Adversarial cases | 2 (passed: 2) |

## Results

| Case | Task | Adversarial | Result | Quality | Latency |
|---|---|---|---|---|---|
| `T1-01-p1-outage` | task1 | no | PASS | 0.95 | 1752 ms |
| `T1-02-billing-invoice` | task1 | no | PASS | 0.95 | 1733 ms |
| `T1-03-feature-request` | task1 | no | PASS | 0.85 | 21570 ms |
| `T1-04-howto-sso` | task1 | no | PASS | 0.90 | 9771 ms |
| `T1-05-data-loss` | task1 | no | PASS | 0.95 | 9570 ms |
| `T1-06-ADVERSARIAL-vague` | task1 | yes | PASS | 0.80 | 9662 ms |
| `T2-01-high-volume-account` | task2 | no | PASS | 0.93 | 49 ms |
| `T2-02-at-risk-account` | task2 | no | PASS | 0.93 | 2551 ms |
| `T2-03-determinism` | task2 | no | PASS | 0.93 | 2 ms |
| `T2-04-quote-grounding` | task2 | no | PASS | 0.93 | 2 ms |
| `T2-05-structure` | task2 | no | PASS | 0.93 | 22 ms |
| `T2-06-ADVERSARIAL-unknown-account` | task2 | yes | PASS | 1.00 | 0 ms |

## Failed checks

_None. All checks passed._

## Case detail

### `T1-01-p1-outage` — PASS

Production outage, no workaround, many users blocked -> must be P1.

- [x] category_is_valid_enum
- [x] urgency_is_valid_enum
- [x] responder_team_is_valid_enum
- [x] reasoning_present
- [x] urgency in ['P1']
- [x] category in ['Bug', 'Performance', 'Integration']
- [x] product == DataBridge Pro
- [x] confidence >= 0.6
- [x] cites a knowledge-base doc
- [x] draft response >= 80 chars
- [x] cited doc was actually retrieved (no hallucination)

**Judge (0.80):** The response acknowledges the specific issue, mentions a concrete next step, and requests additional details without inventing facts or promising a fix date. However, the phrase 'we will provide updates as soon as possible' could be seen as slightly vague.

**Observed:** `{"category": "Bug", "urgency": "P1", "product": "DataBridge Pro", "responder_team": "Tier-2 Support", "confidence": 0.9, "matched_kb_doc": "troubleshooting/performance-and-integrations.md"}`

### `T1-02-billing-invoice` — PASS

Invoice question -> Billing category, Billing Team, low urgency.

- [x] category_is_valid_enum
- [x] urgency_is_valid_enum
- [x] responder_team_is_valid_enum
- [x] reasoning_present
- [x] urgency in ['P3', 'P4']
- [x] category in ['Billing']
- [x] team in ['Billing Team']
- [x] confidence >= 0.6
- [x] cited doc was actually retrieved (no hallucination)

**Judge (0.80):** The response acknowledges the specific issue with the invoice and seat count, and states a concrete next step by mentioning that the billing team will review the account and provide a detailed explanation. However, the phrase 'we will be in touch with you shortly' could be seen as slightly vague, as it does not specify a clear timeline or method of follow-up.

**Observed:** `{"category": "Billing", "urgency": "P4", "product": "Unknown", "responder_team": "Billing Team", "confidence": 0.8, "matched_kb_doc": "billing/billing-and-plans.md"}`

### `T1-03-feature-request` — PASS

Missing functionality with a workaround -> Feature Request, Product Team.

- [x] category_is_valid_enum
- [x] urgency_is_valid_enum
- [x] responder_team_is_valid_enum
- [x] reasoning_present
- [x] urgency in ['P3', 'P4']
- [x] category in ['Feature Request']
- [x] team in ['Product Team']
- [x] cited doc was actually retrieved (no hallucination)

**Judge (0.40):** The response acknowledges the customer's issue and mentions a next step (reviewing the request), but it is somewhat generic and does not provide a specific or concrete action plan. It also uses vague phrases like 'consider it for future development' and 'keep you updated on any progress' without providing a clear timeline or point of contact for follow-up.

**Observed:** `{"category": "Feature Request", "urgency": "P4", "product": "AnalyticsHub", "responder_team": "Product Team", "confidence": 0.9, "matched_kb_doc": null}`

### `T1-04-howto-sso` — PASS

Guidance request -> How-To, low urgency, should ground in the SSO doc.

- [x] category_is_valid_enum
- [x] urgency_is_valid_enum
- [x] responder_team_is_valid_enum
- [x] reasoning_present
- [x] urgency in ['P3', 'P4']
- [x] category in ['How-To', 'Onboarding']
- [x] cites a knowledge-base doc
- [x] cited doc was actually retrieved (no hallucination)

**Judge (0.60):** The response acknowledges the customer's issue with SAML SSO configuration for SecureVault and mentions providing guidance and relevant resources. However, it is somewhat generic and does not specify a concrete next step beyond 'responding with more information'.

**Observed:** `{"category": "How-To", "urgency": "P4", "product": "SecureVault", "responder_team": "Tier-1 Support", "confidence": 0.9, "matched_kb_doc": "products/securevault.md"}`

### `T1-05-data-loss` — PASS

Missing records -> Data Loss, high urgency, Data Recovery Team.

- [x] category_is_valid_enum
- [x] urgency_is_valid_enum
- [x] responder_team_is_valid_enum
- [x] reasoning_present
- [x] urgency in ['P1', 'P2']
- [x] category in ['Data Loss', 'Bug']
- [x] team in ['Data Recovery Team', 'Tier-2 Support']
- [x] cited doc was actually retrieved (no hallucination)

**Judge (0.80):** The response acknowledges the specific issue with missing records in SecureVault, expresses understanding of the urgency, and states a concrete next step to investigate the cause and work on a recovery plan. However, the phrase 'we will be in touch soon' is somewhat vague and could be improved for clarity.

**Observed:** `{"category": "Data Loss", "urgency": "P1", "product": "SecureVault", "responder_team": "Data Recovery Team", "confidence": 0.9, "matched_kb_doc": null}`

### `T1-06-ADVERSARIAL-vague` — PASS

ADVERSARIAL — near-empty, ambiguous ticket. The system must NOT invent a confident classification. It must lower confidence, flag for human review, ask clarifying questions, and refuse to cite a KB doc it cannot support.

- [x] category_is_valid_enum
- [x] urgency_is_valid_enum
- [x] responder_team_is_valid_enum
- [x] reasoning_present
- [x] confidence <= 0.5
- [x] flagged for human review
- [x] asks >= 1 clarifying question(s)
- [x] refuses to cite a KB doc it cannot support
- [x] cited doc was actually retrieved (no hallucination)

**Judge (0.20):** The response is generic and does not acknowledge a specific issue. It only asks for more information, which is a reasonable next step, but the language used is vague and does not provide any concrete details about how the issue will be addressed.

**Observed:** `{"category": "Bug", "urgency": "P4", "product": "Unknown", "responder_team": "Tier-1 Support", "confidence": 0.2, "matched_kb_doc": null}`

### `T2-01-high-volume-account` — PASS

Account with 17 tickets in 90d -> substantive brief, all quotes verified.

- [x] executive_summary present
- [x] talking_points present
- [x] risk section present (may be empty list)
- [x] analysed >= 5 tickets
- [x] summary is 3-6 sentences (got 3)
- [x] 3-5 talking points (got 3)
- [x] every flagged risk carries a verified verbatim quote

**Judge (0.70):** The first two talking points are specific and actionable, referencing concrete issues, numbers, and events, such as the 5300 missing records and the 396 affected users. However, the third point is more generic and open-ended, which prevents the overall score from being higher.

**Observed:** `{"tickets_analysed": 17, "join_key_used": "company", "risks_flagged": 3, "risks_rejected_unverified": 1}`

### `T2-02-at-risk-account` — PASS

At Risk account -> must surface at least one risk signal with a quote.

- [x] executive_summary present
- [x] talking_points present
- [x] risk section present (may be empty list)
- [x] summary is 3-99 sentences (got 5)
- [x] 3-99 talking points (got 3)
- [x] every flagged risk carries a verified verbatim quote

**Judge (0.70):** The output references specific issues like 'DataBridge Pro slowdown' and '7 open tickets', providing concrete context for the talking points, but could be more detailed with exact ticket numbers or events.

**Observed:** `{"tickets_analysed": 1, "join_key_used": "account_id", "risks_flagged": 3, "risks_rejected_unverified": 0}`

### `T2-03-determinism` — PASS

Same account run twice -> byte-identical brief (hard task requirement).

- [x] executive_summary present
- [x] talking_points present
- [x] risk section present (may be empty list)
- [x] identical output on re-run (determinism)

**Judge (0.70):** The first two talking points are specific and actionable, referencing concrete issues, numbers, and events, such as the 5300 missing records and the 396 affected users. However, the third point is more generic and open-ended, which prevents the overall score from being higher.

**Observed:** `{"tickets_analysed": 17, "join_key_used": "company", "risks_flagged": 3, "risks_rejected_unverified": 1}`

### `T2-04-quote-grounding` — PASS

Every flagged risk quote must appear verbatim in the source text.

- [x] executive_summary present
- [x] talking_points present
- [x] risk section present (may be empty list)
- [x] every flagged risk carries a verified verbatim quote
- [x] every risk source is a real ticket id or escalation_note

**Judge (0.70):** The first two talking points are specific and actionable, referencing concrete issues, numbers, and events, such as the 5300 missing records and the 396 affected users. However, the third point is more generic and open-ended, which prevents the overall score from being higher.

**Observed:** `{"tickets_analysed": 17, "join_key_used": "company", "risks_flagged": 3, "risks_rejected_unverified": 1}`

### `T2-05-structure` — PASS

Output must always carry all three required sections.

- [x] executive_summary present
- [x] talking_points present
- [x] risk section present (may be empty list)
- [x] all three required sections present

**Judge (0.70):** The output references specific issues like 'DataBridge Pro slowdown' and '7 open tickets', providing concrete context for the talking points, but could be more detailed with exact ticket numbers or events.

**Observed:** `{"tickets_analysed": 1, "join_key_used": "account_id", "risks_flagged": 3, "risks_rejected_unverified": 0}`

### `T2-06-ADVERSARIAL-unknown-account` — PASS

ADVERSARIAL — account id that does not exist in accounts.json. The system must raise AccountNotFoundError cleanly, not hallucinate a brief for a fictional customer.

- [x] raises AccountNotFoundError for unknown id

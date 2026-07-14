# Support & TAM AI Toolkit

Internal AI tooling for two customer-facing units: **Technical Support** (ticket triage) and
**Technical Account Management** (account health briefs), with an evaluation harness that gates
both against regression.

| Task | Deliverable | Status |
|---|---|---|
| 1 | Intelligent ticket triage agent (RAG + structured output + FastAPI) | ✅ |
| 2 | TAM account health summariser (prompt chain, deterministic, quote-verified) | ✅ |
| 3 | Evaluation harness (12 cases, rule-based gates + LLM-as-judge) | ✅ |
| 4 | Design note | ✅ (below) |
| Bonus | Streamlit UI · prompt versioning · CI on every commit | ✅ |

**Current eval result: 12/12 passing, mean quality 0.919.** See [`eval_report.md`](eval_report.md).

---

## Setup

```bash
git clone https://github.com/sakshigodse05/zycus-support-ai.git
cd zycus-support-ai

python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS / Linux

pip install -r requirements.txt

cp .env.example .env           # then add your API key
```

The toolkit is provider-agnostic. Set `LLM_PROVIDER` to `groq` (default) or `gemini` in `.env`.
A free Groq key takes about a minute: <https://console.groq.com/keys>.

---

## Sample runs

Every command is routed through the single entry point, `main.py`.

### Task 1 — triage a ticket

```bash
python main.py triage
python main.py triage --subject "SSO login failing" --body "New joiners cannot authenticate."
python main.py triage --file data/sample_ticket.json
```

```json
{
  "product": "DataBridge Pro",
  "product_area": "Connectors",
  "category": "Bug",
  "urgency": "P1",
  "reasoning": "Production pipeline down since 03:00 UTC, 200 engineers blocked, no workaround...",
  "matched_kb_doc": "troubleshooting/performance-and-integrations.md",
  "responder_team": "Tier-2 Support",
  "draft_response": "Dear customer, thank you for reporting the issue with your production...",
  "confidence": 0.9,
  "needs_human_review": false,
  "prompt_version": "triage/v1.0.0",
  "latency_ms": 1548
}
```

### Task 2 — generate an account brief

```bash
python main.py brief --account ACC-3033
python main.py brief --account ACC-3033 --json
```

Produces a three-section brief: executive summary, open risks (each with a **verified verbatim
quote** and its ticket id), and recommended talking points.

### Task 3 — run the eval harness

```bash
python main.py evals        # writes eval_report.json and eval_report.md
```

### REST API and UI

```bash
python main.py serve        # http://127.0.0.1:8000/docs
python main.py ui           # Streamlit UI for non-technical users
```

---

## Architecture

```
raw ticket ──► TF-IDF retrieval ──► LLM (JSON mode) ──► enum validation ──► triage result
                (knowledge-base)                         + grounding check

account id ──► account + 90d tickets ──► LLM: risk detection ──► quote verification
                                              │                        │
                                              └──► LLM: brief synthesis ◄┘  ──► TAM brief
```

| File | Role |
|---|---|
| `src/config.py` | Single source of truth for paths, keys, enums |
| `src/llm.py` | Provider-agnostic LLM client; JSON coercion, response cache, 429 backoff |
| `src/retriever.py` | TF-IDF retrieval over the knowledge base |
| `src/prompts.py` | All prompts, each with a version id and changelog |
| `src/triage.py` | **Task 1** |
| `src/account_brief.py` | **Task 2** |
| `src/data_loader.py` | Dataset loading and the ticket↔account join |
| `evals/` | **Task 3** |

### Two decisions worth calling out

**Retrieval is TF-IDF, not embeddings.** The corpus is nine markdown documents (~680 lines).
At that size a TF-IDF + cosine search is faster, free, fully offline and deterministic, with no
measurable quality loss over an embedding model and vector store. A `min_score` floor means an
unintelligible ticket returns *no* document rather than the least-bad one — a confidently wrong
help article is worse than none. Swapping to embeddings later touches only `retriever.py`.

**The dataset's `account_id` join is broken, deliberately.** Tickets reference 484 distinct
account ids; `accounts.json` holds 50; only **four** overlap. Joining on id alone yields an empty
brief for 46 of 50 accounts. The `company` field, however, joins cleanly for all 50. The loader
therefore joins on `account_id` first and falls back to an exact company match, reporting the key
it actually used (`join_key_used`) so the degradation is visible rather than silent.

---

# Design note

## Failure modes

**1 — Hallucinated grounding.** The highest-consequence failure is not a misrouted ticket; it is a
fabricated citation. In Task 2 a TAM carries the brief into a customer meeting, so an invented
quote gets repeated *to the customer*. Two guards exist. In triage, a `matched_kb_doc` that was not
in the retrieved set is dropped — the model cannot cite a document the retriever never surfaced. In
the brief, every risk quote is checked verbatim against the source text and discarded if absent; the
count of discards is surfaced in the output. This fires in practice: on `ACC-3033` the model
produced five risks and one was rejected as unverifiable. **Detection:** the rejection rate is a
first-class metric; a rising rate means the prompt or the model has drifted. **Mitigation:** the
guard already fails closed — an unverifiable claim never reaches a human.

**2 — Silent schema drift.** A model upgrade starts returning `"Critical"` instead of `"P1"`, and
downstream routing quietly breaks. Every field is coerced against the enums in `config.py` and every
correction is recorded in `validation_warnings`. **Detection:** alert on non-empty warnings.
**Mitigation:** the eval harness asserts enum validity on every case, so a bad model or prompt fails
CI before it ships.

**3 — Overconfidence on ambiguous input.** Real tickets say "it's broken, pls fix". A system that
confidently assigns P2 and routes it is worse than one that admits it doesn't know. The prompt
requires a confidence score; below 0.5 the ticket sets `needs_human_review` and returns clarifying
questions instead of a guess. **Detection:** track the human-review rate. **Mitigation:** it is an
explicit adversarial eval case (`T1-06`) and would fail CI if the behaviour regressed.

## Latency vs quality

Task 2 uses a **two-call prompt chain** — risk detection, then brief synthesis — rather than one
call producing everything. One call is roughly twice as fast; it also produces vaguer risks and
looser quotes, because a prompt asked to do two jobs does neither strictly. Splitting them lets the
risk stage enforce a hard rule ("if you cannot quote it verbatim, do not flag it") that the
verification step can then check. For a QBR brief a TAM requests minutes before a meeting, ~4s is
irrelevant and correctness is everything, so the trade is obviously right.

**If latency were the hard constraint** (e.g. real-time triage on ticket submission at p95 < 1s):
collapse the chain to one call, run retrieval and the LLM call concurrently, stream the draft
response token-by-token so the agent starts reading immediately, and move to a smaller model for
classification while reserving the large model for the draft reply. Cold triage is currently
**~1.5s**; the response cache already makes the repeat path effectively instant.

## Data sensitivity

Ticket bodies and escalation notes contain names, titles, company identities and operational
detail — all of which currently leave the process to a third-party API. Three things follow.

The design deliberately **minimises what is sent**: retrieval is local (TF-IDF, no embedding API),
ticket bodies are truncated in the brief digest, and only the fields a task actually needs are
included. Nothing beyond the prompt ever leaves.

Secrets never enter the repository: `.env` is gitignored from the first commit, `.env.example`
documents the variable names only, and CI runs on a dummy key.

**What I would add before production:** a PII redaction pass between the data layer and the LLM
client — names, emails and account identifiers replaced by stable pseudonyms (`CONTACT_1`), rehydrated
on the way out — so the provider never sees them. Because every model call already funnels through
`ask_llm()`, that is a single choke point, not a refactor. For a genuinely sensitive tenant the
`LLM_PROVIDER` abstraction allows a self-hosted model with no code change.

## Scaling

At 10× volume (5,000 tickets), the pieces fail in a specific order.

**The provider rate limit breaks first** — and already does: the free tier caps at 12,000 tokens per
minute, which four brief calls exhaust. Mitigated today by an on-disk response cache and exponential
backoff; at scale, triage moves to a queue with worker concurrency tuned to the token budget, not
to CPU.

**Retrieval holds far longer than expected.** TF-IDF scales with the *knowledge base*, not the
ticket volume — 5,000 tickets against nine documents is unchanged. It is the KB growing past a few
thousand chunks that forces embeddings plus a vector store.

**Cost scales linearly and becomes the real constraint.** Two LLM calls per brief × 50 accounts is
trivial; per-ticket triage at 5,000 tickets is not. The mitigation is tiering: a cheap classifier
for the ~70% of tickets that are unambiguous, escalating only low-confidence cases to the large
model — for which the confidence score already exists.

**The eval harness is what makes any of this safe to change.** All 12 cases pass today, but the
value is not the green ticks; it is that the suite turns red the moment a prompt change breaks
grounding, determinism, or enum validity. It is a regression gate, not a scoreboard.

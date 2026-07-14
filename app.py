"""Thin Streamlit UI for the Support & TAM AI toolkit (bonus).

Deliberately built for the non-technical user: a support agent pastes a ticket
and gets a routing decision plus a sendable draft; a TAM picks an account and
gets a brief they can walk into a meeting with. No JSON is shown by default —
raw payloads are tucked behind expanders for the engineers.

Run:  python main.py ui     (or: streamlit run app.py)
"""
from __future__ import annotations

import streamlit as st

from src.account_brief import generate_account_brief, render_markdown
from src.data_loader import AccountNotFoundError, get_account, list_account_ids
from src.llm import LLMError
from src.triage import triage_ticket

st.set_page_config(page_title="Support & TAM AI Toolkit", page_icon="🎧", layout="wide")

URGENCY_COLOUR = {"P1": "🔴", "P2": "🟠", "P3": "🟡", "P4": "🟢"}
SEVERITY_COLOUR = {"High": "🔴", "Medium": "🟠", "Low": "🟡"}

st.title("Support & TAM AI Toolkit")
st.caption("Ticket triage for Support · Account health briefs for TAMs")

tab_triage, tab_brief = st.tabs(["🎫  Ticket Triage", "📊  Account Brief"])


# --------------------------------------------------------------------------- #
# Task 1 — Triage
# --------------------------------------------------------------------------- #
with tab_triage:
    st.subheader("Triage an incoming ticket")

    col_form, col_result = st.columns([1, 1.3])

    with col_form:
        subject = st.text_input(
            "Subject",
            value="CRITICAL: DataBridge Pro Connectors pipeline down in production",
        )
        body = st.text_area(
            "Ticket body",
            height=220,
            value=(
                "Our production Connectors pipeline has been down since 03:00 UTC.\n"
                "Error: 'ERR_CONNECTION_TIMEOUT after 30s'.\n"
                "200 engineers are blocked and there is no workaround."
            ),
        )
        run = st.button("Triage ticket", type="primary", use_container_width=True)

    with col_result:
        if run:
            if not subject.strip() and not body.strip():
                st.warning("Enter a subject or a body first.")
            else:
                try:
                    with st.spinner("Retrieving knowledge base and classifying…"):
                        r = triage_ticket(subject=subject, body=body)
                except LLMError as exc:
                    st.error(f"The model is unavailable right now: {exc}")
                else:
                    if r["needs_human_review"]:
                        st.warning(
                            f"**Low confidence ({r['confidence']:.0%}) — flagged for human review.** "
                            "The ticket is too vague to classify reliably."
                        )

                    a, b, c = st.columns(3)
                    a.metric("Urgency", f"{URGENCY_COLOUR.get(r['urgency'], '')} {r['urgency']}")
                    b.metric("Category", r["category"])
                    c.metric("Confidence", f"{r['confidence']:.0%}")

                    st.markdown(f"**Route to:** {r['responder_team']}")
                    st.markdown(f"**Product:** {r['product']} — {r['product_area']}")

                    st.markdown("**Why:**")
                    st.info(r["reasoning"])

                    if r["matched_kb_doc"]:
                        st.markdown("**Matching knowledge-base article**")
                        st.success(f"`{r['matched_kb_doc']}` — {r['kb_match_reason']}")
                    else:
                        st.markdown("**Matching knowledge-base article**")
                        st.info("No article confidently matches this ticket.")

                    if r["clarifying_questions"]:
                        st.markdown("**Ask the customer:**")
                        for q in r["clarifying_questions"]:
                            st.markdown(f"- {q}")

                    st.markdown("**Draft first response** — edit, then send")
                    st.text_area("Draft", value=r["draft_response"], height=180,
                                 label_visibility="collapsed")

                    with st.expander("Engineering detail (retrieval scores, raw payload)"):
                        st.write(f"Prompt version: `{r['prompt_version']}` · "
                                 f"Latency: {r['latency_ms']} ms")
                        st.dataframe(r["retrieved_docs"], use_container_width=True)
                        if r["validation_warnings"]:
                            st.warning("Validation warnings: " + "; ".join(r["validation_warnings"]))
                        st.json(r)


# --------------------------------------------------------------------------- #
# Task 2 — Account brief
# --------------------------------------------------------------------------- #
with tab_brief:
    st.subheader("Generate a QBR account brief")

    ids = list_account_ids()
    labels = {aid: f"{get_account(aid)['company']} ({aid})" for aid in ids}
    default = ids.index("ACC-3033") if "ACC-3033" in ids else 0

    account_id = st.selectbox(
        "Account", ids, index=default, format_func=lambda a: labels[a],
    )

    if st.button("Generate brief", type="primary"):
        try:
            with st.spinner("Reading account history and 90 days of tickets…"):
                brief = generate_account_brief(account_id)
        except AccountNotFoundError:
            st.error("That account does not exist.")
        except LLMError as exc:
            st.error(f"The model is unavailable right now: {exc}")
        else:
            a, b, c, d = st.columns(4)
            a.metric("Health", brief["health_status"])
            b.metric("ARR", f"${brief['arr_usd']:,}")
            c.metric("Renewal", brief["renewal_date"])
            d.metric("Tickets (90d)", brief["tickets_analysed"])

            st.markdown("### 1. Executive summary")
            st.write(brief["executive_summary"])

            st.markdown("### 2. Open risks & flagged issues")
            if brief["flagged_signals"]:
                for r in brief["flagged_signals"]:
                    icon = SEVERITY_COLOUR.get(r["severity"], "")
                    with st.container(border=True):
                        st.markdown(f"{icon} **{r['signal']}** — {r['severity']}")
                        st.markdown(f"> {r['evidence_quote']}")
                        st.caption(f"Source: {r['source']} · {r['why_it_matters']}")
            else:
                st.success("No verified risk signals in the last 90 days.")

            if brief["rejected_signals"]:
                st.caption(
                    f"⚠️ {len(brief['rejected_signals'])} signal(s) were discarded: the model's "
                    "supporting quote could not be found verbatim in the source text."
                )

            st.markdown("### 3. Recommended talking points")
            for i, point in enumerate(brief["talking_points"], 1):
                st.markdown(f"**{i}.** {point}")

            st.download_button(
                "Download brief (Markdown)",
                data=render_markdown(brief),
                file_name=f"brief-{account_id}.md",
                mime="text/markdown",
            )

            with st.expander("Engineering detail"):
                st.write(
                    f"Join key used: `{brief['join_key_used']}` · "
                    f"Prompts: `{brief['prompt_versions']}` · "
                    f"Latency: {brief['latency_ms']} ms"
                )
                st.json(brief)
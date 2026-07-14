"""Single entry point for the Support & TAM AI toolkit.

    python main.py triage --file data/sample_ticket.json
    python main.py triage --subject "..." --body "..."
    python main.py brief --account ACC-3033
    python main.py brief --account ACC-3033 --json
    python main.py evals
    python main.py serve
    python main.py ui
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys


def cmd_triage(args: argparse.Namespace) -> int:
    from src.triage import triage_from_dict, triage_ticket

    if args.file:
        ticket = json.loads(open(args.file, encoding="utf-8").read())
        result = triage_from_dict(ticket)
    elif args.subject or args.body:
        result = triage_ticket(subject=args.subject or "", body=args.body or "")
    else:
        # Default demo ticket so `python main.py triage` always does something.
        result = triage_ticket(
            subject="CRITICAL: DataBridge Pro Connectors pipeline down in production",
            body=(
                "Our production Connectors pipeline has been down since 03:00 UTC. "
                "Error: 'ERR_CONNECTION_TIMEOUT after 30s'. 200 engineers are blocked "
                "and there is no workaround."
            ),
        )

    print(json.dumps(result, indent=2))
    return 0


def cmd_brief(args: argparse.Namespace) -> int:
    from src.account_brief import generate_account_brief, render_markdown
    from src.data_loader import AccountNotFoundError

    try:
        brief = generate_account_brief(args.account)
    except AccountNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(brief, indent=2) if args.json else render_markdown(brief))
    return 0


def cmd_evals(_: argparse.Namespace) -> int:
    from evals.run_evals import main as run_evals
    return run_evals()


def cmd_serve(_: argparse.Namespace) -> int:
    return subprocess.call([sys.executable, "-m", "uvicorn", "src.api:app", "--reload"])


def cmd_ui(_: argparse.Namespace) -> int:
    return subprocess.call([sys.executable, "-m", "streamlit", "run", "app.py"])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="AI toolkit for Technical Support and TAM teams.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_triage = sub.add_parser("triage", help="Task 1 — triage a support ticket")
    p_triage.add_argument("--file", help="Path to a ticket JSON file")
    p_triage.add_argument("--subject", help="Ticket subject line")
    p_triage.add_argument("--body", help="Ticket body text")
    p_triage.set_defaults(func=cmd_triage)

    p_brief = sub.add_parser("brief", help="Task 2 — generate a TAM account brief")
    p_brief.add_argument("--account", required=True, help="Account id, e.g. ACC-3033")
    p_brief.add_argument("--json", action="store_true", help="Emit raw JSON instead of Markdown")
    p_brief.set_defaults(func=cmd_brief)

    sub.add_parser("evals", help="Task 3 — run the evaluation harness").set_defaults(func=cmd_evals)
    sub.add_parser("serve", help="Run the FastAPI server").set_defaults(func=cmd_serve)
    sub.add_parser("ui", help="Run the Streamlit UI").set_defaults(func=cmd_ui)

    return parser


if __name__ == "__main__":
    parsed = build_parser().parse_args()
    sys.exit(parsed.func(parsed))
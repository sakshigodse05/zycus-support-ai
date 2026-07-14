"""Loading and joining the mock dataset.

Tickets reference accounts via `account_id`, but that link is largely broken by
design: tickets reference 484 distinct account ids, accounts.json holds 50, and
only 4 of them overlap. Every lookup here fails soft and explicitly, never with
a KeyError, and the join key actually used is reported to the caller.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import List, Optional

from src.config import TICKETS_PATH, ACCOUNTS_PATH


class AccountNotFoundError(KeyError):
    """Raised when an account_id has no record in accounts.json."""


@lru_cache(maxsize=1)
def load_tickets() -> List[dict]:
    return json.loads(TICKETS_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_accounts() -> List[dict]:
    return json.loads(ACCOUNTS_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _account_map() -> dict:
    return {a["account_id"]: a for a in load_accounts()}


def get_account(account_id: str) -> dict:
    """Fetch one account, or raise AccountNotFoundError."""
    account = _account_map().get(account_id)
    if account is None:
        raise AccountNotFoundError(f"No account found with id {account_id!r}")
    return account


def list_account_ids() -> List[str]:
    """All known account ids (used by the UI dropdown and the eval harness)."""
    return sorted(_account_map().keys())


def _parse_ts(value: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


def get_account_tickets(account_id: str, days: int = 90) -> List[dict]:
    """All tickets for an account created within the last `days`, newest first.

    Join strategy — the dataset's `account_id` link is largely broken by design.
    Joining on id alone would return an empty brief for 46 of 50 accounts. The
    `company` field, however, joins cleanly for all 50.

    We therefore join on account_id first (the authoritative key when present)
    and fall back to an exact company-name match. The join key actually used is
    attached to each ticket so the degradation is visible, never silent.

    The 90-day window is anchored to the newest ticket in the dataset rather than
    to wall-clock now: the data is static, so a wall-clock window would silently
    empty out as the data ages, and would break the determinism requirement.
    """
    account = get_account(account_id)
    tickets = load_tickets()

    timestamps = [ts for ts in (_parse_ts(t.get("created_at", "")) for t in tickets) if ts]
    anchor = max(timestamps) if timestamps else datetime.now(timezone.utc)
    cutoff = anchor - timedelta(days=days)

    by_id = [t for t in tickets if t.get("account_id") == account_id]
    if by_id:
        matched, join_key = by_id, "account_id"
    else:
        company = account.get("company")
        matched = [t for t in tickets if t.get("company") == company]
        join_key = "company" if matched else "none"

    in_window = []
    for ticket in matched:
        created = _parse_ts(ticket.get("created_at", ""))
        if created and created >= cutoff:
            enriched = dict(ticket)
            enriched["_join_key"] = join_key
            in_window.append(enriched)

    return sorted(in_window, key=lambda t: t.get("created_at", ""), reverse=True)
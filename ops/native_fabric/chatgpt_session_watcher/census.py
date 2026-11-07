"""Census reconciliation: new sidebar rows, duplicate chain heads, account mismatches."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from policy import Account, other_account

_ARCHIVED = frozenset({"archived", "superseded"})


@dataclass
class Census:
    new_rows: list[dict] = field(default_factory=list)
    archive_ids: set[str] = field(default_factory=set)
    discrepancies: list[dict] = field(default_factory=list)


def title_stem(title: str) -> str:
    return re.sub(r"\s+\d+$", "", (title or "").strip()).casefold()


def title_number(title: str) -> int:
    match = re.search(r"(\d+)\s*$", title or "")
    return int(match.group(1)) if match else 1


def reconcile(sessions: list[dict], rows: list[dict], account: Account) -> Census:
    known = {row.get("chat_id") for row in sessions if row.get("chat_id")}
    result = Census()
    for row in rows:
        chat_id = row.get("chat_id")
        if chat_id and chat_id not in known:
            result.new_rows.append(dict(row))
        badge = str(row.get("account_badge") or "")
        other = other_account(badge, account)
        if other is not None:
            result.discrepancies.append({
                "chat_id": chat_id,
                "expected": account.account,
                "observed": badge,
                "observed_profile": other.profile,
            })
    heads: dict[str, list[dict]] = {}
    for session in sessions:
        if session.get("profile") not in {account.profile, account.account}:
            continue
        if str(session.get("status") or "") in _ARCHIVED:
            continue
        if session.get("replaced_by") or session.get("do_not_steer"):
            continue
        if str(session.get("status") or "") in {"HOLD", "leave_alone", "personal", "chris_own"}:
            continue
        key = str(session.get("chain_root") or title_stem(str(session.get("title") or "")))
        if not key:
            continue
        heads.setdefault(key, []).append(session)
    for group in heads.values():
        if len(group) < 2:
            continue
        ordered = sorted(group, key=lambda row: title_number(str(row.get("title") or "")))
        keeper = ordered[-1]
        for older in ordered[:-1]:
            if older.get("chat_id") and older.get("chat_id") != keeper.get("chat_id"):
                result.archive_ids.add(older["chat_id"])
    return result

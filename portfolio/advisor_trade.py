"""Proposal-only lifecycle for the private Portfolio Research Advisor.

The historical module name is retained to avoid a broad import migration.  This
module owns only a validated review queue: it cannot size an order, write a
position ledger, import an account, or execute a fill.  The active US PM may read
pending proposals as context and, after submitting its final book, mark each
presented proposal selected or not selected.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_PROPOSALS = _ROOT / "data" / "research" / "recommendations.jsonl"

SCHEMA = "portfolio_action_proposal.v1"
QUARANTINE_SCHEMA = "portfolio_action_proposal_quarantine.v1"
ACTIONS = frozenset({"add", "trim", "exit"})
URGENCIES = frozenset({"routine", "next_cycle", "urgent_review"})
PENDING_STATUS = "proposed"
REVIEWED_STATUSES = frozenset({"selected", "not_selected"})

_SIZING_AUTHORITY = "deterministic_scheduled_engine_only"
_FORBIDDEN_FIELDS = frozenset({"weight", "size", "shares", "notional", "price", "fill"})
_MAX_THESIS_CHARS = 2_000
_MAX_EVIDENCE_ITEMS = 12
_MAX_EVIDENCE_CHARS = 500


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _normalize_ticker(value: object) -> str:
    ticker = str(value or "").upper().strip()
    if not ticker or len(ticker) > 16:
        return ""
    if any(not (c.isalnum() or c in ".-") for c in ticker):
        return ""
    return ticker


def _normalize_evidence(values: Iterable[object] | None) -> list[str]:
    if isinstance(values, (str, bytes)):
        values = [values]
    out: list[str] = []
    for value in values or []:
        item = str(value or "").strip()
        if not item or item in out:
            continue
        out.append(item[:_MAX_EVIDENCE_CHARS])
        if len(out) >= _MAX_EVIDENCE_ITEMS:
            break
    return out


def _valid_date(value: object) -> bool:
    try:
        date.fromisoformat(str(value))
        return True
    except (TypeError, ValueError):
        return False


def _valid_datetime(value: object) -> bool:
    try:
        datetime.fromisoformat(str(value))
        return True
    except (TypeError, ValueError):
        return False


def _validation_error(row: object) -> str | None:
    """Return a stable quarantine reason, or ``None`` for a homogeneous queue row."""
    if not isinstance(row, dict):
        return "row_not_object"
    if row.get("schema") != SCHEMA:
        return "foreign_schema"
    if _FORBIDDEN_FIELDS & set(row):
        return "forbidden_order_or_sizing_field"
    if not isinstance(row.get("id"), str) or not row["id"].strip():
        return "invalid_id"
    if not _valid_datetime(row.get("created_at")):
        return "invalid_created_at"
    if not _valid_date(row.get("asof")):
        return "invalid_asof"
    if not isinstance(row.get("source"), str) or not row["source"].strip():
        return "invalid_source"
    if row.get("ticker") != _normalize_ticker(row.get("ticker")):
        return "invalid_ticker"
    if row.get("action") not in ACTIONS:
        return "invalid_action"
    thesis = row.get("thesis")
    if not isinstance(thesis, str) or not thesis.strip() or len(thesis) > _MAX_THESIS_CHARS:
        return "invalid_thesis"
    evidence = row.get("evidence")
    if (
        not isinstance(evidence, list)
        or not evidence
        or len(evidence) > _MAX_EVIDENCE_ITEMS
        or any(
            not isinstance(item, str)
            or not item.strip()
            or len(item) > _MAX_EVIDENCE_CHARS
            for item in evidence
        )
    ):
        return "invalid_evidence"
    if row.get("urgency") not in URGENCIES:
        return "invalid_urgency"
    if row.get("executed") is not False:
        return "invalid_execution_marker"
    if row.get("sizing_authority") != _SIZING_AUTHORITY:
        return "invalid_sizing_authority"

    status = row.get("status")
    if status != PENDING_STATUS and status not in REVIEWED_STATUSES:
        return "invalid_status"
    if status in REVIEWED_STATUSES:
        if not _valid_datetime(row.get("reviewed_at")):
            return "invalid_reviewed_at"
        if not _valid_date(row.get("review_asof")):
            return "invalid_review_asof"
        if not isinstance(row.get("review_portfolio_id"), str) or not row["review_portfolio_id"]:
            return "invalid_review_portfolio_id"
        if row.get("review_basis") not in {
            "matched_explicit_final_action",
            "not_in_final_submitted_actions",
        }:
            return "invalid_review_basis"
    return None


def _quarantine_path() -> Path:
    return _PROPOSALS.with_name(f"{_PROPOSALS.stem}.quarantine.jsonl")


def _lock_path() -> Path:
    return _PROPOSALS.with_name(f".{_PROPOSALS.name}.lock")


@contextmanager
def _queue_lock() -> Iterator[None]:
    _PROPOSALS.parent.mkdir(parents=True, exist_ok=True)
    with _lock_path().open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _atomic_write_rows(rows: list[dict]) -> None:
    """Replace the queue atomically while the caller holds ``_queue_lock``."""
    _PROPOSALS.parent.mkdir(parents=True, exist_ok=True)
    tmp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=_PROPOSALS.parent,
            prefix=f".{_PROPOSALS.name}.",
            suffix=".tmp",
            delete=False,
        ) as tmp:
            tmp_name = tmp.name
            for row in rows:
                tmp.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_name, _PROPOSALS)
    finally:
        if tmp_name:
            try:
                Path(tmp_name).unlink(missing_ok=True)
            except OSError:
                pass


def _append_quarantine(bad_rows: list[tuple[str, str]]) -> None:
    """Persist rejected raw rows before they are removed from the live queue."""
    if not bad_rows:
        return
    path = _quarantine_path()
    existing: set[str] = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict) and isinstance(record.get("fingerprint"), str):
                existing.add(record["fingerprint"])

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for raw, reason in bad_rows:
            fingerprint = hashlib.sha256(f"{reason}\n{raw}".encode()).hexdigest()
            if fingerprint in existing:
                continue
            record = {
                "schema": QUARANTINE_SCHEMA,
                "quarantined_at": _now(),
                "reason": reason,
                "fingerprint": fingerprint,
                "raw": raw,
            }
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            existing.add(fingerprint)


def _validated_rows_locked() -> list[dict]:
    """Load valid rows and recoverably remove malformed/foreign rows from the queue."""
    if not _PROPOSALS.exists():
        return []
    valid: list[dict] = []
    bad: list[tuple[str, str]] = []
    dirty = False
    seen_ids: set[str] = set()
    for raw in _PROPOSALS.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            dirty = True
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError:
            bad.append((raw, "invalid_json"))
            dirty = True
            continue
        reason = _validation_error(row)
        if reason is None and row["id"] in seen_ids:
            reason = "duplicate_id"
        if reason is not None:
            bad.append((raw, reason))
            dirty = True
            continue
        seen_ids.add(row["id"])
        valid.append(row)

    if dirty:
        # Do not discard anything unless its raw representation was preserved first.
        _append_quarantine(bad)
        _atomic_write_rows(valid)
    return valid


def pending_proposals(*, limit: int | None = None) -> list[dict]:
    """Return validated pending proposals, quarantining foreign/malformed rows.

    Urgent reviews appear first; creation time then provides deterministic FIFO order.
    """
    with _queue_lock():
        rows = _validated_rows_locked()
    pending = [dict(row) for row in rows if row.get("status") == PENDING_STATUS]
    rank = {"urgent_review": 0, "next_cycle": 1, "routine": 2}
    pending.sort(key=lambda row: (rank.get(row.get("urgency"), 9), row["created_at"], row["id"]))
    if limit is not None:
        return pending[: max(0, int(limit))]
    return pending


def prompt_context(*, limit: int = 24) -> str:
    """Render bounded, compact context for the active US nightly PM."""
    pending = pending_proposals()
    if not pending:
        return ""
    shown = pending[: max(0, int(limit))]
    lines = [
        "## Pending Portfolio Advisor proposals (context only)",
        (
            "These are unverified research proposals, not orders, positions, sizing instructions, or buy authority. "
            "Review them independently. Your explicit final ADD/TRIM/EXIT actions will mark matching presented "
            "proposals selected; every other presented proposal will be marked not_selected. Selection never fills a trade."
        ),
    ]
    for row in shown:
        thesis = " ".join(row["thesis"].split())[:280]
        evidence = "; ".join(" ".join(item.split())[:120] for item in row["evidence"][:2])
        lines.append(
            f"- {row['id']} | {row['action'].upper()} {row['ticker']} | {row['urgency']} | "
            f"thesis: {thesis} | evidence: {evidence}"
        )
    omitted = len(pending) - len(shown)
    if omitted:
        lines.append(f"- {omitted} additional proposal(s) remain pending and are not reviewed this cycle.")
    return "\n".join(lines)


def _proposal_id(
    *,
    asof: str,
    source: str,
    ticker: str,
    action: str,
    thesis: str,
    evidence: list[str],
    urgency: str,
) -> str:
    canonical = json.dumps(
        {
            "schema": SCHEMA,
            "asof": asof,
            "source": source,
            "ticker": ticker,
            "action": action,
            "thesis": thesis,
            "evidence": evidence,
            "urgency": urgency,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()[:20]


def propose_action(
    ticker: str,
    action: str,
    *,
    thesis: str,
    evidence: Iterable[object] | None,
    urgency: str,
    asof: str | None = None,
    source: str = "advisor_chat",
) -> dict:
    """Idempotently queue a non-executing portfolio-action proposal."""
    normalized_ticker = _normalize_ticker(ticker)
    normalized_action = str(action or "").lower().strip()
    normalized_thesis = str(thesis or "").strip()[:_MAX_THESIS_CHARS]
    normalized_urgency = str(urgency or "").lower().strip()
    normalized_evidence = _normalize_evidence(evidence)
    normalized_asof = str(asof or datetime.now(UTC).date().isoformat())
    normalized_source = str(source or "advisor_chat").strip()[:40]

    if not normalized_ticker:
        return {"ok": False, "executed": False, "error": "invalid ticker"}
    if normalized_action not in ACTIONS:
        return {
            "ok": False,
            "executed": False,
            "ticker": normalized_ticker,
            "error": f"unsupported action '{normalized_action}'",
        }
    if normalized_action in {"add", "trim"}:
        from portfolio import instrument_policy

        identity = instrument_policy.classify_us_instrument(normalized_ticker)
        if not (
            identity.get("kind") == "common_stock"
            and identity.get("verified") is True
        ):
            return {
                "ok": False,
                "executed": False,
                "ticker": normalized_ticker,
                "action": normalized_action,
                "error": "US portfolio proposals are verified-common-stock-only",
                "identity_status": identity.get("status") or "unverified_identity",
            }
    if not normalized_thesis:
        return {
            "ok": False,
            "executed": False,
            "ticker": normalized_ticker,
            "action": normalized_action,
            "error": "thesis is required",
        }
    if not normalized_evidence:
        return {
            "ok": False,
            "executed": False,
            "ticker": normalized_ticker,
            "action": normalized_action,
            "error": "at least one evidence item is required",
        }
    if normalized_urgency not in URGENCIES:
        return {
            "ok": False,
            "executed": False,
            "ticker": normalized_ticker,
            "action": normalized_action,
            "error": f"unsupported urgency '{normalized_urgency}'",
        }
    if not _valid_date(normalized_asof):
        return {
            "ok": False,
            "executed": False,
            "ticker": normalized_ticker,
            "action": normalized_action,
            "error": "invalid asof date",
        }
    if not normalized_source:
        return {
            "ok": False,
            "executed": False,
            "ticker": normalized_ticker,
            "action": normalized_action,
            "error": "source is required",
        }

    proposal_id = _proposal_id(
        asof=normalized_asof,
        source=normalized_source,
        ticker=normalized_ticker,
        action=normalized_action,
        thesis=normalized_thesis,
        evidence=normalized_evidence,
        urgency=normalized_urgency,
    )
    proposal = {
        "schema": SCHEMA,
        "id": proposal_id,
        "created_at": _now(),
        "asof": normalized_asof,
        "source": normalized_source,
        "status": PENDING_STATUS,
        "ticker": normalized_ticker,
        "action": normalized_action,
        "thesis": normalized_thesis,
        "evidence": normalized_evidence,
        "urgency": normalized_urgency,
        "executed": False,
        "sizing_authority": _SIZING_AUTHORITY,
    }
    try:
        with _queue_lock():
            rows = _validated_rows_locked()
            existing = next((row for row in rows if row["id"] == proposal_id), None)
            if existing is not None:
                return {
                    "ok": True,
                    "executed": False,
                    "deduplicated": True,
                    "proposal": dict(existing),
                    "note": (
                        f"Proposal {proposal_id} already exists with status {existing['status']}; "
                        "no duplicate row, order, size, or fill was created."
                    ),
                }
            _atomic_write_rows([*rows, proposal])
    except Exception as exc:  # noqa: BLE001 - report proposal persistence failure honestly
        return {
            "ok": False,
            "executed": False,
            "ticker": normalized_ticker,
            "action": normalized_action,
            "error": f"proposal write failed: {type(exc).__name__}",
        }

    return {
        "ok": True,
        "executed": False,
        "deduplicated": False,
        "proposal": proposal,
        "note": (
            f"Queued {normalized_action.upper()} proposal for {normalized_ticker}; no order was "
            "sized or filled. Scheduled deterministic portfolio engines retain execution authority."
        ),
    }


def _explicit_final_actions(submission: object) -> tuple[set[tuple[str, str]] | None, str | None]:
    """Validate the final-book action surface and return explicit action pairs."""
    if not isinstance(submission, dict):
        return None, "submission_not_object"
    holdings = submission.get("holdings")
    exits = submission.get("exit_decisions", [])
    if not isinstance(holdings, list) or not isinstance(exits, list):
        return None, "submission_actions_not_lists"

    actions: set[tuple[str, str]] = set()
    tickers: set[str] = set()
    for row in holdings:
        if not isinstance(row, dict):
            return None, "invalid_holding_action_row"
        ticker = _normalize_ticker(row.get("ticker"))
        # The MCP request carries ``action``; the trusted decision boundary persists the
        # requested/effective split instead. Review what may actually reach execution, so a blocked
        # trim or quarantined legacy instrument cannot be credited as a selected proposal.
        action = str(row.get("action_effective") or row.get("action") or "").lower().strip()
        if not ticker or action not in {"add", "hold", "trim", "quarantine_hold"}:
            return None, "invalid_holding_action_row"
        if ticker in tickers:
            return None, "duplicate_final_action_ticker"
        tickers.add(ticker)
        if action in {"add", "trim"}:
            actions.add((ticker, action))
    for row in exits:
        if not isinstance(row, dict):
            return None, "invalid_exit_action_row"
        ticker = _normalize_ticker(row.get("ticker"))
        action = str(row.get("action") or "").lower().strip()
        if not ticker or action != "exit":
            return None, "invalid_exit_action_row"
        if ticker in tickers:
            return None, "duplicate_final_action_ticker"
        tickers.add(ticker)
        actions.add((ticker, "exit"))
    return actions, None


def review_submitted_book(
    submission: object,
    *,
    asof: str,
    portfolio_id: str,
    proposal_ids: Iterable[str],
) -> dict:
    """Idempotently review presented proposals against an explicit final book.

    Only proposals whose ids were presented to this PM turn are transitioned.  A
    proposal is selected solely when the final submission explicitly carries the
    same ticker/action pair; omission becomes ``not_selected``.  This function has
    no account, sizing, order, position-ledger, or execution dependency.
    """
    if not _valid_date(asof):
        return {"ok": False, "reviewed": 0, "error": "invalid review asof"}
    if not isinstance(portfolio_id, str) or not portfolio_id.strip():
        return {"ok": False, "reviewed": 0, "error": "invalid portfolio id"}
    explicit, error = _explicit_final_actions(submission)
    if error is not None:
        return {"ok": False, "reviewed": 0, "error": error}
    wanted_ids = {str(value) for value in proposal_ids if str(value)}
    if not wanted_ids:
        return {"ok": True, "reviewed": 0, "selected": 0, "not_selected": 0}

    reviewed_at = _now()
    selected_ids: list[str] = []
    not_selected_ids: list[str] = []
    try:
        with _queue_lock():
            rows = _validated_rows_locked()
            updated: list[dict] = []
            for row in rows:
                if row["id"] not in wanted_ids or row["status"] != PENDING_STATUS:
                    updated.append(row)
                    continue
                selected = (row["ticker"], row["action"]) in explicit
                outcome = "selected" if selected else "not_selected"
                reviewed = {
                    **row,
                    "status": outcome,
                    "reviewed_at": reviewed_at,
                    "review_asof": asof,
                    "review_portfolio_id": portfolio_id.strip(),
                    "review_basis": (
                        "matched_explicit_final_action"
                        if selected
                        else "not_in_final_submitted_actions"
                    ),
                    # A selected proposal is still context-only; execution remains elsewhere.
                    "executed": False,
                }
                validation_error = _validation_error(reviewed)
                if validation_error is not None:  # pragma: no cover - defensive invariant
                    raise ValueError(f"invalid reviewed proposal: {validation_error}")
                updated.append(reviewed)
                (selected_ids if selected else not_selected_ids).append(row["id"])
            if selected_ids or not_selected_ids:
                _atomic_write_rows(updated)
    except Exception as exc:  # noqa: BLE001 - review failure must not affect the submitted book
        return {
            "ok": False,
            "reviewed": 0,
            "error": f"proposal review failed: {type(exc).__name__}",
        }

    return {
        "ok": True,
        "reviewed": len(selected_ids) + len(not_selected_ids),
        "selected": len(selected_ids),
        "not_selected": len(not_selected_ids),
        "selected_ids": selected_ids,
        "not_selected_ids": not_selected_ids,
        "executed": False,
    }

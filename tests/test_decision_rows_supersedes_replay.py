"""Event replay: the append-only ledger reproduces master's in-place ledger exactly.

One ``replay`` function drives BOTH sides from the same synthetic run events:

  NEW side      — real ``decisions.jsonl`` files under ``root``, written ONLY through
                  ``bot.decision_rows.append_decision_row``;
  REFERENCE side — master's in-place ledger: the frozen ``_master_replace_for_asof`` plus
                  in-place revision.

After EVERY event the per-(book, asof) stripped effective rows, serialized with
``json.dumps(r, default=str, ensure_ascii=False)``, must be byte-equal to the reference, and
the raw bytes must stay append-only. ``replay`` returns counts only.

``test_replay_runtime_capture`` replays the real staged capture when
``PBR_DECISION_ROW_REPLAY_CAPTURE`` names it; payloads are synthetic either way.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from bot import decision_rows as dr


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _serialized(row) -> str:
    return json.dumps(dr.strip_supersession(row), default=str, ensure_ascii=False)


def _is_accepted_queued(row) -> bool:
    return (
        isinstance(row, dict)
        and row.get("decision_effective") is True
        and row.get("target_status") == "queued"
    )


def _is_barren_row(row: dict) -> bool:
    return not dr.is_substantive(row)


def _synthetic_accepted_row(book: str, asof: str, event: dict) -> dict:
    extra = event.get("extra") or {}
    run_id = str(extra.get("run_id") or event.get("event_id") or "")
    return {
        "asof": asof,
        "summary": "synthetic",
        "holdings": [{"ticker": "SYN1", "weight": 1.0}],
        "decision_effective": True,
        "target_status": "queued",
        "target_sha256": _sha256(run_id),
        "decision_id": "decision.v1." + _sha256(book + asof)[:24],
    }


def _synthetic_barren_row(asof: str, event: dict) -> dict:
    extra = event.get("extra") or {}
    return {
        "asof": asof,
        "summary": None,
        "holdings": [],
        "error": "synthetic",
        "target_status": extra.get("target_status") or "rejected_no_submission",
        "decision_effective": False,
    }


def _synthetic_narrative_row(asof: str) -> dict:
    # a narrative row carries no decision_effective key
    return {"asof": asof, "summary": "synthetic narrative", "holdings": []}


def _revise_target(rows, event_asof: str):
    """Newest effective queued accepted row with asof <= event date (None when absent)."""
    candidates = [
        (index, row)
        for index, row in enumerate(rows)
        if _is_accepted_queued(row) and str(row.get("asof") or "")[:10] <= event_asof
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda pair: str(pair[1].get("asof") or "")[:10])


def replay(events, root):
    """Replay synthetic run events through the append-only ledger AND master's in-place
    reference, asserting per-(book, asof) byte equality and append-only bytes after every
    event. Returns counts only."""
    from test_decision_rows_supersedes import _master_replace_for_asof

    books = ("autonomous", "china", "hk")
    paths = {book: Path(root) / book / "decisions.jsonl" for book in books}
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    reference = {book: [] for book in books}
    previous_bytes = {book: b"" for book in books}
    counts = {
        "events": 0,
        "events_by_kind": {},
        "writes": 0,
        "barren_drops": 0,
        "noop_writes": 0,
        "supersessions": 0,
        "revisions": 0,
        "order_diffs": 0,
        "raw_rows": 0,
        "effective_rows": 0,
        "mismatches": 0,
    }

    def applied(book, appended, entry):
        if appended is None:
            counts["noop_writes"] += 1
            if _is_barren_row(entry):
                effective = dr.read_effective_rows(paths[book])
                same_day = [
                    r for r in effective
                    if isinstance(r, dict) and r.get("asof") == entry.get("asof")
                ]
                if any(dr.is_substantive(r) for r in same_day):
                    counts["barren_drops"] += 1
            return
        counts["writes"] += 1
        counts["supersessions"] += len(appended.get("supersedes") or [])
        if appended.get("supersede_mode") == "revise":
            counts["revisions"] += 1

    def check(book, event_id):
        eff = dr.read_effective_rows(paths[book]) if paths[book].exists() else []
        ref = reference[book]
        new_groups: dict[str, list[str]] = {}
        ref_groups: dict[str, list[str]] = {}
        for row in eff:
            new_groups.setdefault(str(row.get("asof")), []).append(_serialized(row))
        for row in ref:
            ref_groups.setdefault(str(row.get("asof")), []).append(_serialized(row))
        for asof in sorted(set(new_groups) | set(ref_groups)):
            if new_groups.get(asof, []) != ref_groups.get(asof, []):
                counts["mismatches"] += 1
        if [_serialized(r) for r in eff] != [_serialized(r) for r in ref]:
            counts["order_diffs"] += 1

    def append(book, entry):
        return dr.append_decision_row(paths[book], entry, entry.get("asof"))

    for event in sorted(events, key=lambda e: (str(e.get("ts") or ""), str(e.get("event_id") or ""))):
        counts["events"] += 1
        counts["events_by_kind"][str(event.get("kind"))] = (
            counts["events_by_kind"].get(str(event.get("kind")), 0) + 1
        )
        kind = str(event.get("kind"))
        job = str(event.get("job") or "")
        event_asof = str(event.get("ts") or "")[:10]
        event_id = str(event.get("event_id") or "")

        if kind == "run_finished" and job in ("autonomous_daily", "china_daily", "hk_daily"):
            book = str(event.get("book") or "") or job.split("_")[0]
            status = str(event.get("status") or "")
            target_status = (event.get("extra") or {}).get("target_status")
            if status == "ok" and target_status in {"queued", "executed"}:
                entry = _synthetic_accepted_row(book, event_asof, event)
            else:
                entry = _synthetic_barren_row(event_asof, event)
            appended = append(book, entry)
            reference[book][:] = _master_replace_for_asof(reference[book], entry, event_asof)
            applied(book, appended, entry)

        elif kind == "run_finished" and job == "watch_asia_overnight":
            watch_books = ("hk", "china")
            if str(event.get("status") or "") == "ok":
                for book in watch_books:
                    entry = _synthetic_narrative_row(event_asof)
                    appended = append(book, entry)
                    reference[book][:] = _master_replace_for_asof(
                        reference[book], entry, event_asof)
                    applied(book, appended, entry)
            else:
                for book in watch_books:
                    entry = _synthetic_barren_row(event_asof, event)
                    appended = append(book, entry)
                    reference[book][:] = _master_replace_for_asof(
                        reference[book], entry, event_asof)
                    applied(book, appended, entry)

        elif kind == "run_finished" and job == "watch_us_overnight":
            book = "autonomous"
            if str(event.get("status") or "") == "ok":
                entry = _synthetic_narrative_row(event_asof)
            else:
                entry = _synthetic_barren_row(event_asof, event)
            appended = append(book, entry)
            reference[book][:] = _master_replace_for_asof(reference[book], entry, event_asof)
            applied(book, appended, entry)

        elif kind == "run_finished" and job in ("settle_brain_asia", "settle_pending"):
            settle_books = (
                ("hk", "china") if job == "settle_brain_asia" else ("autonomous",)
            )
            if str(event.get("status") or "") == "ok":
                fields = {
                    "target_status": "executed",
                    "settled_asof": event_asof,
                    "settlement_transaction_id": "txn." + _sha256(event_id)[:24],
                }
                for book in settle_books:
                    found = _revise_target(reference[book], event_asof)
                    if found is None:
                        continue
                    _, ref_row = found
                    ref_revised = dict(ref_row)
                    ref_revised.update(fields)
                    effective = (
                        dr.read_effective_rows(paths[book]) if paths[book].exists() else []
                    )
                    twins = [
                        row for row in effective
                        if _is_accepted_queued(row)
                        and str(row.get("asof") or "")[:10] <= event_asof
                        and dr.strip_supersession(row) == dr.strip_supersession(ref_row)
                    ]
                    if len(twins) != 1:
                        counts["mismatches"] += 1
                        continue
                    appended = dr.append_decision_row(
                        paths[book], dict(twins[0], **fields), twins[0].get("asof"),
                        revises=twins[0],
                    )
                    reference[book][found[0]] = ref_revised
                    applied(book, appended, twins[0])

        elif kind == "packet_accepted" and str(event.get("book") or "") in books:
            book = str(event.get("book"))
            fields = {"lesson_link_ids": [_sha256(event_id)[:12]]}
            found = _revise_target(reference[book], event_asof)
            if found is not None:
                _, ref_row = found
                ref_revised = dict(ref_row)
                ref_revised.update(fields)
                effective = (
                    dr.read_effective_rows(paths[book]) if paths[book].exists() else []
                )
                twins = [
                    row for row in effective
                    if _is_accepted_queued(row)
                    and str(row.get("asof") or "")[:10] <= event_asof
                    and dr.strip_supersession(row) == dr.strip_supersession(ref_row)
                ]
                if len(twins) != 1:
                    counts["mismatches"] += 1
                else:
                    appended = dr.append_decision_row(
                        paths[book], dict(twins[0], **fields), twins[0].get("asof"),
                        revises=twins[0],
                    )
                    reference[book][found[0]] = ref_revised
                    applied(book, appended, twins[0])

        # every other event: counted above, ignored

        # append-only bytes, per book, after EVERY event
        for book in books:
            current = paths[book].read_bytes() if paths[book].exists() else b""
            assert current.startswith(previous_bytes[book]), (event_id, book)
            previous_bytes[book] = current
            check(book, event_id)

    for book in books:
        counts["raw_rows"] += len(
            dr.read_rows(paths[book])) if paths[book].exists() else 0
        counts["effective_rows"] += (
            len(dr.read_effective_rows(paths[book])) if paths[book].exists() else 0
        )
    return counts


def _synthetic_events() -> list[dict]:
    """>=40 hand-built events covering every branch."""
    events: list[dict] = []

    def ev(ts, event_id, kind, job, status, *, book=None, extra=None):
        events.append({
            "ts": ts, "event_id": event_id, "kind": kind, "job": job, "status": status,
            "book": book, "extra": extra or {},
        })

    # --- day 1: settle BEFORE any accepted row (branch: no target, no write) -------------
    ev("2026-10-01T02:00:00Z", "ev-001", "run_finished", "settle_pending", "ok")
    ev("2026-10-01T02:05:00Z", "ev-002", "run_finished", "settle_brain_asia", "ok")
    # --- day 1: ignored events -----------------------------------------------------------
    ev("2026-10-01T03:00:00Z", "ev-003", "run_started", "autonomous_daily", "ok")
    ev("2026-10-01T03:00:30Z", "ev-004", "app_started", "startup", "ok")
    ev("2026-10-01T03:01:00Z", "ev-005", "pending_target_cutover_preflight", "startup", "ok")
    ev("2026-10-01T03:02:00Z", "ev-006", "lock_conflict", "daily_mark", "lock_held")
    ev("2026-10-01T03:03:00Z", "ev-007", "run_skipped", "derisk_us_intraday", "skip")
    ev("2026-10-01T03:04:00Z", "ev-008", "run_finished", "daily_mark", "ok")
    # --- day 1: accepted books ------------------------------------------------------------
    ev("2026-10-01T13:00:00Z", "ev-009", "run_finished", "autonomous_daily", "ok",
       book="autonomous", extra={"target_status": "queued", "run_id": "run-a1"})
    ev("2026-10-01T13:05:00Z", "ev-010", "run_finished", "china_daily", "ok",
       book="china", extra={"target_status": "queued", "run_id": "run-c1"})
    ev("2026-10-01T13:10:00Z", "ev-011", "run_finished", "hk_daily", "ok",
       book="hk", extra={"target_status": "queued", "run_id": "run-h1"})
    # --- day 1: narrative re-runs AFTER accepted books (they replace them, both sides) ----
    ev("2026-10-01T21:00:00Z", "ev-012", "run_finished", "watch_us_overnight", "ok")
    ev("2026-10-01T21:05:00Z", "ev-013", "run_finished", "watch_asia_overnight", "ok")
    # --- day 1: barren AFTER accepted/narrative (barren guard: nothing written) -----------
    ev("2026-10-01T22:00:00Z", "ev-014", "run_finished", "autonomous_daily", "error",
       book="autonomous", extra={"target_status": "rejected_no_submission",
                                 "run_id": "run-a2"})
    ev("2026-10-01T22:05:00Z", "ev-015", "run_finished", "hk_daily", "error",
       book="hk", extra={"target_status": "rejected_no_submission", "run_id": "run-h2"})
    ev("2026-10-01T22:06:00Z", "ev-016", "run_finished", "watch_us_overnight", "error")
    # --- day 2: barren first, then accepted (a real book replaces a stub) -----------------
    ev("2026-10-02T09:00:00Z", "ev-017", "run_finished", "autonomous_daily", "error",
       book="autonomous", extra={"target_status": "rejected_no_submission",
                                 "run_id": "run-a3"})
    ev("2026-10-02T13:00:00Z", "ev-018", "run_finished", "autonomous_daily", "ok",
       book="autonomous", extra={"target_status": "queued", "run_id": "run-a4"})
    ev("2026-10-02T13:05:00Z", "ev-019", "run_finished", "china_daily", "error",
       book="china", extra={"target_status": "rejected_no_submission", "run_id": "run-c2"})
    ev("2026-10-02T13:10:00Z", "ev-020", "run_finished", "hk_daily", "ok",
       book="hk", extra={"target_status": "queued", "run_id": "run-h3"})
    # --- day 2: settle then packet link (revise + second revise) --------------------------
    ev("2026-10-02T14:00:00Z", "ev-021", "run_finished", "settle_pending", "ok")
    ev("2026-10-02T14:05:00Z", "ev-022", "run_finished", "settle_brain_asia", "ok")
    ev("2026-10-02T15:00:00Z", "ev-023", "packet_accepted", "unknown", "ok",
       book="autonomous")
    ev("2026-10-02T15:01:00Z", "ev-024", "packet_accepted", "unknown", "ok", book="china")
    ev("2026-10-02T15:02:00Z", "ev-025", "packet_accepted", "unknown", "ok", book="hk")
    # --- day 2: settle again — day 1 books were replaced by narratives (no queued row) ----
    ev("2026-10-02T16:00:00Z", "ev-026", "run_finished", "settle_brain_asia", "ok")
    # --- day 3: rejected (barren) rows on fresh days, then error again (barren replaces
    #     barren on the reference side; the effective view keeps one barren row) -----------
    ev("2026-10-03T13:00:00Z", "ev-027", "run_finished", "china_daily", "error",
       book="china", extra={"target_status": "rejected_no_submission", "run_id": "run-c3"})
    ev("2026-10-03T13:05:00Z", "ev-028", "run_finished", "hk_daily", "error",
       book="hk", extra={"target_status": "rejected_no_submission", "run_id": "run-h4"})
    ev("2026-10-03T13:10:00Z", "ev-029", "run_finished", "china_daily", "error",
       book="china", extra={"target_status": "rejected_no_submission", "run_id": "run-c4"})
    # --- day 3: watch error → barren rows for hk + china ----------------------------------
    ev("2026-10-03T21:00:00Z", "ev-030", "run_finished", "watch_asia_overnight", "error")
    # --- day 4: three books queued, settled, packet-linked --------------------------------
    ev("2026-10-04T13:00:00Z", "ev-031", "run_finished", "autonomous_daily", "ok",
       book="autonomous", extra={"target_status": "queued", "run_id": "run-a5"})
    ev("2026-10-04T13:05:00Z", "ev-032", "run_finished", "china_daily", "ok",
       book="china", extra={"target_status": "queued", "run_id": "run-c5"})
    ev("2026-10-04T13:10:00Z", "ev-033", "run_finished", "hk_daily", "ok",
       book="hk", extra={"target_status": "queued", "run_id": "run-h5"})
    ev("2026-10-04T14:00:00Z", "ev-034", "run_finished", "settle_pending", "ok")
    ev("2026-10-04T14:05:00Z", "ev-035", "run_finished", "settle_brain_asia", "ok")
    ev("2026-10-04T15:00:00Z", "ev-036", "packet_accepted", "unknown", "ok", book="autonomous")
    ev("2026-10-04T15:01:00Z", "ev-037", "packet_accepted", "unknown", "ok", book="china")
    ev("2026-10-04T15:02:00Z", "ev-038", "packet_accepted", "unknown", "ok", book="hk")
    # --- day 5: a late daily re-run for an OLDER asof is impossible here (asof = ts[:10]),
    #     but a narrative after settle + a second packet link on the same day must stay in
    #     step — and settle must no-op once the day's row is already executed ---------------
    ev("2026-10-04T15:03:00Z", "ev-039", "packet_accepted", "unknown", "ok", book="hk")
    ev("2026-10-04T16:00:00Z", "ev-040", "run_finished", "settle_pending", "ok")
    ev("2026-10-05T21:00:00Z", "ev-041", "run_finished", "watch_us_overnight", "ok")
    ev("2026-10-05T21:05:00Z", "ev-042", "run_finished", "watch_asia_overnight", "ok")
    ev("2026-10-05T22:00:00Z", "ev-043", "run_finished", "autonomous_daily", "error",
       book="autonomous", extra={"target_status": "rejected_no_submission",
                                 "run_id": "run-a6"})
    # same event ids sorted by (ts, event_id): two events sharing a ts
    ev("2026-10-05T23:00:00Z", "ev-044", "run_finished", "china_daily", "error",
       book="china", extra={"target_status": "rejected_no_submission", "run_id": "run-c6"})
    ev("2026-10-05T23:00:00Z", "ev-045", "run_finished", "hk_daily", "ok",
       book="hk", extra={"target_status": "queued", "run_id": "run-h6"})
    ev("2026-10-05T23:30:00Z", "ev-046", "packet_accepted", "unknown", "ok", book="hk")
    return events


def test_replay_synthetic_events(tmp_path):
    counts = replay(_synthetic_events(), tmp_path)
    assert counts["mismatches"] == 0
    # every branch really was exercised
    assert counts["writes"] > 0
    assert counts["barren_drops"] > 0          # barren after accepted: nothing written
    assert counts["supersessions"] > 0         # asof-mode replacements named their targets
    assert counts["revisions"] > 0             # settle/packet revise rows were appended
    assert counts["raw_rows"] > counts["effective_rows"]
    # asof == ts[:10] and events replay in ts order, so every reference same-day block is
    # already last when its barren guard fires: the reference never reorders here. (The
    # out-of-order-asof reorder class is covered by the sibling property-equivalence test,
    # which drives asofs in random order.)
    assert counts["order_diffs"] == 0
    print(counts)


def test_replay_runtime_capture(tmp_path):
    capture = os.environ.get("PBR_DECISION_ROW_REPLAY_CAPTURE")
    if not capture:
        pytest.skip("PBR_DECISION_ROW_REPLAY_CAPTURE not set")
    digest = hashlib.sha256(Path(capture).read_bytes()).hexdigest()
    assert digest == "6a423ef96978bb698bf38f27cdff2c9dfa1ad1317a788b6f893c045c04da542b"
    events = [
        json.loads(line)
        for line in Path(capture).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    counts = replay(events, tmp_path)
    assert counts["mismatches"] == 0
    print(counts)

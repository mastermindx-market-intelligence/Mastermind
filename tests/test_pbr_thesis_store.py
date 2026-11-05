"""PBR L-S5 — durable episode thesis + amendment records (spec §5.2, rulings Q1/Q4).

Contract tests import the new module inside the test body, so on code without
``brain/thesis_store.py`` they FAIL with ModuleNotFoundError.  All stores live
under ``tmp_path``; no network, no live data, nothing written outside the
caller-supplied ``store_dir``.

Seat ruling Q1 is the shape of the detection tests: conviction is NOT watched
(it is a per-cycle observation in ``observations.jsonl``, schema
``pbr.thesis_observation.v1``); the MU 75→76 finding lists the watched
holding-row fields the fixture's ``derived.case_holding_changes`` shows changed
(falsifier, exit_plan, expected_horizon, rationale, why_now) and never
conviction; the later-row null ``proposed_weight`` is a not-a-restatement.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from brain import decision_submission

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "pbr" / "decision_cases"
CONFIG = ROOT / "config" / "pbr_shadow_risk_budget.yml"

MU_ENTRY = "mu_2026-10-02_entry.json"
MU_AMENDMENT = "mu_2026-10-05_amendment.json"
PLANLESS = "mu_2026-10-22_planless_summary.json"
XOM_CONTROL = "xom_2026-08-12_positive_control.json"

AUDIT_KEYS_BASELINE = {
    "carried",
    "blocked_early_exits",
    "blocked_exits",
    "blocked_actions",
    "invalid_exit_requests",
    "ignored_exit_requests",
    "rejected",
    "quarantined",
    "mandatory_instrument_migrations",
    "identity",
    "unallocated_adds",
    "quote_fallback_holdings",
    "sizing",
}

PROSE_DIGEST = "pbr.prose_digest.v1"


# ─────────────────────────────── helpers ────────────────────────────────────


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _record_by_line(fix: dict, line: int) -> dict:
    for record in fix["records"]:
        if record["line_index_0based"] == line:
            return record
    raise AssertionError(f"line {line} not among records")


def _is_digest(value) -> bool:
    return isinstance(value, dict) and value.get("redacted") == PROSE_DIGEST


def _placeholder(digest: dict) -> str:
    """SR-1 rule (1): deterministic placeholder for one redacted prose string."""
    return (
        "<redacted sha256={sha} len={n} dates={dates} periods={periods} terms={terms}>".format(
            sha=digest["sha256"][:12],
            n=digest["length"],
            dates=",".join(digest.get("iso_dates") or []) or "none",
            periods=",".join(digest.get("period_labels") or []) or "none",
            terms=",".join(digest.get("terms") or []) or "none",
        )
    )


def _rehydrate(node):
    if _is_digest(node):
        return _placeholder(node)
    if isinstance(node, dict):
        return {key: _rehydrate(value) for key, value in node.items()}
    if isinstance(node, list):
        return [_rehydrate(value) for value in node]
    return node


def _scan(node, needles):
    found = set()
    if isinstance(node, dict):
        for key, value in node.items():
            found |= _scan(key, needles)
            found |= _scan(value, needles)
    elif isinstance(node, (list, tuple)):
        for value in node:
            found |= _scan(value, needles)
    elif isinstance(node, str):
        for needle in needles:
            if needle in node:
                found.add(needle)
    return found


def _note_digest(text: str) -> dict:
    """Q4: a test note is never prose — it travels as a digest-shaped dict."""
    return {
        "redacted": PROSE_DIGEST,
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "length": len(text),
    }


def _book_of(fix: dict) -> str:
    return fix["provenance"][0]["source_book"]


def _holding_row(fix: dict, line: int) -> dict:
    """Watched-field row built from a fixture record's case holding.

    Narrative values stay as their committed redacted digests — diffs are
    visible as differing sha256 values and no prose ever enters the repo.
    """
    record = _record_by_line(fix, line)
    holding = record["case_holding"]
    return {
        "book": _book_of(fix),
        "ticker": holding["ticker"],
        "decision_id": record["decision_id"],
        "asof": record["row"]["asof"],
        "ts": record["row"]["ts"],
        "conviction": holding["conviction"],
        "rationale": holding["rationale"],
        "falsifier": holding["falsifier"],
        "expected_horizon": holding["expected_horizon"],
        "exit_plan": holding["exit_plan"],
        "proposed_weight": holding.get("proposed_weight"),
        "why_now": holding["why_now"],
    }


def _prior_book(fix: dict, line: int, extra_rows=()) -> dict:
    prior = {}
    for other in fix["redaction"]["other_holdings"]:
        if other["line_index_0based"] == line:
            prior[other["ticker"]] = {
                "ticker": other["ticker"],
                "weight": float(other["weight"]),
                "conviction": other["conviction"],
            }
    for row in extra_rows:
        prior[row["ticker"]] = row
    return prior


def _run_normalize(monkeypatch, fix, record, prior, *, extra_args=None, holdings=None):
    """Baseline normalize() with only READ seams patched (each listed in RETURN).

    Seams: ``brain.decision_submission._latest_holdings``,
    ``brain.decision_submission._instrument_identity_for_book``,
    ``portfolio.registry.requires_single_name_equity``.  No write path is
    patched: normalize() writes nothing.
    """
    from portfolio import registry

    holding = record.get("case_holding") or {}
    row = record["row"]

    def _fake_latest_holdings(book):
        return copy.deepcopy(prior)

    def _fake_identity(book, ticker):
        status = holding.get("identity_status") or "trusted_company_profile.v1"
        return {"kind": "common_stock", "status": status, "verified": True, "market": book}

    monkeypatch.setattr(decision_submission, "_latest_holdings", _fake_latest_holdings)
    monkeypatch.setattr(decision_submission, "_instrument_identity_for_book", _fake_identity)
    monkeypatch.setattr(registry, "requires_single_name_equity", lambda book: True)

    if holdings is None:
        holdings = (
            [{**_rehydrate(holding), "action": holding["action_requested"]}] if holding else []
        )
    args = {"holdings": holdings, "risk_posture": row.get("risk_posture")}
    if extra_args:
        args.update(extra_args)
    return decision_submission.normalize(
        _book_of(fix), args, deterministic_sizing=True, decision_asof=row.get("asof")
    )


def _mu_thesis_record(store, fix, thesis_store):
    """The MU episode thesis: opens at the first entry fill (2026-10-05).

    Narrative fields are stored as their rule-(1) placeholders — strings, so
    the append-only store stays comparable, and never original prose.
    """
    import brain.thesis_store as thesis_store_mod

    assert thesis_store_mod is thesis_store
    record = fix["records"][0]
    holding = record["case_holding"]
    fill = fix["fills"][0]["row"]
    assert fill["side"] == "buy" and fill["ticker"] == fix["ticker"]
    assert fill["date"] == "2026-10-05"
    return thesis_store.record_thesis(
        store,
        {
            "book": _book_of(fix),
            "ticker": fix["ticker"],
            "episode_open_date": fill["date"],
            "entry_fill_ids": [fill["fill_id"]],
            "why_now": _placeholder(holding["why_now"]),
            "fact_ids": [],
            "horizon": _placeholder(holding["expected_horizon"]),
            "falsifiers": [_placeholder(holding["falsifier"])],
            "exit_conditions": [_placeholder(holding["exit_plan"])],
            "position_role": "starter",
            "originating_decision_id": record["decision_id"],
            "created_at": record["row"]["ts"],
        },
    )


# ───────────────────────────── baseline (master) ─────────────────────────────


def test_baseline_master_amendment_and_exit_leave_no_trace(monkeypatch, tmp_path):
    store = tmp_path / "store"  # nothing in this wave may write here
    """Rows 75→76 and the row-89 exit leave no amendment record and no finding.

    Passes on master; documents the A15 gap: a held position's falsifier, exit
    plan and conviction changed with no amendment record anywhere, and a full
    exit was justified from the provider's planless status with no
    thesis-continuity finding.
    """
    amendment_fix = _load(MU_AMENDMENT)
    by_line = {r["line_index_0based"]: r for r in amendment_fix["records"]}
    row75, row76 = by_line[75], by_line[76]
    assert row76["case_holding"]["action_requested"] == "hold"
    assert row76["case_holding"]["conviction"] == "high"
    assert row75["case_holding"]["conviction"] == "medium"
    assert row75["case_holding"]["weight"] == 0.10
    prior = _prior_book(
        amendment_fix,
        76,
        extra_rows=[
            {
                "ticker": "MU",
                "weight": float(row75["case_holding"]["weight"]),
                "conviction": str(row75["case_holding"]["conviction"]),
            }
        ],
    )
    payload, audit = _run_normalize(monkeypatch, amendment_fix, row76, prior)
    held = [h for h in payload["holdings"] if h["ticker"] == "MU"]
    assert len(held) == 1
    assert held[0]["conviction"] == "high", "master accepts the conviction change verbatim"
    assert held[0]["weight_source"] == "deterministic_existing_hold.v1"
    assert set(audit) == AUDIT_KEYS_BASELINE
    assert not ({"fact_verification", "thesis_continuity", "risk_budget"} & set(audit))
    assert (
        _scan(
            payload,
            [
                "UNRECORDED_AMENDMENT",
                "amendment_id",
                "thesis_id",
                "fact_verification",
                "thesis_continuity",
                "risk_budget",
            ],
        )
        == set()
    )

    # The row-89 planless exit: accepted, and no finding marks the missing plan.
    planless_fix = _load(PLANLESS)
    row89 = next(r for r in planless_fix["records"] if r["line_index_0based"] == 89)
    row78 = next(r for r in planless_fix["records"] if r["line_index_0based"] == 78)
    assert row78["case_holding"]["ticker"] == "MU"
    prior89 = _prior_book(
        planless_fix,
        89,
        extra_rows=[
            {
                "ticker": "MU",
                "weight": float(row78["case_holding"]["weight"]),
                "conviction": str(row78["case_holding"]["conviction"]),
            }
        ],
    )
    payload89, audit89 = _run_normalize(
        monkeypatch,
        planless_fix,
        row89,
        prior89,
        extra_args={"exit_decisions": _rehydrate(row89["row"]["requested_exit_decisions"])},
        holdings=[],
    )
    accepted = [e for e in payload89["exit_decisions"] if e["ticker"] == "MU"]
    assert len(accepted) == 1 and accepted[0]["reason_code"] == "risk_limit"
    assert set(audit89) == AUDIT_KEYS_BASELINE
    assert (
        _scan(
            payload89,
            [
                "PROVIDER_PLAN_MISSING_LOCAL_THESIS_PRESENT",
                "UNRECORDED_AMENDMENT",
                "thesis_id",
                "thesis_continuity",
                "risk_budget",
            ],
        )
        == set()
    )
    # And nothing was written to any store: the dedicated dir stays absent.
    assert not store.exists()


# ────────────────────────────── contract tests ───────────────────────────────


def test_thesis_record_roundtrip_linked_to_entry_fill(tmp_path):
    import brain.thesis_store as thesis_store

    store = tmp_path / "store"
    fix = _load(MU_ENTRY)
    fill = fix["fills"][0]["row"]
    record = _mu_thesis_record(store, fix, thesis_store)
    assert record["schema"] == "pbr.thesis.v1"
    assert record["thesis_id"].startswith("thesis.v1.")
    assert record["entry_fill_ids"] == [fill["fill_id"]]
    assert record["originating_decision_id"] == fix["records"][0]["decision_id"]
    assert record["position_role"] == "starter"
    assert record["falsifiers"] == [_placeholder(fix["records"][0]["case_holding"]["falsifier"])]
    assert record["exit_conditions"] == [
        _placeholder(fix["records"][0]["case_holding"]["exit_plan"])
    ]

    by_episode = thesis_store.thesis_for_episode(store, "autonomous", "MU", "2026-10-05")
    assert by_episode is not None
    assert by_episode["thesis_id"] == record["thesis_id"]
    by_fill = thesis_store.thesis_for_fill(store, fill["fill_id"])
    assert by_fill is not None
    assert by_fill["thesis_id"] == record["thesis_id"]
    # An unrelated fill id retrieves nothing.
    assert thesis_store.thesis_for_fill(store, "f" * 64) is None
    assert thesis_store.thesis_for_episode(store, "autonomous", "MU", "2026-10-06") is None

    # Append-only file layout, exactly the one named file under store_dir.
    assert sorted(p.name for p in store.iterdir()) == ["theses.jsonl"]
    lines = (store / "theses.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    with pytest.raises(thesis_store.ThesisStoreError):
        thesis_store.record_thesis(store, record)


def test_amendment_append_only_and_non_retroactive(tmp_path):
    import brain.thesis_store as thesis_store

    store = tmp_path / "store"
    fix = _load(MU_ENTRY)
    amendment_fix = _load(MU_AMENDMENT)
    row75 = _holding_row(amendment_fix, 75)
    row76 = _holding_row(amendment_fix, 76)
    thesis = _mu_thesis_record(store, fix, thesis_store)
    # The thesis stores rule-(1) placeholder strings; the rows carry the raw
    # committed digests.  Compare like with like.
    old_falsifier = _placeholder(row75["falsifier"])
    new_falsifier = _placeholder(row76["falsifier"])
    old_exit = _placeholder(row75["exit_plan"])
    new_exit = _placeholder(row76["exit_plan"])
    assert old_falsifier != new_falsifier and old_exit != new_exit

    amendment = thesis_store.record_amendment(
        store,
        {
            "thesis_id": thesis["thesis_id"],
            "changes": {
                "falsifier": {"old": old_falsifier, "new": new_falsifier},
                "exit_plan": {"old": old_exit, "new": new_exit},
                "expected_horizon": {"old": row75["expected_horizon"], "new": row76["expected_horizon"]},
            },
            "reason_code": "SUPERSEDED",
            "note": _note_digest("held position re-underwritten against the fresh tape"),
            "evidence_refs": [row75["decision_id"]],
            "effective_at": row76["asof"],
            "recorded_at": row76["ts"],
            "accountable_decision_id": row76["decision_id"],
        },
        originating_decision_asof=row75["asof"],
    )
    assert amendment["schema"] == "pbr.thesis_amendment.v1"
    assert amendment["amendment_id"].startswith("amendment.v1.")
    assert amendment["reason_code"] == "SUPERSEDED"
    assert isinstance(amendment["note"], dict), "a test note travels as a digest dict"

    # The conviction leg of the same cycle is an observation, not an amendment.
    observation = thesis_store.record_observation(
        store,
        {
            "thesis_id": thesis["thesis_id"],
            "cycle_id": row76["decision_id"],
            "asof": row76["asof"],
            "field": "conviction",
            "value": row76["conviction"],
            "previous_value": row75["conviction"],
        },
    )
    assert observation["schema"] == "pbr.thesis_observation.v1"
    assert observation["cycle_id"] == row76["decision_id"]

    # Non-retroactive retrieval: the 2026-10-02 view still holds the originals.
    early = thesis_store.thesis_as_of(store, thesis["thesis_id"], "2026-10-02")
    assert early["local_thesis_status"] == "ACTIVE"
    assert early["fields"]["falsifier"] == old_falsifier
    assert early["fields"]["exit_plan"] == old_exit
    assert early["applied_amendment_ids"] == []
    late = thesis_store.thesis_as_of(store, thesis["thesis_id"], "2026-10-06")
    assert late["local_thesis_status"] == "AMENDED"
    assert late["fields"]["falsifier"] == new_falsifier
    assert late["fields"]["exit_plan"] == new_exit
    assert late["applied_amendment_ids"] == [amendment["amendment_id"]]

    # Append-only: one line per record, and a rejected amendment appends nothing.
    assert len((store / "theses.jsonl").read_text(encoding="utf-8").splitlines()) == 1
    before = (store / "amendments.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(before) == 1
    with pytest.raises(thesis_store.RetroactiveAmendmentError) as excinfo:
        thesis_store.record_amendment(
            store,
            {
                "thesis_id": thesis["thesis_id"],
                "changes": {"falsifier": {"old": new_falsifier, "new": "rewritten"}},
                "reason_code": "MANUAL",
                "evidence_refs": [row76["decision_id"]],
                "effective_at": "2026-10-01",
                "recorded_at": "2026-10-06T00:00:00+00:00",
                "accountable_decision_id": row76["decision_id"],
            },
            originating_decision_asof=row75["asof"],
        )
    assert excinfo.value.code == "retroactive_amendment_rejected"
    after = (store / "amendments.jsonl").read_text(encoding="utf-8").splitlines()
    assert after == before, "a rejected retroactive amendment must not be appended"


def test_unrecorded_amendment_detected_mu_75_to_76(tmp_path):
    import brain.thesis_store as thesis_store

    store = tmp_path / "store"
    fix = _load(MU_ENTRY)
    amendment_fix = _load(MU_AMENDMENT)
    rows = [_holding_row(amendment_fix, 75), _holding_row(amendment_fix, 76)]
    assert rows[0]["conviction"] == "medium" and rows[1]["conviction"] == "high"
    findings = thesis_store.detect_unrecorded_amendments(rows)
    assert len(findings) == 1
    finding = findings[0]
    assert finding["code"] == "UNRECORDED_AMENDMENT"
    assert finding["from_decision_id"] == rows[0]["decision_id"]
    assert finding["to_decision_id"] == rows[1]["decision_id"]
    changes = finding["changes"]
    # Seat ruling Q1: exactly the watched holding-row fields the fixture's
    # derived diff shows changed — falsifier and exit_plan among them — and
    # never conviction; the later-row null proposed_weight is a not-a-restatement.
    fixture_changed = set(amendment_fix["derived"]["case_holding_changes"])
    watched = set(thesis_store.WATCHED_HOLDING_ROW_FIELDS)
    # proposed_weight is watched but exempted by ruling Q1 (later-row null =
    # not restated); everything else the fixture shows changed must be listed.
    assert set(changes) == (fixture_changed & watched) - {"proposed_weight"}
    assert {"falsifier", "exit_plan"} <= set(changes)
    assert set(changes) == {"falsifier", "exit_plan", "expected_horizon", "rationale", "why_now"}
    assert "conviction" not in changes
    assert "conviction" not in finding["thesis_fields"]
    assert "conviction" not in str(sorted(changes))
    assert changes["falsifier"] == {"old": rows[0]["falsifier"], "new": rows[1]["falsifier"]}
    assert changes["exit_plan"]["new"] == rows[1]["exit_plan"]
    assert finding["exempted_fields"] == {
        "proposed_weight": (
            "later row leaves proposed_weight null/absent: not restated, "
            "not a change (seat ruling Q1)"
        )
    }
    assert amendment_fix["derived"]["case_holding_changes"]["proposed_weight"] == {
        "old": 0.08,
        "new": None,
    }
    assert {"falsifiers", "exit_conditions", "thesis_statement", "catalyst"} <= set(
        finding["thesis_fields"]
    )

    # Perturbation: an explicit amendment naming the superseded decision and
    # covering the whole diff suppresses the finding.
    thesis = _mu_thesis_record(store, fix, thesis_store)
    amendment = thesis_store.record_amendment(
        store,
        {
            "thesis_id": thesis["thesis_id"],
            "changes": dict(changes),
            "reason_code": "SUPERSEDED",
            "note": _note_digest("explicit re-underwrite recorded against the superseded decision"),
            "evidence_refs": [rows[0]["decision_id"]],
            "effective_at": rows[1]["asof"],
            "recorded_at": rows[1]["ts"],
            "accountable_decision_id": rows[1]["decision_id"],
        },
        originating_decision_asof=rows[0]["asof"],
    )
    loaded = thesis_store.load_amendments(store)
    assert loaded == [amendment]
    assert thesis_store.detect_unrecorded_amendments(rows, loaded) == []

    # Fail-closed: a partial amendment (one field) still leaves the finding.
    partial = dict(amendment)
    partial["changes"] = {"falsifier": changes["falsifier"]}
    partial["amendment_id"] = "amendment.v1.partial0000000"
    assert thesis_store.detect_unrecorded_amendments(rows, [partial]) != []
    # ...and a linked amendment that leaves a changed field out of `changes`
    # also fails to suppress: coverage must be complete.
    incomplete = dict(amendment)
    incomplete["changes"] = {"falsifier": changes["falsifier"], "exit_plan": changes["exit_plan"]}
    incomplete["amendment_id"] = "amendment.v1.incomplete000"
    assert thesis_store.detect_unrecorded_amendments(rows, [incomplete]) != []


def test_mu_silent_amendment_rejected(tmp_path):
    import brain.thesis_store as thesis_store

    store = tmp_path / "store"
    fix = _load(MU_ENTRY)
    amendment_fix = _load(MU_AMENDMENT)
    thesis = _mu_thesis_record(store, fix, thesis_store)
    rows = [_holding_row(amendment_fix, 75), _holding_row(amendment_fix, 76)]
    original_falsifier = _placeholder(fix["records"][0]["case_holding"]["falsifier"])
    original_exit = _placeholder(fix["records"][0]["case_holding"]["exit_plan"])

    verdict = thesis_store.check_continuity(store, rows[0], rows[1])
    assert verdict["status"] == "REJECTED_UNRECORDED_AMENDMENT"
    assert verdict["thesis_unchanged"] is True
    assert len(verdict["findings"]) == 1
    assert verdict["findings"][0]["code"] == "UNRECORDED_AMENDMENT"
    assert "conviction" not in verdict["findings"][0]["changes"]
    assert verdict["conviction_change"] == {"old": "medium", "new": "high"}

    # The stored thesis is untouched: the as-of view after the rejected call
    # still returns the original falsifier and exit condition.
    after = thesis_store.thesis_as_of(store, thesis["thesis_id"], "2026-10-06")
    assert after["fields"]["falsifier"] == original_falsifier
    assert after["fields"]["exit_plan"] == original_exit
    assert after["local_thesis_status"] == "ACTIVE"
    assert after["applied_amendment_ids"] == []
    assert thesis_store.load_amendments(store) == [], "no amendment may be implied"

    # The conviction leg was recorded as an observation instead.
    observations = thesis_store.load_observations(store)
    assert len(observations) == 1
    assert observations[0]["schema"] == "pbr.thesis_observation.v1"
    assert observations[0]["field"] == "conviction"
    assert observations[0]["value"] == "high" and observations[0]["previous_value"] == "medium"
    assert observations[0]["cycle_id"] == rows[1]["decision_id"]
    assert observations[0]["thesis_id"] == thesis["thesis_id"]

    # With a covering AmendmentRecord the same pair is accepted.
    covering = thesis_store.record_amendment(
        store,
        {
            "thesis_id": thesis["thesis_id"],
            "changes": verdict["watched_changes"],
            "reason_code": "SUPERSEDED",
            "note": _note_digest("amendment recorded against the superseded decision"),
            "evidence_refs": [rows[0]["decision_id"]],
            "effective_at": rows[1]["asof"],
            "recorded_at": rows[1]["ts"],
            "accountable_decision_id": rows[1]["decision_id"],
        },
        originating_decision_asof=rows[0]["asof"],
    )
    assert covering["reason_code"] == "SUPERSEDED"
    accepted = thesis_store.check_continuity(store, rows[0], rows[1])
    assert accepted["status"] == "ACCEPTED_AMENDMENT_RECORDED"
    assert accepted["findings"] == []
    assert accepted["amendment_covered"] is True
    assert accepted["thesis_unchanged"] is True


def test_conviction_change_is_observation_not_amendment(tmp_path):
    import brain.thesis_store as thesis_store

    store = tmp_path / "store"
    fix = _load(MU_ENTRY)
    thesis = _mu_thesis_record(store, fix, thesis_store)
    amendment_fix = _load(MU_AMENDMENT)
    row = _holding_row(amendment_fix, 76)
    perturbed = dict(row, conviction="medium")  # differs ONLY in conviction
    assert set(
        key for key in row if thesis_store.materially_different(row[key], perturbed[key])
    ) == {"conviction"}

    verdict = thesis_store.check_continuity(store, row, perturbed)
    assert verdict["status"] == "ACCEPTED_NO_WATCHED_CHANGE"
    assert verdict["findings"] == []
    assert verdict["watched_changes"] == {}
    assert verdict["conviction_change"] == {"old": "high", "new": "medium"}
    assert verdict["thesis_unchanged"] is True

    lines = (store / "observations.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    observation = json.loads(lines[0])
    assert observation["schema"] == "pbr.thesis_observation.v1"
    assert observation["thesis_id"] == thesis["thesis_id"]
    assert observation["cycle_id"] == perturbed["decision_id"]
    assert observation["asof"] == perturbed["asof"]
    assert observation["field"] == "conviction"
    assert observation["value"] == "medium"
    assert thesis_store.load_amendments(store) == []
    # And a pure conviction change never produces an UNRECORDED_AMENDMENT.
    assert thesis_store.detect_unrecorded_amendments([row, perturbed]) == []


def test_terminal_amendment_requires_closed_reason_code(tmp_path):
    import brain.thesis_store as thesis_store

    store = tmp_path / "store"
    fix = _load(MU_ENTRY)
    thesis = _mu_thesis_record(store, fix, thesis_store)
    record = fix["records"][0]
    common = dict(
        effective_at="2026-10-07",
        recorded_at="2026-10-07T00:00:00+00:00",
        accountable_decision_id=record["decision_id"],
        originating_decision_asof=record["row"]["asof"],
    )
    before = thesis_store.load_amendments(store)

    # INVALIDATED without a reason_code → refused, nothing appended.
    with pytest.raises(thesis_store.ThesisStoreError):
        thesis_store.record_terminal_amendment(
            store, thesis["thesis_id"], status="INVALIDATED", reason_code=None, **common
        )
    # An unknown reason_code → refused (terminal ...).
    with pytest.raises(thesis_store.ThesisStoreError):
        thesis_store.record_terminal_amendment(
            store, thesis["thesis_id"], status="INVALIDATED", reason_code="GUT_FEEL", **common
        )
    # ...and on any amendment that carries one.
    with pytest.raises(thesis_store.ThesisStoreError):
        thesis_store.record_amendment(
            store,
            {
                "thesis_id": thesis["thesis_id"],
                "changes": {"falsifier": {"old": "a", "new": "b"}},
                "reason_code": "NOT_IN_THE_ENUM",
                "evidence_refs": [record["decision_id"]],
                "effective_at": "2026-10-07",
                "recorded_at": "2026-10-07T00:00:00+00:00",
                "accountable_decision_id": record["decision_id"],
            },
            originating_decision_asof=record["row"]["asof"],
        )
    assert thesis_store.load_amendments(store) == before

    # FALSIFIED → accepted; the note is a digest-shaped dict, never prose.
    amendment = thesis_store.record_terminal_amendment(
        store,
        thesis["thesis_id"],
        status="INVALIDATED",
        reason_code="FALSIFIED",
        note=_note_digest("dated falsifier event recorded against the episode"),
        evidence_refs=[record["decision_id"]],
        **common,
    )
    assert amendment["reason_code"] == "FALSIFIED"
    assert amendment["schema"] == "pbr.thesis_amendment.v1"
    assert isinstance(amendment["note"], dict) and set(amendment["note"]) >= {"sha256", "length"}
    assert thesis_store.thesis_as_of(store, thesis["thesis_id"], "2026-10-08")[
        "local_thesis_status"
    ] == "INVALIDATED"


def test_provider_plan_missing_never_yields_local_none_recorded(tmp_path):
    import brain.facts as facts
    import brain.thesis_store as thesis_store

    store = tmp_path / "store"
    fix = _load(MU_ENTRY)
    _mu_thesis_record(store, fix, thesis_store)
    planless_packet = {
        "feed_active": True,
        "management": ["MSFT", "XOM"],
        "discovery": [],
        "held_without_active_plan": ["MU"],
    }
    view = thesis_store.thesis_view(
        store, "autonomous", "MU", "2026-10-05", planless_packet, "2026-10-22"
    )
    assert view["provider_plan_status"] == "held_without_active_plan"
    assert view["local_thesis_status"] == "ACTIVE"
    assert [f["code"] for f in view["findings"]] == [
        "PROVIDER_PLAN_MISSING_LOCAL_THESIS_PRESENT"
    ]
    assert view["thesis"]["thesis_id"].startswith("thesis.v1.")

    # An unavailable feed changes nothing about the local state.
    unavailable = thesis_store.thesis_view(
        store, "autonomous", "MU", "2026-10-05", {"feed_active": False}, "2026-10-22"
    )
    assert unavailable["provider_plan_status"] == "unavailable"
    assert unavailable["local_thesis_status"] == "ACTIVE"
    assert [f["code"] for f in unavailable["findings"]] == [
        "PROVIDER_PLAN_MISSING_LOCAL_THESIS_PRESENT"
    ]

    # Perturbation: no local record and no provider plan — NONE_RECORDED is
    # legitimate, and the exit path stays eligible (rule iv).
    empty_store = tmp_path / "empty_store"
    empty_store.mkdir()
    none_view = thesis_store.thesis_view(
        empty_store, "autonomous", "MU", "2026-10-05", planless_packet, "2026-10-22"
    )
    assert none_view["local_thesis_status"] == "NONE_RECORDED"
    assert none_view["findings"] == []
    assert none_view["thesis"] is None
    assert facts.entry_fact_findings([], [], "exit")["eligible"] is True
    active_plan_view = thesis_store.thesis_view(
        store,
        "autonomous",
        "MU",
        "2026-10-05",
        {
            "feed_active": True,
            "management": ["MU"],
            "discovery": [],
            "held_without_active_plan": [],
        },
        "2026-10-22",
    )
    assert active_plan_view["provider_plan_status"] == "active_plan"
    assert active_plan_view["findings"] == []


def test_xom_thesis_episode_positive_control(tmp_path):
    import brain.facts as facts
    import brain.shadow_risk_budget as shadow_risk_budget
    import brain.thesis_store as thesis_store

    store = tmp_path / "store"
    fix = _load(XOM_CONTROL)
    by_line = {r["line_index_0based"]: r for r in fix["records"]}
    row38 = by_line[38]
    holding = row38["case_holding"]
    assert holding["ticker"] == "XOM"
    fill1, fill2 = fix["fills"][0]["row"], fix["fills"][1]["row"]
    assert fix["fills"][1]["linked_decision_ids"] == [by_line[40]["decision_id"]]
    assert fill1["price"] == 158.03 and fill2["price"] == 160.10
    assert (fill1["date"], fill2["date"]) == ("2026-08-13", "2026-08-17")

    thesis = thesis_store.record_thesis(
        store,
        {
            "book": "autonomous",
            "ticker": "XOM",
            "episode_open_date": fill1["date"],
            "entry_fill_ids": [fill1["fill_id"], fill2["fill_id"]],
            "why_now": _placeholder(holding["why_now"]),
            "fact_ids": [],
            "horizon": _placeholder(holding["expected_horizon"]),
            "falsifiers": [_placeholder(holding["falsifier"])],
            "exit_conditions": [_placeholder(holding["exit_plan"])],
            "position_role": "starter",
            "originating_decision_id": row38["decision_id"],
            "created_at": row38["row"]["ts"],
        },
    )
    assert thesis["schema"] == "pbr.thesis.v1"
    # Retrieval by episode and by both entry fill ids.
    assert thesis_store.thesis_for_episode(
        store, "autonomous", "XOM", "2026-08-13"
    )["thesis_id"] == thesis["thesis_id"]
    assert thesis_store.thesis_for_fill(store, fill1["fill_id"]) is not None
    assert thesis_store.thesis_for_fill(store, fill2["fill_id"]) is not None

    as_of = thesis_store.thesis_as_of(store, thesis["thesis_id"], "2026-08-14")
    assert as_of["local_thesis_status"] == "ACTIVE"
    assert as_of["fields"]["falsifier"] == _placeholder(holding["falsifier"])
    assert as_of["applied_amendment_ids"] == []

    # Eligible under every check: clean provider plan, no findings, price levels
    # inside the band against a qualified mark, and a positive eligible weight.
    view = thesis_store.thesis_view(
        store,
        "autonomous",
        "XOM",
        "2026-08-13",
        {"feed_active": True, "management": ["XOM"], "discovery": [], "held_without_active_plan": []},
        "2026-08-14",
    )
    assert view["local_thesis_status"] == "ACTIVE"
    assert view["provider_plan_status"] == "active_plan"
    assert view["findings"] == []

    cfg = shadow_risk_budget.load_params(CONFIG)
    mark = {
        "schema": facts.REFERENCE_MARK_SCHEMA,
        "value": 158.03,
        "currency": "USD",
        "basis": {"adjustment": "unadjusted_close", "split_assumption": "current_shares"},
        "symbol": "XOM",
        "asof": row38["row"]["asof"],
        "source": facts.MARK_SOURCE_ECON_UNION_MARK,
        "store_ref": "test-double",
        "mark_source": "test-double",
    }
    instrument = {"ticker": "XOM", "book": "autonomous", "venue": None, "identity_status": holding["identity_status"]}
    outcomes = []
    for value in (153.0, 137.5):  # SR-1 rule (3) declared levels; tokens "153" / "137.50"
        price_fact = {
            "fact_id": facts.fact_id_for(
                _placeholder(holding["falsifier"]), instrument, "price_level", f"{row38['decision_id']}#falsifier:{value}"
            ),
            "claim_text": _placeholder(holding["falsifier"]),
            "kind": "price_level",
            "instrument": instrument,
            "value": value,
            "unit": "price_per_share",
            "currency": "USD",
            "period": None,
            "published_at": None,
            "available_at": None,
            "observed_at": None,
            "basis": {"adjustment": "unadjusted_close", "split_assumption": "current_shares", "currency": "USD"},
            "source_class": "model_interpretation",
            "source_family": "decision_package",
            "source_ref": f"{row38['decision_id']}#falsifier:{value}",
            "decision_asof": row38["row"]["asof"],
        }
        outcome = facts.verify_fact(price_fact, reference_mark=mark, config=cfg)
        assert outcome["verdict"] == facts.VerificationOutcome.UNVERIFIED
        assert outcome["verdict"] != facts.VerificationOutcome.BASIS_UNRECONCILED
        outcomes.append((price_fact, outcome))
    findings = facts.entry_fact_findings(
        [f for f, _ in outcomes], [o for _, o in outcomes], "add"
    )
    assert findings["eligible"] is True
    assessment = shadow_risk_budget.assess(
        {
            "book": "autonomous",
            "ticker": "XOM",
            "action": "add",
            "position_role": "starter",
            "categorical_cap": 0.10,
            "cap_source": "autonomous deterministic_conviction_allocator.v2 conviction_caps.medium (recorded row-38 weight 0.10)",
            "source_families": 3,
            "primary_mix": "primary_dominant",
            "technical_coverage": "ok",
            "fact_outcomes": [o for _, o in outcomes],
        },
        cfg,
    )
    assert assessment["eligible_weight"] > 0


def test_falsy_thesis_id_backfilled_with_derived_id(tmp_path):
    """R-1750 F4: a present-but-falsy ``thesis_id`` ("" or None) is treated as
    absent — the derived episode id is backfilled, never the falsy value."""
    import brain.thesis_store as thesis_store

    fix = _load(MU_ENTRY)
    record = fix["records"][0]
    holding = record["case_holding"]
    fill = fix["fills"][0]["row"]
    derived = thesis_store.make_thesis_id(
        _book_of(fix), fix["ticker"], fill["date"], record["decision_id"]
    )

    def _payload(thesis_id):
        return {
            "thesis_id": thesis_id,
            "book": _book_of(fix),
            "ticker": fix["ticker"],
            "episode_open_date": fill["date"],
            "entry_fill_ids": [fill["fill_id"]],
            "why_now": _placeholder(holding["why_now"]),
            "fact_ids": [],
            "horizon": _placeholder(holding["expected_horizon"]),
            "falsifiers": [_placeholder(holding["falsifier"])],
            "exit_conditions": [_placeholder(holding["exit_plan"])],
            "position_role": "starter",
            "originating_decision_id": record["decision_id"],
            "created_at": record["row"]["ts"],
        }

    for falsy in (None, ""):
        store = tmp_path / ("store_" + ("none" if falsy is None else "empty"))
        stored = thesis_store.record_thesis(store, _payload(falsy))
        assert stored["thesis_id"] == derived, falsy
        retrieved = thesis_store.thesis_for_episode(
            store, _book_of(fix), fix["ticker"], fill["date"]
        )
        assert retrieved["thesis_id"] == derived, falsy

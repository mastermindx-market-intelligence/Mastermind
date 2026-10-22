"""The decision ledger is APPEND-ONLY with ``supersedes`` (bot/decision_rows).

A later same-day write appends a new row naming the rows it supersedes; prior bytes are never
rewritten. One effective-row accessor (``effective_rows`` / ``read_effective_rows``) reproduces
exactly the historical one-row-per-asof view, so every reader keeps its behaviour.

Layers covered here:
  1. accessor units (``row_identity``, ``effective_rows``, ``read_effective_rows``);
  2. append-only byte law (asof mode, revise mode, barren drop, identical re-write);
  3. legacy files (two same-day rows, no row_id) superseded by one appended row;
  4. property equivalence against a FROZEN verbatim copy of master's in-place
     ``replace_for_asof`` over seeded random op sequences;
  5. discriminating settlement behaviour through ``reconcile_settlement`` (the retry that the
     raw matcher would have false-conflicted);
  6. ``refresh_lesson_links`` + ``validate_queued_decision_snapshot`` on a 2-raw-row file;
  7. the static guard: no production module rewrites the ledger behind the accessor.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
from pathlib import Path

import pytest

from bot import decision_rows as dr
from bot.decision_rows import is_substantive
from test_decision_settlement_reconciliation import _receipt_for, _sign_receipt_fills


def _canon(value) -> str:
    return dr._canonical_sha256(value)


def _dump(row) -> str:
    return json.dumps(dr.strip_supersession(row), default=str, ensure_ascii=False)


# ---------------------------------------------------------------------------
# FROZEN reference: master's in-place replace_for_asof (1b7e1b3e), byte-verbatim body.
# ---------------------------------------------------------------------------

def _master_replace_for_asof(existing: list[dict], entry: dict, asof: str) -> list[dict]:
    """FROZEN verbatim copy of master's pre-append-only ``replace_for_asof``.

    Equivalence oracle for the properties below: the append-only ledger's effective view must
    reproduce exactly this in-place-rewrite behaviour per asof, and in global order except when
    this reference's barren guard reorders same-day rows to the end (the new side writes nothing
    there, so the file order legitimately differs).
    """
    kept = [r for r in existing if r.get("asof") != asof]
    same_day = [r for r in existing if r.get("asof") == asof]
    if same_day and not is_substantive(entry) and any(is_substantive(r) for r in same_day):
        return kept + same_day
    return kept + [entry]


# ---------------------------------------------------------------------------
# 1. accessor units
# ---------------------------------------------------------------------------

def test_row_identity_uses_stored_row_id_when_valid():
    row = dr.plan_decision_row([], {"asof": "2026-08-01", "summary": "s"}, "2026-08-01")
    assert re.fullmatch(r"row\.v1\.[0-9a-f]{24}", row["row_id"])
    assert dr.row_identity(row) == row["row_id"]


def test_row_identity_legacy_rows_hash_canonically():
    legacy = {"asof": "2026-08-01", "summary": "s"}
    assert dr.row_identity(legacy) == "row.v1." + _canon(legacy)[:24]
    reordered = {"summary": "s", "asof": "2026-08-01"}
    assert dr.row_identity(legacy) == dr.row_identity(reordered)
    # an invalid stored row_id is not trusted: the row hashes as it stands
    with_row_id = {**legacy, "row_id": "not-a-row-id"}
    assert dr.row_identity(with_row_id) == "row.v1." + _canon(with_row_id)[:24]


def test_row_id_hash_excludes_row_id_itself():
    entry = {"asof": "2026-08-01", "summary": "s"}
    row = dr.plan_decision_row([], entry, "2026-08-01")
    without_row_id = {k: v for k, v in row.items() if k != "row_id"}
    assert row["row_id"] == "row.v1." + _canon(without_row_id)[:24]


def test_effective_rows_cross_asof_pointer_is_ignored():
    a = dr.plan_decision_row([], {"asof": "2026-08-01", "summary": "a"}, "2026-08-01")
    other_day = {"asof": "2026-08-02", "summary": "b", "supersedes": [a["row_id"]],
                 "supersede_mode": "asof", "row_id": "row.v1." + "b" * 24}
    assert dr.effective_rows([a, other_day]) == [a, other_day]


def test_effective_rows_forward_pointer_is_ignored():
    a = dr.plan_decision_row([], {"asof": "2026-08-01", "summary": "a"}, "2026-08-01")
    early = {"asof": "2026-08-01", "summary": "early", "supersedes": [a["row_id"]],
             "supersede_mode": "asof", "row_id": "row.v1." + "c" * 24}
    assert dr.effective_rows([early, a]) == [early, a]


def test_effective_rows_unknown_pointer_is_ignored():
    a = {"asof": "2026-08-01", "summary": "a", "supersedes": ["row.v1." + "f" * 24],
         "supersede_mode": "asof", "row_id": "row.v1." + "d" * 24}
    assert dr.effective_rows([a]) == [a]


def test_effective_rows_non_dict_items_pass_through_never_superseded():
    a = dr.plan_decision_row([], {"asof": "2026-08-01", "summary": "a"}, "2026-08-01")
    killer = {"asof": "2026-08-01", "summary": "k", "supersedes": [a["row_id"]],
              "supersede_mode": "asof", "row_id": "row.v1." + "e" * 24}
    junk = ["not a dict", 42]
    rows = [junk[0], a, junk[1], killer]
    assert dr.effective_rows(rows) == [junk[0], junk[1], killer]


@pytest.mark.parametrize("bad", [
    "row.v1.x", ["not", "a", "list"], ["ok", 5], [], {"nope": True}, None,
])
def test_effective_rows_invalid_supersedes_is_ignored(bad):
    a = dr.plan_decision_row([], {"asof": "2026-08-01", "summary": "a"}, "2026-08-01")
    killer = {"asof": "2026-08-01", "summary": "k", "supersedes": bad,
              "supersede_mode": "asof", "row_id": "row.v1." + "9" * 24}
    assert dr.effective_rows([a, killer]) == [a, killer]


def test_effective_rows_revise_row_takes_the_superseded_row_slot():
    monday = dr.plan_decision_row([], {"asof": "2026-08-11", "summary": "m"}, "2026-08-11")
    tuesday = dr.plan_decision_row([], {"asof": "2026-08-12", "summary": "t"}, "2026-08-12")
    fix = dr.plan_decision_row(
        [monday, tuesday], {"asof": "2026-08-11", "summary": "m-fixed"}, "2026-08-11",
        revises=monday,
    )
    rows = [monday, tuesday, fix]
    assert [r["summary"] for r in dr.effective_rows(rows)] == ["m-fixed", "t"]


def test_effective_rows_revise_chain_resolves_to_the_original_slot():
    first = dr.plan_decision_row([], {"asof": "2026-08-11", "summary": "v1"}, "2026-08-11")
    second = dr.plan_decision_row(
        [first], {"asof": "2026-08-11", "summary": "v2"}, "2026-08-11", revises=first)
    third = dr.plan_decision_row(
        [first, second], {"asof": "2026-08-11", "summary": "v3"}, "2026-08-11", revises=second)
    later_day = dr.plan_decision_row([], {"asof": "2026-08-12", "summary": "next"}, "2026-08-12")
    rows = [first, later_day, second, third]
    assert [r["summary"] for r in dr.effective_rows(rows)] == ["v3", "next"]


def test_effective_rows_single_long_revise_chain_keeps_exact_order():
    """One 400-row revise chain on one asof, interleaved with other-asof rows: the chain head
    takes the original row's slot, every link is superseded, and the interleaved rows keep
    their exact file order after it."""
    chain_length = 400
    chain = [dr._build_row({"asof": "2026-08-01", "summary": "v0"}, [], "asof")]
    for index in range(1, chain_length):
        chain.append(dr._build_row(
            {"asof": "2026-08-01", "summary": f"v{index}"},
            [chain[-1]["row_id"]], "revise",
        ))
    rows: list = []
    interleaved: list[dict] = []
    for index, row in enumerate(chain):
        rows.append(row)
        if index % 37 == 0:
            other = {"asof": "2026-08-02", "summary": f"other-{index}", "holdings": []}
            interleaved.append(other)
            rows.append(other)

    effective = dr.effective_rows(rows)
    assert effective[0] == chain[-1]
    assert [r["summary"] for r in effective] == \
        ["v399"] + [other["summary"] for other in interleaved]
    assert all(other in effective for other in interleaved)
    assert len(effective) == 1 + len(interleaved)


def test_effective_rows_fast_path_hashes_nothing_and_copies(monkeypatch):
    rows = [{"asof": "2026-08-01", "summary": "a"}, {"asof": "2026-08-02", "summary": "b"}]

    def boom(value):
        raise AssertionError("fast path must not hash anything")

    monkeypatch.setattr(dr, "_canonical_sha256", boom)
    out = dr.effective_rows(rows)
    assert out == rows
    assert out is not rows


def test_effective_rows_is_pure():
    original = [
        {"asof": "2026-08-01", "summary": "a"},
        {"asof": "2026-08-01", "summary": "a", "supersedes": ["row.v1." + "1" * 24],
         "supersede_mode": "asof", "row_id": "row.v1." + "2" * 24},
    ]
    frozen = json.loads(json.dumps(original))
    dr.effective_rows(original)
    assert original == frozen
    out = dr.effective_rows(original)
    out.append({"injected": True})
    assert len(original) == 2


def test_read_effective_rows_strict_matches_read_rows_errors(tmp_path):
    p = tmp_path / "decisions.jsonl"
    assert dr.read_effective_rows(p, strict=True) == []          # missing -> [] like read_rows
    p.write_text('{"asof": "2026-08-01"}\n[1, 2]\n', encoding="utf-8")
    with pytest.raises(ValueError, match="decision ledger row must be an object"):
        dr.read_effective_rows(p, strict=True)
    p.write_text('{"asof": "2026-08-01"}\n{broken\n', encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        dr.read_effective_rows(p, strict=True)


def test_read_effective_rows_lenient_skips_junk_and_missing(tmp_path):
    p = tmp_path / "decisions.jsonl"
    assert dr.read_effective_rows(p) == []                       # missing
    (tmp_path / "adir").mkdir()
    assert dr.read_effective_rows(tmp_path / "adir") == []       # unreadable
    good = '{"asof": "2026-08-01", "summary": "a"}'
    p.write_bytes(
        b"\n" + good.encode("utf-8") + b"\n{broken\n[1,2]\n\xff\xfe\xfa\n" + good.encode() + b"\n"
    )
    rows = dr.read_effective_rows(p)
    assert [r.get("summary") for r in rows] == ["a", "a"]


def test_read_effective_rows_tail_applies_after_the_whole_file_is_effectivized(tmp_path):
    p = tmp_path / "decisions.jsonl"
    a = dr.append_decision_row(p, {"asof": "2026-08-01", "summary": "a"}, "2026-08-01")
    b = dr.append_decision_row(p, {"asof": "2026-08-02", "summary": "b"}, "2026-08-02")
    # a same-day correction APPENDED LAST still owns the first slot: tail must read it all
    fix = dr.append_decision_row(
        p, {**a, "summary": "a-fixed"}, "2026-08-01", revises=a)
    assert [r["summary"] for r in dr.read_effective_rows(p)] == ["a-fixed", "b"]
    assert [r["summary"] for r in dr.read_effective_rows(p, tail=1)] == ["b"]
    assert [r["summary"] for r in dr.read_effective_rows(p, tail=2)] == ["a-fixed", "b"]
    assert dr.read_effective_rows(p, tail=0) == []
    assert dr.read_effective_rows(p, tail=99) == [fix, b]


# ---------------------------------------------------------------------------
# 2. append-only byte law
# ---------------------------------------------------------------------------

BOOK = {"asof": "2026-07-24", "summary": "Rotating into HK financials",
        "holdings": [{"ticker": "0005.HK", "weight": 0.1}]}
STUB = {"asof": "2026-07-24", "summary": None, "holdings": [],
        "error": "You've hit your session limit"}


def _write_seed(path: Path, rows: list[dict]) -> bytes:
    dr.write_rows(path, rows)  # tests seed fixtures with write_rows (production never does)
    return path.read_bytes()


def test_append_only_asof_mode(tmp_path):
    p = tmp_path / "decisions.jsonl"
    first = dr.append_decision_row(p, BOOK, "2026-07-24")
    assert first["supersede_mode"] == "asof"
    before = p.read_bytes()
    better = {**BOOK, "summary": "revised after the close"}
    appended = dr.append_decision_row(p, better, "2026-07-24")
    raw = p.read_bytes()
    assert raw.startswith(before)
    assert raw == before + _dump_row_bytes(appended)
    assert appended["supersedes"] == [first["row_id"]]
    assert [r["summary"] for r in dr.read_effective_rows(p)] == ["revised after the close"]


def test_append_only_revise_mode(tmp_path):
    p = tmp_path / "decisions.jsonl"
    queued = dr.append_decision_row(p, BOOK, "2026-07-24")
    before = p.read_bytes()
    executed = dr.append_decision_row(
        p, {**BOOK, "target_status": "executed"}, "2026-07-24", revises=queued)
    raw = p.read_bytes()
    assert raw.startswith(before)
    assert raw == before + _dump_row_bytes(executed)
    assert executed["supersede_mode"] == "revise"
    assert executed["supersedes"] == [queued["row_id"]]
    effective = dr.read_effective_rows(p)
    assert len(effective) == 1 and effective[0]["target_status"] == "executed"


def _dump_row_bytes(row: dict) -> bytes:
    return json.dumps(row, default=str, ensure_ascii=False).encode("utf-8") + b"\n"


def test_no_op_writes_leave_the_file_byte_identical(tmp_path):
    p = tmp_path / "decisions.jsonl"
    dr.append_decision_row(p, BOOK, "2026-07-24")
    before = p.read_bytes()
    # barren entry after a substantive book: nothing written
    assert dr.append_decision_row(p, STUB, "2026-07-24") is None
    assert p.read_bytes() == before
    # identical re-write: nothing written
    assert dr.append_decision_row(p, dict(BOOK), "2026-07-24") is None
    assert p.read_bytes() == before


def test_file_without_trailing_newline_gets_exactly_one_separator(tmp_path):
    p = tmp_path / "decisions.jsonl"
    legacy = {"asof": "2026-07-23", "summary": "older book"}
    p.write_bytes(json.dumps(legacy).encode("utf-8"))          # no trailing newline
    before = p.read_bytes()
    appended = dr.append_decision_row(p, BOOK, "2026-07-24")
    raw = p.read_bytes()
    assert raw.startswith(before)
    assert raw == before + b"\n" + _dump_row_bytes(appended)


def test_empty_file_writes_without_separator(tmp_path):
    p = tmp_path / "decisions.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"")
    appended = dr.append_decision_row(p, BOOK, "2026-07-24")
    assert p.read_bytes() == _dump_row_bytes(appended)


# ---------------------------------------------------------------------------
# 3. legacy file with two same-day rows (no row_id)
# ---------------------------------------------------------------------------

def test_legacy_two_same_day_rows_both_superseded_by_one_appended_row(tmp_path):
    p = tmp_path / "decisions.jsonl"
    a = {"asof": "2026-08-01", "summary": "first", "holdings": [{"ticker": "X", "weight": 0.3}]}
    b = {"asof": "2026-08-01", "summary": "second", "holdings": [{"ticker": "Y", "weight": 0.4}]}
    seeded = _write_seed(p, [a, b])
    entry = {"asof": "2026-08-01", "summary": "real book",
             "holdings": [{"ticker": "Z", "weight": 0.5}]}
    appended = dr.append_decision_row(p, entry, "2026-08-01")
    raw = p.read_bytes()
    assert raw.startswith(seeded)                              # append-only: legacy bytes intact
    assert appended["supersede_mode"] == "asof"
    assert appended["supersedes"] == [dr.row_identity(a), dr.row_identity(b)]
    effective = dr.read_effective_rows(p)
    assert len(effective) == 1
    assert [dr.strip_supersession(r) for r in effective] == [entry]
    # the legacy rows keep their original bytes, line for line
    lines = raw.splitlines()
    assert lines[0] == json.dumps(a, default=str, ensure_ascii=False).encode()
    assert lines[1] == json.dumps(b, default=str, ensure_ascii=False).encode()


# ---------------------------------------------------------------------------
# 4. property equivalence vs master's in-place replace_for_asof
# ---------------------------------------------------------------------------

_ASOFS = ["2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04", "2026-09-05"]
_TRIALS = 205
_OPS = 32


def _random_entry(rng: random.Random, op_index: int, last_accepted: dict) -> dict:
    asof = rng.choice(_ASOFS)
    kind = rng.choices(
        ("accept", "accept_repeat", "barren_stub", "barren_reject", "narrative"),
        weights=(4, 2, 2, 1, 2),
    )[0]
    if kind == "accept":
        ticker = f"T{rng.randrange(5)}"
        weight = round(rng.uniform(0.05, 0.5), 3)
        entry = {
            "asof": asof,
            "summary": f"book {op_index}",
            "holdings": [{"ticker": ticker, "weight": weight}],
        }
        if rng.random() < 0.4:
            entry.update({
                "decision_effective": True,
                "target_status": "queued",
                "target_sha256": _canon({ticker: weight}),
                "decision_id": "decision.v1." + _canon([asof, ticker])[:24],
            })
        last_accepted[asof] = json.loads(json.dumps(entry))
        return entry
    if kind == "accept_repeat":
        prior = last_accepted.get(asof)
        if prior is None:
            entry = {"asof": asof, "summary": f"book {op_index}",
                     "holdings": [{"ticker": "T0", "weight": 0.2}]}
            last_accepted[asof] = json.loads(json.dumps(entry))
            return entry
        return json.loads(json.dumps(prior))
    if kind == "barren_stub":
        return {"asof": asof, "summary": None, "holdings": [],
                "error": "synthetic session limit"}
    if kind == "barren_reject":
        return {"asof": asof, "summary": None, "holdings": [],
                "target_status": "rejected_no_submission", "decision_effective": False}
    return {"asof": asof, "summary": f"narrative {op_index}", "holdings": []}


def _assert_trial_invariants(path: Path, reference: list, as_of_stack: list):
    effective = dr.read_effective_rows(path) if path.exists() else []
    # per-asof: the effective view must equal the reference, always
    for asof in _ASOFS:
        new_view = [_dump(r) for r in effective if r.get("asof") == asof]
        ref_view = [_dump(r) for r in reference if r.get("asof") == asof]
        assert new_view == ref_view, (as_of_stack, asof, new_view, ref_view)
    return effective


def _run_trial(trial_index: int, root: Path) -> int:
    rng = random.Random(1_000_003 + trial_index)
    path = root / f"trial_{trial_index}" / "decisions.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    reference: list[dict] = []
    last_accepted: dict[str, dict] = {}
    previous_bytes = b""
    order_diffs = 0
    order_was_diff = False

    for op_index in range(_OPS):
        if reference and rng.random() < 0.22:
            # revise op on a random effective row (reference side: in-place revision)
            idx = rng.randrange(len(reference))
            target = reference[idx]
            revised = dict(target)
            revised["summary"] = f"revise {trial_index}.{op_index}"
            effective_before = dr.read_effective_rows(path)
            twins = [
                r for r in effective_before
                if r.get("asof") == target.get("asof")
                and dr.strip_supersession(r) == dr.strip_supersession(target)
            ]
            assert len(twins) == 1, (trial_index, op_index)
            appended = dr.append_decision_row(
                path, revised, revised["asof"], revises=twins[0])
            reference[idx] = revised
        else:
            entry = _random_entry(rng, op_index, last_accepted)
            appended = dr.append_decision_row(path, entry, entry["asof"])
            reference[:] = _master_replace_for_asof(reference, entry, entry["asof"])

        # append-only bytes, checked after EVERY op
        current = path.read_bytes() if path.exists() else b""
        if appended is None:
            assert current == previous_bytes, (trial_index, op_index)
        else:
            assert current.startswith(previous_bytes), (trial_index, op_index)
        previous_bytes = current

        effective = _assert_trial_invariants(path, reference, (trial_index, op_index))
        order_is_diff = [_dump(r) for r in effective] != [_dump(r) for r in reference]
        if order_is_diff:
            order_diffs += 1
            if not order_was_diff:
                # a NEW divergence may only be introduced where the reference's barren guard /
                # identical re-write moved rows to the end while the append-only file
                # (correctly) wrote nothing; a writing op keeps both orders locked in step
                assert appended is None, (trial_index, op_index)
        order_was_diff = order_is_diff
    return order_diffs


def test_property_equivalence_with_master_reference_over_random_sequences(tmp_path):
    """>=200 seeded sequences of >=30 ops: per-asof equality with master's in-place reference
    after EVERY op; global order equal except reference-side barren-guard reorders."""
    total_order_diffs = 0
    for trial in range(_TRIALS):
        total_order_diffs += _run_trial(trial, tmp_path)
    assert total_order_diffs > 0  # the reorder class really was exercised


# ---------------------------------------------------------------------------
# 5. settlement: discriminating behaviour through reconcile_settlement
# ---------------------------------------------------------------------------

def _master_raw_matches(rows, accepted_asof, decision_id_value, submission_hash, snapshot,
                        receipt_target_hash):
    """Master's RAW-row matcher predicate, verbatim in shape (it had no effective view)."""
    return [
        row for row in rows
        if str(row.get("accepted_asof") or row.get("asof") or "")[:10] == accepted_asof
        and row.get("decision_id") in {None, "", decision_id_value}
        and row.get("submission_sha256") in {None, "", submission_hash}
        and dr._target_lineage_matches(
            snapshot, dr._row_target_sha256(row), receipt_target_hash)
    ]


_SUBMISSION = {
    "schema": "mastermind.target_book.v2",
    "holdings": [{
        "ticker": "AAPL", "weight": 0.20, "action": "add", "action_effective": "add",
        "rationale": "accepted and receipt bound",
    }],
    "summary": "queued target",
}
_DERIVED = [{
    "ticker": "AAPL", "side": "buy", "shares": 2000.0,
    "price": 100.0, "value": 200_000.0, "fill_price_source": "test_open",
}]


def _queued_autonomous_book(monkeypatch, tmp_path):
    from bot import autonomous
    from portfolio import registry
    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    autonomous._append_decision_log(
        "2026-08-12", _SUBMISSION, [], [], {},
        target_status="queued", effective_target={"AAPL": 0.20},
    )
    return registry.data_dir("autonomous") / "decisions.jsonl"


def test_settlement_retry_is_idempotent_with_unchanged_bytes(tmp_path, monkeypatch):
    """(a) settle txn A, retry txn A: same success, no exception, bytes unchanged — and master's
    RAW matcher would have matched 2 rows (the false conflict this design removes)."""
    path = _queued_autonomous_book(monkeypatch, tmp_path)
    receipt = _receipt_for(_SUBMISSION)

    first = dr.reconcile_settlement("autonomous", receipt, _DERIVED)
    assert first["ok"] is True and first["reconciled"] is True
    before = path.read_bytes()

    second = dr.reconcile_settlement("autonomous", receipt, _DERIVED)
    assert second["ok"] is True
    assert second["deduplicated"] is True
    assert second["reconciled"] is False
    assert second["transaction_id"] == first["transaction_id"]
    assert second["decision_id"] == first["decision_id"]
    assert path.read_bytes() == before

    raw_rows = dr.read_rows(path)
    assert len(raw_rows) == 2                       # queued row + appended executed revise row
    expected_decision = dr.decision_id("autonomous", "2026-08-12", _SUBMISSION)
    snapshot = receipt["decision_snapshot"]
    would_match = _master_raw_matches(
        raw_rows, "2026-08-12", expected_decision,
        dr.submission_sha256(_SUBMISSION), snapshot, receipt["target_sha256"],
    )
    assert len(would_match) == 2, "master's raw matcher would have raised a false conflict"


def test_settlement_with_different_transaction_id_conflicts_without_mutating(tmp_path, monkeypatch):
    """(b) settle A, then reconcile a DIFFERENT committed transaction: today's conflict, bytes
    unchanged."""
    path = _queued_autonomous_book(monkeypatch, tmp_path)
    receipt = _receipt_for(_SUBMISSION)
    assert dr.reconcile_settlement("autonomous", receipt, _DERIVED)["reconciled"] is True
    before = path.read_bytes()

    other = _receipt_for(_SUBMISSION, transaction_id="b" * 64)
    # a genuinely different COMMITTED transaction: re-sign with a different settlement date —
    # the deterministic transaction id is the content hash of the identity preimage
    other["settlement_asof"] = "2026-08-14"
    other["fills"][0]["date"] = "2026-08-14"
    other = _sign_receipt_fills(other)
    assert other["transaction_id"] != receipt["transaction_id"]
    with pytest.raises(dr.DecisionSettlementConflict,
                       match="queued decision has conflicting settlement lineage"):
        dr.reconcile_settlement("autonomous", other, _DERIVED)
    assert path.read_bytes() == before


def test_two_unsuperseded_queued_rows_conflict_exactly_one_message(tmp_path, monkeypatch):
    """(c) two queued rows for the same decision, neither superseded: today's exactly-one
    conflict."""
    path = _queued_autonomous_book(monkeypatch, tmp_path)
    rows = dr.read_rows(path)
    dr.write_rows(path, rows + [dict(rows[0])])     # seed: duplicate the queued row (fixture)
    before = path.read_bytes()
    receipt = _receipt_for(_SUBMISSION)
    with pytest.raises(dr.DecisionSettlementConflict,
                       match="settlement did not match exactly one queued decision row"):
        dr.reconcile_settlement("autonomous", receipt, _DERIVED)
    assert path.read_bytes() == before


# ---------------------------------------------------------------------------
# 6. refresh_lesson_links + validate_queued_decision_snapshot (raw file has 2 rows)
# ---------------------------------------------------------------------------

def test_refresh_then_validate_finds_exactly_one_effective_row(tmp_path, monkeypatch):
    from brain import portfolio_learning
    from portfolio import registry
    path = _queued_autonomous_book(monkeypatch, tmp_path)
    monkeypatch.setattr(
        portfolio_learning, "trace_links",
        lambda submission, target_status: {"lesson_ids_cited": ["lesson-a1"]},
    )

    out = dr.refresh_lesson_links("autonomous", "2026-08-12", _SUBMISSION,
                                  target_status="queued")
    assert out == {
        "ok": True, "updated": True,
        "decision_id": dr.decision_id("autonomous", "2026-08-12", _SUBMISSION),
    }

    raw_rows = dr.read_rows(path)
    assert len(raw_rows) == 2                       # queued row + appended refreshed revise row
    assert raw_rows[1]["supersede_mode"] == "revise"
    assert raw_rows[1]["supersedes"] == [raw_rows[0]["row_id"]]
    assert raw_rows[1]["lesson_ids_cited"] == ["lesson-a1"]

    snapshot = {
        "decision_log_required": True,
        "portfolio_id": "autonomous",
        "accepted_asof": "2026-08-12",
        "submission": _SUBMISSION,
        "target_sha256": dr.target_sha256({"AAPL": 0.20}),
    }
    result = dr.validate_queued_decision_snapshot("autonomous", snapshot)
    assert result == {
        "ok": True, "required": True,
        "decision_id": dr.decision_id("autonomous", "2026-08-12", _SUBMISSION),
        "target_sha256": snapshot["target_sha256"],
    }
    # the discriminator: over RAW rows the validator's predicate would see 2 and raise
    assert len(_master_raw_matches(
        raw_rows, "2026-08-12",
        dr.decision_id("autonomous", "2026-08-12", _SUBMISSION),
        dr.submission_sha256(_SUBMISSION), snapshot, snapshot["target_sha256"],
    )) == 2


# ---------------------------------------------------------------------------
# 7. static guard: no production module rewrites the ledger
# ---------------------------------------------------------------------------

_WRITER_CALL = re.compile(r"\bwrite_rows\(|\b_atomic_write_rows\(")
# an alias import renames the writer at the import boundary: `import ... as ...`
_WRITER_ALIAS_IMPORT = re.compile(
    r"\b(?:write_rows|_atomic_write_rows|replace_for_asof)\s+as\b"
)
_WRITE_PRIMITIVE = re.compile(
    r"\.write_text\(|\.write_bytes\(|os\.replace\(|shutil\.move\(|shutil\.copy"
)
_QUOTED_LITERAL = re.compile(r"([\"'])([^\"'\n]*)\1")
_EXCLUDED_TOP_DIRS = {"vendor", "tests", "research", "docs", "node_modules"}
# bot/decision_rows.py OWNS the whole-file writers (tests seed fixtures through them).
# portfolio/advisor_trade.py defines its own unrelated local ``_atomic_write_rows`` for the
# advisor-proposal queue — a name collision, never the decision ledger.
_ALLOWED = {"bot/decision_rows.py", "portfolio/advisor_trade.py"}


def _names_writer_through_getattr(line: str) -> bool:
    """``getattr(<module>, "write_rows")`` — the writer reached under a dynamic name."""
    if "getattr(" not in line:
        return False
    return any(
        match.group(2) in ("write_rows", "_atomic_write_rows")
        for match in _QUOTED_LITERAL.finditer(line)
    )


def _opens_for_writing(line: str) -> bool:
    """``open(`` whose line carries a quoted ``w``/``a``/``x`` mode literal."""
    if "open(" not in line:
        return False
    for match in _QUOTED_LITERAL.finditer(line):
        mode = match.group(2)
        if re.fullmatch(r"[rwaxbt+]{1,4}", mode) and any(c in mode for c in "wax"):
            return True
    return False


def _ledger_write_guard_hits(line: str) -> list[str]:
    """Evasion-class labels one source line trips for the decision-ledger rewrite guard."""
    hits: list[str] = []
    if _WRITER_CALL.search(line):
        hits.append("direct_writer_call")
    if _WRITER_ALIAS_IMPORT.search(line):
        hits.append("writer_alias_import")
    if _names_writer_through_getattr(line):
        hits.append("getattr_writer_name")
    if "decisions.jsonl" in line and (
        _WRITE_PRIMITIVE.search(line) or _opens_for_writing(line)
    ):
        hits.append("inline_ledger_write")
    return hits


def test_ledger_write_guard_discriminates_evasion_classes_from_benign_lines():
    offenders = {
        "out = dr.write_rows(path, rows)": ["direct_writer_call"],
        "_atomic_write_rows(tmp_path, seeded)": ["direct_writer_call"],
        "from bot.decision_rows import write_rows as overwrite_ledger":
            ["writer_alias_import"],
        "from bot.decision_rows import replace_for_asof as rewrite_for_asof":
            ["writer_alias_import"],
        "writer = getattr(dr, \"write_rows\")": ["getattr_writer_name"],
        "writer = getattr(dr, '_atomic_write_rows')": ["getattr_writer_name"],
        '(root / "decisions.jsonl").write_text(payload)': ["inline_ledger_write"],
        'path.write_bytes(b"")  # decisions.jsonl': ["inline_ledger_write"],
        "os.replace(tmp, ledger_path)  # ledger_path is decisions.jsonl":
            ["inline_ledger_write"],
        'shutil.move(src, dst)  # dst is the decisions.jsonl path': ["inline_ledger_write"],
        'shutil.copy2(p, backup / p.name)  # decisions.jsonl backup': ["inline_ledger_write"],
        'handle = open("data/portfolios/hk/decisions.jsonl", "w")': ["inline_ledger_write"],
        # benign: a read-only open, and a plain mention
        'rows = dr.read_effective_rows(root / "decisions.jsonl")': [],
        'handle = open("data/portfolios/hk/decisions.jsonl", "r")': [],
    }
    for line, expected in offenders.items():
        assert _ledger_write_guard_hits(line) == expected, line


def test_no_production_module_rewrites_the_decision_ledger():
    root = Path(__file__).resolve().parent.parent
    offenders = []
    for py in sorted(root.rglob("*.py")):
        rel = py.relative_to(root)
        parts = rel.parts
        if parts[0] in _EXCLUDED_TOP_DIRS or any(part.startswith(".") for part in parts):
            continue
        rel_posix = rel.as_posix()
        if rel_posix in _ALLOWED:
            continue
        for lineno, line in enumerate(
            py.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if _ledger_write_guard_hits(line):
                offenders.append(f"{rel_posix}:{lineno}: {line.strip()}")
    assert offenders == []


# ---------------------------------------------------------------------------
# 8. operator scrub scripts tolerate degenerate effective rows
# ---------------------------------------------------------------------------

def _load_remove_positions_module():
    """Import scripts/remove_positions.py by file path (scripts is not a package)."""
    import importlib.util

    module_path = Path(__file__).resolve().parent.parent / "scripts" / "remove_positions.py"
    spec = importlib.util.spec_from_file_location("remove_positions_under_test", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_scrub_decisions_duplicate_identical_rows(tmp_path):
    """Two byte-identical effective rows: ONE revise supersedes both — no crash, the effective
    view holds the scrubbed row, the raw file keeps its byte prefix, and the count includes
    both copies' dropped entries."""
    rp = _load_remove_positions_module()
    path = tmp_path / "decisions.jsonl"
    row = {
        "asof": "2026-08-01",
        "summary": "book with the scrubbed name",
        "holdings": [{"ticker": "BAD", "weight": 0.5}],
        "executed": [{"ticker": "BAD", "side": "sell", "shares": 1.0}],
    }
    line = json.dumps(row)
    path.write_text(line + "\n" + line + "\n", encoding="utf-8")
    before = path.read_bytes()

    count = rp._scrub_decisions(path, {"BAD"})

    assert count == 4                       # 2 entries dropped per copy × 2 copies
    raw = path.read_bytes()
    assert raw.startswith(before)           # append-only: seeded bytes intact
    lines = raw.splitlines()
    assert len(lines) == 3                  # two seeded copies + exactly one appended revise
    effective = dr.read_effective_rows(path)
    assert len(effective) == 1
    assert effective[0]["holdings"] == []
    assert effective[0]["executed"] == []


def test_scrub_decisions_row_without_asof_is_skipped_uncounted(tmp_path, capsys):
    """A row without ``asof`` cannot name a revise target: no exception, row untouched, its
    drops are NOT counted, and one stderr line reports how many rows were left unscrubbed."""
    rp = _load_remove_positions_module()
    path = tmp_path / "decisions.jsonl"
    missing = {"summary": "legacy line", "holdings": [{"ticker": "BAD", "weight": 0.5}]}
    none_asof = {"asof": None, "summary": "undated line",
                 "executed": [{"ticker": "BAD", "side": "sell", "shares": 2.0}]}
    path.write_text(
        json.dumps(missing) + "\n" + json.dumps(none_asof) + "\n", encoding="utf-8"
    )
    before = path.read_bytes()

    count = rp._scrub_decisions(path, {"BAD"})

    assert count == 0
    assert path.read_bytes() == before      # nothing appended
    err = capsys.readouterr().err
    assert "2" in err and "asof" in err

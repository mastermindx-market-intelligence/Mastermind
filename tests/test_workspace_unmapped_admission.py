"""Canonical unmapped membership is readable, never a fabricated seat or root."""
import copy
from dataclasses import replace

import pytest

from control_plane import chairman_control_room as composer
from scripts import chairman_control_room as publisher
from tests.test_workspace_programs_qualification import empty_inputs, publish
from tests.test_workspace_read_service import cache_fixture, frame, run, service


def canonical(*, mapped=1, unmapped=1, stale=False, unreadable=False, blocked=False):
    inputs = empty_inputs()
    if stale:
        inputs["agent_os_state"]["generated_at"] = "2020-01-01T00:00:00Z"
    inputs["agent_os_state"]["workstreams"] = [
        {"key": f"MAPPED-{i}", "title": f"Mapped {i}", "owner": "ceo-sol", "status": "active"}
        for i in range(mapped)
    ] + [
        {"key": f"UNMAPPED-{i}", "title": "" if unreadable else f"Unmapped {i}",
         "owner": "ceo-sol" if unreadable else "unrecognized-owner", "status": "active",
         "blocked_by": ["WS:DEPENDENCY"] if blocked else []}
        for i in range(unmapped)
    ]
    return composer.compose_control_room(**inputs)


@pytest.mark.parametrize("mapped,unmapped", [(1, 1), (58, 17), (0, 2)])
@pytest.mark.parametrize("stale", [False, True])
def test_canonical_unmapped_coverage_is_readable_without_rewriting(tmp_path, mapped, unmapped, stale):
    doc = canonical(mapped=mapped, unmapped=unmapped, stale=stale)
    baseline = copy.deepcopy(doc)
    assert len(doc["work"]) == mapped + unmapped
    assert len(doc["autonomy"]["responsibilities"]) == mapped
    assert len(doc["autonomy"]["unmapped_responsibilities"]) == unmapped
    assert doc["autonomy"]["counts"]["empty"] is False
    result = publish(tmp_path, doc)
    assert result["availability"] == "AVAILABLE"
    assert result["control_room"] == baseline == doc
    assert result["source_observation"]["state"] == "SAME"
    assert result["source_observation"]["runtime"] is None
    assert {row["freshness"] for row in doc["autonomy"]["responsibilities"]} == (
        {"stale" if stale else "current"} if mapped else set())


@pytest.mark.parametrize("unreadable,blocked", [(True, False), (False, True)])
def test_canonical_unreadable_or_blocked_receipt_is_preserved(tmp_path, unreadable, blocked):
    doc = canonical(unreadable=unreadable, blocked=blocked)
    row = doc["autonomy"]["unmapped_responsibilities"][0]
    assert row["reason"] == ("row_unreadable" if unreadable else "owner_not_a_recognized_seat")
    assert ("declared_blocker" in row) is blocked
    assert publish(tmp_path, doc)["control_room"] == doc


@pytest.mark.parametrize("mutation", ["null", "code", "missing", "extra", "explanation", "seat", "unreadable"])
def test_malformed_declared_blocker_refuses(tmp_path, mutation):
    doc = canonical(blocked=True)
    row = doc["autonomy"]["unmapped_responsibilities"][0]
    blocker = row["declared_blocker"]
    if mutation == "null": row["declared_blocker"] = None
    elif mutation == "code": blocker["code"] = "healthy"
    elif mutation == "missing": del blocker["target_seat"]
    elif mutation == "extra": blocker["healthy"] = True
    elif mutation == "explanation": blocker["explanation"] = " "
    elif mutation == "seat": blocker["target_seat"] = "invented"
    elif mutation == "unreadable": row["reason"] = "row_unreadable"
    assert publish(tmp_path, doc)["availability"] == "UNAVAILABLE"


@pytest.mark.parametrize("mutation", [
    "absent", "null", "wrong_container", "non_row", "missing_ref", "null_ref", "non_string_ref",
    "blank_ref", "missing_reason", "unknown_reason", "extra_seat", "duplicate", "overlap", "orphan",
    "uncovered_work", "duplicate_work", "duplicate_mapped", "orphan_mapped", "bad_mapped_freshness",
])
def test_incomplete_malformed_or_conflicting_membership_refuses(tmp_path, mutation):
    doc = canonical()
    autonomy = doc["autonomy"]
    row = autonomy["unmapped_responsibilities"][0]
    if mutation == "absent": del autonomy["unmapped_responsibilities"]
    elif mutation == "null": autonomy["unmapped_responsibilities"] = None
    elif mutation == "wrong_container": autonomy["unmapped_responsibilities"] = {}
    elif mutation == "non_row": autonomy["unmapped_responsibilities"] = [None]
    elif mutation == "missing_ref": del row["responsibility_ref"]
    elif mutation == "null_ref": row["responsibility_ref"] = None
    elif mutation == "non_string_ref": row["responsibility_ref"] = ["WS:UNMAPPED-0"]
    elif mutation == "blank_ref": row["responsibility_ref"] = ""
    elif mutation == "missing_reason": del row["reason"]
    elif mutation == "unknown_reason": row["reason"] = "healthy"
    elif mutation == "extra_seat": row["accountable_seat"] = "ceo"
    elif mutation == "duplicate": autonomy["unmapped_responsibilities"].append(copy.deepcopy(row))
    elif mutation == "overlap": row["responsibility_ref"] = "WS:MAPPED-0"
    elif mutation == "orphan": row["responsibility_ref"] = "WS:NOT-IN-WORK"
    elif mutation == "uncovered_work": doc["work"].append({"work_ref": "WS:EXTRA"})
    elif mutation == "duplicate_work": doc["work"].append(copy.deepcopy(doc["work"][0]))
    elif mutation == "duplicate_mapped": autonomy["responsibilities"] *= 2
    elif mutation == "orphan_mapped": autonomy["responsibilities"][0]["responsibility_ref"] = "WS:ORPHAN"
    elif mutation == "bad_mapped_freshness": autonomy["responsibilities"][0]["freshness"] = "healthy"
    result = publish(tmp_path, doc)
    assert result["availability"] == "UNAVAILABLE"
    assert result["control_room"] is None


def snapshot(tmp_path, doc):
    owners, clock, cache = cache_fixture(tmp_path)
    owner = owners[0]
    owner.state_cache["doc"] = doc
    owner.state_cache.pop("source_validity_bounds", None)
    with owner.state_lock:
        publisher._publish_source_validity(owner, doc, tuple(clock), tuple(clock))
    return cache.snapshot()


class Samples:
    def __init__(self, *samples):
        self.samples = iter(samples)

    def snapshot(self):
        return next(self.samples)


def programs(*samples):
    return run(service(Samples(*samples), acquire=lambda *a, **k: pytest.fail("Unexpected Runtime read")),
               frame("programs"))["result"]


@pytest.mark.parametrize("mutation", [
    "missing", "duplicate", "orphan", "unmapped", "non_row", "bad_ref", "bad_root", "proof",
    "expired", "foreign_publication", "stale_cache", "stale_promoted",
])
def test_mapped_receipts_remain_exactly_paired(tmp_path, mutation):
    doc = canonical(stale=mutation == "stale_promoted")
    sample = snapshot(tmp_path, doc)
    validity = copy.deepcopy(sample.validity)
    card = validity["cards"][0]
    if mutation == "missing": validity["cards"] = []
    elif mutation == "duplicate": validity["cards"].append(copy.deepcopy(card))
    elif mutation == "orphan": validity["cards"].append(dict(card, responsibility_ref="WS:ORPHAN"))
    elif mutation == "unmapped": validity["cards"].append(dict(card, responsibility_ref="WS:UNMAPPED-0"))
    elif mutation == "non_row": validity["cards"].append(None)
    elif mutation == "bad_ref": validity["cards"].append(dict(card, responsibility_ref=[]))
    elif mutation == "bad_root": validity["cards"].append(dict(card, root_job_id=[]))
    elif mutation == "proof": card["components"]["card"]["proof_ref"] = "f" * 64
    elif mutation == "expired": card["components"]["card"].update(remaining_ms=0, state="expired")
    elif mutation == "foreign_publication": validity["publication_seq"] += 1
    elif mutation == "stale_cache": sample = replace(sample, currentness={"state": "stale", "publication_seq": 1})
    elif mutation == "stale_promoted": card["components"]["card"].update(state="current", remaining_ms=1)
    sample = replace(sample, validity=validity)
    assert programs(sample, sample)["availability"] == "UNAVAILABLE"


def test_all_unmapped_does_not_allow_unpaired_validity(tmp_path):
    sample = snapshot(tmp_path, canonical(mapped=0))
    validity = copy.deepcopy(sample.validity)
    validity["cards"] = [{"responsibility_ref": "WS:UNMAPPED-0", "root_job_id": None}]
    sample = replace(sample, validity=validity)
    assert programs(sample, sample)["availability"] == "UNAVAILABLE"


def test_unmapped_drift_between_samples_refuses(tmp_path):
    before = snapshot(tmp_path, canonical())
    document = copy.deepcopy(before.document)
    document["autonomy"]["unmapped_responsibilities"][0]["reason"] = "row_unreadable"
    after = replace(before, document=document)
    assert programs(before, after)["availability"] == "UNAVAILABLE"


def test_unmapped_cannot_supply_selected_mission_root(tmp_path):
    sample = snapshot(tmp_path, canonical())
    request = frame()
    request["selection"] = {"work_ref": "WS:UNMAPPED-0", "root_job_id": "JOB-001"}
    result = run(service(Samples(sample), acquire=lambda *a, **k: pytest.fail("Unexpected Runtime read")), request)
    assert result["ok"] is False
    assert result["error"]["code"] == "selection_not_found"


def test_empty_work_cannot_hide_unmapped_rows(tmp_path):
    doc = composer.compose_control_room(**empty_inputs())
    doc["autonomy"]["unmapped_responsibilities"] = [
        {"responsibility_ref": "WS:HIDDEN", "reason": "owner_not_a_recognized_seat"}]
    assert publish(tmp_path, doc)["availability"] == "UNAVAILABLE"


@pytest.mark.parametrize("mutation", ["missing", "empty", "count", "bool_count"])
def test_unmapped_publication_cannot_claim_empty_or_wrong_count(tmp_path, mutation):
    doc = canonical(mapped=0)
    if mutation == "missing": del doc["autonomy"]["counts"]
    elif mutation == "empty": doc["autonomy"]["counts"]["empty"] = True
    elif mutation == "count": doc["autonomy"]["counts"]["total"] = 1
    elif mutation == "bool_count": doc["autonomy"]["counts"]["total"] = False
    assert publish(tmp_path, doc)["availability"] == "UNAVAILABLE"


def test_mapped_selection_still_joins_with_unmapped_neighbors(tmp_path):
    owners, clock, cache = cache_fixture(tmp_path)
    doc = owners[0].state_cache["doc"]
    doc["work"].append({"work_ref": "WS:UNMAPPED"})
    doc["autonomy"]["unmapped_responsibilities"] = [
        {"responsibility_ref": "WS:UNMAPPED", "reason": "owner_not_a_recognized_seat"}]
    result = run(service(cache))
    assert result["ok"] is True
    assert result["result"]["fixture_inputs"]["root_job_id"] == "JOB-001"

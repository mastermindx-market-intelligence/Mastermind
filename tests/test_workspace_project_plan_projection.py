"""Focused tests for the pure workspace project-plan read contract + projector.

Coverage commissioned for P16.T1.S1 (all fixtures synthetic; no I/O, no
network, no auth, no producer source acquired at test time):

  * strict WS: selector validation with no path/Job companion selector
  * exact source identity (repository/commit/path/content_sha256)
  * closed unavailable bodies over the closed reason enum
  * authentic synthetic canonical workstream record -> closed available body
  * authored wave order, forward dependencies, authored status vocabularies
    (a ``done`` status is record state, never runtime acceptance)
  * absent optional fields -> closed defaults
  * explicit-field projection: unknown metadata (incl. a secret sentinel and
    wave ``wait`` structures) never leaks
  * adoption/version_history stay UNAVAILABLE even with ``status: active`` and
    misleading raw metadata claiming adoption or version 18
  * mismatched key/path/commit, duplicate/unknown/cyclic wave dependencies,
    >64 waves, Unicode response budget -> typed unavailability, never a
    truncated plan
  * detached returned structure (caller mutation cannot change a response)

Run:
    python -m pytest tests/test_workspace_project_plan_projection.py -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Repo-root import bootstrap (repo idiom): also lets this module run from a
# bare extracted tree rather than a full source checkout.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import workspace_project_plan_contract as contract
from common.workspace_project_plan_contract import (
    BODY_KEYS,
    BODY_SCHEMA,
    CANONICAL_REPOSITORY,
    FRAME_SCHEMA,
    MAX_RESPONSE_BYTES,
    OPERATION,
    REASON_CODES,
    canonical_record_path,
    unavailable,
    validate_selection,
    validate_source,
)
from control_plane.workspace_project_plan import (
    MAX_WAVES,
    project_workstream_plan,
)

SECRET_SENTINEL = "SECRET-SENTINEL-7f3d-do-not-project"

WORK_REF = "WS:P16T1"
SOURCE = {
    "repository": CANONICAL_REPOSITORY,
    "commit": "0123456789abcdef0123456789abcdef01234567",
    "path": canonical_record_path("P16T1"),
    "content_sha256": "a" * 64,
}

# Authored producer status vocabularies as inspected at scripts/agentos.py
# (blob 5aae3c5e): the projector passes them through verbatim and owns no
# private enum of its own.
WORKSTREAM_STATUSES = (
    "proposed",
    "active",
    "blocked",
    "awaiting_ci",
    "awaiting_review",
    "done",
    "parked",
    "killed",
)
WAVE_STATUSES = ("todo", "in_progress", "awaiting_ci", "done", "dropped")


def wave(wid, title=None, status="todo", depends_on=None, next_action=None, pr=None, **extra):
    """One authored wave, optionally carrying non-canonical ``extra`` fields."""
    record = {"id": wid, "status": status}
    if title is not None:
        record["title"] = title
    if depends_on is not None:
        record["depends_on"] = depends_on
    if next_action is not None:
        record["next_action"] = next_action
    if pr is not None:
        record["pr"] = pr
    record.update(extra)
    return record


def canonical_record(**overrides):
    """Authentic-shaped synthetic canonical workstream record."""
    record = {
        "key": "P16T1",
        "title": "Project the canonical workspace plan",
        "objective": "Expose the authored workstream plan through one closed read.",
        "status": "active",
        "program": "workspace-reads",
        "repos": ["mastermindx-market-intelligence/macro"],
        "owner": "platform-workspaces",
        "class": "build",
        "blast_radius": "reversible",
        "ambiguity": "specified",
        "waves": [
            wave("W1", "Bind the read contract", "done", next_action="n/a"),
            wave("W2", "Pure projector", "in_progress", depends_on=["W1"], pr=1800),
            wave("W3", "Parent integration", "todo", depends_on=["W1", "W2"]),
        ],
        "next_action": "Land the focused test module.",
    }
    record.update(overrides)
    return record


def serialize(body) -> str:
    return json.dumps(body, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


# ---------------------------------------------------------------------------
# Contract constants
# ---------------------------------------------------------------------------


def test_contract_constants_exact():
    assert BODY_SCHEMA == "mastermind.workspace_project_plan.v1"
    assert FRAME_SCHEMA == "mastermind.workspace_project_plan_read.v1"
    assert OPERATION == "project_plan"
    assert MAX_RESPONSE_BYTES == 131072
    assert CANONICAL_REPOSITORY == "mastermindx-market-intelligence/macro"
    assert BODY_KEYS == (
        "schema",
        "selection",
        "availability",
        "source",
        "plan",
        "reason_codes",
    )
    assert set(REASON_CODES) == {
        "SOURCE_UNAVAILABLE",
        "SOURCE_CHANGED",
        "RECORD_NOT_FOUND",
        "RECORD_INVALID",
        "CONTENT_OVER_BUDGET",
    }


def test_canonical_record_path_layout_matches_producer_store():
    assert canonical_record_path("P16T1") == "agentos/workstreams/WS-P16T1.md"
    assert SOURCE["path"] == canonical_record_path("P16T1")


# ---------------------------------------------------------------------------
# Selection validation: strict WS: selector, no Job/path companion
# ---------------------------------------------------------------------------


def test_validate_selection_accepts_strict_selector():
    assert validate_selection({"work_ref": WORK_REF}) == {"work_ref": WORK_REF}
    assert validate_selection({"work_ref": "WS:AB"}) == {"work_ref": "WS:AB"}
    long_key = "A" * 64
    assert validate_selection({"work_ref": f"WS:{long_key}"}) == {"work_ref": f"WS:{long_key}"}
    assert validate_selection({"work_ref": "WS:A1-B2-C3"}) == {"work_ref": "WS:A1-B2-C3"}


def test_validate_selection_rejects_non_work_ref_keys():
    with pytest.raises(ValueError) as exc:
        validate_selection({"work_ref": WORK_REF, "job": "J1"})
    assert str(exc.value) == contract.INVALID_WORK_REF_MESSAGE
    with pytest.raises(ValueError) as exc:
        validate_selection({"work_ref": WORK_REF, "path": canonical_record_path("P16T1")})
    assert str(exc.value) == contract.INVALID_WORK_REF_MESSAGE
    with pytest.raises(ValueError) as exc:
        validate_selection({"work_ref": WORK_REF, "commit": SOURCE["commit"]})
    assert str(exc.value) == contract.INVALID_WORK_REF_MESSAGE
    with pytest.raises(ValueError) as exc:
        validate_selection({})
    assert str(exc.value) == contract.INVALID_WORK_REF_MESSAGE


@pytest.mark.parametrize(
    "value",
    [
        None,
        "WS:P16T1",
        7,
        {"work_ref": None},
        {"work_ref": 7},
        {"work_ref": "P16T1"},  # missing WS: prefix
        {"work_ref": "ws:P16T1"},  # lowercase prefix
        {"work_ref": "WS:p16t1"},  # lowercase key
        {"work_ref": "WS:A"},  # key below the 2-char floor
        {"work_ref": "WS:" + "A" * 65},  # key above the 64-char ceiling
        {"work_ref": "WS:-AB"},  # leading dash
        {"work_ref": "WS:AB-"},  # trailing dash
        {"work_ref": "WS:A--B"},  # double dash
        {"work_ref": "WS:A_B"},  # non A-Z0-9 group
        {"work_ref": "WS:agentos/workstreams/WS-AB.md"},  # path-shaped selector
        {"work_ref": "WS:P16T1 ",},  # trailing whitespace
    ],
)
def test_validate_selection_rejects_malformed_selectors(value):
    with pytest.raises(ValueError) as exc:
        validate_selection(value)
    assert str(exc.value) == contract.INVALID_WORK_REF_MESSAGE


def test_validate_selection_result_is_detached():
    original = {"work_ref": WORK_REF}
    result = validate_selection(original)
    assert result == original
    assert result is not original
    result["work_ref"] = "WS:OTHER"
    assert original["work_ref"] == WORK_REF


def test_work_ref_key_splits_selector():
    assert contract.work_ref_key("WS:P16T1") == "P16T1"
    with pytest.raises(ValueError) as exc:
        contract.work_ref_key("WS:X")
    assert str(exc.value) == contract.INVALID_WORK_REF_MESSAGE


# ---------------------------------------------------------------------------
# Source identity validation: exact repository/commit/path/content_sha256
# ---------------------------------------------------------------------------


def test_validate_source_accepts_exact_identity():
    result = validate_source(SOURCE, WORK_REF)
    assert result == SOURCE
    assert result is not SOURCE


@pytest.mark.parametrize(
    "mutate",
    [
        lambda s: s.update({"repository": "other-org/macro"}),
        lambda s: s.update({"repository": "mastermindx-market-intelligence/other"}),
        lambda s: s.update({"commit": "0123456789ABCDEF0123456789ABCDEF01234567"}),  # upper
        lambda s: s.update({"commit": "0" * 39}),
        lambda s: s.update({"commit": "0" * 41}),
        lambda s: s.update({"commit": "g" * 40}),
        lambda s: s.update({"path": "agentos/workstreams/WS-OTHER.md"}),
        lambda s: s.update({"path": "agentos/workstreams/WS-p16t1.md"}),
        lambda s: s.update({"path": "workstreams/WS-P16T1.md"}),
        lambda s: s.update({"path": None}),
        lambda s: s.update({"content_sha256": "A" * 64}),
        lambda s: s.update({"content_sha256": "a" * 63}),
        lambda s: s.update({"content_sha256": 5}),
    ],
)
def test_validate_source_rejects_mismatched_identity(mutate):
    source = dict(SOURCE)
    mutate(source)
    with pytest.raises(ValueError) as exc:
        validate_source(source, WORK_REF)
    assert str(exc.value) == contract.INVALID_SOURCE_MESSAGE


@pytest.mark.parametrize(
    "mutate",
    [
        lambda s: s.pop("content_sha256"),
        lambda s: s.update({"extra": 1}),
    ],
)
def test_validate_source_requires_exact_key_set(mutate):
    source = dict(SOURCE)
    mutate(source)
    with pytest.raises(ValueError) as exc:
        validate_source(source, WORK_REF)
    assert str(exc.value) == contract.INVALID_SOURCE_MESSAGE


def test_validate_source_rejects_non_mapping_and_bad_selector():
    with pytest.raises(ValueError) as exc:
        validate_source("agentos/workstreams/WS-P16T1.md", WORK_REF)
    assert str(exc.value) == contract.INVALID_SOURCE_MESSAGE
    with pytest.raises(ValueError) as exc:
        validate_source(dict(SOURCE), "WS:BAD~")
    assert str(exc.value) == contract.INVALID_WORK_REF_MESSAGE


# ---------------------------------------------------------------------------
# Closed unavailable bodies
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("reason", sorted(REASON_CODES))
def test_unavailable_body_is_closed_per_reason(reason):
    body = unavailable(WORK_REF, reason)
    assert body == {
        "schema": BODY_SCHEMA,
        "selection": {"work_ref": WORK_REF},
        "availability": "UNAVAILABLE",
        "source": None,
        "plan": None,
        "reason_codes": [reason],
    }
    assert tuple(body.keys()) == BODY_KEYS


def test_unavailable_rejects_unknown_reason_and_bad_selector():
    with pytest.raises(ValueError) as exc:
        unavailable(WORK_REF, "SOURCE_EXPLODED")
    assert str(exc.value) == contract.INVALID_REASON_MESSAGE
    with pytest.raises(ValueError) as exc:
        unavailable("WS:~", contract.REASON_RECORD_NOT_FOUND)
    assert str(exc.value) == contract.INVALID_WORK_REF_MESSAGE


# ---------------------------------------------------------------------------
# Available projection of an authentic synthetic canonical record
# ---------------------------------------------------------------------------


def test_available_body_shape_is_closed():
    body = project_workstream_plan(canonical_record(), work_ref=WORK_REF, source=SOURCE)
    assert tuple(body.keys()) == BODY_KEYS
    assert body["schema"] == BODY_SCHEMA
    assert body["selection"] == {"work_ref": WORK_REF}
    assert body["availability"] == "AVAILABLE"
    assert body["source"] == SOURCE
    assert body["reason_codes"] == []
    plan = body["plan"]
    assert tuple(plan.keys()) == (
        "title",
        "objective",
        "status",
        "owner",
        "next_action",
        "waves",
        "adoption",
        "version_history",
    )
    for projected in plan["waves"]:
        assert tuple(projected.keys()) == (
            "id",
            "title",
            "status",
            "depends_on",
            "next_action",
            "prs",
        )


def test_plan_reproduces_authored_content_order_and_dependencies():
    record = canonical_record()
    body = project_workstream_plan(record, work_ref=WORK_REF, source=SOURCE)
    plan = body["plan"]
    assert plan["title"] == record["title"]
    assert plan["objective"] == record["objective"]
    assert plan["status"] == record["status"]
    assert plan["owner"] == record["owner"]
    assert plan["next_action"] == record["next_action"]
    assert [w["id"] for w in plan["waves"]] == ["W1", "W2", "W3"]
    assert plan["waves"][0]["depends_on"] == []
    assert plan["waves"][1]["depends_on"] == ["W1"]
    assert plan["waves"][2]["depends_on"] == ["W1", "W2"]
    assert plan["waves"][1]["prs"] == [1800]


def test_forward_dependencies_are_supported():
    record = canonical_record(
        waves=[
            wave("W1", "first", "todo", depends_on=["W3"]),
            wave("W2", "middle", "todo", depends_on=["W1"]),
            wave("W3", "last authored first-dep target", "todo"),
        ]
    )
    body = project_workstream_plan(record, work_ref=WORK_REF, source=SOURCE)
    assert body["availability"] == "AVAILABLE"
    assert body["plan"]["waves"][0]["depends_on"] == ["W3"]


@pytest.mark.parametrize("status", WORKSTREAM_STATUSES)
def test_authored_workstream_statuses_pass_through_verbatim(status):
    body = project_workstream_plan(
        canonical_record(status=status), work_ref=WORK_REF, source=SOURCE
    )
    assert body["availability"] == "AVAILABLE"
    assert body["plan"]["status"] == status


@pytest.mark.parametrize("status", WAVE_STATUSES)
def test_authored_wave_statuses_pass_through_verbatim(status):
    record = canonical_record(waves=[wave("W1", "one wave", status)])
    body = project_workstream_plan(record, work_ref=WORK_REF, source=SOURCE)
    assert body["availability"] == "AVAILABLE"
    assert body["plan"]["waves"][0]["status"] == status


def test_done_status_is_never_runtime_acceptance_or_adoption():
    record = canonical_record(
        status="done",
        waves=[wave("W1", "shipped", "done", pr=[1800, 1801])],
        adoption={"state": "ADOPTED", "approved_by": "chairman"},
        accepted_by_governance=True,
    )
    body = project_workstream_plan(record, work_ref=WORK_REF, source=SOURCE)
    text = serialize(body)
    assert body["availability"] == "AVAILABLE"
    assert body["plan"]["status"] == "done"
    assert body["plan"]["waves"][0]["status"] == "done"
    assert body["plan"]["adoption"] == {"state": "UNAVAILABLE", "reason": "NOT_DECLARED"}
    assert body["plan"]["version_history"] == {
        "state": "UNAVAILABLE",
        "reason": "NOT_SUPPLIED_BY_OWNER",
    }
    for banned in ("ADOPTED", "approved_by", "accepted", "merged", "APPROVED"):
        assert banned not in text


def test_adoption_and_version_history_stay_unavailable_despite_active_and_misleading_metadata():
    record = canonical_record(
        status="active",
        adoption={"state": "ADOPTED", "reference": "execution-run-99"},
        plan_version=18,
        version="v18",
        versions=[{"number": 17}, {"number": 18, "accepted": True}],
        accepted=True,
        execution_plan=["step-1", "step-2"],
        git_published_at="2026-11-03T00:00:00Z",
    )
    body = project_workstream_plan(record, work_ref=WORK_REF, source=SOURCE)
    assert body["availability"] == "AVAILABLE"
    assert body["plan"]["adoption"] == {"state": "UNAVAILABLE", "reason": "NOT_DECLARED"}
    assert body["plan"]["version_history"] == {
        "state": "UNAVAILABLE",
        "reason": "NOT_SUPPLIED_BY_OWNER",
    }
    text = serialize(body)
    assert "ADOPTED" not in text
    assert "execution-run-99" not in text
    for banned in ("plan_version", "execution_plan", "git_published_at", '"accepted"', "v18"):
        assert banned not in text


def test_absent_optional_fields_project_closed_defaults():
    record = canonical_record(
        waves=[wave("W1", "bare wave", "todo")],
        program=None,
        repos=None,
        depends_on=None,
    )
    del record["next_action"]
    body = project_workstream_plan(record, work_ref=WORK_REF, source=SOURCE)
    assert body["availability"] == "AVAILABLE"
    projected = body["plan"]["waves"][0]
    assert projected["depends_on"] == []
    assert projected["next_action"] is None
    assert projected["prs"] == []
    assert body["plan"]["next_action"] is None


def test_blank_optional_text_projects_to_null():
    record = canonical_record(next_action="   ", waves=[wave("W1", "w", "todo", next_action="")])
    body = project_workstream_plan(record, work_ref=WORK_REF, source=SOURCE)
    assert body["plan"]["next_action"] is None
    assert body["plan"]["waves"][0]["next_action"] is None


# ---------------------------------------------------------------------------
# pr reference normalization (no Git state inferred)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, []),
        (1800, [1800]),
        ("1801", [1801]),
        ([1800, "1801"], [1800, 1801]),
        ([], []),
        # malformed tokens are skipped exactly as the producer's own records
        # view skips them (authored '#5593' shapes on real records)
        ("#5593", []),
        (["#5593", 5700, "ok"], [5700]),
        (0, []),
        (-5, []),
        (1.5, []),
        (True, []),
        ("PR-1800", []),
        ("", []),
        ({"number": 1800}, []),
        ([1800, 0, None, False], [1800]),
    ],
)
def test_pr_normalization_to_prs_list(raw, expected):
    record = canonical_record(waves=[wave("W1", "w", "todo", pr=raw)])
    body = project_workstream_plan(record, work_ref=WORK_REF, source=SOURCE)
    assert body["plan"]["waves"][0]["prs"] == expected


def test_more_than_32_kept_references_is_record_invalid():
    body = project_workstream_plan(
        canonical_record(waves=[wave("W1", "w", "todo", pr=list(range(1, 34)))]),
        work_ref=WORK_REF,
        source=SOURCE,
    )
    assert body["availability"] == "UNAVAILABLE"
    assert body["reason_codes"] == ["RECORD_INVALID"]
    assert body["plan"] is None
    assert body["source"] is None


def test_32_kept_references_after_skipping_malformed_tokens_is_accepted():
    raw = ["#1", "#2"] + list(range(100, 132))
    record = canonical_record(waves=[wave("W1", "w", "todo", pr=raw)])
    body = project_workstream_plan(record, work_ref=WORK_REF, source=SOURCE)
    assert body["availability"] == "AVAILABLE"
    assert body["plan"]["waves"][0]["prs"] == list(range(100, 132))


# ---------------------------------------------------------------------------
# Explicit-field projection: no raw body / secret / wait leakage
# ---------------------------------------------------------------------------


def test_unknown_metadata_with_secret_sentinel_is_never_projected():
    record = canonical_record(
        internal_notes=f"rotate {SECRET_SENTINEL} now",
        credentials={"token": SECRET_SENTINEL},
        raw_history=f"---\nprevious body with {SECRET_SENTINEL}\n---",
        security={"classification": SECRET_SENTINEL},
        waves=[
            wave(
                "W1",
                "wave with private extras",
                "todo",
                wait={"owner": "ops", "note": SECRET_SENTINEL},
                secret=SECRET_SENTINEL,
                credential_ref=SECRET_SENTINEL,
                done_at="2026-11-02T00:00:00Z",
                deps_satisfied=True,
            )
        ],
    )
    body = project_workstream_plan(record, work_ref=WORK_REF, source=SOURCE)
    text = serialize(body)
    assert body["availability"] == "AVAILABLE"
    assert SECRET_SENTINEL not in text
    assert "wait" not in text
    assert "deps_satisfied" not in text
    assert "done_at" not in text
    assert "internal_notes" not in text
    assert "credentials" not in text


# ---------------------------------------------------------------------------
# Negative producer-record cases -> typed RECORD_INVALID
# ---------------------------------------------------------------------------


def test_mismatched_record_key_returns_record_invalid():
    body = project_workstream_plan(
        canonical_record(key="OTHER"), work_ref=WORK_REF, source=SOURCE
    )
    assert body == unavailable(WORK_REF, contract.REASON_RECORD_INVALID)
    assert body["selection"] == {"work_ref": WORK_REF}
    assert body["plan"] is None
    assert body["source"] is None


def test_mismatched_selector_record_pair_via_source_path_is_caller_error():
    # A well-formed but non-matching source identity is a caller bug and stays
    # a closed ValueError at the contract boundary; it is never folded into a
    # response body.
    with pytest.raises(ValueError) as exc:
        project_workstream_plan(
            canonical_record(), work_ref=WORK_REF, source=dict(SOURCE, path="agentos/workstreams/WS-X.md")
        )
    assert str(exc.value) == contract.INVALID_SOURCE_MESSAGE


INVALID_CASES = {
    "none_record": lambda r: None,
    "list_record": lambda r: ["not", "a", "mapping"],
    "missing_title": lambda r: r.pop("title"),
    "empty_title": lambda r: r.update({"title": "   "}),
    "title_513": lambda r: r.update({"title": "x" * 513}),
    "objective_16385": lambda r: r.update({"objective": "x" * 16385}),
    "owner_257": lambda r: r.update({"owner": "x" * 257}),
    "next_action_16385": lambda r: r.update({"next_action": "x" * 16385}),
    "status_65": lambda r: r.update({"status": "x" * 65}),
    "empty_status": lambda r: r.update({"status": ""}),
    "non_string_title": lambda r: r.update({"title": 7}),
    "non_string_owner": lambda r: r.update({"owner": None}),
    "waves_missing": lambda r: r.pop("waves"),
    "waves_not_list": lambda r: r.update({"waves": {"W1": {}}}),
    "wave_not_mapping": lambda r: r.update({"waves": ["W1"]}),
    "wave_missing_id": lambda r: r.update({"waves": [{"title": "t", "status": "todo"}]}),
    "wave_empty_id": lambda r: r.update({"waves": [wave("", "t")]}),
    "wave_padded_id": lambda r: r.update({"waves": [wave(" W1", "t")]}),
    "wave_id_129": lambda r: r.update({"waves": [wave("W" * 129, "t")]}),
    "wave_missing_title": lambda r: r.update({"waves": [{"id": "W1", "status": "todo"}]}),
    "wave_title_1025": lambda r: r.update({"waves": [wave("W1", "x" * 1025)]}),
    "wave_missing_status": lambda r: r.update({"waves": [{"id": "W1", "title": "t"}]}),
    "wave_status_33": lambda r: r.update({"waves": [wave("W1", "t", "x" * 33)]}),
    "wave_dep_not_list": lambda r: r.update({"waves": [wave("W1", "t", "todo", depends_on="W2")]}),
    "wave_dep_not_string": lambda r: r.update({"waves": [wave("W1", "t", "todo", depends_on=[2])]}),
    "65_waves": lambda r: r.update(
        {"waves": [wave(f"W{n:02d}", f"wave {n}") for n in range(1, 66)]}
    ),
}


@pytest.mark.parametrize("name", sorted(INVALID_CASES))
def test_structurally_invalid_records_return_record_invalid(name):
    mutate = INVALID_CASES[name]
    record = mutate(canonical_record())
    body = project_workstream_plan(record, work_ref=WORK_REF, source=SOURCE)
    assert body == unavailable(WORK_REF, contract.REASON_RECORD_INVALID)


def test_boundary_string_lengths_are_accepted():
    record = canonical_record(
        title="x" * 512,
        objective="x" * 16384,
        owner="x" * 256,
        next_action="x" * 16384,
        status="x" * 64,
        waves=[
            wave(
                "W" * 128,
                "x" * 1024,
                "x" * 32,
                depends_on=[],
                next_action="x" * 16384,
                pr=[1],
            )
        ],
    )
    body = project_workstream_plan(record, work_ref=WORK_REF, source=SOURCE)
    assert body["availability"] == "AVAILABLE"


def test_wave_count_boundary_64_is_accepted():
    record = canonical_record(
        waves=[wave(f"W{n:02d}", f"wave {n}") for n in range(1, 65)]
    )
    body = project_workstream_plan(record, work_ref=WORK_REF, source=SOURCE)
    assert body["availability"] == "AVAILABLE"
    assert len(body["plan"]["waves"]) == MAX_WAVES == 64


def test_duplicate_wave_ids_are_rejected():
    record = canonical_record(waves=[wave("W1", "a"), wave("W1", "b")])
    body = project_workstream_plan(record, work_ref=WORK_REF, source=SOURCE)
    assert body["reason_codes"] == ["RECORD_INVALID"]


def test_unknown_dependency_is_rejected():
    record = canonical_record(waves=[wave("W1", "a", depends_on=["W9"])])
    body = project_workstream_plan(record, work_ref=WORK_REF, source=SOURCE)
    assert body["reason_codes"] == ["RECORD_INVALID"]


def test_duplicate_dependency_within_wave_is_rejected():
    record = canonical_record(
        waves=[wave("W1", "a"), wave("W2", "b", depends_on=["W1", "W1"])]
    )
    body = project_workstream_plan(record, work_ref=WORK_REF, source=SOURCE)
    assert body["reason_codes"] == ["RECORD_INVALID"]


@pytest.mark.parametrize(
    "waves",
    [
        [wave("W1", "self", depends_on=["W1"])],
        [
            wave("W1", "a", depends_on=["W2"]),
            wave("W2", "b", depends_on=["W1"]),
        ],
        [
            wave("W1", "a", depends_on=["W3"]),
            wave("W2", "b", depends_on=["W1"]),
            wave("W3", "c", depends_on=["W2"]),
        ],
    ],
)
def test_dependency_cycles_are_rejected(waves):
    record = canonical_record(waves=waves)
    body = project_workstream_plan(record, work_ref=WORK_REF, source=SOURCE)
    assert body["reason_codes"] == ["RECORD_INVALID"]
    assert body["plan"] is None


# ---------------------------------------------------------------------------
# Response budget (UTF-8 bytes, Unicode heavy) -> typed CONTENT_OVER_BUDGET
# ---------------------------------------------------------------------------


def test_oversized_unicode_record_returns_content_over_budget_not_truncation():
    # Multi-byte characters: each wave's projected text alone is ~3x its
    # character count in UTF-8 bytes, so this exceeds the 131072-byte budget
    # by a wide margin while every single field respects its own bound.
    record = canonical_record(
        title="é" * 512,
        objective="海" * 16384,
        owner="ö" * 256,
        next_action="β" * 16384,
        waves=[wave(f"W{n:02d}", "à" * 1024, next_action="🌊" * 100) for n in range(1, 65)],
    )
    body = project_workstream_plan(record, work_ref=WORK_REF, source=SOURCE)
    assert body == unavailable(WORK_REF, contract.REASON_CONTENT_OVER_BUDGET)
    assert body["plan"] is None
    assert len(serialize(body).encode("utf-8")) < MAX_RESPONSE_BYTES


def test_just_under_budget_record_stays_available():
    # Deliberately tight: ~128 KB of projected JSON, close enough to the
    # 131072-byte ceiling that a per-character (not per-UTF-8-byte) budget or
    # a small arithmetic slip would trip it.
    record = canonical_record(
        waves=[wave(f"W{n:02d}", "x" * 1024, next_action="x" * 900) for n in range(1, 65)],
    )
    body = project_workstream_plan(record, work_ref=WORK_REF, source=SOURCE)
    assert body["availability"] == "AVAILABLE"
    assert 120000 < len(serialize(body).encode("utf-8")) <= MAX_RESPONSE_BYTES


def test_budget_is_measured_in_utf8_bytes_not_characters():
    # 65536 'ε' characters fit no character-count heuristic but serialize to
    # 196608 UTF-8 bytes; bounded fields keep it a legitimate record, so the
    # byte budget is what must trip.
    record = canonical_record(
        objective="ε" * 16384,
        next_action="ε" * 16384,
        waves=[wave(f"W{n:02d}", "ε" * 1024, next_action="ε" * 1024) for n in range(1, 65)],
    )
    body = project_workstream_plan(record, work_ref=WORK_REF, source=SOURCE)
    assert body["reason_codes"] == ["CONTENT_OVER_BUDGET"]


# ---------------------------------------------------------------------------
# Detached structures, determinism, closed serialization
# ---------------------------------------------------------------------------


def test_returned_structure_is_detached_from_caller_record_and_source():
    record = canonical_record()
    source = dict(SOURCE)
    body = project_workstream_plan(record, work_ref=WORK_REF, source=source)
    assert body["availability"] == "AVAILABLE"

    body["plan"]["title"] = "mutated"
    body["plan"]["waves"].append({"id": "W9"})
    body["plan"]["waves"][0]["depends_on"].append("W8")
    body["source"]["commit"] = "f" * 40
    body["selection"]["work_ref"] = "WS:OTHER"
    assert record["title"] == "Project the canonical workspace plan"
    assert len(record["waves"]) == 3
    assert record["waves"][0].get("depends_on") is None
    assert source["commit"] == SOURCE["commit"]

    fresh = project_workstream_plan(record, work_ref=WORK_REF, source=SOURCE)
    assert fresh["plan"]["title"] == "Project the canonical workspace plan"
    assert len(fresh["plan"]["waves"]) == 3
    assert fresh["source"]["commit"] == SOURCE["commit"]
    assert fresh["selection"] == {"work_ref": WORK_REF}


def test_mutating_record_after_projection_does_not_change_response():
    record = canonical_record()
    body = project_workstream_plan(record, work_ref=WORK_REF, source=SOURCE)
    before = serialize(body)
    record["title"] = "rewritten by caller"
    record["waves"].append(wave("W4", "late wave"))
    record["waves"][1]["pr"] = 999
    assert serialize(body) == before


def test_repeated_projection_is_byte_deterministic():
    record = canonical_record()
    first = project_workstream_plan(record, work_ref=WORK_REF, source=SOURCE)
    second = project_workstream_plan(canonical_record(), work_ref=WORK_REF, source=SOURCE)
    assert first is not second
    assert serialize(first) == serialize(second)
    assert json.loads(serialize(first))["plan"]["waves"][1]["prs"] == [1800]


def test_projector_exports_no_private_state_through_the_body():
    body = project_workstream_plan(canonical_record(), work_ref=WORK_REF, source=SOURCE)
    assert set(body) == set(BODY_KEYS)
    assert all(isinstance(value, (str, dict, list, type(None))) for value in body.values())

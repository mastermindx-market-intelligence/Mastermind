from __future__ import annotations

import copy
import json

import pytest

from control_plane.context_materiality import (
    ContextMaterialityError,
    build_materiality_snapshot,
    diff_materiality,
)


def _snapshot(**overrides):
    values = dict(
        task_digest="a" * 64,
        procedure_sha="b" * 40,
        owner_digests={"agentos": "c" * 64, "github": "d" * 64},
        source_refs=[
            {"identity": "file:alpha.py", "kind": "source", "digest": "e" * 40},
            {"identity": "doc:plan.md", "kind": "research", "digest": "f" * 40},
        ],
        workspace_overlays=[{"operation_id": "context-op", "generation": "1" * 64}],
        collision_refs=[{"identity": "pr:1205", "revision": "2" * 40}],
        return_refs=[{"identity": "worker:return:1", "digest": "3" * 64}],
    )
    values.update(overrides)
    return build_materiality_snapshot(**values)


def _codes(diff):
    return [(x["code"], x["identity"]) for x in diff["invalidators"]]


def test_identical_selected_dependencies_have_no_material_change():
    before = _snapshot()
    after = _snapshot()
    diff = diff_materiality(before, after)
    assert diff["material_change"] is False
    assert diff["recovery_mode"] == "DELTA_RECOVERY"
    assert diff["invalidators"] == []


def test_unrelated_estate_movement_is_invisible_by_contract():
    before = _snapshot()
    after = _snapshot()
    assert before == after
    assert diff_materiality(before, after)["invalidators"] == []


@pytest.mark.parametrize(
    ("field", "replacement", "code"),
    [
        ("task_digest", "9" * 64, "TASK_CHANGED"),
        ("procedure_sha", "8" * 40, "PROCEDURE_CHANGED"),
    ],
)
def test_task_or_procedure_change_forces_full_recovery(field, replacement, code):
    before = _snapshot()
    kwargs = {field: replacement}
    after = _snapshot(**kwargs)
    diff = diff_materiality(before, after)
    assert diff["recovery_mode"] == "FULL_RECOVERY"
    assert (
        code,
        "task" if code == "TASK_CHANGED" else "protected-skillpack",
    ) in _codes(diff)


def test_owner_context_change_is_typed():
    before = _snapshot()
    after = _snapshot(owner_digests={"agentos": "4" * 64, "github": "d" * 64})
    assert ("OWNER_CONTEXT_CHANGED", "owner:agentos") in _codes(
        diff_materiality(before, after)
    )


def test_relevant_source_change_is_typed():
    before = _snapshot()
    after = _snapshot(
        source_refs=[
            {"identity": "file:alpha.py", "kind": "source", "digest": "7" * 40},
            {"identity": "doc:plan.md", "kind": "research", "digest": "f" * 40},
        ]
    )
    assert ("RELEVANT_SOURCE_CHANGED", "file:alpha.py") in _codes(
        diff_materiality(before, after)
    )


def test_workspace_overlay_change_is_typed():
    before = _snapshot()
    after = _snapshot(
        workspace_overlays=[{"operation_id": "context-op", "generation": "5" * 64}]
    )
    assert ("WORKSPACE_OVERLAY_CHANGED", "context-op") in _codes(
        diff_materiality(before, after)
    )


def test_collision_addition_is_typed():
    before = _snapshot()
    after = _snapshot(
        collision_refs=[
            {"identity": "pr:1205", "revision": "2" * 40},
            {"identity": "pr:1210", "revision": "6" * 40},
        ]
    )
    assert ("COLLISION_ADDED", "pr:1210") in _codes(diff_materiality(before, after))


def test_material_return_received_is_typed():
    before = _snapshot(return_refs=[])
    after = _snapshot(return_refs=[{"identity": "worker:return:1", "digest": "3" * 64}])
    assert ("MATERIAL_RETURN_RECEIVED", "worker:return:1") in _codes(
        diff_materiality(before, after)
    )


def test_input_order_does_not_change_generation():
    left = _snapshot()
    right = build_materiality_snapshot(
        task_digest="a" * 64,
        procedure_sha="b" * 40,
        owner_digests={"github": "d" * 64, "agentos": "c" * 64},
        source_refs=list(reversed(left["source_refs"])),
        workspace_overlays=list(reversed(left["workspace_overlays"])),
        collision_refs=list(reversed(left["collision_refs"])),
        return_refs=list(reversed(left["return_refs"])),
    )
    assert left == right


def test_snapshot_is_byte_deterministic_and_does_not_mutate_inputs():
    owners = {"agentos": "c" * 64}
    sources = [{"identity": "x", "kind": "source", "digest": "e" * 40}]
    before_owners = copy.deepcopy(owners)
    before_sources = copy.deepcopy(sources)
    one = build_materiality_snapshot(
        task_digest="a" * 64,
        procedure_sha="b" * 40,
        owner_digests=owners,
        source_refs=sources,
    )
    two = build_materiality_snapshot(
        task_digest="a" * 64,
        procedure_sha="b" * 40,
        owner_digests=owners,
        source_refs=sources,
    )
    assert owners == before_owners
    assert sources == before_sources
    assert one == two
    assert json.dumps(one, sort_keys=True, separators=(",", ":")) == json.dumps(
        two, sort_keys=True, separators=(",", ":")
    )


def test_tampered_snapshot_generation_is_refused():
    before = _snapshot()
    tampered = copy.deepcopy(before)
    tampered["generation"] = "0" * 64
    with pytest.raises(ContextMaterialityError, match="generation"):
        diff_materiality(tampered, before)


def test_snapshot_cannot_claim_authority():
    before = _snapshot()
    tampered = copy.deepcopy(before)
    tampered["authoritative"] = True
    with pytest.raises(ContextMaterialityError, match="authority"):
        diff_materiality(tampered, before)


def test_duplicate_source_identity_is_refused():
    with pytest.raises(ContextMaterialityError, match="duplicate"):
        build_materiality_snapshot(
            task_digest="a" * 64,
            procedure_sha="b" * 40,
            owner_digests={},
            source_refs=[
                {"identity": "same", "kind": "source", "digest": "1" * 40},
                {"identity": "same", "kind": "source", "digest": "2" * 40},
            ],
        )

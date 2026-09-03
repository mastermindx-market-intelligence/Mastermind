from __future__ import annotations

from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "control_plane" / "source_continuity.py"

BASE_SHA = "1" * 40
HEAD_SHA = "2" * 40
TREE_SHA = "3" * 40
LOCAL_HEAD_SHA = "4" * 40
LOCAL_TREE_SHA = "5" * 40
CURRENT_BASE_SHA = "6" * 40
BLOB_A = "a" * 40
BLOB_B = "b" * 40
EFFECT_FINGERPRINT = "c" * 64
VERIFIED_AT = "2026-09-03T05:00:00Z"
OPERATION = "agent-dialogue-source-continuity-rchp0-rch1-20260903-sol-001"
REPOSITORY = "mastermindx-market-intelligence/Mastermind"
PR_NUMBER = 410
BRANCH = "sol/source-continuity-v1-20260903"
OWNED_PATHS = (
    "control_plane/source_continuity.py",
    "tests/test_source_continuity.py",
)


def _contract():
    assert CONTRACT_PATH.is_file(), "control_plane/source_continuity.py must exist"
    name = "source_continuity_contract_under_test"
    spec = importlib.util.spec_from_file_location(name, CONTRACT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _request(module, *, kind=None, owned_paths=OWNED_PATHS, **overrides):
    values = dict(
        receipt_kind=kind or module.ReceiptKind.CHECKPOINT_VERIFIED,
        operation_key=OPERATION,
        repository=REPOSITORY,
        pr_number=PR_NUMBER,
        branch=BRANCH,
        base_ref="master",
        pinned_base_sha=BASE_SHA,
        owned_paths=owned_paths,
        verified_at=VERIFIED_AT,
    )
    values.update(overrides)
    return module.SourceContinuityRequest(**values)


def _entries(module, *, first_mode="100644", first_size=123, first_type="blob"):
    return (
        module.RemotePathEntry(
            path=OWNED_PATHS[1],
            mode="100644",
            object_type="blob",
            object_sha=BLOB_B,
            size=456,
        ),
        module.RemotePathEntry(
            path=OWNED_PATHS[0],
            mode=first_mode,
            object_type=first_type,
            object_sha=BLOB_A,
            size=first_size,
        ),
    )


def _remote(module, **overrides):
    values = dict(
        repository=REPOSITORY,
        pr_number=PR_NUMBER,
        branch=BRANCH,
        base_ref="master",
        pr_open=True,
        pr_draft_or_hold=True,
        head_sha=HEAD_SHA,
        tree_sha=TREE_SHA,
        merge_base_sha=BASE_SHA,
        current_base_head_sha=CURRENT_BASE_SHA,
        changed_paths=(OWNED_PATHS[1], OWNED_PATHS[0]),
        path_entries=_entries(module),
        collision_state=module.CollisionState.NONE,
        colliding_pr_numbers=(),
        pagination_complete=True,
    )
    values.update(overrides)
    return module.RemoteGitFacts(**values)


def _checkpoint_local(module, **overrides):
    values = dict(
        branch=BRANCH,
        head_sha=LOCAL_HEAD_SHA,
        tree_sha=LOCAL_TREE_SHA,
        remote_head_object_exists=True,
        remote_head_is_ancestor_of_local=True,
        unpushed_commit_count=1,
        uncommitted_in_scope_count=1,
        untracked_in_scope_count=1,
        uncommitted_out_of_scope_count=0,
        untracked_out_of_scope_count=0,
    )
    values.update(overrides)
    return module.LocalGitFacts(**values)


def _complete_local(module, **overrides):
    values = dict(
        branch=BRANCH,
        head_sha=HEAD_SHA,
        tree_sha=TREE_SHA,
        remote_head_object_exists=True,
        remote_head_is_ancestor_of_local=True,
        unpushed_commit_count=0,
        uncommitted_in_scope_count=0,
        untracked_in_scope_count=0,
        uncommitted_out_of_scope_count=0,
        untracked_out_of_scope_count=0,
    )
    values.update(overrides)
    return module.LocalGitFacts(**values)


def _external(module, **overrides):
    values = dict(
        state=module.ExternalEffectState.NONE,
        branch_dependency=module.BranchEffectDependency.NONE,
        evidence_fingerprint=EFFECT_FINGERPRINT,
    )
    values.update(overrides)
    return module.ExternalEffectEvidence(**values)


def _verify(module, *, request=None, local=None, remote=None, external=None):
    return module.verify_source_continuity(
        request or _request(module),
        local or _checkpoint_local(module),
        remote or _remote(module),
        external or _external(module),
    )


def _assert_refusal(module, result, code: str, *, exit_code: int):
    assert isinstance(result, module.SourceContinuityRefusal)
    payload = result.to_dict()
    assert payload == {
        "schema": "mastermind.source_continuity_refusal/v1",
        "ok": False,
        "code": code,
        "message": module.REFUSAL_MESSAGES[result.code],
    }
    assert result.exit_code == exit_code
    encoded = json.dumps(payload, sort_keys=True)
    assert OPERATION not in encoded
    assert REPOSITORY not in encoded
    assert BRANCH not in encoded


def test_checkpoint_receipt_binds_complete_identity_without_authority() -> None:
    module = _contract()
    result = _verify(module)

    assert isinstance(result, module.SourceContinuityReceipt)
    payload = result.to_dict()
    assert payload == {
        "schema": "mastermind.source_continuity_receipt/v1",
        "operation_key": OPERATION,
        "repository": REPOSITORY,
        "pr_number": PR_NUMBER,
        "branch": BRANCH,
        "base_ref": "master",
        "pinned_base_sha": BASE_SHA,
        "remote_head_sha": HEAD_SHA,
        "remote_tree_sha": TREE_SHA,
        "remote_merge_base_sha": BASE_SHA,
        "current_base_head_sha": CURRENT_BASE_SHA,
        "changed_paths": sorted(OWNED_PATHS),
        "owned_path_digest": result.owned_path_digest,
        "local_branch": BRANCH,
        "local_head_sha": LOCAL_HEAD_SHA,
        "local_tree_sha": LOCAL_TREE_SHA,
        "remote_head_is_ancestor_of_local": True,
        "local_equals_remote": False,
        "unpushed_commit_count": 1,
        "uncommitted_in_scope_count": 1,
        "untracked_in_scope_count": 1,
        "uncommitted_out_of_scope_count": 0,
        "untracked_out_of_scope_count": 0,
        "external_effect_state": "NONE",
        "branch_effect_dependency": "NONE",
        "external_effect_evidence_fingerprint": EFFECT_FINGERPRINT,
        "collision_state": "NONE",
        "colliding_pr_numbers": [],
        "receipt_kind": "CHECKPOINT_VERIFIED",
        "receipt_version": "v1",
        "verified_at": VERIFIED_AT,
        "authority_effect": "NONE",
        "writer_release_authorized": False,
        "merge_authorized": False,
        "receiver_transfer_authorized": False,
        "receipt_digest": result.receipt_digest,
    }
    assert len(result.owned_path_digest) == 64
    assert len(result.receipt_digest) == 64


def test_receipt_is_canonical_and_order_independent() -> None:
    module = _contract()
    first = _verify(module)
    second = _verify(
        module,
        request=_request(module, owned_paths=tuple(reversed(OWNED_PATHS))),
        remote=_remote(
            module,
            changed_paths=tuple(reversed(_remote(module).changed_paths)),
            path_entries=tuple(reversed(_entries(module))),
        ),
    )
    assert isinstance(first, module.SourceContinuityReceipt)
    assert isinstance(second, module.SourceContinuityReceipt)
    assert first.to_dict() == second.to_dict()
    assert module.canonical_json(first.to_dict()) == json.dumps(
        first.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def test_local_branch_is_bound_into_receipt_digest() -> None:
    module = _contract()
    result = _verify(module)
    assert isinstance(result, module.SourceContinuityReceipt)
    tampered = replace(result, local_branch="sol/tampered", receipt_digest="")
    assert module._digest(tampered._payload_without_digest()) != result.receipt_digest


@pytest.mark.parametrize("branch", [None, "", "HEAD", "wrong-branch", "/detached"])
def test_wrong_detached_or_missing_local_branch_uses_one_value_free_refusal(
    branch: object,
) -> None:
    module = _contract()
    result = _verify(module, local=_checkpoint_local(module, branch=branch))
    _assert_refusal(module, result, "LOCAL_BRANCH_MISMATCH", exit_code=1)


def test_current_base_and_merge_base_movement_refresh_identity_without_refusal() -> None:
    module = _contract()
    initial = _verify(module)
    moved_current_base = _verify(
        module, remote=_remote(module, current_base_head_sha="7" * 40)
    )
    moved_merge_base = _verify(
        module, remote=_remote(module, merge_base_sha="8" * 40)
    )

    for result in (initial, moved_current_base, moved_merge_base):
        assert isinstance(result, module.SourceContinuityReceipt)
    assert moved_current_base.current_base_head_sha == "7" * 40
    assert moved_merge_base.remote_merge_base_sha == "8" * 40
    assert len(
        {
            initial.receipt_digest,
            moved_current_base.receipt_digest,
            moved_merge_base.receipt_digest,
        }
    ) == 3


@pytest.mark.parametrize(
    ("remote_changes", "code"),
    [
        ({"repository": "wrong/repo"}, "REMOTE_IDENTITY_MISMATCH"),
        ({"pr_number": 411}, "REMOTE_IDENTITY_MISMATCH"),
        ({"branch": "wrong-branch"}, "REMOTE_IDENTITY_MISMATCH"),
        ({"base_ref": "other"}, "REMOTE_IDENTITY_MISMATCH"),
        ({"pr_open": False}, "PR_NOT_OPEN"),
        ({"pr_draft_or_hold": False}, "PR_NOT_DRAFT_OR_HOLD"),
        ({"head_sha": BASE_SHA}, "REMOTE_HEAD_EQUALS_PICKUP_BASE"),
        ({"pagination_complete": False}, "REMOTE_CENSUS_INCOMPLETE"),
        (
            {"changed_paths": OWNED_PATHS + ("docs/unowned.md",)},
            "PATH_OUTSIDE_OWNERSHIP",
        ),
    ],
)
def test_remote_identity_and_census_fail_closed(
    remote_changes: dict[str, Any], code: str
) -> None:
    module = _contract()
    result = _verify(module, remote=_remote(module, **remote_changes))
    _assert_refusal(module, result, code, exit_code=2)


@pytest.mark.parametrize(
    ("changed_paths", "entry_case", "code"),
    [
        (
            (OWNED_PATHS[0], OWNED_PATHS[0]),
            "valid",
            "REMOTE_FACTS_INVALID",
        ),
        (OWNED_PATHS, "missing", "PATH_ENTRY_MISMATCH"),
        ((OWNED_PATHS[0],), "extra", "PATH_ENTRY_MISMATCH"),
        (OWNED_PATHS, "duplicate", "PATH_ENTRY_MISMATCH"),
    ],
)
def test_changed_paths_and_path_entries_are_an_exact_duplicate_free_bijection(
    changed_paths: tuple[str, ...], entry_case: str, code: str
) -> None:
    module = _contract()
    entries = _entries(module)
    selected = {
        "valid": entries,
        "missing": (entries[0],),
        "extra": entries,
        "duplicate": (entries[0], entries[0], entries[1]),
    }[entry_case]
    result = _verify(
        module,
        remote=_remote(
            module,
            changed_paths=changed_paths,
            path_entries=selected,
        ),
    )
    _assert_refusal(module, result, code, exit_code=2)


def test_non_blob_path_entry_refuses() -> None:
    module = _contract()
    result = _verify(
        module,
        remote=_remote(module, path_entries=_entries(module, first_type="tree")),
    )
    _assert_refusal(module, result, "UNSAFE_REMOTE_OBJECT", exit_code=2)


@pytest.mark.parametrize(
    ("entries", "code"),
    [
        ({"first_mode": "120000"}, "UNSAFE_REMOTE_OBJECT"),
        ({"first_mode": "160000"}, "UNSAFE_REMOTE_OBJECT"),
        ({"first_size": -1}, "REMOTE_FACTS_INVALID"),
        ({"first_size": 10_000_001}, "REMOTE_BLOB_TOO_LARGE"),
    ],
)
def test_remote_path_policy_rejects_unsafe_modes_and_sizes(
    entries: dict[str, Any], code: str
) -> None:
    module = _contract()
    result = _verify(
        module, remote=_remote(module, path_entries=_entries(module, **entries))
    )
    _assert_refusal(module, result, code, exit_code=2)


@pytest.mark.parametrize(
    "unsafe_path",
    ["../escape.py", "/absolute.py", ".git/config", "docs//double.md", "docs/./dot.md"],
)
def test_owned_paths_reject_unsafe_relative_paths(unsafe_path: str) -> None:
    module = _contract()
    result = _verify(
        module,
        request=_request(module, owned_paths=(unsafe_path,)),
        remote=_remote(
            module,
            changed_paths=(unsafe_path,),
            path_entries=(
                module.RemotePathEntry(
                    path=unsafe_path,
                    mode="100644",
                    object_type="blob",
                    object_sha=BLOB_A,
                    size=1,
                ),
            ),
        ),
    )
    _assert_refusal(module, result, "INVALID_REQUEST", exit_code=2)


@pytest.mark.parametrize(
    "request_changes",
    [
        {"receipt_kind": "CHECKPOINT_VERIFIED"},
        {"operation_key": ""},
        {"operation_key": 7},
        {"repository": "invalid"},
        {"pr_number": True},
        {"pr_number": 0},
        {"pr_number": 2_147_483_648},
        {"branch": "bad..branch"},
        {"base_ref": None},
        {"pinned_base_sha": "A" * 40},
        {"owned_paths": ()},
        {"owned_paths": [OWNED_PATHS[0]]},
        {"owned_paths": (OWNED_PATHS[0], OWNED_PATHS[0])},
        {"verified_at": "2026-13-03T05:00:00Z"},
        {"verified_at": "2026-09-03T05:00:00+00:00"},
    ],
)
def test_hostile_request_scalar_range_hash_time_and_enum_shapes_refuse(
    request_changes: dict[str, Any],
) -> None:
    module = _contract()
    result = _verify(module, request=_request(module, **request_changes))
    _assert_refusal(module, result, "INVALID_REQUEST", exit_code=2)


@pytest.mark.parametrize(
    "remote_changes",
    [
        {"pr_number": True},
        {"pr_number": -1},
        {"pr_number": 2_147_483_648},
        {"pr_open": 1},
        {"head_sha": "g" * 40},
        {"tree_sha": "2" * 39},
        {"merge_base_sha": None},
        {"current_base_head_sha": "A" * 40},
        {"changed_paths": list(OWNED_PATHS)},
        {"collision_state": "NONE"},
        {"colliding_pr_numbers": (True,)},
        {"pagination_complete": 1},
    ],
)
def test_hostile_remote_scalar_range_hash_and_enum_shapes_refuse(
    remote_changes: dict[str, Any],
) -> None:
    module = _contract()
    result = _verify(module, remote=_remote(module, **remote_changes))
    _assert_refusal(module, result, "REMOTE_FACTS_INVALID", exit_code=2)


def test_remote_path_entries_requires_an_immutable_tuple() -> None:
    module = _contract()
    result = _verify(
        module, remote=_remote(module, path_entries=list(_entries(module)))
    )
    _assert_refusal(module, result, "REMOTE_FACTS_INVALID", exit_code=2)


@pytest.mark.parametrize(
    "local_changes",
    [
        {"head_sha": "A" * 40},
        {"tree_sha": None},
        {"remote_head_object_exists": 1},
        {"remote_head_is_ancestor_of_local": "yes"},
        {"unpushed_commit_count": -1},
        {"uncommitted_in_scope_count": True},
        {"untracked_in_scope_count": "0"},
        {"uncommitted_out_of_scope_count": -1},
        {"untracked_out_of_scope_count": True},
    ],
)
def test_hostile_local_scalar_range_and_hash_shapes_refuse(
    local_changes: dict[str, Any],
) -> None:
    module = _contract()
    result = _verify(module, local=_checkpoint_local(module, **local_changes))
    _assert_refusal(module, result, "LOCAL_FACTS_INVALID", exit_code=2)


@pytest.mark.parametrize(
    "external_changes",
    [
        {"state": "NONE"},
        {"branch_dependency": "NONE"},
        {"evidence_fingerprint": "c" * 63},
        {"evidence_fingerprint": "G" * 64},
        {"evidence_fingerprint": None},
    ],
)
def test_hostile_external_enum_and_hash_shapes_refuse(
    external_changes: dict[str, Any],
) -> None:
    module = _contract()
    result = _verify(module, external=_external(module, **external_changes))
    _assert_refusal(module, result, "EXTERNAL_EFFECT_INVALID", exit_code=2)


@pytest.mark.parametrize(
    ("local_changes", "code"),
    [
        ({"remote_head_object_exists": False}, "REMOTE_HEAD_OBJECT_MISSING"),
        ({"remote_head_is_ancestor_of_local": False}, "REMOTE_HEAD_NOT_ANCESTOR"),
        ({"uncommitted_out_of_scope_count": 1}, "OUT_OF_SCOPE_DIRT"),
        ({"untracked_out_of_scope_count": 1}, "OUT_OF_SCOPE_DIRT"),
    ],
)
def test_checkpoint_refuses_unrecoverable_or_unowned_local_state(
    local_changes: dict[str, Any], code: str
) -> None:
    module = _contract()
    result = _verify(module, local=_checkpoint_local(module, **local_changes))
    _assert_refusal(module, result, code, exit_code=1)


@pytest.mark.parametrize(
    ("local_changes", "code"),
    [
        ({"head_sha": LOCAL_HEAD_SHA}, "LOCAL_REMOTE_IDENTITY_MISMATCH"),
        ({"tree_sha": LOCAL_TREE_SHA}, "LOCAL_REMOTE_IDENTITY_MISMATCH"),
        ({"unpushed_commit_count": 1}, "UNPUSHED_COMMITS"),
        ({"uncommitted_in_scope_count": 1}, "IN_SCOPE_DIRT"),
        ({"untracked_in_scope_count": 1}, "IN_SCOPE_DIRT"),
        ({"uncommitted_out_of_scope_count": 1}, "OUT_OF_SCOPE_DIRT"),
        ({"untracked_out_of_scope_count": 1}, "OUT_OF_SCOPE_DIRT"),
    ],
)
def test_remote_complete_requires_exact_clean_local_remote_identity(
    local_changes: dict[str, Any], code: str
) -> None:
    module = _contract()
    result = _verify(
        module,
        request=_request(module, kind=module.ReceiptKind.REMOTE_COMPLETE_VERIFIED),
        local=_complete_local(module, **local_changes),
    )
    _assert_refusal(module, result, code, exit_code=1)


@pytest.mark.parametrize(
    "kind_name", ["CHECKPOINT_VERIFIED", "REMOTE_COMPLETE_VERIFIED"]
)
def test_effect_unknown_refuses_both_receipt_kinds(kind_name: str) -> None:
    module = _contract()
    kind = module.ReceiptKind(kind_name)
    result = _verify(
        module,
        request=_request(module, kind=kind),
        local=(
            _complete_local(module)
            if kind is module.ReceiptKind.REMOTE_COMPLETE_VERIFIED
            else _checkpoint_local(module)
        ),
        external=_external(
            module,
            state=module.ExternalEffectState.EFFECT_UNKNOWN,
            branch_dependency=module.BranchEffectDependency.UNKNOWN,
        ),
    )
    _assert_refusal(module, result, "EXTERNAL_EFFECT_UNKNOWN", exit_code=1)


def test_effect_and_overlap_remain_evidence_only() -> None:
    module = _contract()
    complete = _request(module, kind=module.ReceiptKind.REMOTE_COMPLETE_VERIFIED)

    separable = _verify(
        module,
        request=complete,
        local=_complete_local(module),
        external=_external(
            module,
            state=module.ExternalEffectState.OPEN_KNOWN_EFFECT,
            branch_dependency=module.BranchEffectDependency.SEPARABLE,
        ),
    )
    assert isinstance(separable, module.SourceContinuityReceipt)
    assert separable.external_effect_state is module.ExternalEffectState.OPEN_KNOWN_EFFECT

    overlap = _verify(
        module,
        remote=_remote(
            module,
            collision_state=module.CollisionState.OVERLAP,
            colliding_pr_numbers=(404, 147, 404),
        ),
    )
    assert isinstance(overlap, module.SourceContinuityReceipt)
    assert overlap.collision_state is module.CollisionState.OVERLAP
    assert overlap.colliding_pr_numbers == (147, 404)

    for receipt in (separable, overlap):
        payload = receipt.to_dict()
        assert payload["authority_effect"] == "NONE"
        assert payload["writer_release_authorized"] is False
        assert payload["merge_authorized"] is False
        assert payload["receiver_transfer_authorized"] is False


def test_required_or_unknown_branch_effect_refuses() -> None:
    module = _contract()
    complete = _request(module, kind=module.ReceiptKind.REMOTE_COMPLETE_VERIFIED)
    for external, code in (
        (
            _external(
                module,
                state=module.ExternalEffectState.OPEN_KNOWN_EFFECT,
                branch_dependency=module.BranchEffectDependency.REQUIRED,
            ),
            "BRANCH_EFFECT_REQUIRED",
        ),
        (
            _external(
                module,
                state=module.ExternalEffectState.OPEN_KNOWN_EFFECT,
                branch_dependency=module.BranchEffectDependency.UNKNOWN,
            ),
            "BRANCH_EFFECT_UNKNOWN",
        ),
    ):
        _assert_refusal(
            module,
            _verify(
                module,
                request=complete,
                local=_complete_local(module),
                external=external,
            ),
            code,
            exit_code=1,
        )


def test_receipt_digest_changes_after_remote_path_or_effect_identity_moves() -> None:
    module = _contract()
    first = _verify(module)
    assert isinstance(first, module.SourceContinuityReceipt)

    moved = _verify(
        module,
        local=_checkpoint_local(module, head_sha="9" * 40, tree_sha="0" * 40),
        remote=_remote(
            module,
            head_sha="6" * 40,
            tree_sha="7" * 40,
            path_entries=(
                replace(_entries(module)[0], object_sha="8" * 40),
                _entries(module)[1],
            ),
        ),
    )
    assert isinstance(moved, module.SourceContinuityReceipt)
    assert moved.receipt_digest != first.receipt_digest
    assert moved.owned_path_digest != first.owned_path_digest

    moved_effect = _verify(
        module,
        external=_external(
            module,
            state=module.ExternalEffectState.OPEN_KNOWN_EFFECT,
            branch_dependency=module.BranchEffectDependency.SEPARABLE,
            evidence_fingerprint="d" * 64,
        ),
    )
    assert isinstance(moved_effect, module.SourceContinuityReceipt)
    assert moved_effect.receipt_digest != first.receipt_digest

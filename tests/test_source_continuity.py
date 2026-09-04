from __future__ import annotations

from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any
from urllib.parse import quote

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


@pytest.mark.parametrize("invalid_ref", ["HEAD", "foo/.bar", "foo.lock/bar"])
def test_aligned_invalid_branch_refs_cannot_mint_receipts(invalid_ref: str) -> None:
    module = _contract()
    result = _verify(
        module,
        request=_request(module, branch=invalid_ref),
        remote=_remote(module, branch=invalid_ref),
        local=_checkpoint_local(module, branch=invalid_ref),
    )
    _assert_refusal(module, result, "INVALID_REQUEST", exit_code=2)


@pytest.mark.parametrize("valid_ref", ["head", "foo/bar", BRANCH])
def test_canonical_branch_refs_remain_valid(valid_ref: str) -> None:
    module = _contract()
    result = _verify(
        module,
        request=_request(module, branch=valid_ref),
        remote=_remote(module, branch=valid_ref),
        local=_checkpoint_local(module, branch=valid_ref),
    )
    assert isinstance(result, module.SourceContinuityReceipt)


@pytest.mark.parametrize("invalid_ref", ["HEAD", "foo/.bar", "foo.lock/bar"])
def test_invalid_base_refs_use_the_same_complete_ref_grammar(invalid_ref: str) -> None:
    module = _contract()
    result = _verify(
        module,
        request=_request(module, base_ref=invalid_ref),
        remote=_remote(module, base_ref=invalid_ref),
    )
    _assert_refusal(module, result, "INVALID_REQUEST", exit_code=2)


def test_request_lone_surrogate_path_stays_inside_invalid_request_envelope() -> None:
    module = _contract()
    unsafe_path = "docs/\ud800.py"
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


def test_remote_changed_path_lone_surrogate_stays_inside_remote_refusal_envelope() -> None:
    module = _contract()
    unsafe_path = "docs/\ud800.py"
    result = _verify(
        module,
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
    _assert_refusal(module, result, "REMOTE_FACTS_INVALID", exit_code=2)


def test_remote_entry_path_lone_surrogate_stays_inside_remote_refusal_envelope() -> None:
    module = _contract()
    unsafe_path = "docs/\ud800.py"
    entries = (
        replace(_entries(module)[0], path=unsafe_path),
        _entries(module)[1],
    )
    result = _verify(module, remote=_remote(module, path_entries=entries))
    _assert_refusal(module, result, "REMOTE_FACTS_INVALID", exit_code=2)


@pytest.mark.parametrize(
    "local_changes",
    [
        {
            "head_sha": HEAD_SHA,
            "tree_sha": LOCAL_TREE_SHA,
            "unpushed_commit_count": 0,
        },
        {
            "head_sha": HEAD_SHA,
            "tree_sha": TREE_SHA,
            "unpushed_commit_count": 1,
        },
        {
            "head_sha": LOCAL_HEAD_SHA,
            "tree_sha": LOCAL_TREE_SHA,
            "unpushed_commit_count": 0,
        },
    ],
)
def test_checkpoint_refuses_mutually_impossible_local_remote_facts(
    local_changes: dict[str, Any],
) -> None:
    module = _contract()
    result = _verify(module, local=_checkpoint_local(module, **local_changes))
    _assert_refusal(module, result, "LOCAL_FACTS_INVALID", exit_code=2)


def test_checkpoint_same_remote_head_allows_only_same_tree_and_zero_unpushed() -> None:
    module = _contract()
    result = _verify(
        module,
        local=_checkpoint_local(
            module,
            head_sha=HEAD_SHA,
            tree_sha=TREE_SHA,
            unpushed_commit_count=0,
        ),
    )
    assert isinstance(result, module.SourceContinuityReceipt)
    assert result.local_equals_remote is True
    assert result.uncommitted_in_scope_count == 1
    assert result.untracked_in_scope_count == 1


def test_checkpoint_empty_descendant_commit_is_valid_with_positive_unpushed_count() -> None:
    module = _contract()
    result = _verify(
        module,
        local=_checkpoint_local(
            module,
            head_sha=LOCAL_HEAD_SHA,
            tree_sha=TREE_SHA,
            unpushed_commit_count=1,
        ),
    )
    assert isinstance(result, module.SourceContinuityReceipt)
    assert result.local_equals_remote is False
    assert result.local_tree_sha == result.remote_tree_sha
    assert result.unpushed_commit_count == 1


FINAL_OWNED_PATHS = (
    "control_plane/source_continuity.py",
    "scripts/source_continuity.py",
    "tests/test_source_continuity.py",
    "docs/sol_skills/COMMISSION_WAVE.md",
    "docs/sol_skills/REVIEW_RETURN.md",
    "docs/AGENT_DIALOGUE_SESSION_CLOSE_LAW.md",
)
CLI_PATH = ROOT / "scripts" / "source_continuity.py"
COMMISSION_WAVE_PATH = ROOT / "docs" / "sol_skills" / "COMMISSION_WAVE.md"
REVIEW_RETURN_PATH = ROOT / "docs" / "sol_skills" / "REVIEW_RETURN.md"
SESSION_CLOSE_PATH = ROOT / "docs" / "AGENT_DIALOGUE_SESSION_CLOSE_LAW.md"
WORKSPACE = "/repo"
TOKEN = "test-token"
API_ROOT = "https://api.github.com"


def _cli_module():
    assert CLI_PATH.is_file(), "scripts/source_continuity.py must exist"
    name = "source_continuity_cli_under_test"
    spec = importlib.util.spec_from_file_location(name, CLI_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _cli_argv(kind: str = "checkpoint") -> list[str]:
    args = [
        "verify",
        "--kind",
        kind,
        "--operation-key",
        OPERATION,
        "--workspace",
        WORKSPACE,
        "--repository",
        REPOSITORY,
        "--pr-number",
        str(PR_NUMBER),
        "--branch",
        BRANCH,
        "--base-ref",
        "master",
        "--pinned-base-sha",
        BASE_SHA,
        "--external-effect-state",
        "NONE",
        "--branch-effect-dependency",
        "NONE",
        "--external-effect-evidence-fingerprint",
        EFFECT_FINGERPRINT,
    ]
    for path in FINAL_OWNED_PATHS:
        args.extend(("--owned-path", path))
    return args


class _ProbeRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.kwargs: list[dict[str, Any]] = []

    @staticmethod
    def _done(returncode: int = 0, stdout: str = "", stderr: str = ""):
        from types import SimpleNamespace

        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)

    def __call__(self, command, **kwargs):
        call = tuple(str(part) for part in command)
        self.calls.append(call)
        self.kwargs.append(dict(kwargs))

        commands = {
            "rev-parse",
            "symbolic-ref",
            "cat-file",
            "merge-base",
            "rev-list",
            "config",
            "diff",
            "ls-files",
            "ls-tree",
            "status",
        }
        command_index = next(
            index for index, value in enumerate(call) if index and value in commands
        )
        assert call[:3] == ("/usr/bin/git", "--no-pager", "--no-replace-objects")
        assert call[command_index - 1] == "--work-tree=."
        prefix = call[3 : command_index - 1]
        assert len(prefix) % 2 == 0
        assert all(prefix[index] == "-c" for index in range(0, len(prefix), 2))
        assert {
            "core.fsmonitor=false",
            "core.untrackedCache=false",
            "core.hooksPath=/dev/null",
            "core.attributesFile=/dev/null",
            "core.excludesFile=/dev/null",
            "diff.external=",
            "diff.renames=false",
            "core.checkStat=default",
            "core.trustctime=true",
            "core.symlinks=true",
            "credential.helper=",
            "protocol.allow=never",
            "protocol.file.allow=always",
        } <= set(prefix[1::2])
        call = call[command_index:]

        if call == ("rev-parse", "--show-toplevel"):
            return self._done(stdout=f"{WORKSPACE}\n")
        if call == ("symbolic-ref", "--short", "HEAD"):
            return self._done(stdout=f"{BRANCH}\n")
        if call == ("rev-parse", "HEAD^{commit}"):
            return self._done(stdout=f"{HEAD_SHA}\n")
        if call == ("rev-parse", "HEAD^{tree}"):
            return self._done(stdout=f"{TREE_SHA}\n")
        if call in {
            ("cat-file", "-e", f"{HEAD_SHA}^{{commit}}"),
            ("cat-file", "-e", f"{BASE_SHA}^{{commit}}"),
        }:
            return self._done()
        if call == ("merge-base", "--is-ancestor", HEAD_SHA, "HEAD"):
            return self._done()
        if call == ("rev-list", "--count", f"{HEAD_SHA}..HEAD"):
            return self._done(stdout="0\n")
        if call == (
            "config", "--null", "--name-only", "--get-regexp",
            r"^filter\..*\.(clean|process)$",
        ):
            return self._done(returncode=1)
        if call == (
            "diff", "--no-renames", "--no-ext-diff", "--no-textconv",
            "--ignore-submodules=none", "--name-only", "-z", "HEAD", "--",
        ):
            return self._done()
        if call == (
            "diff", "--cached", "--no-renames", "--no-ext-diff", "--no-textconv",
            "--ignore-submodules=none", "--name-only", "-z", "--",
        ):
            return self._done()
        if call == ("ls-files", "-v", "-z"):
            return self._done(
                stdout="".join(f"H {path}\0" for path in FINAL_OWNED_PATHS)
            )
        if call == ("ls-files", "--others", "--exclude-standard", "-z"):
            return self._done()
        if call == (
            "diff",
            "--no-renames",
            "--no-ext-diff",
            "--no-textconv",
            "--ignore-submodules=none",
            "--name-only",
            "-z",
            f"{BASE_SHA}..{HEAD_SHA}",
            "--",
        ):
            return self._done(stdout="\0".join(FINAL_OWNED_PATHS) + "\0")
        if call == (
            "ls-tree",
            "-z",
            "-l",
            HEAD_SHA,
            "--",
            *FINAL_OWNED_PATHS,
        ):
            hex_chars = "789abc"
            payload = "".join(
                f"100644 blob {hex_chars[index] * 40} {100 + index}\t{path}\0"
                for index, path in enumerate(FINAL_OWNED_PATHS)
            )
            return self._done(stdout=payload)
        raise AssertionError(f"unexpected git probe command: {call!r}")


class _ProbeHTTP:
    def __init__(self, *, move_remote_head_on_second_read: bool = False) -> None:
        self.move_remote_head_on_second_read = move_remote_head_on_second_read
        self.calls: list[tuple[str, str, float]] = []
        self.pr_reads = 0

    def __call__(self, url: str, *, token: str, timeout: float):
        self.calls.append((url, token, timeout))
        assert url.startswith(API_ROOT + "/")
        assert token == TOKEN
        assert TOKEN not in url
        endpoint = url.removeprefix(API_ROOT + "/")
        pr_endpoint = f"repos/{REPOSITORY}/pulls/{PR_NUMBER}"
        if endpoint == pr_endpoint:
            self.pr_reads += 1
            head = (
                "9" * 40
                if self.move_remote_head_on_second_read and self.pr_reads > 1
                else HEAD_SHA
            )
            return {
                "state": "open",
                "draft": True,
                "labels": [],
                "head": {
                    "ref": BRANCH,
                    "sha": head,
                    "repo": {"full_name": REPOSITORY},
                },
                "base": {"ref": "master"},
            }
        if endpoint == f"repos/{REPOSITORY}/branches/{quote(BRANCH, safe='')}":
            return {"commit": {"sha": HEAD_SHA}}
        if endpoint == f"repos/{REPOSITORY}/git/commits/{HEAD_SHA}":
            return {"tree": {"sha": TREE_SHA}}
        if endpoint == f"repos/{REPOSITORY}/branches/master":
            return {"commit": {"sha": CURRENT_BASE_SHA}}
        if endpoint == f"repos/{REPOSITORY}/compare/{CURRENT_BASE_SHA}...{HEAD_SHA}":
            return {"merge_base_commit": {"sha": BASE_SHA}}
        if endpoint == f"repos/{REPOSITORY}/pulls/{PR_NUMBER}/files?per_page=100&page=1":
            return [{"filename": path, "status": "modified"} for path in FINAL_OWNED_PATHS]
        if endpoint == f"repos/{REPOSITORY}/pulls?state=open&per_page=100&page=1":
            return [{"number": PR_NUMBER}]
        raise AssertionError(f"unexpected HTTP probe endpoint: {endpoint}")


def _run_cli(module, argv: list[str], *, runner=None, http=None, environ=None):
    return module.main(
        argv,
        runner=runner or _ProbeRunner(),
        http_get=http or _ProbeHTTP(),
        environ=environ if environ is not None else {"GITHUB_TOKEN": TOKEN},
        clock=lambda: VERIFIED_AT,
    )


@pytest.mark.parametrize(
    ("kind", "receipt_kind"),
    [("checkpoint", "CHECKPOINT_VERIFIED"), ("remote-complete", "REMOTE_COMPLETE_VERIFIED")],
)
def test_cli_collects_facts_with_canonical_read_only_probes_and_prints_one_receipt(
    kind: str,
    receipt_kind: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _cli_module()
    runner = _ProbeRunner()
    http = _ProbeHTTP()

    exit_code = _run_cli(module, _cli_argv(kind), runner=runner, http=http)
    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert captured.out.count("\n") == 1
    payload = json.loads(captured.out)
    assert payload["schema"] == "mastermind.source_continuity_receipt/v1"
    assert payload["receipt_kind"] == receipt_kind
    assert payload["changed_paths"] == sorted(FINAL_OWNED_PATHS)
    assert payload["local_equals_remote"] is True
    assert payload["authority_effect"] == "NONE"
    assert payload["writer_release_authorized"] is False
    assert payload["merge_authorized"] is False
    assert payload["receiver_transfer_authorized"] is False

    forbidden = {
        "fetch",
        "checkout",
        "add",
        "commit",
        "push",
        "reset",
        "rebase",
        "merge",
        "pull",
        "switch",
        "clean",
    }
    assert runner.calls
    for call, kwargs in zip(runner.calls, runner.kwargs, strict=True):
        assert call[0] == "/usr/bin/git"
        assert not forbidden.intersection(call)
        assert kwargs.get("cwd") == WORKSPACE
        assert kwargs.get("env", {}).get("GIT_OPTIONAL_LOCKS") == "0"
        assert kwargs.get("env", {}).get("GIT_NO_LAZY_FETCH") == "1"
        assert "GITHUB_TOKEN" not in kwargs.get("env", {})
    assert any("ls-tree" in call for call in runner.calls)
    assert any(
        "diff" in call
        and f"{BASE_SHA}..{HEAD_SHA}" in call
        and {
            "--no-renames",
            "--no-ext-diff",
            "--no-textconv",
            "--name-only",
            "-z",
            "--",
        }
        <= set(call)
        for call in runner.calls
    )
    assert http.calls
    assert all(call[0].startswith(API_ROOT + "/") for call in http.calls)


def test_cli_rejects_invalid_request_before_any_probe(
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _cli_module()
    runner = _ProbeRunner()
    http = _ProbeHTTP()
    args = _cli_argv()
    args[args.index("--repository") + 1] = "not-a-repository"

    exit_code = _run_cli(module, args, runner=runner, http=http)
    captured = capsys.readouterr()
    assert exit_code == 2
    assert runner.calls == []
    assert http.calls == []
    payload = json.loads(captured.out)
    assert payload["code"] == "INVALID_REQUEST"
    assert OPERATION not in captured.out
    assert BRANCH not in captured.out
    assert WORKSPACE not in captured.out


def test_cli_requires_absolute_workspace_before_any_probe(
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _cli_module()
    runner = _ProbeRunner()
    http = _ProbeHTTP()
    args = _cli_argv()
    args[args.index("--workspace") + 1] = "relative/worktree"

    exit_code = _run_cli(module, args, runner=runner, http=http)
    captured = capsys.readouterr()
    assert exit_code == 2
    assert runner.calls == []
    assert http.calls == []
    assert json.loads(captured.out)["code"] == "INVALID_REQUEST"
    assert "relative/worktree" not in captured.out


def test_cli_missing_token_is_fixed_value_free_and_stops_before_probes(
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _cli_module()
    runner = _ProbeRunner()
    http = _ProbeHTTP()

    exit_code = _run_cli(
        module,
        _cli_argv(),
        runner=runner,
        http=http,
        environ={},
    )
    captured = capsys.readouterr()
    assert exit_code == 2
    assert runner.calls == []
    assert http.calls == []
    payload = json.loads(captured.out)
    assert payload["code"] == "AUTH_UNAVAILABLE"
    assert REPOSITORY not in captured.out
    assert WORKSPACE not in captured.out


def test_cli_refuses_if_remote_head_moves_during_same_proof(
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _cli_module()
    runner = _ProbeRunner()
    http = _ProbeHTTP(move_remote_head_on_second_read=True)

    exit_code = _run_cli(module, _cli_argv(), runner=runner, http=http)
    captured = capsys.readouterr()
    assert exit_code == 1
    payload = json.loads(captured.out)
    assert payload["code"] == "REMOTE_PROOF_CHANGED"
    assert http.pr_reads == 2
    assert "9" * 40 not in captured.out


def test_commission_wave_requires_a_remote_checkpoint_before_long_source_exposure() -> None:
    text = COMMISSION_WAVE_PATH.read_text(encoding="utf-8")
    assert "### Source Continuity checkpoint gate" in text
    assert "CHECKPOINT_VERIFIED" in text
    assert "before long CI, review, or context-budget exposure" in text
    assert "same operation branch and Draft/HOLD PR" in text
    assert "does not grant receiver transfer, retry, Ready, merge, or writer release" in text
    assert "Refresh the receipt after head, path, base, or external-effect identity moves" in text


def test_session_close_keeps_remote_complete_nonterminal_until_writer_release() -> None:
    text = SESSION_CLOSE_PATH.read_text(encoding="utf-8")
    assert "### 3.6 Source-writer stickiness and remote-complete terminality" in text
    sequence = """REMOTE_COMPLETE_VERIFIED
-> SOL_ACCEPTED_BUILDER_RESULT
-> TERMINAL_BUILDER_STOP
-> EXACT_CHILD_SOURCE_REMOVAL_OR_WATCH_STOP_FAILED
-> BRANCH_WRITER_RELEASED"""
    assert sequence in text
    assert "CHECKPOINT_VERIFIED is never a terminal, retry, transfer, or writer-release edge" in text
    assert "EFFECT_UNKNOWN remains exact-session sticky" in text


def test_review_return_remote_complete_preserves_review_reuse_and_release_maintainer_boundary() -> None:
    text = REVIEW_RETURN_PATH.read_text(encoding="utf-8")
    for required in ("REVIEW_REUSE_ALLOWED", "FULL_REREVIEW_REQUIRED", "RELEASE_BLOCKED"):
        assert required in text
    assert "### Step 8A — Source Continuity remote-complete and release-maintainer boundary" in text
    assert "REMOTE_COMPLETE_VERIFIED is evidence, not terminality or writer-release authority" in text
    assert "fresh maintenance-only release operation on the same PR/branch" in text
    assert "must not edit feature semantics" in text
    assert "Step 2A review-reuse classification remains controlling" in text


def test_checkpoint_allows_required_open_known_effect_without_authority() -> None:
    module = _contract()
    result = _verify(
        module,
        external=_external(
            module,
            state=module.ExternalEffectState.OPEN_KNOWN_EFFECT,
            branch_dependency=module.BranchEffectDependency.REQUIRED,
        ),
    )

    assert isinstance(result, module.SourceContinuityReceipt)
    payload = result.to_dict()
    assert payload["receipt_kind"] == "CHECKPOINT_VERIFIED"
    assert payload["external_effect_state"] == "OPEN_KNOWN_EFFECT"
    assert payload["branch_effect_dependency"] == "REQUIRED"
    assert payload["authority_effect"] == "NONE"
    assert payload["writer_release_authorized"] is False
    assert payload["merge_authorized"] is False
    assert payload["receiver_transfer_authorized"] is False


def test_remote_complete_still_refuses_the_same_required_open_effect() -> None:
    module = _contract()
    result = _verify(
        module,
        request=_request(module, kind=module.ReceiptKind.REMOTE_COMPLETE_VERIFIED),
        local=_complete_local(module),
        external=_external(
            module,
            state=module.ExternalEffectState.OPEN_KNOWN_EFFECT,
            branch_dependency=module.BranchEffectDependency.REQUIRED,
        ),
    )
    _assert_refusal(module, result, "BRANCH_EFFECT_REQUIRED", exit_code=1)


@pytest.mark.parametrize(
    ("state_name", "dependency_name"),
    [
        ("NONE", "REQUIRED"),
        ("NONE", "SEPARABLE"),
        ("RECONCILED_NO_OPEN_EFFECT", "REQUIRED"),
        ("RECONCILED_NO_OPEN_EFFECT", "SEPARABLE"),
        ("OPEN_KNOWN_EFFECT", "NONE"),
    ],
)
def test_incoherent_effect_dependency_pairs_refuse(
    state_name: str,
    dependency_name: str,
) -> None:
    module = _contract()
    result = _verify(
        module,
        external=_external(
            module,
            state=module.ExternalEffectState(state_name),
            branch_dependency=module.BranchEffectDependency(dependency_name),
        ),
    )
    _assert_refusal(module, result, "EXTERNAL_EFFECT_INVALID", exit_code=2)


@pytest.mark.parametrize(
    "kind_name", ["CHECKPOINT_VERIFIED", "REMOTE_COMPLETE_VERIFIED"]
)
def test_unknown_branch_dependency_refuses_both_receipt_kinds(kind_name: str) -> None:
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
            state=module.ExternalEffectState.OPEN_KNOWN_EFFECT,
            branch_dependency=module.BranchEffectDependency.UNKNOWN,
        ),
    )
    _assert_refusal(module, result, "BRANCH_EFFECT_UNKNOWN", exit_code=1)


def _cli_argv_with_effect(kind: str, state: str, dependency: str) -> list[str]:
    args = _cli_argv(kind)
    args[args.index("--external-effect-state") + 1] = state
    args[args.index("--branch-effect-dependency") + 1] = dependency
    return args


def test_cli_checkpoint_allows_required_open_known_effect_and_remote_complete_refuses(
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _cli_module()

    checkpoint_exit = _run_cli(
        module,
        _cli_argv_with_effect("checkpoint", "OPEN_KNOWN_EFFECT", "REQUIRED"),
    )
    checkpoint_output = capsys.readouterr()
    assert checkpoint_exit == 0
    checkpoint = json.loads(checkpoint_output.out)
    assert checkpoint["receipt_kind"] == "CHECKPOINT_VERIFIED"
    assert checkpoint["branch_effect_dependency"] == "REQUIRED"
    assert checkpoint["authority_effect"] == "NONE"
    assert checkpoint["writer_release_authorized"] is False
    assert checkpoint["merge_authorized"] is False
    assert checkpoint["receiver_transfer_authorized"] is False

    complete_exit = _run_cli(
        module,
        _cli_argv_with_effect("remote-complete", "OPEN_KNOWN_EFFECT", "REQUIRED"),
    )
    complete_output = capsys.readouterr()
    assert complete_exit == 1
    assert json.loads(complete_output.out)["code"] == "BRANCH_EFFECT_REQUIRED"


class _CollisionFenceHTTP(_ProbeHTTP):
    OTHER_PR = 999

    def __init__(
        self,
        *,
        initial_other_path: str | None = None,
        final_other_path: str | None = None,
        final_incomplete: bool = False,
    ) -> None:
        super().__init__()
        self.initial_other_path = initial_other_path
        self.final_other_path = final_other_path
        self.final_incomplete = final_incomplete
        self.census_reads = 0

    def __call__(self, url: str, *, token: str, timeout: float):
        assert url.startswith(API_ROOT + "/")
        endpoint = url.removeprefix(API_ROOT + "/")
        open_prefix = f"repos/{REPOSITORY}/pulls?state=open&per_page=100&page="
        if endpoint.startswith(open_prefix):
            self.calls.append((url, token, timeout))
            assert token == TOKEN
            page = int(endpoint.removeprefix(open_prefix))
            if page == 1:
                self.census_reads += 1
                if self.final_incomplete and self.census_reads == 2:
                    return [{"number": PR_NUMBER}] + [
                        {"number": 1000 + index} for index in range(99)
                    ]
                selected = (
                    self.initial_other_path
                    if self.census_reads == 1
                    else self.final_other_path
                )
                pulls = [{"number": PR_NUMBER}]
                if selected is not None:
                    pulls.append({"number": self.OTHER_PR})
                return pulls
            if self.final_incomplete and self.census_reads == 2:
                return [{"number": 9999}]
            return []

        other_files = (
            f"repos/{REPOSITORY}/pulls/{self.OTHER_PR}/files?per_page=100&page=1"
        )
        if endpoint == other_files:
            self.calls.append((url, token, timeout))
            assert token == TOKEN
            selected = (
                self.initial_other_path
                if self.census_reads == 1
                else self.final_other_path
            )
            assert selected is not None
            return [{"filename": selected, "status": "modified"}]

        return super().__call__(url, token=token, timeout=timeout)


def test_cli_refuses_if_collision_census_changes_while_target_identity_stays_fixed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _cli_module()
    http = _CollisionFenceHTTP(
        initial_other_path=None,
        final_other_path=FINAL_OWNED_PATHS[0],
    )

    exit_code = _run_cli(module, _cli_argv(), http=http)
    captured = capsys.readouterr()
    assert exit_code == 1
    payload = json.loads(captured.out)
    assert payload["code"] == "REMOTE_PROOF_CHANGED"
    assert payload["schema"] == "mastermind.source_continuity_refusal/v1"
    assert http.pr_reads == 2
    assert http.census_reads == 2


def test_cli_refuses_incomplete_final_collision_census_without_a_receipt(
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _cli_module()
    http = _CollisionFenceHTTP(final_incomplete=True)

    exit_code = _run_cli(module, _cli_argv(), http=http)
    captured = capsys.readouterr()
    assert exit_code == 2
    payload = json.loads(captured.out)
    assert payload["code"] == "REMOTE_CENSUS_INCOMPLETE"
    assert payload["schema"] == "mastermind.source_continuity_refusal/v1"
    assert http.census_reads == 2


@pytest.mark.parametrize(
    ("other_path", "expected_state", "expected_numbers"),
    [
        ("docs/unrelated.md", "DISJOINT", []),
        (FINAL_OWNED_PATHS[0], "OVERLAP", [_CollisionFenceHTTP.OTHER_PR]),
    ],
)
def test_cli_repeats_stable_collision_census_deterministically(
    other_path: str,
    expected_state: str,
    expected_numbers: list[int],
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _cli_module()
    http = _CollisionFenceHTTP(
        initial_other_path=other_path,
        final_other_path=other_path,
    )

    exit_code = _run_cli(module, _cli_argv(), http=http)
    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["collision_state"] == expected_state
    assert payload["colliding_pr_numbers"] == expected_numbers
    assert http.census_reads == 2

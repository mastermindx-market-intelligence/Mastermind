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
BLOB_A = "a" * 40
BLOB_B = "b" * 40
EFFECT_FINGERPRINT = "c" * 64
VERIFIED_AT = "2026-09-03T05:00:00Z"
OPERATION = "agent-dialogue-source-continuity-rchp0-rch1-20260903-sol-001"
REPOSITORY = "mastermindx-market-intelligence/Mastermind"
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


def _request(module, *, kind=None, owned_paths=OWNED_PATHS):
    return module.SourceContinuityRequest(
        receipt_kind=kind or module.ReceiptKind.CHECKPOINT_VERIFIED,
        operation_key=OPERATION,
        repository=REPOSITORY,
        pr_number=346,
        branch=BRANCH,
        base_ref="master",
        pinned_base_sha=BASE_SHA,
        owned_paths=tuple(owned_paths),
        verified_at=VERIFIED_AT,
    )


def _entries(module, *, first_mode="100644", first_size=123):
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
            object_type="blob",
            object_sha=BLOB_A,
            size=first_size,
        ),
    )


def _remote(module, **overrides):
    values = dict(
        repository=REPOSITORY,
        pr_number=346,
        branch=BRANCH,
        base_ref="master",
        pr_open=True,
        pr_draft_or_hold=True,
        head_sha=HEAD_SHA,
        tree_sha=TREE_SHA,
        merge_base_sha=BASE_SHA,
        current_base_head_sha=BASE_SHA,
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


def test_checkpoint_binds_source_evidence_without_granting_authority() -> None:
    module = _contract()
    result = _verify(module)

    assert isinstance(result, module.SourceContinuityReceipt)
    payload = result.to_dict()
    assert payload["schema"] == "mastermind.source_continuity_receipt/v1"
    assert payload["receipt_version"] == "v1"
    assert payload["receipt_kind"] == "CHECKPOINT_VERIFIED"
    assert payload["changed_paths"] == sorted(OWNED_PATHS)
    assert payload["authority_effect"] == "NONE"
    assert payload["writer_release_authorized"] is False
    assert payload["merge_authorized"] is False
    assert payload["receiver_transfer_authorized"] is False
    assert payload["local_equals_remote"] is False
    assert payload["unpushed_commit_count"] == 1
    assert payload["uncommitted_in_scope_count"] == 1
    assert payload["untracked_in_scope_count"] == 1
    assert len(payload["owned_path_digest"]) == 64
    assert len(payload["receipt_digest"]) == 64


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


@pytest.mark.parametrize(
    ("remote_changes", "code"),
    [
        ({"repository": "wrong/repo"}, "REMOTE_IDENTITY_MISMATCH"),
        ({"pr_number": 347}, "REMOTE_IDENTITY_MISMATCH"),
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
    ("entries", "code"),
    [
        ({"first_mode": "120000"}, "UNSAFE_REMOTE_OBJECT"),
        ({"first_mode": "160000"}, "UNSAFE_REMOTE_OBJECT"),
        ({"first_size": 10_000_001}, "REMOTE_BLOB_TOO_LARGE"),
    ],
)
def test_remote_path_policy_rejects_symlink_submodule_and_large_blob(
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


def test_effect_and_collision_rules_preserve_external_and_sol_authority() -> None:
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
    assert separable.writer_release_authorized is False

    for external, code in (
        (
            _external(
                module,
                state=module.ExternalEffectState.EFFECT_UNKNOWN,
                branch_dependency=module.BranchEffectDependency.UNKNOWN,
            ),
            "EXTERNAL_EFFECT_UNKNOWN",
        ),
        (
            _external(
                module,
                state=module.ExternalEffectState.OPEN_KNOWN_EFFECT,
                branch_dependency=module.BranchEffectDependency.REQUIRED,
            ),
            "BRANCH_EFFECT_REQUIRED",
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

    _assert_refusal(
        module,
        _verify(
            module,
            remote=_remote(module, collision_state=module.CollisionState.INCOMPLETE),
        ),
        "REMOTE_CENSUS_INCOMPLETE",
        exit_code=2,
    )
    overlap = _verify(
        module,
        remote=_remote(
            module,
            collision_state=module.CollisionState.OVERLAP,
            colliding_pr_numbers=(404, 147, 404),
        ),
    )
    assert isinstance(overlap, module.SourceContinuityReceipt)
    assert overlap.colliding_pr_numbers == (147, 404)
    assert overlap.writer_release_authorized is False


def test_receipt_digest_changes_after_remote_or_effect_identity_moves() -> None:
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

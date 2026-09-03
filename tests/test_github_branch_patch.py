from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path

import pytest

from control_plane.github_branch_patch import (
    INPUT_SCHEMA,
    PUBLIC_RECEIPT_SCHEMA,
    BranchPatchError,
    BranchPatchInput,
    BranchPatchIssue,
    apply_strict_unified_patch,
    git_blob_sha,
)


HEAD = "a" * 40
PATH = "control_plane/large_existing_source.py"


def _input(source: bytes, patch: str, **overrides: object) -> BranchPatchInput:
    values: dict[str, object] = {
        "schema": INPUT_SCHEMA,
        "operation_key": "mastermind-scf-ghp1-test-op",
        "repository": "mastermindx-market-intelligence/Mastermind",
        "branch": "sol/scf-ghp1-test",
        "path": PATH,
        "expected_head_sha": HEAD,
        "expected_blob_sha": git_blob_sha(source),
        "source_bytes": source,
        "patch": patch,
    }
    values.update(overrides)
    return BranchPatchInput(**values)


def _large_source(line_count: int = 12_050) -> bytes:
    return "".join(f"value_{number:05d} = {number}\n" for number in range(1, line_count + 1)).encode()


def _replace_patch(line_number: int, old: str, new: str) -> str:
    return (
        f"--- a/{PATH}\n"
        f"+++ b/{PATH}\n"
        f"@@ -{line_number},1 +{line_number},1 @@\n"
        f"-{old}\n"
        f"+{new}\n"
    )


def _assert_issue(value: BranchPatchInput, issue: BranchPatchIssue) -> None:
    with pytest.raises(BranchPatchError) as caught:
        apply_strict_unified_patch(value)
    assert caught.value.issue is issue
    assert str(caught.value) == issue.value


def test_materializes_tiny_patch_against_12050_line_source_without_full_file_in_receipt() -> None:
    source = _large_source()
    patch = _replace_patch(10_000, "value_10000 = 10000", "value_10000 = 10001")

    first = apply_strict_unified_patch(_input(source, patch))
    second = apply_strict_unified_patch(_input(source, patch))

    assert first == second
    assert first.materialized_bytes.count(b"\n") == 12_050
    assert b"value_10000 = 10001\n" in first.materialized_bytes
    assert b"value_10000 = 10000\n" not in first.materialized_bytes
    assert first.hunk_count == 1
    assert first.added_line_count == 1
    assert first.removed_line_count == 1
    receipt = first.public_receipt()
    assert receipt["schema"] == PUBLIC_RECEIPT_SCHEMA
    assert "materialized_bytes" not in receipt
    assert "value_10000" not in repr(receipt)


def test_stale_expected_blob_refuses_before_patch_application() -> None:
    source = _large_source(3)
    patch = _replace_patch(2, "value_00002 = 2", "value_00002 = 3")
    value = _input(source, patch, expected_blob_sha="b" * 40)
    _assert_issue(value, BranchPatchIssue.SOURCE_BLOB_MISMATCH)


def test_wrong_patch_path_is_a_typed_refusal() -> None:
    source = b"alpha\nbeta\n"
    patch = "--- a/other.py\n+++ b/other.py\n@@ -2,1 +2,1 @@\n-beta\n+gamma\n"
    _assert_issue(_input(source, patch), BranchPatchIssue.PATH_MISMATCH)


def test_hunk_cannot_float_to_matching_content_at_another_offset() -> None:
    source = b"zero\nalpha\nbeta\nalpha\nbeta\n"
    patch = f"--- a/{PATH}\n+++ b/{PATH}\n@@ -1,2 +1,2 @@\n alpha\n-beta\n+gamma\n"
    _assert_issue(_input(source, patch), BranchPatchIssue.HUNK_CONTEXT_MISMATCH)


def test_hunks_must_be_sorted_and_nonoverlapping() -> None:
    source = b"a\nb\nc\nd\n"
    patch = (
        f"--- a/{PATH}\n+++ b/{PATH}\n"
        "@@ -3,1 +3,1 @@\n-c\n+C\n"
        "@@ -2,1 +2,1 @@\n-b\n+B\n"
    )
    _assert_issue(_input(source, patch), BranchPatchIssue.HUNK_ORDER_INVALID)


def test_declared_hunk_counts_and_new_coordinates_are_checked() -> None:
    source = b"a\nb\nc\n"
    count_mismatch = f"--- a/{PATH}\n+++ b/{PATH}\n@@ -2,2 +2,1 @@\n-b\n+B\n"
    _assert_issue(_input(source, count_mismatch), BranchPatchIssue.HUNK_RANGE_INVALID)

    coordinate_mismatch = f"--- a/{PATH}\n+++ b/{PATH}\n@@ -2,1 +3,1 @@\n-b\n+B\n"
    _assert_issue(_input(source, coordinate_mismatch), BranchPatchIssue.HUNK_RANGE_INVALID)


def test_insertions_at_start_and_end_use_exact_zero_length_ranges() -> None:
    source = b"a\nb\n"
    start_patch = f"--- a/{PATH}\n+++ b/{PATH}\n@@ -0,0 +1,1 @@\n+start\n"
    start = apply_strict_unified_patch(_input(source, start_patch))
    assert start.materialized_bytes == b"start\na\nb\n"

    end_patch = f"--- a/{PATH}\n+++ b/{PATH}\n@@ -2,0 +3,1 @@\n+end\n"
    end = apply_strict_unified_patch(_input(source, end_patch))
    assert end.materialized_bytes == b"a\nb\nend\n"


def test_crlf_binary_and_missing_final_newline_are_explicitly_unsupported_in_v1() -> None:
    patch = f"--- a/{PATH}\n+++ b/{PATH}\n@@ -1,1 +1,1 @@\n-a\n+b\n"
    for source in (b"a\r\n", b"a\x00\n", b"a"):
        _assert_issue(_input(source, patch), BranchPatchIssue.SOURCE_FORMAT_UNSUPPORTED)


def test_patch_metadata_renames_deletes_and_no_newline_marker_are_not_accepted() -> None:
    source = b"a\n"
    samples = (
        f"diff --git a/{PATH} b/{PATH}\n--- a/{PATH}\n+++ b/{PATH}\n@@ -1 +1 @@\n-a\n+b\n",
        f"--- a/{PATH}\n+++ /dev/null\n@@ -1 +0,0 @@\n-a\n",
        f"--- a/{PATH}\n+++ b/{PATH}\n@@ -1 +1 @@\n-a\n+b\n\\ No newline at end of file\n",
    )
    for patch in samples:
        with pytest.raises(BranchPatchError) as caught:
            apply_strict_unified_patch(_input(source, patch))
        assert caught.value.issue in {
            BranchPatchIssue.PATCH_FORMAT_INVALID,
            BranchPatchIssue.PATH_MISMATCH,
        }


def test_high_confidence_secret_shaped_addition_is_refused_without_echo() -> None:
    source = b"token = None\n"
    secret = "github_pat_1234567890abcdefghijklmnop"
    patch = _replace_patch(1, "token = None", f'token = "{secret}"')
    with pytest.raises(BranchPatchError) as caught:
        apply_strict_unified_patch(_input(source, patch))
    assert caught.value.issue is BranchPatchIssue.SECRET_SHAPED_ADDITION
    assert secret not in str(caught.value)


def test_noop_patch_is_refused() -> None:
    source = b"a\n"
    patch = _replace_patch(1, "a", "a")
    _assert_issue(_input(source, patch), BranchPatchIssue.NO_CHANGE)


def test_invalid_repository_branch_path_and_schema_fail_closed() -> None:
    source = b"a\n"
    patch = _replace_patch(1, "a", "b")
    base = _input(source, patch)
    cases = (
        (replace(base, schema="other"), BranchPatchIssue.INPUT_SCHEMA_INVALID),
        (replace(base, repository="not-a-repository"), BranchPatchIssue.INPUT_INVALID),
        (replace(base, branch="refs/heads/main"), BranchPatchIssue.INPUT_INVALID),
        (replace(base, path="../escape.py"), BranchPatchIssue.PATH_INVALID),
    )
    for value, issue in cases:
        _assert_issue(value, issue)


def test_module_is_pure_and_has_no_transport_or_runtime_imports() -> None:
    path = Path(__file__).parents[1] / "control_plane" / "github_branch_patch.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported.intersection(
        {
            "asyncio",
            "datetime",
            "httpx",
            "mcp",
            "os",
            "random",
            "requests",
            "socket",
            "subprocess",
            "time",
            "urllib",
        }
    ) == set()
    assert "pathlib" in imported

from __future__ import annotations

import ast
import dataclasses
import hashlib
import importlib
import json
from pathlib import Path

import pytest

from control_plane.github_branch_patch import (
    INPUT_SCHEMA,
    OUTPUT_SCHEMA,
    MAX_CHANGED_LINES,
    BranchPatchError,
    BranchPatchErrorCode,
    BranchPatchInput,
    apply_branch_patch,
    branch_patch_input_from_mapping,
)


HEAD = "a" * 40
BLOB = "b" * 40
PATH = "control_plane/large_existing_source.py"
BRANCH = "sol/ghp1-fixture"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _source(size: int = 12050) -> str:
    return "".join(f"line_{number:05d} = {number}\n" for number in range(1, size + 1))


def _input(
    *,
    source: str | None = None,
    patch: str | None = None,
    **overrides: object,
) -> BranchPatchInput:
    source = source if source is not None else _source()
    patch = patch if patch is not None else (
        f"diff --git a/{PATH} b/{PATH}\n"
        "index 1111111..2222222 100644\n"
        f"--- a/{PATH}\n"
        f"+++ b/{PATH}\n"
        "@@ -4999,3 +4999,4 @@\n"
        " line_04999 = 4999\n"
        "-line_05000 = 5000\n"
        "+line_05000 = 500000\n"
        "+line_05000_note = 'patched'\n"
        " line_05001 = 5001\n"
        "@@ -11000,2 +11001,2 @@\n"
        " line_11000 = 11000\n"
        "-line_11001 = 11001\n"
        "+line_11001 = 110010\n"
    )
    values: dict[str, object] = {
        "schema": INPUT_SCHEMA,
        "operation_key": "scf-ghp1-test-001",
        "repository": "mastermindx-market-intelligence/Mastermind",
        "target_branch": BRANCH,
        "expected_head_sha": HEAD,
        "target_path": PATH,
        "expected_blob_oid": BLOB,
        "expected_source_sha256": _sha256(source),
        "source_text": source,
        "unified_diff": patch,
        "allowed_paths": (PATH,),
        "protected_branches": ("master",),
    }
    values.update(overrides)
    return BranchPatchInput(**values)


def _refusal(code: BranchPatchErrorCode, **overrides: object) -> BranchPatchError:
    with pytest.raises(BranchPatchError) as caught:
        apply_branch_patch(_input(**overrides))
    assert caught.value.code is code
    return caught.value


def test_large_file_two_hunk_patch_is_exact_and_preview_is_content_free() -> None:
    packet = _input()
    result = apply_branch_patch(packet)
    assert result.schema == OUTPUT_SCHEMA
    assert result.hunk_count == 2
    assert result.additions == 3
    assert result.deletions == 2
    assert result.changed_lines == 5
    assert "line_05000 = 500000\n" in result.result_text
    assert "line_05000_note = 'patched'\n" in result.result_text
    assert "line_11001 = 110010\n" in result.result_text
    assert "line_05000 = 5000\n" not in result.result_text
    assert result.source_sha256 == _sha256(packet.source_text)
    assert result.result_sha256 == _sha256(result.result_text)
    preview = result.preview()
    assert preview["canonical_digest"] == result.canonical_digest
    rendered = json.dumps(preview, sort_keys=True)
    assert "source_text" not in rendered
    assert "result_text" not in rendered
    assert "500000" not in rendered
    assert len(result.result_text.splitlines()) == 12051


def test_same_input_and_permuted_authority_lists_have_same_digest() -> None:
    first = apply_branch_patch(
        _input(
            allowed_paths=(PATH, "tests/test_large_existing_source.py"),
            protected_branches=("release", "master"),
        )
    )
    second = apply_branch_patch(
        _input(
            allowed_paths=("tests/test_large_existing_source.py", PATH),
            protected_branches=("master", "release"),
        )
    )
    assert first.preview() == second.preview()
    assert first.canonical_digest == second.canonical_digest


def test_closed_mapping_rejects_unknown_or_missing_privileged_fields() -> None:
    raw = dataclasses.asdict(_input())
    raw["credential"] = "not-accepted"
    with pytest.raises(BranchPatchError) as caught:
        branch_patch_input_from_mapping(raw)
    assert caught.value.code is BranchPatchErrorCode.INPUT_SCHEMA_INVALID
    raw = dataclasses.asdict(_input())
    del raw["expected_head_sha"]
    with pytest.raises(BranchPatchError) as caught:
        branch_patch_input_from_mapping(raw)
    assert caught.value.code is BranchPatchErrorCode.INPUT_SCHEMA_INVALID


def test_wrong_schema_and_invalid_identity_are_refused() -> None:
    _refusal(BranchPatchErrorCode.INPUT_SCHEMA_INVALID, schema="other")
    _refusal(BranchPatchErrorCode.IDENTITY_INVALID, target_branch="../master")
    _refusal(BranchPatchErrorCode.IDENTITY_INVALID, expected_head_sha="not-a-sha")


def test_path_must_be_safe_exact_and_owner_allowed() -> None:
    _refusal(BranchPatchErrorCode.PATH_INVALID, target_path="../escape.py")
    _refusal(
        BranchPatchErrorCode.PATH_NOT_ALLOWED,
        allowed_paths=("tests/other.py",),
    )
    wrong = _input().unified_diff.replace(PATH, "control_plane/other.py")
    _refusal(BranchPatchErrorCode.MULTI_FILE_PATCH_REFUSED, patch=wrong)


def test_protected_branch_is_refused_before_patch_materialization() -> None:
    _refusal(
        BranchPatchErrorCode.PROTECTED_BRANCH_REFUSED,
        target_branch="master",
    )


def test_source_digest_must_match_exact_bytes() -> None:
    _refusal(
        BranchPatchErrorCode.SOURCE_DIGEST_MISMATCH,
        expected_source_sha256="0" * 64,
    )


def test_cr_nul_and_missing_final_newline_are_refused() -> None:
    source = _source().replace("\n", "\r\n", 1)
    packet = _input(source=source, expected_source_sha256=_sha256(source))
    with pytest.raises(BranchPatchError) as caught:
        apply_branch_patch(packet)
    assert caught.value.code is BranchPatchErrorCode.SOURCE_ENCODING_REFUSED
    source = _source() + "\x00"
    packet = _input(source=source, expected_source_sha256=_sha256(source))
    with pytest.raises(BranchPatchError) as caught:
        apply_branch_patch(packet)
    assert caught.value.code is BranchPatchErrorCode.SOURCE_ENCODING_REFUSED
    source = _source().removesuffix("\n")
    packet = _input(source=source, expected_source_sha256=_sha256(source))
    with pytest.raises(BranchPatchError) as caught:
        apply_branch_patch(packet)
    assert caught.value.code is BranchPatchErrorCode.NO_FINAL_NEWLINE_REFUSED


def test_context_mismatch_never_fuzzes_to_duplicate_text_elsewhere() -> None:
    source = "alpha\nneedle\nomega\nalpha\nneedle\nomega\n"
    patch = (
        f"--- a/{PATH}\n"
        f"+++ b/{PATH}\n"
        "@@ -2,2 +2,2 @@\n"
        "-needle-moved\n"
        "+replacement\n"
        " omega\n"
    )
    packet = _input(source=source, patch=patch)
    with pytest.raises(BranchPatchError) as caught:
        apply_branch_patch(packet)
    assert caught.value.code is BranchPatchErrorCode.CONTEXT_MISMATCH


def test_hunk_old_and_new_positions_must_both_be_consistent() -> None:
    source = "one\ntwo\nthree\n"
    old_position = (
        f"--- a/{PATH}\n"
        f"+++ b/{PATH}\n"
        "@@ -9,1 +9,1 @@\n"
        "-two\n"
        "+TWO\n"
    )
    packet = _input(source=source, patch=old_position)
    with pytest.raises(BranchPatchError) as caught:
        apply_branch_patch(packet)
    assert caught.value.code is BranchPatchErrorCode.HUNK_ORDER_REFUSED
    new_position = (
        f"--- a/{PATH}\n"
        f"+++ b/{PATH}\n"
        "@@ -2,1 +3,1 @@\n"
        "-two\n"
        "+TWO\n"
    )
    packet = _input(source=source, patch=new_position)
    with pytest.raises(BranchPatchError) as caught:
        apply_branch_patch(packet)
    assert caught.value.code is BranchPatchErrorCode.HUNK_ORDER_REFUSED


def test_hunk_counts_must_equal_body_counts() -> None:
    source = "one\ntwo\nthree\n"
    patch = (
        f"--- a/{PATH}\n"
        f"+++ b/{PATH}\n"
        "@@ -2,2 +2,1 @@\n"
        "-two\n"
        "+TWO\n"
    )
    packet = _input(source=source, patch=patch)
    with pytest.raises(BranchPatchError) as caught:
        apply_branch_patch(packet)
    assert caught.value.code is BranchPatchErrorCode.HUNK_COUNT_MISMATCH


def test_multiple_files_and_nonordinary_file_operations_are_refused() -> None:
    normal = _input().unified_diff
    multi = normal + (
        "diff --git a/tests/other.py b/tests/other.py\n"
        "--- a/tests/other.py\n"
        "+++ b/tests/other.py\n"
        "@@ -1,1 +1,1 @@\n"
        "-old\n"
        "+new\n"
    )
    _refusal(BranchPatchErrorCode.MULTI_FILE_PATCH_REFUSED, patch=multi)
    new_file = (
        f"diff --git a/{PATH} b/{PATH}\n"
        "new file mode 100644\n"
        "--- /dev/null\n"
        f"+++ b/{PATH}\n"
        "@@ -0,0 +1,1 @@\n"
        "+new\n"
    )
    _refusal(BranchPatchErrorCode.FILE_OPERATION_REFUSED, patch=new_file)
    binary = (
        f"diff --git a/{PATH} b/{PATH}\n"
        "GIT binary patch\n"
        "literal 1\n"
    )
    _refusal(BranchPatchErrorCode.FILE_OPERATION_REFUSED, patch=binary)


def test_no_newline_markers_and_zero_effect_patch_are_refused() -> None:
    source = "one\ntwo\n"
    marker = (
        f"--- a/{PATH}\n"
        f"+++ b/{PATH}\n"
        "@@ -2,1 +2,1 @@\n"
        "-two\n"
        "\\ No newline at end of file\n"
        "+TWO\n"
    )
    packet = _input(source=source, patch=marker)
    with pytest.raises(BranchPatchError) as caught:
        apply_branch_patch(packet)
    assert caught.value.code is BranchPatchErrorCode.NO_FINAL_NEWLINE_REFUSED
    zero = (
        f"--- a/{PATH}\n"
        f"+++ b/{PATH}\n"
        "@@ -2,1 +2,1 @@\n"
        " two\n"
    )
    packet = _input(source=source, patch=zero)
    with pytest.raises(BranchPatchError) as caught:
        apply_branch_patch(packet)
    assert caught.value.code is BranchPatchErrorCode.PATCH_FORMAT_REFUSED


def test_changed_line_ceiling_is_enforced() -> None:
    count = MAX_CHANGED_LINES // 2 + 1
    source = "".join(f"old-{number}\n" for number in range(count))
    body = "".join(f"-old-{number}\n" for number in range(count)) + "".join(
        f"+new-{number}\n" for number in range(count)
    )
    patch = (
        f"--- a/{PATH}\n"
        f"+++ b/{PATH}\n"
        f"@@ -1,{count} +1,{count} @@\n"
        f"{body}"
    )
    packet = _input(source=source, patch=patch)
    with pytest.raises(BranchPatchError) as caught:
        apply_branch_patch(packet)
    assert caught.value.code is BranchPatchErrorCode.CHANGED_LINE_LIMIT_EXCEEDED


def test_direct_dataclass_construction_does_not_bypass_closed_validation() -> None:
    unsafe = dataclasses.replace(_input(), allowed_paths=(PATH, PATH))
    with pytest.raises(BranchPatchError) as caught:
        apply_branch_patch(unsafe)
    assert caught.value.code is BranchPatchErrorCode.INPUT_SCHEMA_INVALID


def test_source_lines_resembling_file_headers_are_valid_hunk_payload() -> None:
    source = "before\n-- old-header-looking-line\nafter\n"
    patch = (
        f"--- a/{PATH}\n"
        f"+++ b/{PATH}\n"
        "@@ -2,1 +2,1 @@\n"
        "--- old-header-looking-line\n"
        "+++ new-header-looking-line\n"
    )
    result = apply_branch_patch(_input(source=source, patch=patch))
    assert result.result_text == "before\n++ new-header-looking-line\nafter\n"


def test_unbounded_hunk_integer_is_refused_as_format_not_runtime_error() -> None:
    source = "one\n"
    huge = "9" * 100
    patch = (
        f"--- a/{PATH}\n"
        f"+++ b/{PATH}\n"
        f"@@ -{huge},1 +1,1 @@\n"
        "-one\n"
        "+ONE\n"
    )
    packet = _input(source=source, patch=patch)
    with pytest.raises(BranchPatchError) as caught:
        apply_branch_patch(packet)
    assert caught.value.code is BranchPatchErrorCode.PATCH_FORMAT_REFUSED


def test_module_is_pure_and_does_not_import_effectful_surfaces() -> None:
    module = importlib.import_module("control_plane.github_branch_patch")
    path = Path(module.__file__ or "")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    assert imports.isdisjoint(
        {
            "asyncio",
            "datetime",
            "fastapi",
            "httpx",
            "integrations",
            "mcp",
            "os",
            "pathlib",
            "random",
            "requests",
            "socket",
            "subprocess",
            "time",
            "urllib",
        }
    )

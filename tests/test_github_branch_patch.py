from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path

import pytest

from control_plane.github_branch_patch import (
    INPUT_SCHEMA,
    MAX_CHANGED_LINES_PER_FILE,
    BranchPatchError,
    BranchPatchInput,
    MaterializedFile,
    PatchErrorCode,
    PatchFileIntent,
    git_blob_oid,
    prepare_branch_patch,
)


HEAD = "a" * 40
REPOSITORY = "mastermindx-market-intelligence/Mastermind"
BRANCH = "sol/ghp1-test"
PATH = "control_plane/large_fixture.py"


def _source(lines: int = 12_050) -> str:
    return "".join(f"line-{index:05d}\n" for index in range(1, lines + 1))


def _materialized(path: str, content: str) -> MaterializedFile:
    return MaterializedFile(
        path=path,
        observed_blob_oid=git_blob_oid(content),
        content=content,
    )


def _intent(path: str = PATH, *, blob: str, patch: str) -> PatchFileIntent:
    return PatchFileIntent(path=path, expected_blob_oid=blob, unified_diff=patch)


def _request(*files: PatchFileIntent, branch: str = BRANCH) -> BranchPatchInput:
    return BranchPatchInput(
        schema=INPUT_SCHEMA,
        operation_key="mastermind-scf-ghp1-test-op",
        repository=REPOSITORY,
        branch=branch,
        expected_head_oid=HEAD,
        files=tuple(files),
    )


def _prepare(
    content: str,
    patch: str,
    *,
    path: str = PATH,
    request_overrides: dict[str, object] | None = None,
):
    materialized = _materialized(path, content)
    request = _request(_intent(path, blob=materialized.observed_blob_oid, patch=patch))
    if request_overrides:
        request = replace(request, **request_overrides)
    return prepare_branch_patch(
        request,
        {path: materialized},
        allowed_paths=(path,),
        protected_branches=("master", "main"),
    )


def _error(code: PatchErrorCode, callable_) -> None:
    with pytest.raises(BranchPatchError) as caught:
        callable_()
    assert caught.value.code is code
    assert str(caught.value) == code.value


def test_large_file_interior_patch_is_exact_and_does_not_reconstruct_client_side() -> None:
    content = _source()
    patch = (
        f"--- a/{PATH}\n"
        f"+++ b/{PATH}\n"
        "@@ -6000,3 +6000,4 @@\n"
        " line-06000\n"
        "-line-06001\n"
        "+line-06001-repaired\n"
        "+line-06001-proof\n"
        " line-06002\n"
    )
    result = _prepare(content, patch)

    assert result.total_additions == 2
    assert result.total_deletions == 1
    assert len(result.files) == 1
    prepared = result.files[0]
    assert prepared.hunk_count == 1
    assert prepared.result_content.startswith("line-00001\nline-00002\n")
    assert prepared.result_content.endswith("line-12049\nline-12050\n")
    assert "line-06001-repaired\nline-06001-proof\n" in prepared.result_content
    assert prepared.before_sha256 != prepared.after_sha256
    assert prepared.before_bytes == len(content.encode("utf-8"))
    assert prepared.after_bytes == len(prepared.result_content.encode("utf-8"))


def test_public_receipt_omits_full_result_and_source_content() -> None:
    content = "alpha\nbeta\ngamma\n"
    patch = (
        f"--- a/{PATH}\n+++ b/{PATH}\n"
        "@@ -1,3 +1,3 @@\n alpha\n-beta\n+repaired\n gamma\n"
    )
    result = _prepare(content, patch)
    public = result.public_dict()
    rendered = repr(public)
    assert "result_content" not in rendered
    assert content not in rendered
    assert "repaired" not in rendered
    assert public["normalized_effect_digest"] == result.normalized_effect_digest


def test_same_semantics_are_order_stable_across_file_order() -> None:
    first_path = "control_plane/a.py"
    second_path = "control_plane/b.py"
    first_content = "a1\na2\na3\n"
    second_content = "b1\nb2\nb3\n"
    first = _materialized(first_path, first_content)
    second = _materialized(second_path, second_content)
    first_intent = _intent(
        first_path,
        blob=first.observed_blob_oid,
        patch=(
            f"--- a/{first_path}\n+++ b/{first_path}\n"
            "@@ -1,3 +1,3 @@\n a1\n-a2\n+a2x\n a3\n"
        ),
    )
    second_intent = _intent(
        second_path,
        blob=second.observed_blob_oid,
        patch=(
            f"--- a/{second_path}\n+++ b/{second_path}\n"
            "@@ -1,3 +1,3 @@\n b1\n-b2\n+b2x\n b3\n"
        ),
    )
    materialized = {first_path: first, second_path: second}
    kwargs = {
        "allowed_paths": (first_path, second_path),
        "protected_branches": ("master", "main"),
    }
    left = prepare_branch_patch(_request(first_intent, second_intent), materialized, **kwargs)
    right = prepare_branch_patch(_request(second_intent, first_intent), materialized, **kwargs)
    assert left.public_dict() == right.public_dict()
    assert left.normalized_effect_digest == right.normalized_effect_digest
    assert [row.path for row in left.files] == [first_path, second_path]


def test_protected_branch_is_refused_even_with_valid_patch() -> None:
    content = "a\nb\nc\n"
    materialized = _materialized(PATH, content)
    patch = f"--- a/{PATH}\n+++ b/{PATH}\n@@ -1,3 +1,3 @@\n a\n-b\n+x\n c\n"
    request = _request(
        _intent(blob=materialized.observed_blob_oid, patch=patch),
        branch="master",
    )
    _error(
        PatchErrorCode.PROTECTED_BRANCH_REFUSED,
        lambda: prepare_branch_patch(
            request,
            {PATH: materialized},
            allowed_paths=(PATH,),
            protected_branches=("master", "main"),
        ),
    )


def test_path_must_be_exactly_owner_allowed() -> None:
    content = "a\nb\nc\n"
    materialized = _materialized(PATH, content)
    patch = f"--- a/{PATH}\n+++ b/{PATH}\n@@ -1,3 +1,3 @@\n a\n-b\n+x\n c\n"
    request = _request(_intent(blob=materialized.observed_blob_oid, patch=patch))
    _error(
        PatchErrorCode.PATH_NOT_OWNED,
        lambda: prepare_branch_patch(
            request,
            {PATH: materialized},
            allowed_paths=("control_plane/other.py",),
        ),
    )


@pytest.mark.parametrize(
    "path",
    (
        "../escape.py",
        "/absolute.py",
        "control_plane\\escape.py",
        "control_plane//escape.py",
        ".git/config",
        "control_plane/../escape.py",
        "control_plane/bad\tpath.py",
    ),
)
def test_unsafe_paths_are_refused(path: str) -> None:
    content = "a\nb\nc\n"
    materialized = _materialized(path, content)
    patch = f"--- a/{path}\n+++ b/{path}\n@@ -1,3 +1,3 @@\n a\n-b\n+x\n c\n"
    request = _request(_intent(path, blob=materialized.observed_blob_oid, patch=patch))
    _error(
        PatchErrorCode.PATH_INVALID,
        lambda: prepare_branch_patch(request, {path: materialized}, allowed_paths=(path,)),
    )


def test_stale_or_inconsistent_blob_identity_is_refused() -> None:
    content = "a\nb\nc\n"
    materialized = _materialized(PATH, content)
    patch = f"--- a/{PATH}\n+++ b/{PATH}\n@@ -1,3 +1,3 @@\n a\n-b\n+x\n c\n"
    request = _request(_intent(blob="b" * 40, patch=patch))
    _error(
        PatchErrorCode.BLOB_OID_MISMATCH,
        lambda: prepare_branch_patch(
            request,
            {PATH: materialized},
            allowed_paths=(PATH,),
        ),
    )

    forged = replace(materialized, content="a\nchanged\nc\n")
    valid_request = _request(_intent(blob=materialized.observed_blob_oid, patch=patch))
    _error(
        PatchErrorCode.BLOB_OID_MISMATCH,
        lambda: prepare_branch_patch(valid_request, {PATH: forged}, allowed_paths=(PATH,)),
    )


def test_exact_context_mismatch_and_line_offset_never_fuzz_apply() -> None:
    content = "zero\none\ntwo\nthree\nfour\n"
    bad_context = (
        f"--- a/{PATH}\n+++ b/{PATH}\n"
        "@@ -2,3 +2,3 @@\n one\n-WRONG\n+repaired\n three\n"
    )
    _error(PatchErrorCode.HUNK_CONTEXT_MISMATCH, lambda: _prepare(content, bad_context))

    wrong_position = (
        f"--- a/{PATH}\n+++ b/{PATH}\n"
        "@@ -1,3 +1,3 @@\n one\n-two\n+repaired\n three\n"
    )
    _error(PatchErrorCode.HUNK_CONTEXT_MISMATCH, lambda: _prepare(content, wrong_position))


def test_hunk_header_counts_and_new_position_are_enforced() -> None:
    content = "a\nb\nc\nd\n"
    count_mismatch = (
        f"--- a/{PATH}\n+++ b/{PATH}\n"
        "@@ -1,4 +1,4 @@\n a\n-b\n+x\n c\n"
    )
    _error(PatchErrorCode.HUNK_COUNT_MISMATCH, lambda: _prepare(content, count_mismatch))

    new_position_mismatch = (
        f"--- a/{PATH}\n+++ b/{PATH}\n"
        "@@ -2,2 +3,2 @@\n-b\n+x\n c\n"
    )
    _error(
        PatchErrorCode.HUNK_NEW_POSITION_MISMATCH,
        lambda: _prepare(content, new_position_mismatch),
    )


def test_overlapping_or_out_of_order_hunks_are_refused() -> None:
    content = "a\nb\nc\nd\ne\n"
    patch = (
        f"--- a/{PATH}\n+++ b/{PATH}\n"
        "@@ -2,2 +2,2 @@\n-b\n+B\n c\n"
        "@@ -3,2 +3,2 @@\n-c\n+C\n d\n"
    )
    _error(PatchErrorCode.HUNK_ORDER_INVALID, lambda: _prepare(content, patch))


def test_pure_insertion_without_old_anchor_is_refused() -> None:
    content = "a\nb\n"
    patch = (
        f"--- a/{PATH}\n+++ b/{PATH}\n"
        "@@ -1,0 +2,1 @@\n+inserted\n"
    )
    _error(PatchErrorCode.HUNK_ANCHOR_REQUIRED, lambda: _prepare(content, patch))


def test_noop_patch_is_refused() -> None:
    content = "a\nb\nc\n"
    patch = (
        f"--- a/{PATH}\n+++ b/{PATH}\n"
        "@@ -1,3 +1,3 @@\n a\n b\n c\n"
    )
    _error(PatchErrorCode.NO_EFFECT, lambda: _prepare(content, patch))


@pytest.mark.parametrize(
    ("content", "patch", "code"),
    (
        ("a\r\nb\r\n", None, PatchErrorCode.SOURCE_CRLF_REFUSED),
        ("a\nb", None, PatchErrorCode.SOURCE_FINAL_NEWLINE_REQUIRED),
        ("a\0b\n", None, PatchErrorCode.SOURCE_NUL_REFUSED),
        ("a\nb\nc\n", "crlf", PatchErrorCode.PATCH_CRLF_REFUSED),
        ("a\nb\nc\n", "no-final-newline", PatchErrorCode.PATCH_FINAL_NEWLINE_REQUIRED),
        ("a\nb\nc\n", "nul", PatchErrorCode.PATCH_NUL_REFUSED),
    ),
)
def test_ambiguous_text_encodings_are_refused(
    content: str,
    patch: str | None,
    code: PatchErrorCode,
) -> None:
    base = f"--- a/{PATH}\n+++ b/{PATH}\n@@ -1,3 +1,3 @@\n a\n-b\n+x\n c\n"
    if patch == "crlf":
        value = base.replace("\n", "\r\n")
    elif patch == "no-final-newline":
        value = base.rstrip("\n")
    elif patch == "nul":
        value = base.replace("+x", "+x\0")
    else:
        value = base
    _error(code, lambda: _prepare(content, value))


def test_patch_header_must_match_exact_path() -> None:
    content = "a\nb\nc\n"
    patch = "--- a/other.py\n+++ b/other.py\n@@ -1,3 +1,3 @@\n a\n-b\n+x\n c\n"
    _error(PatchErrorCode.PATCH_PATH_MISMATCH, lambda: _prepare(content, patch))


def test_secret_shaped_added_material_is_refused_without_reflecting_it() -> None:
    content = "a\nb\nc\n"
    secret = "github_pat_" + "A" * 50
    patch = (
        f"--- a/{PATH}\n+++ b/{PATH}\n"
        f"@@ -1,3 +1,3 @@\n a\n-b\n+{secret}\n c\n"
    )
    with pytest.raises(BranchPatchError) as caught:
        _prepare(content, patch)
    assert caught.value.code is PatchErrorCode.SECRET_SHAPE_REFUSED
    assert secret not in str(caught.value)


def test_duplicate_paths_and_materialized_set_mismatch_are_refused() -> None:
    content = "a\nb\nc\n"
    materialized = _materialized(PATH, content)
    patch = f"--- a/{PATH}\n+++ b/{PATH}\n@@ -1,3 +1,3 @@\n a\n-b\n+x\n c\n"
    intent = _intent(blob=materialized.observed_blob_oid, patch=patch)
    duplicate = _request(intent, intent)
    _error(
        PatchErrorCode.DUPLICATE_PATH,
        lambda: prepare_branch_patch(duplicate, {PATH: materialized}, allowed_paths=(PATH,)),
    )

    single = _request(intent)
    _error(
        PatchErrorCode.MATERIALIZED_FILE_SET_MISMATCH,
        lambda: prepare_branch_patch(single, {}, allowed_paths=(PATH,)),
    )


def test_changed_line_ceiling_is_fail_closed() -> None:
    count = MAX_CHANGED_LINES_PER_FILE + 1
    content = "".join(f"old-{index}\n" for index in range(count))
    body = "".join(f"-old-{index}\n+new-{index}\n" for index in range(count))
    patch = f"--- a/{PATH}\n+++ b/{PATH}\n@@ -1,{count} +1,{count} @@\n{body}"
    _error(PatchErrorCode.CHANGE_LIMIT_EXCEEDED, lambda: _prepare(content, patch))


def test_input_identity_and_branch_grammar_are_closed() -> None:
    content = "a\nb\nc\n"
    materialized = _materialized(PATH, content)
    patch = f"--- a/{PATH}\n+++ b/{PATH}\n@@ -1,3 +1,3 @@\n a\n-b\n+x\n c\n"
    intent = _intent(blob=materialized.observed_blob_oid, patch=patch)
    base = _request(intent)

    cases = (
        (replace(base, schema="other"), PatchErrorCode.INPUT_SCHEMA_INVALID),
        (replace(base, operation_key="bad operation"), PatchErrorCode.OPERATION_KEY_INVALID),
        (replace(base, repository="not-a-repository"), PatchErrorCode.REPOSITORY_INVALID),
        (replace(base, branch="bad..branch"), PatchErrorCode.BRANCH_INVALID),
        (replace(base, expected_head_oid="not-an-oid"), PatchErrorCode.EXPECTED_HEAD_INVALID),
    )
    for request, code in cases:
        _error(
            code,
            lambda request=request: prepare_branch_patch(
                request,
                {PATH: materialized},
                allowed_paths=(PATH,),
            ),
        )


def test_module_is_pure_and_has_no_io_network_subprocess_or_clock_imports() -> None:
    module_path = Path(__file__).resolve().parents[1] / "control_plane" / "github_branch_patch.py"
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
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
            "httpx",
            "os",
            "pathlib",
            "requests",
            "socket",
            "subprocess",
            "time",
            "urllib",
        }
    )


def test_result_preserves_single_final_newline() -> None:
    content = "a\nb\nc\n"
    patch = f"--- a/{PATH}\n+++ b/{PATH}\n@@ -1,3 +1,3 @@\n a\n-b\n+x\n c\n"
    result = _prepare(content, patch)
    assert result.files[0].result_content == "a\nx\nc\n"
    assert not result.files[0].result_content.endswith("\n\n")

from __future__ import annotations

import ast
import dataclasses
import json
from pathlib import Path

import pytest

from control_plane.github_exact_edit import (
    INPUT_SCHEMA,
    MAX_FILE_BYTES,
    MAX_FILES,
    MAX_REPLACEMENTS_PER_FILE,
    CarrierState,
    ExactEditAuthority,
    ExactEditError,
    ExactEditIssue,
    ExactEditRequest,
    ExactFileEditRequest,
    ExactFileSnapshot,
    ExactTextReplacement,
    PullRequestState,
    WriterState,
    compile_exact_edit,
)


HEAD = "a" * 40
BLOB_A = "b" * 40
BLOB_B = "c" * 40
OPERATION = "mastermind-sol-capability-fabric-ghp1-test"
PATH_A = "control_plane/example.py"
PATH_B = "tests/test_example.py"


def _authority(**overrides: object) -> ExactEditAuthority:
    values: dict[str, object] = {
        "operation_key": OPERATION,
        "carrier_ref": "github:pr:999",
        "source_ref": "github:pr:999:head:a",
        "repository": "mastermindx-market-intelligence/Mastermind",
        "default_branch": "master",
        "branch": "sol/ghp1-test",
        "pull_request_number": 999,
        "pull_request_state": PullRequestState.OPEN,
        "branch_protected": False,
        "carrier_state": CarrierState.EXACT,
        "writer_state": WriterState.EXACT,
        "observed_head_oid": HEAD,
        "allowed_paths": (PATH_A, PATH_B),
        "allowed_paths_complete": True,
    }
    values.update(overrides)
    return ExactEditAuthority(**values)


def _request(
    *,
    path: str = PATH_A,
    blob: str = BLOB_A,
    replacements: tuple[ExactTextReplacement, ...] | None = None,
    **overrides: object,
) -> ExactEditRequest:
    if replacements is None:
        replacements = (ExactTextReplacement("value = 'old'\n", "value = 'new'\n"),)
    values: dict[str, object] = {
        "schema": INPUT_SCHEMA,
        "operation_key": OPERATION,
        "expected_head_oid": HEAD,
        "files": (ExactFileEditRequest(path, blob, replacements),),
    }
    values.update(overrides)
    return ExactEditRequest(**values)


def _snapshot(
    content: bytes = b"before = 1\nvalue = 'old'\nafter = 2\n",
    *,
    path: str = PATH_A,
    blob: str = BLOB_A,
    mode: str = "100644",
) -> ExactFileSnapshot:
    return ExactFileSnapshot(path=path, blob_oid=blob, mode=mode, content=content)


def _compile(
    *,
    request: ExactEditRequest | None = None,
    authority: ExactEditAuthority | None = None,
    snapshots: tuple[ExactFileSnapshot, ...] | None = None,
):
    return compile_exact_edit(
        request or _request(),
        authority or _authority(),
        (_snapshot(),) if snapshots is None else snapshots,
    )


def _assert_error(code: ExactEditIssue, **kwargs: object) -> ExactEditError:
    with pytest.raises(ExactEditError) as caught:
        _compile(**kwargs)
    assert caught.value.code is code
    assert str(caught.value).startswith(f"{code.value}:")
    return caught.value


def test_ten_thousand_line_file_compiles_tiny_exact_edit_without_public_post_image() -> None:
    lines = [f"line_{index} = {index}\n" for index in range(10_000)]
    lines[5_000] = "unique_target = 'old'\n"
    source = "".join(lines).encode("utf-8")
    request = _request(
        replacements=(
            ExactTextReplacement(
                "unique_target = 'old'\n",
                "unique_target = 'new'\n",
            ),
        )
    )
    result = _compile(request=request, snapshots=(_snapshot(source),))

    assert result.schema == "mastermind.github_exact_edit.compilation.v1"
    assert result.operation_key == OPERATION
    assert result.post_images()[PATH_A].count(b"unique_target = 'new'") == 1
    assert b"unique_target = 'old'" not in result.post_images()[PATH_A]
    public = result.to_public_dict()
    serialized = json.dumps(public, sort_keys=True)
    assert "post_image" not in serialized
    assert "line_0 = 0" not in serialized
    assert "line_9999 = 9999" not in serialized
    assert "unique_target = 'new'" in serialized
    assert len(public["files"][0]["preview_patch"].encode("utf-8")) < 2048


def test_exact_edit_preserves_unrelated_bytes_and_reports_digests() -> None:
    source = b"alpha\nvalue = 'old'\nomega\n"
    result = _compile(snapshots=(_snapshot(source),))
    post = result.post_images()[PATH_A]
    assert post == b"alpha\nvalue = 'new'\nomega\n"
    file_result = result.files[0]
    assert file_result.before_sha256 != file_result.after_sha256
    assert file_result.before_bytes == len(source)
    assert file_result.after_bytes == len(post)
    assert file_result.additions == 1
    assert file_result.deletions == 1
    assert file_result.replacements[0].start_byte == len(b"alpha\n")


def test_unicode_and_crlf_bytes_are_preserved_exactly() -> None:
    source = "π = 'old'\r\nnext = 1\r\n".encode("utf-8")
    request = _request(
        replacements=(ExactTextReplacement("π = 'old'\r\n", "π = 'new'\r\n"),)
    )
    result = _compile(request=request, snapshots=(_snapshot(source),))
    assert result.post_images()[PATH_A] == "π = 'new'\r\nnext = 1\r\n".encode("utf-8")


@pytest.mark.parametrize(
    ("authority", "code"),
    [
        (_authority(carrier_state=CarrierState.CONFLICT), ExactEditIssue.CARRIER_NOT_EXACT),
        (_authority(carrier_state=CarrierState.UNKNOWN), ExactEditIssue.CARRIER_NOT_EXACT),
        (_authority(writer_state=WriterState.CONFLICT), ExactEditIssue.WRITER_NOT_EXACT),
        (_authority(writer_state=WriterState.UNKNOWN), ExactEditIssue.WRITER_NOT_EXACT),
        (
            _authority(pull_request_state=PullRequestState.CLOSED),
            ExactEditIssue.PULL_REQUEST_NOT_OPEN,
        ),
        (
            _authority(pull_request_state=PullRequestState.MERGED),
            ExactEditIssue.PULL_REQUEST_NOT_OPEN,
        ),
        (_authority(branch="master"), ExactEditIssue.DEFAULT_BRANCH_REFUSED),
        (_authority(branch_protected=True), ExactEditIssue.PROTECTED_BRANCH_REFUSED),
        (
            _authority(allowed_paths_complete=False),
            ExactEditIssue.ALLOWED_PATH_COVERAGE_INCOMPLETE,
        ),
    ],
)
def test_authority_fences_fail_closed(
    authority: ExactEditAuthority,
    code: ExactEditIssue,
) -> None:
    _assert_error(code, authority=authority)






def test_malformed_authority_and_request_types_fail_with_typed_errors() -> None:
    _assert_error(
        ExactEditIssue.AUTHORITY_IDENTITY_INVALID,
        authority=_authority(operation_key=123),
    )
    _assert_error(
        ExactEditIssue.OPERATION_IDENTITY_INVALID,
        request=_request(operation_key=123),
    )
    _assert_error(
        ExactEditIssue.AUTHORITY_IDENTITY_INVALID,
        authority=_authority(branch="HEAD"),
    )

def test_full_ref_branch_identity_is_refused_in_authority_snapshot() -> None:
    _assert_error(
        ExactEditIssue.AUTHORITY_IDENTITY_INVALID,
        authority=_authority(branch="refs/heads/sol/ghp1-test"),
    )

def test_moved_head_refuses_before_compilation() -> None:
    _assert_error(
        ExactEditIssue.HEAD_MOVED,
        request=_request(expected_head_oid="d" * 40),
    )


def test_operation_mismatch_refuses() -> None:
    _assert_error(
        ExactEditIssue.OPERATION_IDENTITY_INVALID,
        request=_request(operation_key="different-operation"),
    )


@pytest.mark.parametrize(
    "path",
    [
        "/absolute.py",
        "../escape.py",
        "dir/../escape.py",
        "dir//double.py",
        "dir\\windows.py",
        "dir/",
        "space name.py",
    ],
)
def test_noncanonical_paths_are_refused(path: str) -> None:
    _assert_error(
        ExactEditIssue.PATH_INVALID,
        request=_request(path=path),
        authority=_authority(allowed_paths=(path,)),
    )


@pytest.mark.parametrize(
    "path",
    [
        ".github/workflows/ci.yml",
        "docs/sol_skills/INDEX.md",
        "config/authority_map.yml",
        "config/executive_agent_capabilities.json",
        ".env",
        "config/prod.key",
        "nested/.git/config",
    ],
)
def test_constitutional_and_secret_paths_are_hard_refused(path: str) -> None:
    _assert_error(
        ExactEditIssue.PATH_PROTECTED,
        request=_request(path=path),
        authority=_authority(allowed_paths=(path,)),
    )


def test_path_must_already_belong_to_current_pr_surface() -> None:
    _assert_error(
        ExactEditIssue.PATH_NOT_ALLOWED,
        authority=_authority(allowed_paths=(PATH_B,)),
    )


def test_duplicate_requested_path_is_refused() -> None:
    file_request = _request().files[0]
    _assert_error(
        ExactEditIssue.DUPLICATE_PATH,
        request=_request(files=(file_request, file_request)),
    )


def test_snapshots_must_exactly_match_requested_paths() -> None:
    _assert_error(ExactEditIssue.SNAPSHOT_SET_MISMATCH, snapshots=())
    _assert_error(
        ExactEditIssue.SNAPSHOT_SET_MISMATCH,
        snapshots=(_snapshot(), _snapshot(b"other", path=PATH_B, blob=BLOB_B)),
    )


def test_blob_movement_is_refused() -> None:
    _assert_error(ExactEditIssue.BLOB_MOVED, snapshots=(_snapshot(blob=BLOB_B),))


def test_only_regular_100644_existing_files_are_accepted() -> None:
    _assert_error(ExactEditIssue.FILE_MODE_REFUSED, snapshots=(_snapshot(mode="100755"),))
    _assert_error(ExactEditIssue.FILE_MODE_REFUSED, snapshots=(_snapshot(mode="120000"),))


def test_binary_invalid_utf8_and_oversized_source_are_refused() -> None:
    _assert_error(ExactEditIssue.BINARY_REFUSED, snapshots=(_snapshot(b"a\x00b"),))
    _assert_error(ExactEditIssue.INVALID_UTF8, snapshots=(_snapshot(b"\xff\xfe"),))
    _assert_error(
        ExactEditIssue.FILE_TOO_LARGE,
        snapshots=(_snapshot(b"x" * (MAX_FILE_BYTES + 1)),),
    )


def test_empty_noop_missing_and_nonunique_anchors_are_refused() -> None:
    _assert_error(
        ExactEditIssue.EMPTY_ANCHOR,
        request=_request(replacements=(ExactTextReplacement("", "x"),)),
    )
    _assert_error(
        ExactEditIssue.NOOP_REPLACEMENT,
        request=_request(replacements=(ExactTextReplacement("value", "value"),)),
    )
    _assert_error(
        ExactEditIssue.ANCHOR_NOT_FOUND,
        request=_request(replacements=(ExactTextReplacement("missing", "new"),)),
    )
    _assert_error(
        ExactEditIssue.ANCHOR_NOT_UNIQUE,
        request=_request(replacements=(ExactTextReplacement("same", "new"),)),
        snapshots=(_snapshot(b"same and same\n"),),
    )


def test_overlapping_exact_anchors_are_refused() -> None:
    request = _request(
        replacements=(
            ExactTextReplacement("abcde", "A"),
            ExactTextReplacement("cdefg", "B"),
        )
    )
    _assert_error(
        ExactEditIssue.EDIT_OVERLAP,
        request=request,
        snapshots=(_snapshot(b"abcdefg\n"),),
    )


def test_multiple_nonoverlapping_replacements_apply_against_original_bytes() -> None:
    request = _request(
        replacements=(
            ExactTextReplacement("first = 1\n", "first = 10\n"),
            ExactTextReplacement("last = 3\n", "last = 30\n"),
        )
    )
    source = b"first = 1\nmiddle = 2\nlast = 3\n"
    result = _compile(request=request, snapshots=(_snapshot(source),))
    assert result.post_images()[PATH_A] == b"first = 10\nmiddle = 2\nlast = 30\n"


@pytest.mark.parametrize(
    "secret",
    [
        "ghp_" + "A" * 36,
        "github_pat_" + "A" * 50,
        "xoxb-" + "1" * 24,
        "sk-" + "A" * 40,
        "-----BEGIN PRIVATE KEY-----",
    ],
)
def test_secret_shaped_patch_content_is_refused(secret: str) -> None:
    _assert_error(
        ExactEditIssue.SECRET_SHAPED_CONTENT,
        request=_request(
            replacements=(ExactTextReplacement("value = 'old'\n", f"value = '{secret}'\n"),)
        ),
    )


def test_file_and_replacement_bounds_are_enforced() -> None:
    files = tuple(
        ExactFileEditRequest(
            path=f"control_plane/file_{index}.py",
            expected_blob_oid=BLOB_A,
            replacements=(ExactTextReplacement("old", "new"),),
        )
        for index in range(MAX_FILES + 1)
    )
    allowed = tuple(file.path for file in files)
    _assert_error(
        ExactEditIssue.FILE_COUNT_INVALID,
        request=_request(files=files),
        authority=_authority(allowed_paths=allowed),
    )

    replacements = tuple(
        ExactTextReplacement(f"old_{index}", f"new_{index}")
        for index in range(MAX_REPLACEMENTS_PER_FILE + 1)
    )
    _assert_error(
        ExactEditIssue.REPLACEMENT_COUNT_INVALID,
        request=_request(replacements=replacements),
    )


def test_compilation_is_permutation_stable_for_files_and_authority_paths() -> None:
    request_a = ExactEditRequest(
        schema=INPUT_SCHEMA,
        operation_key=OPERATION,
        expected_head_oid=HEAD,
        files=(
            ExactFileEditRequest(
                PATH_A,
                BLOB_A,
                (ExactTextReplacement("a = 1\n", "a = 2\n"),),
            ),
            ExactFileEditRequest(
                PATH_B,
                BLOB_B,
                (ExactTextReplacement("b = 1\n", "b = 2\n"),),
            ),
        ),
    )
    request_b = dataclasses.replace(request_a, files=tuple(reversed(request_a.files)))
    snapshots_a = (
        _snapshot(b"a = 1\n", path=PATH_A, blob=BLOB_A),
        _snapshot(b"b = 1\n", path=PATH_B, blob=BLOB_B),
    )
    snapshots_b = tuple(reversed(snapshots_a))
    result_a = _compile(request=request_a, snapshots=snapshots_a)
    result_b = _compile(
        request=request_b,
        authority=_authority(allowed_paths=(PATH_B, PATH_A)),
        snapshots=snapshots_b,
    )
    assert result_a.canonical_digest == result_b.canonical_digest
    assert result_a.to_public_dict() == result_b.to_public_dict()
    assert [item.path for item in result_a.files] == [PATH_A, PATH_B]




def test_replacement_order_is_semantically_permutation_stable() -> None:
    source = b"first = 1\nmiddle = 2\nlast = 3\n"
    replacements = (
        ExactTextReplacement("first = 1\n", "first = 10\n"),
        ExactTextReplacement("last = 3\n", "last = 30\n"),
    )
    first = _compile(
        request=_request(replacements=replacements),
        snapshots=(_snapshot(source),),
    )
    second = _compile(
        request=_request(replacements=tuple(reversed(replacements))),
        snapshots=(_snapshot(source),),
    )
    assert first.canonical_digest == second.canonical_digest
    assert first.to_public_dict() == second.to_public_dict()

def test_load_bearing_edit_change_changes_digest() -> None:
    first = _compile()
    second = _compile(
        request=_request(
            replacements=(ExactTextReplacement("value = 'old'\n", "value = 'other'\n"),)
        )
    )
    assert first.canonical_digest != second.canonical_digest


def test_public_projection_is_json_serializable_and_post_images_are_immutable_copy() -> None:
    result = _compile()
    encoded = json.dumps(result.to_public_dict(), sort_keys=True, allow_nan=False)
    assert result.canonical_digest in encoded
    post_images = result.post_images()
    assert post_images == {PATH_A: b"before = 1\nvalue = 'new'\nafter = 2\n"}
    with pytest.raises(TypeError):
        post_images[PATH_A] = b"mutate"  # type: ignore[index]


def test_module_is_pure_and_does_not_import_effectful_surfaces() -> None:
    module_path = Path(__file__).parents[1] / "control_plane" / "github_exact_edit.py"
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".", 1)[0])
    assert imports.isdisjoint(
        {
            "asyncio",
            "httpx",
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
    forbidden_calls = {
        "createCommitOnBranch",
        "open",
        "update_ref",
    }
    called_names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            called_names.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            called_names.add(node.func.attr)
    assert called_names.isdisjoint(forbidden_calls)

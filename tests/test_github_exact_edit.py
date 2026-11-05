from __future__ import annotations

import ast
import dataclasses
import hashlib
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
OPERATION = "mastermind-sol-capability-fabric-ghp1-test"
PATH_A = "control_plane/example.py"
PATH_B = "tests/test_example.py"
DEFAULT_SOURCE = b"before = 1\nvalue = 'old'\nafter = 2\n"


def _git_blob_oid(content: bytes, *, sha256: bool = False) -> str:
    framed = b"blob " + str(len(content)).encode("ascii") + b"\0" + content
    if sha256:
        return hashlib.sha256(framed).hexdigest()
    return hashlib.sha1(framed, usedforsecurity=False).hexdigest()


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
    content: bytes = DEFAULT_SOURCE,
    path: str = PATH_A,
    blob: str | None = None,
    replacements: tuple[ExactTextReplacement, ...] | None = None,
    **overrides: object,
) -> ExactEditRequest:
    if blob is None:
        blob = _git_blob_oid(content)
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
    content: bytes = DEFAULT_SOURCE,
    *,
    path: str = PATH_A,
    blob: str | None = None,
    mode: str = "100644",
    sha256: bool = False,
) -> ExactFileSnapshot:
    return ExactFileSnapshot(
        path=path,
        blob_oid=blob or _git_blob_oid(content, sha256=sha256),
        mode=mode,
        content=content,
    )


def _compile(
    *,
    content: bytes = DEFAULT_SOURCE,
    request: ExactEditRequest | None = None,
    authority: ExactEditAuthority | None = None,
    snapshots: tuple[ExactFileSnapshot, ...] | None = None,
):
    return compile_exact_edit(
        request or _request(content=content),
        authority or _authority(),
        (_snapshot(content),) if snapshots is None else snapshots,
    )


def _assert_error(code: ExactEditIssue, **kwargs: object) -> ExactEditError:
    with pytest.raises(ExactEditError) as caught:
        _compile(**kwargs)
    assert caught.value.code is code
    assert str(caught.value).startswith(f"{code.value}:")
    return caught.value


def test_large_file_compiles_tiny_edit_without_public_post_image() -> None:
    lines = [f"line_{index} = {index}\n" for index in range(12_050)]
    lines[6_000] = "unique_target = 'old'\n"
    source = "".join(lines).encode()
    request = _request(
        content=source,
        replacements=(ExactTextReplacement("unique_target = 'old'\n", "unique_target = 'new'\n"),),
    )
    result = _compile(content=source, request=request)
    assert result.post_images()[PATH_A].count(b"unique_target = 'new'") == 1
    public = json.dumps(result.to_public_dict(), sort_keys=True)
    assert "post_image" not in public
    assert "line_0 = 0" not in public
    assert "line_12049 = 12049" not in public
    assert "unique_target = 'new'" in public
    assert len(result.files[0].preview_patch.encode()) < 2048


def test_source_bytes_must_match_claimed_sha1_blob_oid() -> None:
    request = _request(content=DEFAULT_SOURCE)
    forged = _snapshot(
        DEFAULT_SOURCE.replace(b"before = 1", b"before = 9"),
        blob=request.files[0].expected_blob_oid,
    )
    _assert_error(
        ExactEditIssue.SOURCE_BLOB_CONTENT_MISMATCH,
        request=request,
        snapshots=(forged,),
    )


def test_sha256_repository_blob_oid_is_verified() -> None:
    blob = _git_blob_oid(DEFAULT_SOURCE, sha256=True)
    request = _request(content=DEFAULT_SOURCE, blob=blob)
    result = _compile(request=request, snapshots=(_snapshot(DEFAULT_SOURCE, blob=blob),))
    assert result.files[0].before_blob_oid == blob
    forged = DEFAULT_SOURCE + b"# forged\n"
    _assert_error(
        ExactEditIssue.SOURCE_BLOB_CONTENT_MISMATCH,
        request=request,
        snapshots=(_snapshot(forged, blob=blob),),
    )


def test_exact_edit_preserves_bytes_unicode_crlf_and_no_final_newline() -> None:
    source = "π = 'old'\r\nnext = 1".encode()
    request = _request(
        content=source,
        replacements=(ExactTextReplacement("π = 'old'\r\n", "π = 'new'\r\n"),),
    )
    result = _compile(content=source, request=request)
    assert result.post_images()[PATH_A] == "π = 'new'\r\nnext = 1".encode()
    assert "No newline" not in result.files[0].preview_patch


@pytest.mark.parametrize(
    ("authority", "code"),
    [
        (_authority(carrier_state=CarrierState.CONFLICT), ExactEditIssue.CARRIER_NOT_EXACT),
        (_authority(carrier_state=CarrierState.UNKNOWN), ExactEditIssue.CARRIER_NOT_EXACT),
        (_authority(writer_state=WriterState.CONFLICT), ExactEditIssue.WRITER_NOT_EXACT),
        (_authority(writer_state=WriterState.UNKNOWN), ExactEditIssue.WRITER_NOT_EXACT),
        (_authority(pull_request_state=PullRequestState.CLOSED), ExactEditIssue.PULL_REQUEST_NOT_OPEN),
        (_authority(pull_request_state=PullRequestState.MERGED), ExactEditIssue.PULL_REQUEST_NOT_OPEN),
        (_authority(branch="master"), ExactEditIssue.DEFAULT_BRANCH_REFUSED),
        (_authority(branch_protected=True), ExactEditIssue.PROTECTED_BRANCH_REFUSED),
        (_authority(allowed_paths_complete=False), ExactEditIssue.ALLOWED_PATH_COVERAGE_INCOMPLETE),
    ],
)
def test_authority_fences_fail_closed(
    authority: ExactEditAuthority,
    code: ExactEditIssue,
) -> None:
    _assert_error(code, authority=authority)


@pytest.mark.parametrize(
    "branch",
    ["HEAD", "refs/heads/sol/test", "-bad", "bad..name", "bad//name", "bad.lock", "bad@{name"],
)
def test_noncanonical_branch_identity_is_refused(branch: str) -> None:
    _assert_error(ExactEditIssue.AUTHORITY_IDENTITY_INVALID, authority=_authority(branch=branch))


def test_moved_head_and_operation_mismatch_refuse() -> None:
    _assert_error(ExactEditIssue.HEAD_MOVED, request=_request(expected_head_oid="d" * 40))
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
def test_constitutional_and_secret_paths_are_refused(path: str) -> None:
    _assert_error(
        ExactEditIssue.PATH_PROTECTED,
        request=_request(path=path),
        authority=_authority(allowed_paths=(path,)),
    )


def test_path_and_snapshot_sets_are_exact() -> None:
    _assert_error(ExactEditIssue.PATH_NOT_ALLOWED, authority=_authority(allowed_paths=(PATH_B,)))
    file_request = _request().files[0]
    _assert_error(ExactEditIssue.DUPLICATE_PATH, request=_request(files=(file_request, file_request)))
    _assert_error(ExactEditIssue.SNAPSHOT_SET_MISMATCH, snapshots=())
    extra = b"other\n"
    _assert_error(
        ExactEditIssue.SNAPSHOT_SET_MISMATCH,
        snapshots=(_snapshot(), _snapshot(extra, path=PATH_B)),
    )


def test_blob_movement_and_source_kind_are_refused() -> None:
    other_content = b"other\n"
    other = _git_blob_oid(other_content)
    _assert_error(
        ExactEditIssue.BLOB_MOVED,
        snapshots=(_snapshot(other_content, blob=other),),
    )
    _assert_error(ExactEditIssue.FILE_MODE_REFUSED, snapshots=(_snapshot(mode="100755"),))
    _assert_error(ExactEditIssue.FILE_MODE_REFUSED, snapshots=(_snapshot(mode="120000"),))
    binary = b"a\x00b"
    _assert_error(
        ExactEditIssue.BINARY_REFUSED,
        content=binary,
        request=_request(content=binary, replacements=(ExactTextReplacement("a", "b"),)),
    )
    invalid = b"\xff\xfe"
    _assert_error(
        ExactEditIssue.INVALID_UTF8,
        content=invalid,
        request=_request(content=invalid, replacements=(ExactTextReplacement("x", "y"),)),
    )


def test_empty_noop_missing_nonunique_and_overlap_refuse() -> None:
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
    source = b"same and same\n"
    _assert_error(
        ExactEditIssue.ANCHOR_NOT_UNIQUE,
        content=source,
        request=_request(content=source, replacements=(ExactTextReplacement("same", "new"),)),
    )
    source = b"abcdefg\n"
    _assert_error(
        ExactEditIssue.EDIT_OVERLAP,
        content=source,
        request=_request(
            content=source,
            replacements=(
                ExactTextReplacement("abcde", "A"),
                ExactTextReplacement("cdefg", "B"),
            ),
        ),
    )


def test_nonoverlapping_replacements_and_request_order_are_stable() -> None:
    source = b"first = 1\nmiddle = 2\nlast = 3\n"
    replacements = (
        ExactTextReplacement("first = 1\n", "first = 10\n"),
        ExactTextReplacement("last = 3\n", "last = 30\n"),
    )
    first = _compile(
        content=source,
        request=_request(content=source, replacements=replacements),
    )
    second = _compile(
        content=source,
        request=_request(content=source, replacements=tuple(reversed(replacements))),
    )
    assert first.post_images()[PATH_A] == b"first = 10\nmiddle = 2\nlast = 30\n"
    assert first.canonical_digest == second.canonical_digest
    assert first.to_public_dict() == second.to_public_dict()


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
def test_secret_shaped_content_is_refused_without_reflection(secret: str) -> None:
    error = _assert_error(
        ExactEditIssue.SECRET_SHAPED_CONTENT,
        request=_request(
            replacements=(
                ExactTextReplacement(
                    "value = 'old'\n",
                    f"value = '{secret}'\n",
                ),
            )
        ),
    )
    assert secret not in str(error)


def test_file_replacement_and_source_bounds_are_enforced() -> None:
    files = tuple(
        ExactFileEditRequest(
            f"control_plane/file_{index}.py",
            _git_blob_oid(b"old"),
            (ExactTextReplacement("old", "new"),),
        )
        for index in range(MAX_FILES + 1)
    )
    _assert_error(
        ExactEditIssue.FILE_COUNT_INVALID,
        request=_request(files=files),
        authority=_authority(allowed_paths=tuple(row.path for row in files)),
    )
    replacements = tuple(
        ExactTextReplacement(f"old_{index}", f"new_{index}")
        for index in range(MAX_REPLACEMENTS_PER_FILE + 1)
    )
    _assert_error(
        ExactEditIssue.REPLACEMENT_COUNT_INVALID,
        request=_request(replacements=replacements),
    )
    oversized = b"x" * (MAX_FILE_BYTES + 1)
    _assert_error(
        ExactEditIssue.FILE_TOO_LARGE,
        content=oversized,
        request=_request(
            content=oversized,
            replacements=(ExactTextReplacement("x", "y"),),
        ),
    )


def test_file_and_authority_order_are_permutation_stable() -> None:
    source_a = b"a = 1\n"
    source_b = b"b = 1\n"
    file_a = ExactFileEditRequest(
        PATH_A,
        _git_blob_oid(source_a),
        (ExactTextReplacement("a = 1\n", "a = 2\n"),),
    )
    file_b = ExactFileEditRequest(
        PATH_B,
        _git_blob_oid(source_b),
        (ExactTextReplacement("b = 1\n", "b = 2\n"),),
    )
    request_a = ExactEditRequest(INPUT_SCHEMA, OPERATION, HEAD, (file_a, file_b))
    request_b = dataclasses.replace(request_a, files=(file_b, file_a))
    snapshots_a = (
        _snapshot(source_a, path=PATH_A),
        _snapshot(source_b, path=PATH_B),
    )
    first = compile_exact_edit(request_a, _authority(), snapshots_a)
    second = compile_exact_edit(
        request_b,
        _authority(allowed_paths=(PATH_B, PATH_A)),
        tuple(reversed(snapshots_a)),
    )
    assert first.to_public_dict() == second.to_public_dict()
    assert first.canonical_digest == second.canonical_digest


def test_context_rich_preview_counts_only_changed_middle_lines() -> None:
    source = b"before\nvalue = 1\nafter\n"
    request = _request(
        content=source,
        replacements=(
            ExactTextReplacement(
                "before\nvalue = 1\nafter\n",
                "before\nvalue = 2\nafter\n",
            ),
        ),
    )
    result = _compile(content=source, request=request)
    preview = result.files[0].preview_patch
    assert " before\n" in preview
    assert "-value = 1\n" in preview
    assert "+value = 2\n" in preview
    assert " after\n" in preview
    assert result.files[0].additions == result.files[0].deletions == 1


def test_public_projection_is_json_serializable_and_post_images_are_immutable() -> None:
    result = _compile()
    encoded = json.dumps(result.to_public_dict(), sort_keys=True, allow_nan=False)
    assert result.canonical_digest in encoded
    post_images = result.post_images()
    assert post_images[PATH_A] == b"before = 1\nvalue = 'new'\nafter = 2\n"
    with pytest.raises(TypeError):
        post_images[PATH_A] = b"mutate"  # type: ignore[index]


def test_module_is_pure_and_does_not_import_effectful_surfaces() -> None:
    module_path = Path(__file__).parents[1] / "control_plane" / "github_exact_edit.py"
    tree = ast.parse(module_path.read_text())
    imports: set[str] = set()
    calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".", 1)[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)
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
    assert calls.isdisjoint({"createCommitOnBranch", "open", "update_ref"})

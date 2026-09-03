from __future__ import annotations

import asyncio
import base64
import dataclasses
import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from integrations.mastermind_github_app.adapter import (
    COMMIT_TOOL,
    MAX_MODEL_EDIT_BYTES,
    PREPARE_TOOL,
    RECONCILE_TOOL,
    GithubPatchGateway,
)
from integrations.mastermind_github_app.github_port import (
    GRAPHQL_ENDPOINT,
    REST_ROOT,
    GithubApiPatchPort,
    GithubReadError,
    HttpResponse,
)
from integrations.mastermind_github_app.models import (
    AppConfig,
    AuthenticatedPrincipal,
    CommitFile,
    EffectObservation,
    EffectState,
    GithubBlob,
    IssueCode,
    NativeCommitError,
    NativeCommitResult,
    PatchEligibility,
    ResolvedPatchTarget,
)
from integrations.mastermind_github_app.prepared_token import (
    HmacPreparedTokenCodec,
    PreparedTokenError,
)
from integrations.mastermind_github_app.schemas import SCHEMA_DIGEST, TOOL_SPECS


OPERATION = "mastermind-ghp2-test-op"
REPOSITORY = "mastermindx-market-intelligence/Mastermind"
BRANCH = "sol/ghp2-test"
PATH = "control_plane/large_fixture.py"
HEAD = "a" * 40
PRINCIPAL = "1" * 64
SECRET = b"s" * 32


def _run(awaitable):
    return asyncio.run(awaitable)


def _git_blob_oid(content: str) -> str:
    raw = content.encode("utf-8")
    framed = b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    return hashlib.sha1(framed, usedforsecurity=False).hexdigest()


@dataclasses.dataclass
class FakeClock:
    value: int = 1_800_000_000

    def now(self) -> int:
        return self.value


@dataclasses.dataclass
class FakePrincipalProvider:
    principal: AuthenticatedPrincipal
    fail: bool = False

    async def current_principal(self) -> AuthenticatedPrincipal:
        if self.fail:
            raise RuntimeError("private auth payload")
        return self.principal


@dataclasses.dataclass
class FakeAuthorityResolver:
    target: ResolvedPatchTarget
    fail: bool = False

    async def resolve_patch_target(
        self,
        operation_key: str,
        principal_digest: str,
    ) -> ResolvedPatchTarget:
        if self.fail:
            raise RuntimeError("private authority payload")
        assert principal_digest == PRINCIPAL
        return self.target


class FakeGithub:
    def __init__(self, content: str) -> None:
        self.head = HEAD
        self.blobs = {
            PATH: GithubBlob(
                path=PATH,
                oid=_git_blob_oid(content),
                content=content,
            )
        }
        self.commit_mode = "success"
        self.commit_calls = 0
        self.read_blob_calls = 0
        self.applied: dict[str, tuple[str, dict[str, str]]] = {}
        self.effect_unknown: set[str] = set()

    async def read_branch_head(self, target: ResolvedPatchTarget) -> str:
        assert target.repository == REPOSITORY
        return self.head

    async def read_blob(
        self,
        target: ResolvedPatchTarget,
        head_oid: str,
        path: str,
    ) -> GithubBlob:
        self.read_blob_calls += 1
        assert head_oid == self.head or head_oid == HEAD
        return self.blobs[path]

    async def commit_branch_patch(
        self,
        target: ResolvedPatchTarget,
        expected_head_oid: str,
        operation_key: str,
        effect_digest: str,
        files: Sequence[CommitFile],
    ) -> NativeCommitResult:
        self.commit_calls += 1
        assert operation_key == OPERATION
        assert expected_head_oid == HEAD
        if self.commit_mode == "definite_refusal":
            raise NativeCommitError(effect_possible=False)
        if self.commit_mode == "ambiguous_unknown":
            self.effect_unknown.add(effect_digest)
            raise NativeCommitError(effect_possible=True)
        if self.commit_mode == "ambiguous_not_applied":
            raise NativeCommitError(effect_possible=True)

        commit_oid = "c" * 40
        after: dict[str, str] = {}
        for item in files:
            assert hashlib.sha256(item.content.encode("utf-8")).hexdigest() == item.after_sha256
            self.blobs[item.path] = GithubBlob(
                path=item.path,
                oid=_git_blob_oid(item.content),
                content=item.content,
            )
            after[item.path] = item.after_sha256
        self.head = commit_oid
        self.applied[effect_digest] = (commit_oid, after)
        if self.commit_mode == "ambiguous_applied":
            raise NativeCommitError(effect_possible=True)
        return NativeCommitResult(
            request_sent=True,
            commit_oid=commit_oid,
            definite_no_effect=False,
        )

    async def reconcile_branch_patch(
        self,
        target: ResolvedPatchTarget,
        expected_head_oid: str,
        operation_key: str,
        effect_digest: str,
        expected_after_sha256: Mapping[str, str],
    ) -> EffectObservation:
        if effect_digest in self.effect_unknown:
            return EffectObservation(
                state=EffectState.EFFECT_UNKNOWN,
                commit_oid=None,
                branch_head_oid=self.head,
                complete=False,
            )
        if effect_digest in self.applied:
            commit_oid, after = self.applied[effect_digest]
            assert dict(expected_after_sha256) == after
            return EffectObservation(
                state=EffectState.APPLIED,
                commit_oid=commit_oid,
                branch_head_oid=self.head,
                complete=True,
            )
        return EffectObservation(
            state=EffectState.NOT_APPLIED,
            commit_oid=None,
            branch_head_oid=self.head,
            complete=True,
        )


def _target(**changes: object) -> ResolvedPatchTarget:
    base = ResolvedPatchTarget(
        operation_key=OPERATION,
        repository=REPOSITORY,
        branch=BRANCH,
        pull_request_number=999,
        protected_branches=("main", "master"),
        allowed_paths=(PATH,),
        carrier_digest="2" * 64,
        writer_digest="3" * 64,
        authority_digest="4" * 64,
        source_digest="5" * 64,
        patch_eligibility=PatchEligibility.ELIGIBLE,
    )
    return dataclasses.replace(base, **changes)


def _source(lines: int = 12_050) -> str:
    return "".join(f"line-{index:05d}\n" for index in range(1, lines + 1))


def _replacement() -> dict[str, str]:
    return {
        "old_text": "line-06000\nline-06001\nline-06002\n",
        "new_text": (
            "line-06000\n"
            "line-06001-repaired\n"
            "line-06001-proof\n"
            "line-06002\n"
        ),
    }


def _arguments(github: FakeGithub) -> dict[str, object]:
    return {
        "operation_key": OPERATION,
        "expected_head_oid": HEAD,
        "files": [
            {
                "path": PATH,
                "expected_blob_oid": github.blobs[PATH].oid,
                "replacements": [_replacement()],
            }
        ],
    }


def _gateway(
    github: FakeGithub,
    *,
    armed: bool = True,
    clock: FakeClock | None = None,
    principal: AuthenticatedPrincipal | None = None,
    target: ResolvedPatchTarget | None = None,
) -> tuple[GithubPatchGateway, FakeClock, FakeAuthorityResolver]:
    clock = clock or FakeClock()
    principal = principal or AuthenticatedPrincipal(
        principal_digest=PRINCIPAL,
        scopes=("mastermind.github.exact_branch_repair",),
    )
    resolver = FakeAuthorityResolver(target or _target())
    gateway = GithubPatchGateway(
        config=AppConfig(
            app_id="mastermind-github-exact-repair",
            app_generation="ghp2-exact-test-generation",
            schema_digest=SCHEMA_DIGEST,
            policy_id="ghp2-exact-test-policy",
            production_armed=armed,
            token_ttl_seconds=300,
        ),
        principal_provider=FakePrincipalProvider(principal),
        authority_resolver=resolver,
        github=github,
        token_codec=HmacPreparedTokenCodec(SECRET, context="ghp2-exact-test"),
        clock=clock,
    )
    return gateway, clock, resolver


def _prepare(gateway: GithubPatchGateway, github: FakeGithub) -> dict[str, object]:
    return _run(gateway.call(PREPARE_TOOL, _arguments(github)))


def _token(result: Mapping[str, object]) -> str:
    data = result["data"]
    assert isinstance(data, Mapping)
    token = data["prepared_token"]
    assert isinstance(token, str)
    return token


def test_exact_three_tool_surface_has_no_open_patch_or_model_selected_target() -> None:
    assert [spec.name for spec in TOOL_SPECS] == [
        PREPARE_TOOL,
        COMMIT_TOOL,
        RECONCILE_TOOL,
    ]
    prepare = TOOL_SPECS[0].input_schema
    properties = prepare["properties"]
    assert set(properties) == {"operation_key", "expected_head_oid", "files"}
    file_properties = properties["files"]["items"]["properties"]
    assert set(file_properties) == {"path", "expected_blob_oid", "replacements"}
    replacement_properties = file_properties["replacements"]["items"]["properties"]
    assert set(replacement_properties) == {"old_text", "new_text"}
    rendered = json.dumps([spec.input_schema for spec in TOOL_SPECS], sort_keys=True)
    for forbidden in (
        '"repository"',
        '"branch"',
        '"url"',
        '"method"',
        '"credential"',
        '"token_provider"',
        '"force"',
        '"shell"',
        '"unified_diff"',
    ):
        assert forbidden not in rendered


def test_adapter_has_no_removed_unified_diff_kernel_dependency() -> None:
    source = Path("integrations/mastermind_github_app/adapter.py").read_text(encoding="utf-8")
    assert "control_plane.github_branch_patch" not in source
    assert "unified_diff" not in source
    assert "control_plane.github_exact_edit" in source


def test_production_disarmed_prepare_returns_preview_without_token_or_mutation() -> None:
    github = FakeGithub(_source())
    gateway, _, _ = _gateway(github, armed=False)
    result = _prepare(gateway, github)
    assert result["status"] == "BLOCKED"
    assert result["issues"] == ["PRODUCTION_DISARMED"]
    data = result["data"]
    assert data["preview_state"] == "BLOCKED"
    assert data["prepared_token"] is None
    assert data["expires_at"] is None
    assert github.commit_calls == 0
    assert github.read_blob_calls == 1


def test_armed_prepare_materializes_large_file_server_side_and_returns_bounded_preview() -> None:
    content = _source()
    github = FakeGithub(content)
    gateway, _, _ = _gateway(github)
    result = _prepare(gateway, github)
    assert result["status"] == "OK"
    assert result["issues"] == []
    data = result["data"]
    assert data["preview_state"] == "READY"
    assert isinstance(data["prepared_token"], str)
    assert data["normalized_effect_digest"] == data["canonical_digest"]
    rendered = json.dumps({key: value for key, value in data.items() if key != "prepared_token"})
    assert content not in rendered
    assert len(rendered.encode("utf-8")) < 50_000
    assert data["files"][0]["additions"] == 2
    assert data["files"][0]["deletions"] == 1
    assert github.commit_calls == 0


def test_commit_applies_once_and_same_token_reconciles_without_second_request() -> None:
    github = FakeGithub(_source())
    gateway, _, _ = _gateway(github)
    prepared = _prepare(gateway, github)
    token = _token(prepared)

    first = _run(gateway.call(COMMIT_TOOL, {"prepared_token": token}))
    assert first["status"] == "OK"
    assert first["data"]["effect_state"] == "APPLIED"
    assert first["data"]["native_request_attempts"] == 1
    assert github.commit_calls == 1
    assert "line-06001-repaired\nline-06001-proof\n" in github.blobs[PATH].content

    second = _run(gateway.call(COMMIT_TOOL, {"prepared_token": token}))
    assert second["status"] == "OK"
    assert second["data"]["effect_state"] == "APPLIED"
    assert second["data"]["native_request_attempts"] == 0
    assert github.commit_calls == 1


def test_ambiguous_native_response_reconciles_applied_without_resend() -> None:
    github = FakeGithub(_source())
    github.commit_mode = "ambiguous_applied"
    gateway, _, _ = _gateway(github)
    token = _token(_prepare(gateway, github))
    result = _run(gateway.call(COMMIT_TOOL, {"prepared_token": token}))
    assert result["status"] == "OK"
    assert result["data"]["effect_state"] == "APPLIED"
    assert result["data"]["native_request_attempts"] == 1
    assert github.commit_calls == 1


def test_ambiguous_unknown_blocks_retry_and_preserves_one_native_attempt() -> None:
    github = FakeGithub(_source())
    github.commit_mode = "ambiguous_unknown"
    gateway, _, _ = _gateway(github)
    token = _token(_prepare(gateway, github))

    first = _run(gateway.call(COMMIT_TOOL, {"prepared_token": token}))
    assert first["status"] == "UNKNOWN"
    assert first["data"]["effect_state"] == "EFFECT_UNKNOWN"
    assert first["data"]["native_request_attempts"] == 1
    assert github.commit_calls == 1

    second = _run(gateway.call(COMMIT_TOOL, {"prepared_token": token}))
    assert second["status"] == "UNKNOWN"
    assert second["data"]["effect_state"] == "EFFECT_UNKNOWN"
    assert second["data"]["native_request_attempts"] == 0
    assert "PRIOR_EFFECT_UNKNOWN" in second["issues"]
    assert github.commit_calls == 1


def test_definite_native_refusal_is_not_applied_and_never_retried() -> None:
    github = FakeGithub(_source())
    github.commit_mode = "definite_refusal"
    gateway, _, _ = _gateway(github)
    token = _token(_prepare(gateway, github))
    result = _run(gateway.call(COMMIT_TOOL, {"prepared_token": token}))
    assert result["status"] == "REFUSED"
    assert result["data"]["effect_state"] == "NOT_APPLIED"
    assert result["data"]["native_request_attempts"] == 1
    assert result["issues"] == ["NATIVE_REQUEST_REFUSED"]
    assert github.commit_calls == 1


def test_potentially_sent_but_not_observed_is_effect_unknown() -> None:
    github = FakeGithub(_source())
    github.commit_mode = "ambiguous_not_applied"
    gateway, _, _ = _gateway(github)
    token = _token(_prepare(gateway, github))
    result = _run(gateway.call(COMMIT_TOOL, {"prepared_token": token}))
    assert result["status"] == "UNKNOWN"
    assert result["data"]["effect_state"] == "EFFECT_UNKNOWN"
    assert result["data"]["native_request_attempts"] == 1


def test_prepare_stale_head_is_blocked_before_blob_read_or_commit() -> None:
    github = FakeGithub(_source())
    github.head = "b" * 40
    gateway, _, _ = _gateway(github)
    result = _prepare(gateway, github)
    assert result["status"] == "BLOCKED"
    assert result["issues"] == ["BRANCH_HEAD_MOVED"]
    assert github.read_blob_calls == 0
    assert github.commit_calls == 0


def test_head_move_after_prepare_returns_definite_not_applied_without_commit() -> None:
    github = FakeGithub(_source())
    gateway, _, _ = _gateway(github)
    token = _token(_prepare(gateway, github))
    github.head = "b" * 40
    result = _run(gateway.call(COMMIT_TOOL, {"prepared_token": token}))
    assert result["status"] == "BLOCKED"
    assert result["data"]["effect_state"] == "NOT_APPLIED"
    assert result["data"]["native_request_attempts"] == 0
    assert result["issues"] == ["BRANCH_HEAD_MOVED"]
    assert github.commit_calls == 0


def test_blob_change_after_prepare_is_precondition_refusal() -> None:
    github = FakeGithub(_source())
    gateway, _, _ = _gateway(github)
    token = _token(_prepare(gateway, github))
    changed = github.blobs[PATH].content.replace("line-06001\n", "line-06001-other\n")
    github.blobs[PATH] = GithubBlob(
        path=PATH,
        oid=_git_blob_oid(changed),
        content=changed,
    )
    result = _run(gateway.call(COMMIT_TOOL, {"prepared_token": token}))
    assert result["status"] == "REFUSED"
    assert result["data"]["effect_state"] == "NOT_APPLIED"
    assert result["issues"] == ["PRECONDITION_CHANGED"]
    assert github.commit_calls == 0


def test_tampered_expired_and_cross_principal_tokens_are_refused_payload_free() -> None:
    github = FakeGithub(_source())
    gateway, clock, _ = _gateway(github)
    token = _token(_prepare(gateway, github))

    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
    result = _run(gateway.call(COMMIT_TOOL, {"prepared_token": tampered}))
    assert result["status"] == "REFUSED"
    assert result["issues"] == ["PREPARED_TOKEN_INVALID"]
    assert token not in json.dumps(result)

    clock.value += 301
    expired = _run(gateway.call(COMMIT_TOOL, {"prepared_token": token}))
    assert expired["issues"] == ["PREPARED_ACTION_EXPIRED"]

    other = AuthenticatedPrincipal(
        principal_digest="9" * 64,
        scopes=("mastermind.github.exact_branch_repair",),
    )
    other_gateway, _, _ = _gateway(github, clock=clock, principal=other)
    cross = _run(other_gateway.call(COMMIT_TOOL, {"prepared_token": token}))
    assert cross["issues"] in (["AUTHENTICATION_REFUSED"], ["PREPARED_ACTION_EXPIRED"])


def test_expired_token_remains_usable_for_read_only_reconciliation() -> None:
    github = FakeGithub(_source())
    gateway, clock, _ = _gateway(github)
    prepared = _prepare(gateway, github)
    token = _token(prepared)
    effect = prepared["data"]["normalized_effect_digest"]
    clock.value += 10_000
    result = _run(
        gateway.call(
            RECONCILE_TOOL,
            {
                "operation_key": OPERATION,
                "normalized_effect_digest": effect,
                "prepared_token": token,
            },
        )
    )
    assert result["status"] == "OK"
    assert result["data"]["effect_state"] == "NOT_APPLIED"
    assert result["data"]["native_request_attempts"] == 0


def test_authority_or_writer_change_after_prepare_refuses_commit() -> None:
    github = FakeGithub(_source())
    gateway, _, resolver = _gateway(github)
    token = _token(_prepare(gateway, github))
    resolver.target = _target(writer_digest="8" * 64)
    result = _run(gateway.call(COMMIT_TOOL, {"prepared_token": token}))
    assert result["status"] == "REFUSED"
    assert result["issues"] == ["PRECONDITION_CHANGED"]
    assert github.commit_calls == 0


def test_unowned_and_protected_targets_fail_before_native_commit() -> None:
    content = _source()
    github = FakeGithub(content)
    unowned_gateway, _, _ = _gateway(github, target=_target(allowed_paths=("other.py",)))
    unowned = _prepare(unowned_gateway, github)
    assert unowned["status"] == "REFUSED"
    assert unowned["issues"] == ["PATCH_TARGET_NOT_OWNED"]

    protected_gateway, _, _ = _gateway(
        github,
        target=_target(branch="master", protected_branches=("master",)),
    )
    protected = _prepare(protected_gateway, github)
    assert protected["status"] == "REFUSED"
    assert protected["issues"] == ["PROTECTED_BRANCH_REFUSED"]
    assert github.commit_calls == 0


def test_scope_and_target_resolution_fail_closed_without_private_error_reflection() -> None:
    github = FakeGithub(_source())
    no_scope = AuthenticatedPrincipal(principal_digest=PRINCIPAL, scopes=())
    gateway, _, _ = _gateway(github, principal=no_scope)
    result = _prepare(gateway, github)
    assert result["issues"] == ["SCOPE_REFUSED"]
    assert "private" not in json.dumps(result)

    gateway, _, resolver = _gateway(github)
    resolver.fail = True
    result = _prepare(gateway, github)
    assert result["status"] == "UNKNOWN"
    assert result["issues"] == ["ACTION_TARGET_UNRESOLVED"]
    assert "private" not in json.dumps(result)


def test_non_unique_anchor_and_secret_shaped_replacement_fail_closed() -> None:
    repeated = "needle\nneedle\nend\n"
    github = FakeGithub(repeated)
    arguments = _arguments(github)
    arguments["files"][0]["replacements"] = [
        {"old_text": "needle\n", "new_text": "replacement\n"}
    ]
    gateway, _, _ = _gateway(github)
    result = _run(gateway.call(PREPARE_TOOL, arguments))
    assert result["status"] == "REFUSED"
    assert result["issues"] == ["PATCH_CONTEXT_MISMATCH"]

    github = FakeGithub("alpha\nbeta\ngamma\n")
    arguments = _arguments(github)
    arguments["files"][0]["replacements"] = [
        {
            "old_text": "beta\n",
            "new_text": "github_pat_" + "A" * 45 + "\n",
        }
    ]
    gateway, _, _ = _gateway(github)
    result = _run(gateway.call(PREPARE_TOOL, arguments))
    assert result["status"] == "REFUSED"
    assert result["issues"] == ["PATCH_SECRET_SHAPE_REFUSED"]
    assert "github_pat_" not in json.dumps(result)


def test_crlf_and_no_final_newline_are_preserved_byte_for_byte() -> None:
    content = "alpha\r\nbeta\r\ngamma"
    github = FakeGithub(content)
    arguments = _arguments(github)
    arguments["files"][0]["replacements"] = [
        {
            "old_text": "alpha\r\nbeta\r\ngamma",
            "new_text": "alpha\r\nbeta-repaired\r\ngamma",
        }
    ]
    gateway, _, _ = _gateway(github)
    prepared = _run(gateway.call(PREPARE_TOOL, arguments))
    assert prepared["status"] == "OK"
    result = _run(gateway.call(COMMIT_TOOL, {"prepared_token": _token(prepared)}))
    assert result["data"]["effect_state"] == "APPLIED"
    assert github.blobs[PATH].content == "alpha\r\nbeta-repaired\r\ngamma"


def test_model_edit_payload_has_a_stricter_token_safe_byte_ceiling() -> None:
    github = FakeGithub("alpha\nbeta\ngamma\n")
    arguments = _arguments(github)
    arguments["files"][0]["replacements"] = [
        {
            "old_text": "beta\n",
            "new_text": "x" * (MAX_MODEL_EDIT_BYTES + 1),
        }
    ]
    gateway, _, _ = _gateway(github)
    result = _run(gateway.call(PREPARE_TOOL, arguments))
    assert result["status"] == "REFUSED"
    assert result["issues"] == ["PATCH_LIMIT_EXCEEDED"]


def test_token_codec_round_trip_tamper_and_trailing_data_refusal() -> None:
    codec = HmacPreparedTokenCodec(SECRET, context="test")
    payload = {"z": [3, 2, 1], "a": "value"}
    token = codec.encode(payload)
    assert codec.decode(token) == payload
    with pytest.raises(PreparedTokenError):
        codec.decode(token + "x")
    with pytest.raises(PreparedTokenError):
        codec.decode("wrong." + token)


@dataclasses.dataclass
class FakeTokenProvider:
    token: str = "github-installation-token-for-tests"

    async def installation_token(self) -> str:
        return self.token


class QueueTransport:
    def __init__(self, responses: Sequence[HttpResponse | Exception]) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, object]] = []

    async def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | None,
        timeout_seconds: float,
    ) -> HttpResponse:
        self.requests.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers),
                "body": body,
                "timeout_seconds": timeout_seconds,
            }
        )
        if not self.responses:
            raise AssertionError("unexpected HTTP request")
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def _json_response(value: object, *, headers: Mapping[str, str] | None = None) -> HttpResponse:
    return HttpResponse(
        status=200,
        headers=dict(headers or {}),
        body=json.dumps(value).encode(),
    )


def test_fixed_http_port_reads_exact_head_and_never_model_selects_endpoint() -> None:
    transport = QueueTransport([_json_response({"object": {"sha": HEAD}})])
    port = GithubApiPatchPort(transport=transport, token_provider=FakeTokenProvider())
    assert _run(port.read_branch_head(_target())) == HEAD
    request = transport.requests[0]
    assert request["method"] == "GET"
    assert str(request["url"]).startswith(f"{REST_ROOT}/repos/")
    assert request["body"] is None
    assert request["headers"]["Authorization"].startswith("Bearer ")


def test_fixed_http_port_traverses_git_tree_and_reads_complete_regular_blob() -> None:
    content = "alpha\nbeta\ngamma\n"
    blob_oid = _git_blob_oid(content)
    tree_root = "b" * 40
    tree_child = "c" * 40
    transport = QueueTransport(
        [
            _json_response({"tree": {"sha": tree_root}}),
            _json_response(
                {"tree": [{"path": "control_plane", "type": "tree", "mode": "040000", "sha": tree_child}]}
            ),
            _json_response(
                {"tree": [{"path": "large_fixture.py", "type": "blob", "mode": "100644", "sha": blob_oid}]}
            ),
            _json_response(
                {
                    "encoding": "base64",
                    "sha": blob_oid,
                    "size": len(content.encode()),
                    "content": base64.b64encode(content.encode()).decode(),
                }
            ),
        ]
    )
    port = GithubApiPatchPort(transport=transport, token_provider=FakeTokenProvider())
    blob = _run(port.read_blob(_target(), HEAD, PATH))
    assert blob == GithubBlob(path=PATH, oid=blob_oid, content=content)
    assert len(transport.requests) == 4
    assert all(str(row["url"]).startswith(f"{REST_ROOT}/repos/") for row in transport.requests)


def test_fixed_http_port_refuses_symlink_or_executable_mode() -> None:
    transport = QueueTransport(
        [
            _json_response({"tree": {"sha": "b" * 40}}),
            _json_response(
                {"tree": [{"path": "control_plane", "type": "tree", "mode": "040000", "sha": "c" * 40}]}
            ),
            _json_response(
                {"tree": [{"path": "large_fixture.py", "type": "blob", "mode": "100755", "sha": "d" * 40}]}
            ),
        ]
    )
    port = GithubApiPatchPort(transport=transport, token_provider=FakeTokenProvider())
    with pytest.raises(GithubReadError):
        _run(port.read_blob(_target(), HEAD, PATH))


def test_fixed_http_port_emits_one_expected_head_graphql_commit_with_fixed_marker() -> None:
    content = "alpha\r\nrepaired\r\ngamma"
    after = hashlib.sha256(content.encode()).hexdigest()
    commit_oid = "c" * 40
    transport = QueueTransport(
        [
            _json_response(
                {
                    "data": {
                        "createCommitOnBranch": {
                            "commit": {"oid": commit_oid, "url": "https://github.com/example"}
                        }
                    }
                }
            )
        ]
    )
    port = GithubApiPatchPort(transport=transport, token_provider=FakeTokenProvider())
    result = _run(
        port.commit_branch_patch(
            _target(),
            HEAD,
            OPERATION,
            "e" * 64,
            (
                CommitFile(
                    path=PATH,
                    expected_blob_oid="f" * 40,
                    content=content,
                    after_sha256=after,
                ),
            ),
        )
    )
    assert result.commit_oid == commit_oid
    assert result.request_sent is True
    assert len(transport.requests) == 1
    request = transport.requests[0]
    assert request["method"] == "POST"
    assert request["url"] == GRAPHQL_ENDPOINT
    payload = json.loads(request["body"])
    variables = payload["variables"]["input"]
    assert variables["branch"] == {
        "repositoryNameWithOwner": REPOSITORY,
        "branchName": BRANCH,
    }
    assert variables["expectedHeadOid"] == HEAD
    assert base64.b64decode(variables["fileChanges"]["additions"][0]["contents"]) == content.encode()
    assert f"Mastermind-Operation: {OPERATION}" in variables["message"]["body"]
    assert "force" not in json.dumps(payload).lower()


def test_fixed_http_port_reconcile_not_applied_and_moved_unknown() -> None:
    target = _target()
    not_applied_transport = QueueTransport(
        [
            _json_response({"object": {"sha": HEAD}}),
            _json_response([], headers={}),
        ]
    )
    port = GithubApiPatchPort(transport=not_applied_transport, token_provider=FakeTokenProvider())
    observation = _run(
        port.reconcile_branch_patch(target, HEAD, OPERATION, "e" * 64, {PATH: "f" * 64})
    )
    assert observation.state is EffectState.NOT_APPLIED
    assert observation.complete is True

    moved_transport = QueueTransport(
        [
            _json_response({"object": {"sha": "b" * 40}}),
            _json_response([], headers={}),
        ]
    )
    moved_port = GithubApiPatchPort(transport=moved_transport, token_provider=FakeTokenProvider())
    moved = _run(
        moved_port.reconcile_branch_patch(target, HEAD, OPERATION, "e" * 64, {PATH: "f" * 64})
    )
    assert moved.state is EffectState.EFFECT_UNKNOWN
    assert moved.complete is False


def test_fixed_http_port_transport_failure_is_effect_possible_after_commit_call() -> None:
    content = "alpha\nrepaired\ngamma\n"
    after = hashlib.sha256(content.encode()).hexdigest()
    transport = QueueTransport([GithubReadError()])
    port = GithubApiPatchPort(transport=transport, token_provider=FakeTokenProvider())
    with pytest.raises(NativeCommitError) as caught:
        _run(
            port.commit_branch_patch(
                _target(),
                HEAD,
                OPERATION,
                "e" * 64,
                (
                    CommitFile(
                        path=PATH,
                        expected_blob_oid="f" * 40,
                        content=content,
                        after_sha256=after,
                    ),
                )
            )
        )
    assert caught.value.effect_possible is True

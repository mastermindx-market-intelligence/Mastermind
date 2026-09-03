from __future__ import annotations

import asyncio
import base64
import dataclasses
import hashlib
import json
from collections.abc import Mapping, Sequence

import pytest

from integrations.mastermind_github_app.adapter import (
    COMMIT_TOOL,
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
from integrations.mastermind_github_app.prepared_token import HmacPreparedTokenCodec, PreparedTokenError
from integrations.mastermind_github_app.schemas import SCHEMA_DIGEST, TOOL_SPECS

OPERATION = "mastermind-ghp2-test-op"
REPOSITORY = "mastermindx-market-intelligence/Mastermind"
DEFAULT_BRANCH = "master"
BRANCH = "sol/ghp2-test"
PATH = "control_plane/large_fixture.py"
HEAD = "a" * 40
PRINCIPAL = "1" * 64
SECRET = b"s" * 32


def _run(awaitable):
    return asyncio.run(awaitable)


def _git_blob_oid(content: str, *, sha256: bool = False) -> str:
    raw = content.encode("utf-8")
    framed = b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    if sha256:
        return hashlib.sha256(framed).hexdigest()
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
            raise RuntimeError("private authentication payload")
        return self.principal


@dataclasses.dataclass
class FakeAuthorityResolver:
    target: ResolvedPatchTarget
    fail: bool = False
    calls: int = 0

    async def resolve_patch_target(
        self,
        operation_key: str,
        principal_digest: str,
    ) -> ResolvedPatchTarget:
        self.calls += 1
        if self.fail:
            raise RuntimeError("private authority payload")
        assert operation_key == OPERATION
        assert principal_digest == PRINCIPAL
        return self.target


class FakeGithub:
    def __init__(self, content: str) -> None:
        self.head = HEAD
        self.blobs = {PATH: GithubBlob(PATH, _git_blob_oid(content), content)}
        self.commit_mode = "success"
        self.commit_calls = 0
        self.read_head_calls = 0
        self.read_blob_calls = 0
        self.move_head_on_read: int | None = None
        self.fail_head_on_read: int | None = None
        self.applied: dict[str, tuple[str, dict[str, str]]] = {}
        self.effect_unknown: set[str] = set()

    async def read_branch_head(self, target: ResolvedPatchTarget) -> str:
        self.read_head_calls += 1
        assert target.repository == REPOSITORY
        if self.fail_head_on_read == self.read_head_calls:
            raise RuntimeError("private head-read payload")
        if self.move_head_on_read == self.read_head_calls:
            self.head = "d" * 40
        return self.head

    async def read_blob(
        self,
        target: ResolvedPatchTarget,
        head_oid: str,
        path: str,
    ) -> GithubBlob:
        self.read_blob_calls += 1
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
        assert target.default_branch == DEFAULT_BRANCH
        assert expected_head_oid == HEAD
        assert operation_key == OPERATION
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
            assert hashlib.sha256(item.content.encode()).hexdigest() == item.after_sha256
            self.blobs[item.path] = GithubBlob(item.path, _git_blob_oid(item.content), item.content)
            after[item.path] = item.after_sha256
        self.head = commit_oid
        self.applied[effect_digest] = (commit_oid, after)
        if self.commit_mode == "ambiguous_applied":
            raise NativeCommitError(effect_possible=True)
        return NativeCommitResult(True, commit_oid, False)

    async def reconcile_branch_patch(
        self,
        target: ResolvedPatchTarget,
        expected_head_oid: str,
        operation_key: str,
        effect_digest: str,
        expected_after_sha256: Mapping[str, str],
    ) -> EffectObservation:
        assert target.repository == REPOSITORY
        assert target.default_branch == DEFAULT_BRANCH
        if effect_digest in self.effect_unknown:
            return EffectObservation(EffectState.EFFECT_UNKNOWN, None, self.head, False)
        if effect_digest in self.applied:
            commit_oid, after = self.applied[effect_digest]
            assert dict(expected_after_sha256) == after
            return EffectObservation(EffectState.APPLIED, commit_oid, self.head, True)
        return EffectObservation(EffectState.NOT_APPLIED, None, self.head, True)


def _target(**changes: object) -> ResolvedPatchTarget:
    base = ResolvedPatchTarget(
        operation_key=OPERATION,
        repository=REPOSITORY,
        default_branch=DEFAULT_BRANCH,
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
        "new_text": "line-06000\nline-06001-repaired\nline-06001-proof\nline-06002\n",
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


def _effect_digest(result: Mapping[str, object]) -> str:
    data = result["data"]
    assert isinstance(data, Mapping)
    value = data["normalized_effect_digest"]
    assert isinstance(value, str)
    return value


def test_tool_surface_is_exact_and_has_no_model_selected_repository_or_branch() -> None:
    assert [spec.name for spec in TOOL_SPECS] == [PREPARE_TOOL, COMMIT_TOOL, RECONCILE_TOOL]
    properties = TOOL_SPECS[0].input_schema["properties"]
    assert isinstance(properties, Mapping)
    assert set(properties) == {"operation_key", "expected_head_oid", "files"}
    rendered = json.dumps([spec.input_schema for spec in TOOL_SPECS], sort_keys=True)
    for forbidden in ("repository", "branch", "url", "method", "credential", "force", "shell"):
        assert f'"{forbidden}"' not in rendered


def test_prepare_materializes_large_file_server_side_and_returns_bounded_preview() -> None:
    github = FakeGithub(_source())
    gateway, _, _ = _gateway(github)
    result = _prepare(gateway, github)
    assert result["status"] == "OK"
    data = result["data"]
    assert isinstance(data, Mapping)
    assert data["preview_state"] == "READY"
    assert isinstance(data["prepared_token"], str)
    public = json.dumps(data, sort_keys=True)
    assert "line-00001" not in public
    assert "line-12050" not in public
    assert "line-06001-repaired" in public
    assert github.commit_calls == 0
    assert github.read_head_calls == 2


def test_prepare_refuses_head_movement_after_blob_materialization() -> None:
    github = FakeGithub(_source())
    github.move_head_on_read = 2
    gateway, _, _ = _gateway(github)
    result = _prepare(gateway, github)
    assert result["status"] == "BLOCKED"
    assert result["issues"] == [IssueCode.BRANCH_HEAD_MOVED.value]
    assert "prepared_token" not in result["data"]
    assert github.commit_calls == 0


def test_prepare_requires_explicit_default_branch_and_refuses_protected_target() -> None:
    github = FakeGithub(_source())
    gateway, _, _ = _gateway(github, target=_target(default_branch="release", protected_branches=("release",)))
    assert _prepare(gateway, github)["status"] == "OK"
    protected_gateway, _, _ = _gateway(github, target=_target(branch="master"))
    protected = _prepare(protected_gateway, github)
    assert protected["status"] == "REFUSED"
    assert IssueCode.PROTECTED_BRANCH_REFUSED.value in protected["issues"]


def test_prepare_disarmed_returns_preview_but_no_token() -> None:
    github = FakeGithub(_source())
    gateway, _, _ = _gateway(github, armed=False)
    result = _prepare(gateway, github)
    assert result["status"] == "BLOCKED"
    assert result["issues"] == [IssueCode.PRODUCTION_DISARMED.value]
    assert result["data"]["prepared_token"] is None


def test_exact_commit_is_applied_once_and_repeated_commit_is_read_only() -> None:
    github = FakeGithub(_source())
    gateway, _, _ = _gateway(github)
    prepared = _prepare(gateway, github)
    token = _token(prepared)
    first = _run(gateway.call(COMMIT_TOOL, {"prepared_token": token}))
    assert first["status"] == "OK"
    assert first["data"]["effect_state"] == EffectState.APPLIED.value
    assert first["data"]["native_request_attempts"] == 1
    assert github.commit_calls == 1
    second = _run(gateway.call(COMMIT_TOOL, {"prepared_token": token}))
    assert second["status"] == "OK"
    assert second["data"]["effect_state"] == EffectState.APPLIED.value
    assert second["data"]["native_request_attempts"] == 0
    assert github.commit_calls == 1


def test_commit_reconciles_applied_effect_before_current_authority_resolution() -> None:
    github = FakeGithub(_source())
    gateway, _, resolver = _gateway(github)
    prepared = _prepare(gateway, github)
    token = _token(prepared)
    applied = _run(gateway.call(COMMIT_TOOL, {"prepared_token": token}))
    assert applied["data"]["effect_state"] == "APPLIED"
    resolver.fail = True
    repeated = _run(gateway.call(COMMIT_TOOL, {"prepared_token": token}))
    assert repeated["status"] == "OK"
    assert repeated["data"]["effect_state"] == "APPLIED"
    assert repeated["data"]["native_request_attempts"] == 0
    assert github.commit_calls == 1


def test_reconcile_is_token_bound_and_survives_authority_writer_or_path_change() -> None:
    github = FakeGithub(_source())
    gateway, _, resolver = _gateway(github)
    prepared = _prepare(gateway, github)
    token = _token(prepared)
    effect = _effect_digest(prepared)
    _run(gateway.call(COMMIT_TOOL, {"prepared_token": token}))
    resolver.target = _target(
        patch_eligibility=PatchEligibility.REFUSED,
        allowed_paths=("different.py",),
        writer_digest="f" * 64,
        issues=(IssueCode.CARRIER_WRITER_CONFLICT,),
    )
    resolver.fail = True
    before = resolver.calls
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
    assert result["data"]["effect_state"] == "APPLIED"
    assert resolver.calls == before


def test_pre_effect_head_read_failure_remains_definite_not_applied() -> None:
    github = FakeGithub(_source())
    gateway, _, _ = _gateway(github)
    prepared = _prepare(gateway, github)
    github.fail_head_on_read = 3
    result = _run(gateway.call(COMMIT_TOOL, {"prepared_token": _token(prepared)}))
    assert result["status"] == "UNKNOWN"
    assert result["data"]["effect_state"] == "NOT_APPLIED"
    assert result["data"]["native_request_attempts"] == 0
    assert result["issues"] == [IssueCode.SOURCE_TRUNCATED_OR_UNAVAILABLE.value]
    assert github.commit_calls == 0


def test_post_materialization_pre_effect_head_failure_remains_not_applied() -> None:
    github = FakeGithub(_source())
    gateway, _, _ = _gateway(github)
    prepared = _prepare(gateway, github)
    github.fail_head_on_read = 4
    result = _run(gateway.call(COMMIT_TOOL, {"prepared_token": _token(prepared)}))
    assert result["status"] == "UNKNOWN"
    assert result["data"]["effect_state"] == "NOT_APPLIED"
    assert result["data"]["native_request_attempts"] == 0
    assert github.commit_calls == 0


def test_current_authority_change_blocks_new_mutation_after_not_applied_proof() -> None:
    github = FakeGithub(_source())
    gateway, _, resolver = _gateway(github)
    prepared = _prepare(gateway, github)
    token = _token(prepared)
    resolver.target = _target(
        patch_eligibility=PatchEligibility.REFUSED,
        issues=(IssueCode.ORGANIZATIONAL_AUTHORITY_REFUSED,),
    )
    result = _run(gateway.call(COMMIT_TOOL, {"prepared_token": token}))
    assert result["status"] == "REFUSED"
    assert result["data"]["effect_state"] == "NOT_APPLIED"
    assert result["data"]["native_request_attempts"] == 0
    assert github.commit_calls == 0


def test_default_branch_change_is_a_write_precondition_change() -> None:
    github = FakeGithub(_source())
    gateway, _, resolver = _gateway(github)
    prepared = _prepare(gateway, github)
    resolver.target = _target(default_branch="release", protected_branches=("release", "master"))
    result = _run(gateway.call(COMMIT_TOOL, {"prepared_token": _token(prepared)}))
    assert result["status"] == "REFUSED"
    assert result["data"]["effect_state"] == "NOT_APPLIED"
    assert IssueCode.PRECONDITION_CHANGED.value in result["issues"]


def test_expiry_is_exclusive_at_exact_expiry_but_reconcile_remains_available() -> None:
    github = FakeGithub(_source())
    gateway, clock, _ = _gateway(github)
    prepared = _prepare(gateway, github)
    token = _token(prepared)
    effect = _effect_digest(prepared)
    clock.value += 300
    commit = _run(gateway.call(COMMIT_TOOL, {"prepared_token": token}))
    assert commit["status"] == "REFUSED"
    assert commit["issues"] == [IssueCode.PREPARED_ACTION_EXPIRED.value]
    reconcile = _run(
        gateway.call(
            RECONCILE_TOOL,
            {
                "operation_key": OPERATION,
                "normalized_effect_digest": effect,
                "prepared_token": token,
            },
        )
    )
    assert reconcile["status"] == "OK"
    assert reconcile["data"]["effect_state"] == "NOT_APPLIED"


@pytest.mark.parametrize(
    ("mode", "state", "attempts"),
    [
        ("definite_refusal", "NOT_APPLIED", 1),
        ("ambiguous_not_applied", "NOT_APPLIED", 1),
        ("ambiguous_unknown", "EFFECT_UNKNOWN", 1),
        ("ambiguous_applied", "APPLIED", 1),
    ],
)
def test_native_write_outcomes_are_reconciled_without_retry(
    mode: str,
    state: str,
    attempts: int,
) -> None:
    github = FakeGithub(_source())
    github.commit_mode = mode
    gateway, _, _ = _gateway(github)
    prepared = _prepare(gateway, github)
    result = _run(gateway.call(COMMIT_TOOL, {"prepared_token": _token(prepared)}))
    assert result["data"]["effect_state"] == state
    assert result["data"]["native_request_attempts"] == attempts
    assert github.commit_calls == 1


def test_tampered_token_wrong_principal_and_missing_scope_refuse() -> None:
    github = FakeGithub(_source())
    gateway, _, _ = _gateway(github)
    prepared = _prepare(gateway, github)
    token = _token(prepared)
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
    assert _run(gateway.call(COMMIT_TOOL, {"prepared_token": tampered}))["issues"] == [
        IssueCode.PREPARED_TOKEN_INVALID.value
    ]

    wrong_gateway, _, _ = _gateway(
        github,
        principal=AuthenticatedPrincipal("9" * 64, ("mastermind.github.exact_branch_repair",)),
    )
    wrong = _run(wrong_gateway.call(COMMIT_TOOL, {"prepared_token": token}))
    assert IssueCode.AUTHENTICATION_REFUSED.value in wrong["issues"]

    no_scope_gateway, _, _ = _gateway(
        github,
        principal=AuthenticatedPrincipal(PRINCIPAL, ()),
    )
    no_scope = _prepare(no_scope_gateway, github)
    assert no_scope["issues"] == [IssueCode.SCOPE_REFUSED.value]


def test_forged_source_bytes_with_claimed_blob_oid_fail_closed() -> None:
    github = FakeGithub(_source())
    real = github.blobs[PATH]
    github.blobs[PATH] = dataclasses.replace(real, content=real.content + "forged\n")
    gateway, _, _ = _gateway(github)
    result = _prepare(gateway, github)
    assert result["status"] == "REFUSED"
    assert result["issues"] == [IssueCode.SOURCE_BLOB_CONTENT_MISMATCH.value]


def test_prepared_token_codec_is_storeless_context_bound_and_bomb_safe() -> None:
    codec = HmacPreparedTokenCodec(SECRET, context="one")
    token = codec.encode({"value": "ok"})
    assert codec.decode(token) == {"value": "ok"}
    with pytest.raises(PreparedTokenError):
        HmacPreparedTokenCodec(SECRET, context="two").decode(token)
    with pytest.raises(PreparedTokenError):
        codec.decode("not-a-token")


@dataclasses.dataclass
class QueueTokenProvider:
    token: str = "installation-token-1234567890"

    async def installation_token(self) -> str:
        return self.token


class QueueTransport:
    def __init__(self, responses: list[HttpResponse]) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, object]] = []

    async def request(self, **kwargs: object) -> HttpResponse:
        self.requests.append(dict(kwargs))
        if not self.responses:
            raise AssertionError("unexpected HTTP request")
        return self.responses.pop(0)


def _response(value: object, *, headers: Mapping[str, str] | None = None) -> HttpResponse:
    return HttpResponse(200, headers or {}, json.dumps(value).encode())


def _tree_blob_responses(content: str, *, claimed_oid: str | None = None) -> list[HttpResponse]:
    blob_oid = claimed_oid or _git_blob_oid(content)
    return [
        _response({"tree": {"sha": "b" * 40}}),
        _response({"tree": [{"path": "control_plane", "type": "tree", "mode": "040000", "sha": "c" * 40}]}),
        _response({"tree": [{"path": "large_fixture.py", "type": "blob", "mode": "100644", "sha": blob_oid}]}),
        _response(
            {
                "sha": blob_oid,
                "encoding": "base64",
                "size": len(content.encode()),
                "content": base64.b64encode(content.encode()).decode(),
            }
        ),
    ]


def test_github_port_recomputes_blob_oid_from_returned_bytes() -> None:
    content = "hello\n"
    transport = QueueTransport(_tree_blob_responses(content))
    port = GithubApiPatchPort(transport=transport, token_provider=QueueTokenProvider())
    blob = _run(port.read_blob(_target(), HEAD, PATH))
    assert blob.oid == _git_blob_oid(content)

    forged_transport = QueueTransport(_tree_blob_responses(content, claimed_oid="f" * 40))
    forged_port = GithubApiPatchPort(
        transport=forged_transport,
        token_provider=QueueTokenProvider(),
    )
    with pytest.raises(GithubReadError):
        _run(forged_port.read_blob(_target(), HEAD, PATH))


def test_github_port_proves_not_applied_when_expected_head_is_in_scanned_history() -> None:
    current = "c" * 40
    transport = QueueTransport(
        [
            _response({"object": {"sha": current}}),
            _response(
                [
                    {"sha": current, "commit": {"message": "unrelated"}},
                    {"sha": HEAD, "commit": {"message": "base"}},
                ],
                headers={"link": '<next>; rel="next"'},
            ),
        ]
    )
    port = GithubApiPatchPort(transport=transport, token_provider=QueueTokenProvider())
    observation = _run(
        port.reconcile_branch_patch(
            _target(),
            HEAD,
            OPERATION,
            "e" * 64,
            {PATH: "f" * 64},
        )
    )
    assert observation == EffectObservation(EffectState.NOT_APPLIED, None, current, True)


def test_github_port_keeps_unknown_when_expected_head_is_not_in_scanned_history() -> None:
    current = "c" * 40
    transport = QueueTransport(
        [
            _response({"object": {"sha": current}}),
            _response([{"sha": current, "commit": {"message": "unrelated"}}]),
        ]
    )
    port = GithubApiPatchPort(transport=transport, token_provider=QueueTokenProvider())
    observation = _run(
        port.reconcile_branch_patch(
            _target(),
            HEAD,
            OPERATION,
            "e" * 64,
            {PATH: "f" * 64},
        )
    )
    assert observation.state is EffectState.EFFECT_UNKNOWN
    assert observation.complete is False


def test_github_port_commit_uses_one_fixed_graphql_expected_head_request() -> None:
    commit_oid = "c" * 40
    transport = QueueTransport(
        [_response({"data": {"createCommitOnBranch": {"commit": {"oid": commit_oid, "url": "ignored"}}}})]
    )
    port = GithubApiPatchPort(transport=transport, token_provider=QueueTokenProvider())
    content = "after\n"
    result = _run(
        port.commit_branch_patch(
            _target(),
            HEAD,
            OPERATION,
            "e" * 64,
            (CommitFile(PATH, _git_blob_oid("before\n"), content, hashlib.sha256(content.encode()).hexdigest()),),
        )
    )
    assert result.commit_oid == commit_oid
    assert len(transport.requests) == 1
    request = transport.requests[0]
    assert request["method"] == "POST"
    assert request["url"] == GRAPHQL_ENDPOINT
    body = json.loads(request["body"])
    assert body["variables"]["input"]["expectedHeadOid"] == HEAD
    assert body["variables"]["input"]["branch"] == {
        "repositoryNameWithOwner": REPOSITORY,
        "branchName": BRANCH,
    }


def test_port_refuses_arbitrary_endpoint_and_invalid_installation_token() -> None:
    transport = QueueTransport([])
    port = GithubApiPatchPort(transport=transport, token_provider=QueueTokenProvider(token="short"))
    with pytest.raises(GithubReadError):
        _run(port.read_branch_head(_target()))
    assert transport.requests == []
    assert REST_ROOT == "https://api.github.com"
    assert GRAPHQL_ENDPOINT == "https://api.github.com/graphql"

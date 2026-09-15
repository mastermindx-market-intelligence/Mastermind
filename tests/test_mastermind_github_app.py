from __future__ import annotations

import asyncio
import base64
import dataclasses
import hashlib
import json
from collections.abc import Mapping, Sequence

import pytest

from control_plane.github_exact_edit import (
    INPUT_SCHEMA,
    CarrierState,
    ExactEditAuthority,
    ExactEditRequest,
    ExactFileEditRequest,
    ExactFileSnapshot,
    ExactTextReplacement,
    PullRequestState,
    WriterState,
    compile_exact_edit,
)
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
    PatchAttemptPermit,
    PatchAttemptState,
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
    attempt_claim_calls: int = 0
    attempt_claimed: bool = False

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
        if self.attempt_claimed:
            return dataclasses.replace(
                self.target,
                attempt_permit=dataclasses.replace(
                    self.target.attempt_permit,
                    state=PatchAttemptState.CONSUMED,
                ),
            )
        return self.target

    async def claim_patch_attempt(
        self,
        operation_key: str,
        principal_digest: str,
        normalized_effect_digest: str,
        permit_id: str,
        permit_digest: str,
    ) -> PatchAttemptPermit:
        self.attempt_claim_calls += 1
        permit = self.target.attempt_permit
        assert operation_key == permit.operation_key
        assert principal_digest == PRINCIPAL
        assert normalized_effect_digest == permit.normalized_effect_digest
        assert permit_id == permit.permit_id
        assert permit_digest == permit.permit_digest
        if self.attempt_claimed:
            return dataclasses.replace(permit, state=PatchAttemptState.CONSUMED)
        self.attempt_claimed = True
        return dataclasses.replace(permit, state=PatchAttemptState.GRANTED)


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
    authorized_effect = str(changes.pop("authorized_effect_digest", "0" * 64))
    attempt_permit = changes.pop(
        "attempt_permit",
        PatchAttemptPermit(
            permit_id="attempt-1",
            permit_digest="7" * 64,
            operation_key=OPERATION,
            normalized_effect_digest=authorized_effect,
            state=PatchAttemptState.AVAILABLE,
        ),
    )
    base = ResolvedPatchTarget(
        operation_key=OPERATION,
        repository=REPOSITORY,
        default_branch=DEFAULT_BRANCH,
        branch=BRANCH,
        pull_request_number=999,
        protected_branches=("main", "master"),
        protected_branches_complete=True,
        allowed_paths=(PATH,),
        allowed_paths_complete=True,
        pull_request_state=PullRequestState.OPEN,
        branch_protected=False,
        carrier_state=CarrierState.EXACT,
        writer_state=WriterState.EXACT,
        carrier_digest="2" * 64,
        writer_digest="3" * 64,
        authority_digest="4" * 64,
        source_digest="5" * 64,
        authorized_effect_digest=authorized_effect,
        attempt_permit=attempt_permit,
        expected_actor_login="resolver-cannot-select-actor",
        expected_actor_id=987654,
        patch_eligibility=PatchEligibility.ELIGIBLE,
    )
    return dataclasses.replace(base, **changes)


def _target_with_owner_facts(**changes: object) -> ResolvedPatchTarget:
    changes.setdefault("expected_actor_login", "mastermind-github-exact-repair[bot]")
    changes.setdefault("expected_actor_id", 123456)
    attempt_state = changes.pop("attempt_permit_state", None)
    target = _target(**changes)
    if attempt_state is not None:
        target = dataclasses.replace(
            target,
            attempt_permit=dataclasses.replace(target.attempt_permit, state=PatchAttemptState(attempt_state)),
        )
    return target


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


def _owner_effect_digest(github: FakeGithub, target: ResolvedPatchTarget) -> str:
    blob = github.blobs[PATH]
    authority = ExactEditAuthority(
        operation_key=target.operation_key,
        carrier_ref=f"github:carrier:{target.carrier_digest}",
        source_ref=f"github:source:{target.source_digest}",
        repository=target.repository,
        default_branch=target.default_branch,
        branch=target.branch,
        pull_request_number=target.pull_request_number or 0,
        pull_request_state=PullRequestState.OPEN,
        branch_protected=False,
        carrier_state=CarrierState.EXACT,
        writer_state=WriterState.EXACT,
        observed_head_oid=HEAD,
        allowed_paths=target.allowed_paths,
        allowed_paths_complete=True,
    )
    request = ExactEditRequest(
        schema=INPUT_SCHEMA,
        operation_key=OPERATION,
        expected_head_oid=HEAD,
        files=(
            ExactFileEditRequest(
                path=PATH,
                expected_blob_oid=blob.oid,
                replacements=(ExactTextReplacement(**_replacement()),),
            ),
        ),
    )
    snapshot = ExactFileSnapshot(PATH, blob.oid, "100644", blob.content.encode())
    return compile_exact_edit(request, authority, (snapshot,)).canonical_digest


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
    resolved_target = target or _target()
    if resolved_target.authorized_effect_digest == "0" * 64:
        can_compile = (
            resolved_target.branch != resolved_target.default_branch
            and resolved_target.pull_request_state is PullRequestState.OPEN
            and resolved_target.branch_protected is False
            and resolved_target.protected_branches_complete is True
            and resolved_target.allowed_paths_complete is True
            and resolved_target.carrier_state is CarrierState.EXACT
            and resolved_target.writer_state is WriterState.EXACT
            and _git_blob_oid(github.blobs[PATH].content) == github.blobs[PATH].oid
        )
        effect_digest = (
            _owner_effect_digest(github, resolved_target) if can_compile else "6" * 64
        )
        resolved_target = dataclasses.replace(
            resolved_target,
            authorized_effect_digest=effect_digest,
            attempt_permit=dataclasses.replace(
                resolved_target.attempt_permit,
                normalized_effect_digest=effect_digest,
            ),
        )
    resolver = FakeAuthorityResolver(resolved_target)
    gateway = GithubPatchGateway(
        config=AppConfig(
            app_id="mastermind-github-exact-repair",
            app_generation="ghp2-exact-test-generation",
            schema_digest=SCHEMA_DIGEST,
            policy_id="ghp2-exact-test-policy",
            expected_actor_login="mastermind-github-exact-repair[bot]",
            expected_actor_id=123456,
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


def _resign_token(token: str, **changes: object) -> str:
    codec = HmacPreparedTokenCodec(SECRET, context="ghp2-exact-test")
    claims = codec.decode(token)
    claims.update(changes)
    return codec.encode(claims)


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


@pytest.mark.parametrize(
    ("owner_fact", "value", "issue"),
    [
        ("pull_request_state", PullRequestState.CLOSED, IssueCode.ORGANIZATIONAL_AUTHORITY_REFUSED.value),
        ("branch_protected", True, IssueCode.PROTECTED_BRANCH_REFUSED.value),
        ("protected_branches_complete", False, IssueCode.ACTION_TARGET_UNRESOLVED.value),
        ("allowed_paths_complete", False, IssueCode.ACTION_TARGET_UNRESOLVED.value),
        ("carrier_state", CarrierState.CONFLICT, IssueCode.OPERATION_CARRIER_CONFLICT.value),
        ("writer_state", WriterState.UNKNOWN, IssueCode.CARRIER_WRITER_CONFLICT.value),
    ],
)
def test_prepare_consumes_detailed_source_owner_authority_facts(
    owner_fact: str,
    value: object,
    issue: str,
) -> None:
    github = FakeGithub(_source())
    gateway, _, _ = _gateway(github, target=_target_with_owner_facts(**{owner_fact: value}))

    result = _prepare(gateway, github)

    assert result["status"] != "OK"
    assert issue in result["issues"]
    assert github.commit_calls == 0


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


def test_repeated_old_token_after_proven_not_applied_needs_fresh_owner_attempt_permit() -> None:
    github = FakeGithub(_source())
    github.commit_mode = "definite_refusal"
    gateway, _, _ = _gateway(github, target=_target_with_owner_facts())
    token = _token(_prepare(gateway, github))

    first = _run(gateway.call(COMMIT_TOOL, {"prepared_token": token}))
    second = _run(gateway.call(COMMIT_TOOL, {"prepared_token": token}))

    assert first["data"]["effect_state"] == EffectState.NOT_APPLIED.value
    assert first["data"]["native_request_attempts"] == 1
    assert second["status"] == "REFUSED"
    assert second["data"]["effect_state"] == EffectState.NOT_APPLIED.value
    assert second["data"]["native_request_attempts"] == 0
    assert github.commit_calls == 1


def test_fresh_owner_attempt_permit_requires_a_new_prepared_action() -> None:
    github = FakeGithub(_source())
    github.commit_mode = "definite_refusal"
    gateway, _, resolver = _gateway(github)
    old_token = _token(_prepare(gateway, github))
    first = _run(gateway.call(COMMIT_TOOL, {"prepared_token": old_token}))
    assert first["data"]["effect_state"] == EffectState.NOT_APPLIED.value
    effect = resolver.target.authorized_effect_digest
    resolver.target = dataclasses.replace(
        resolver.target,
        attempt_permit=PatchAttemptPermit(
            permit_id="attempt-2",
            permit_digest="8" * 64,
            operation_key=OPERATION,
            normalized_effect_digest=effect,
            state=PatchAttemptState.AVAILABLE,
        ),
    )
    resolver.attempt_claimed = False

    old_repeat = _run(gateway.call(COMMIT_TOOL, {"prepared_token": old_token}))
    assert old_repeat["status"] == "REFUSED"
    assert old_repeat["data"]["native_request_attempts"] == 0
    fresh_token = _token(_prepare(gateway, github))
    github.commit_mode = "success"
    fresh = _run(gateway.call(COMMIT_TOOL, {"prepared_token": fresh_token}))

    assert fresh["data"]["effect_state"] == EffectState.APPLIED.value
    assert fresh["data"]["native_request_attempts"] == 1
    assert github.commit_calls == 2


def test_same_operation_with_changed_normalized_payload_conflicts_before_token() -> None:
    github = FakeGithub(_source())
    target = _target_with_owner_facts()
    gateway, _, resolver = _gateway(github, target=target)
    first = _prepare(gateway, github)
    object.__setattr__(resolver.target, "authorized_effect_digest", _effect_digest(first))
    changed = _arguments(github)
    changed_files = changed["files"]
    assert isinstance(changed_files, list)
    changed_replacements = changed_files[0]["replacements"]
    changed_replacements[0]["new_text"] = "line-06000\nline-06001-different\nline-06002\n"

    result = _run(gateway.call(PREPARE_TOOL, changed))

    assert result["status"] == "REFUSED"
    assert result["issues"] == ["OPERATION_KEY_CONFLICT"]
    assert "prepared_token" not in result["data"]
    assert github.commit_calls == 0


def test_prepared_token_binds_actor_authority_effect_and_attempt_fields() -> None:
    github = FakeGithub(_source())
    gateway, _, _ = _gateway(github, target=_target_with_owner_facts())
    token = _token(_prepare(gateway, github))
    claims = HmacPreparedTokenCodec(SECRET, context="ghp2-exact-test").decode(token)

    assert claims["expected_actor_login"] == "mastermind-github-exact-repair[bot]"
    assert claims["expected_actor_id"] == 123456
    assert claims["pull_request_state"] == PullRequestState.OPEN.value
    assert claims["carrier_state"] == CarrierState.EXACT.value
    assert claims["writer_state"] == WriterState.EXACT.value
    assert claims["authorized_effect_digest"] == claims["normalized_effect_digest"]
    assert claims["attempt_permit_id"] == "attempt-1"
    assert claims["attempt_permit_digest"] == "7" * 64


@pytest.mark.parametrize(
    "changes",
    [
        {"expected_actor_login": "different-writer"},
        {"authority_digest": "8" * 64},
        {"normalized_effect_digest": "8" * 64},
        {"attempt_permit_digest": "8" * 64},
    ],
)
def test_resigned_tampering_of_actor_authority_effect_or_attempt_refuses_before_native_request(
    changes: dict[str, object],
) -> None:
    github = FakeGithub(_source())
    gateway, _, _ = _gateway(github)
    token = _token(_prepare(gateway, github))

    result = _run(gateway.call(COMMIT_TOOL, {"prepared_token": _resign_token(token, **changes)}))

    assert result["status"] == "REFUSED"
    assert github.commit_calls == 0


def test_commit_revalidates_detailed_authority_before_claiming_attempt() -> None:
    github = FakeGithub(_source())
    gateway, _, resolver = _gateway(github)
    token = _token(_prepare(gateway, github))
    resolver.target = dataclasses.replace(
        resolver.target,
        pull_request_state=PullRequestState.CLOSED,
    )

    result = _run(gateway.call(COMMIT_TOOL, {"prepared_token": token}))

    assert result["status"] == "REFUSED"
    assert result["data"]["effect_state"] == EffectState.NOT_APPLIED.value
    assert result["data"]["native_request_attempts"] == 0
    assert github.commit_calls == 0
    assert resolver.attempt_claim_calls == 0


def test_prior_effect_unknown_is_sticky_across_authority_and_permit_movement() -> None:
    github = FakeGithub(_source())
    github.commit_mode = "ambiguous_unknown"
    gateway, _, resolver = _gateway(github)
    token = _token(_prepare(gateway, github))
    first = _run(gateway.call(COMMIT_TOOL, {"prepared_token": token}))
    calls_after_first = resolver.calls
    resolver.target = dataclasses.replace(
        resolver.target,
        branch="sol/alternate-carrier",
        attempt_permit=dataclasses.replace(
            resolver.target.attempt_permit,
            permit_id="alternate-attempt",
            permit_digest="9" * 64,
        ),
    )

    repeated = _run(gateway.call(COMMIT_TOOL, {"prepared_token": token}))

    assert first["data"]["effect_state"] == EffectState.EFFECT_UNKNOWN.value
    assert repeated["status"] == "UNKNOWN"
    assert repeated["data"]["effect_state"] == EffectState.EFFECT_UNKNOWN.value
    assert repeated["data"]["native_request_attempts"] == 0
    assert github.commit_calls == 1
    assert resolver.calls == calls_after_first


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


@pytest.mark.parametrize(
    ("actor_login", "actor_id", "expected_state"),
    [
        ("mastermind-github-exact-repair[bot]", 123456, EffectState.APPLIED),
        ("different-writer", 123456, EffectState.EFFECT_UNKNOWN),
        ("mastermind-github-exact-repair[bot]", 999999, EffectState.EFFECT_UNKNOWN),
    ],
)
def test_github_port_requires_exact_configured_app_actor_for_applied(
    actor_login: str,
    actor_id: int,
    expected_state: EffectState,
) -> None:
    commit_oid = "c" * 40
    content = "after\n"
    after_digest = hashlib.sha256(content.encode()).hexdigest()
    target = _target_with_owner_facts()
    marker = GithubApiPatchPort._marker(OPERATION, "e" * 64, HEAD, {PATH: after_digest})
    transport = QueueTransport(
        [
            _response({"object": {"sha": commit_oid}}),
            _response([{"sha": commit_oid, "commit": {"message": marker}}]),
            _response(
                {
                    "sha": commit_oid,
                    "author": {"login": actor_login, "id": actor_id},
                    "parents": [{"sha": HEAD}],
                    "files": [{"status": "modified", "filename": PATH}],
                }
            ),
            *_tree_blob_responses(content),
        ]
    )
    port = GithubApiPatchPort(transport=transport, token_provider=QueueTokenProvider())

    observation = _run(
        port.reconcile_branch_patch(
            target,
            HEAD,
            OPERATION,
            "e" * 64,
            {PATH: after_digest},
        )
    )

    assert observation.state is expected_state


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

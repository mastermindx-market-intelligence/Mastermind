"""Bounded prepare/commit/reconcile gateway for exact GitHub branch repairs.

The gateway owns no lifecycle, branch registry, retry queue, prepared-action
store, credential, or GitHub truth. It consumes exact owner ports and the sole
GHP1 exact-replacement compiler. All external failures collapse to stable issue
codes without reflecting source, tokens, credentials, provider payloads, or
tracebacks.
"""
from __future__ import annotations

import dataclasses
import hashlib
import re
from collections.abc import Mapping, Sequence
from typing import Any

from control_plane.github_exact_edit import (
    INPUT_SCHEMA,
    CarrierState,
    ExactEditAuthority,
    ExactEditCompilation,
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
from integrations.mastermind_github_app.models import (
    RECEIPT_SCHEMA,
    AppConfig,
    AuthenticatedPrincipal,
    Clock,
    CommitFile,
    EffectObservation,
    EffectState,
    GithubBlob,
    GithubPatchPort,
    IssueCode,
    NativeCommitError,
    PatchAuthorityResolver,
    PatchEligibility,
    PrincipalProvider,
    ResolvedPatchTarget,
    ToolEnvelope,
    ToolStatus,
)
from integrations.mastermind_github_app.prepared_token import (
    HmacPreparedTokenCodec,
    PreparedTokenError,
)
from integrations.mastermind_github_app.schemas import SCHEMA_DIGEST, TOOL_BY_NAME


PREPARE_TOOL = "prepare_exact_branch_repair"
COMMIT_TOOL = "commit_exact_branch_repair"
RECONCILE_TOOL = "reconcile_exact_branch_repair"
TOKEN_SCHEMA = "mastermind.github_exact_branch_repair_prepared_token.v1"
MAX_MODEL_EDIT_BYTES = 48 * 1024

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_OID_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_OPERATION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,191}$")

_TOKEN_KEYS = frozenset(
    {
        "token_schema",
        "app_id",
        "app_generation",
        "schema_digest",
        "policy_id",
        "principal_digest",
        "operation_key",
        "repository",
        "branch",
        "pull_request_number",
        "protected_branches",
        "allowed_paths",
        "carrier_digest",
        "writer_digest",
        "authority_digest",
        "source_digest",
        "expected_head_oid",
        "files",
        "normalized_effect_digest",
        "issued_at",
        "expires_at",
    }
)
_TOKEN_FILE_KEYS = frozenset(
    {
        "path",
        "expected_blob_oid",
        "replacements",
        "before_sha256",
        "after_sha256",
        "preview_sha256",
    }
)
_TOKEN_REPLACEMENT_KEYS = frozenset({"old_text", "new_text"})

_EXACT_ERROR_MAP: dict[ExactEditIssue, IssueCode] = {
    ExactEditIssue.CARRIER_NOT_EXACT: IssueCode.OPERATION_CARRIER_CONFLICT,
    ExactEditIssue.WRITER_NOT_EXACT: IssueCode.CARRIER_WRITER_CONFLICT,
    ExactEditIssue.PULL_REQUEST_NOT_OPEN: IssueCode.ORGANIZATIONAL_AUTHORITY_REFUSED,
    ExactEditIssue.DEFAULT_BRANCH_REFUSED: IssueCode.PROTECTED_BRANCH_REFUSED,
    ExactEditIssue.PROTECTED_BRANCH_REFUSED: IssueCode.PROTECTED_BRANCH_REFUSED,
    ExactEditIssue.ALLOWED_PATH_COVERAGE_INCOMPLETE: IssueCode.ACTION_TARGET_UNRESOLVED,
    ExactEditIssue.HEAD_MOVED: IssueCode.BRANCH_HEAD_MOVED,
    ExactEditIssue.PATH_PROTECTED: IssueCode.PATCH_TARGET_NOT_OWNED,
    ExactEditIssue.PATH_NOT_ALLOWED: IssueCode.PATCH_TARGET_NOT_OWNED,
    ExactEditIssue.BLOB_MOVED: IssueCode.BLOB_OID_MOVED,
    ExactEditIssue.FILE_MODE_REFUSED: IssueCode.SOURCE_KIND_REFUSED,
    ExactEditIssue.INVALID_UTF8: IssueCode.SOURCE_KIND_REFUSED,
    ExactEditIssue.BINARY_REFUSED: IssueCode.SOURCE_KIND_REFUSED,
    ExactEditIssue.SNAPSHOT_SET_MISMATCH: IssueCode.SOURCE_TRUNCATED_OR_UNAVAILABLE,
    ExactEditIssue.FILE_COUNT_INVALID: IssueCode.PATCH_LIMIT_EXCEEDED,
    ExactEditIssue.REPLACEMENT_COUNT_INVALID: IssueCode.PATCH_LIMIT_EXCEEDED,
    ExactEditIssue.FILE_TOO_LARGE: IssueCode.PATCH_LIMIT_EXCEEDED,
    ExactEditIssue.TOTAL_SOURCE_TOO_LARGE: IssueCode.PATCH_LIMIT_EXCEEDED,
    ExactEditIssue.EDIT_TOO_LARGE: IssueCode.PATCH_LIMIT_EXCEEDED,
    ExactEditIssue.TOTAL_EDIT_TOO_LARGE: IssueCode.PATCH_LIMIT_EXCEEDED,
    ExactEditIssue.POST_IMAGE_TOO_LARGE: IssueCode.PATCH_LIMIT_EXCEEDED,
    ExactEditIssue.PREVIEW_TOO_LARGE: IssueCode.PATCH_LIMIT_EXCEEDED,
    ExactEditIssue.EMPTY_ANCHOR: IssueCode.PATCH_NO_EFFECT,
    ExactEditIssue.NOOP_REPLACEMENT: IssueCode.PATCH_NO_EFFECT,
    ExactEditIssue.ANCHOR_NOT_FOUND: IssueCode.PATCH_CONTEXT_MISMATCH,
    ExactEditIssue.ANCHOR_NOT_UNIQUE: IssueCode.PATCH_CONTEXT_MISMATCH,
    ExactEditIssue.EDIT_OVERLAP: IssueCode.PATCH_CONTEXT_MISMATCH,
    ExactEditIssue.SECRET_SHAPED_CONTENT: IssueCode.PATCH_SECRET_SHAPE_REFUSED,
}


class _InputLimitError(ValueError):
    pass


@dataclasses.dataclass(frozen=True)
class _Claims:
    raw: Mapping[str, Any]
    operation_key: str
    expected_head_oid: str
    normalized_effect_digest: str
    issued_at: int
    expires_at: int


class GithubPatchGateway:
    """Exact three-tool adapter over owner-resolved authority and GitHub ports."""

    def __init__(
        self,
        *,
        config: AppConfig,
        principal_provider: PrincipalProvider,
        authority_resolver: PatchAuthorityResolver,
        github: GithubPatchPort,
        token_codec: HmacPreparedTokenCodec,
        clock: Clock,
    ) -> None:
        if config.schema_digest != SCHEMA_DIGEST:
            raise ValueError("config schema digest does not match tool schemas")
        if config.token_ttl_seconds < 30 or config.token_ttl_seconds > 900:
            raise ValueError("token ttl must be between 30 and 900 seconds")
        self._config = config
        self._principal_provider = principal_provider
        self._authority_resolver = authority_resolver
        self._github = github
        self._token_codec = token_codec
        self._clock = clock

    async def call(
        self,
        name: str,
        arguments: Mapping[str, Any] | None,
    ) -> dict[str, object]:
        now = self._clock.now()
        if name not in TOOL_BY_NAME:
            return self._envelope(
                name,
                ToolStatus.REFUSED,
                now,
                {},
                (IssueCode.CAPABILITY_UNAVAILABLE,),
            )
        if not isinstance(arguments, Mapping):
            return self._envelope(
                name,
                ToolStatus.REFUSED,
                now,
                {},
                (IssueCode.PATCH_SCHEMA_INVALID,),
            )
        if name == PREPARE_TOOL:
            return await self._prepare(dict(arguments), now)
        if name == COMMIT_TOOL:
            return await self._commit(dict(arguments), now)
        return await self._reconcile(dict(arguments), now)

    async def _prepare(self, arguments: dict[str, Any], now: int) -> dict[str, object]:
        if set(arguments) != {"operation_key", "expected_head_oid", "files"}:
            return self._refusal(PREPARE_TOOL, now, IssueCode.PATCH_SCHEMA_INVALID)
        try:
            operation_key = self._operation(arguments["operation_key"])
            expected_head_oid = self._oid(arguments["expected_head_oid"])
            intents = self._parse_file_intents(arguments["files"])
        except _InputLimitError:
            return self._refusal(PREPARE_TOOL, now, IssueCode.PATCH_LIMIT_EXCEEDED)
        except ValueError:
            return self._refusal(PREPARE_TOOL, now, IssueCode.PATCH_SCHEMA_INVALID)

        principal, refusal = await self._principal(PREPARE_TOOL, now)
        if refusal is not None:
            return refusal
        assert principal is not None
        target, refusal = await self._target(PREPARE_TOOL, now, operation_key, principal)
        if refusal is not None:
            return refusal
        assert target is not None

        try:
            current_head = await self._github.read_branch_head(target)
        except Exception:
            return self._unknown(
                PREPARE_TOOL,
                now,
                IssueCode.SOURCE_TRUNCATED_OR_UNAVAILABLE,
            )
        if current_head != expected_head_oid:
            return self._envelope(
                PREPARE_TOOL,
                ToolStatus.BLOCKED,
                now,
                {"current_head_oid": current_head},
                (IssueCode.BRANCH_HEAD_MOVED,),
            )

        compilation, issue = await self._materialize(
            target=target,
            expected_head_oid=expected_head_oid,
            intents=intents,
        )
        if issue is not None:
            status = (
                ToolStatus.UNKNOWN
                if issue in {
                    IssueCode.SOURCE_TRUNCATED_OR_UNAVAILABLE,
                    IssueCode.ACTION_TARGET_UNRESOLVED,
                }
                else ToolStatus.REFUSED
            )
            return self._envelope(PREPARE_TOOL, status, now, {}, (issue,))
        assert compilation is not None

        expires_at = now + self._config.token_ttl_seconds
        data = compilation.to_public_dict()
        data["normalized_effect_digest"] = compilation.canonical_digest
        data.update(
            {
                "preview_state": "READY" if self._config.production_armed else "BLOCKED",
                "expires_at": expires_at if self._config.production_armed else None,
                "prepared_token": None,
            }
        )
        if not self._config.production_armed:
            return self._envelope(
                PREPARE_TOOL,
                ToolStatus.BLOCKED,
                now,
                data,
                (IssueCode.PRODUCTION_DISARMED,),
            )

        claims = self._claims_payload(
            now=now,
            expires_at=expires_at,
            principal=principal,
            target=target,
            expected_head_oid=expected_head_oid,
            intents=intents,
            compilation=compilation,
        )
        try:
            token = self._token_codec.encode(claims)
        except PreparedTokenError:
            return self._unknown(PREPARE_TOOL, now, IssueCode.INTERNAL_CONTRACT_ERROR)
        data["prepared_token"] = token
        return self._envelope(PREPARE_TOOL, ToolStatus.OK, now, data, ())

    async def _commit(self, arguments: dict[str, Any], now: int) -> dict[str, object]:
        if set(arguments) != {"prepared_token"}:
            return self._refusal(COMMIT_TOOL, now, IssueCode.PATCH_SCHEMA_INVALID)
        if not self._config.production_armed:
            return self._refusal(COMMIT_TOOL, now, IssueCode.PRODUCTION_DISARMED)

        claims, issue = self._decode_claims(arguments.get("prepared_token"), now, enforce_expiry=True)
        if issue is not None:
            return self._refusal(COMMIT_TOOL, now, issue)
        assert claims is not None

        principal, refusal = await self._principal(COMMIT_TOOL, now)
        if refusal is not None:
            return refusal
        assert principal is not None
        if claims.raw["principal_digest"] != principal.principal_digest:
            return self._refusal(COMMIT_TOOL, now, IssueCode.AUTHENTICATION_REFUSED)

        target, refusal = await self._target(
            COMMIT_TOOL,
            now,
            claims.operation_key,
            principal,
        )
        if refusal is not None:
            return refusal
        assert target is not None
        if not self._target_matches_claims(target, claims.raw):
            return self._refusal(COMMIT_TOOL, now, IssueCode.PRECONDITION_CHANGED)

        observation = await self._observe(target, claims)
        if observation.state is EffectState.APPLIED:
            return self._receipt(
                COMMIT_TOOL,
                now,
                claims,
                observation,
                native_request_attempts=0,
            )
        if observation.state is EffectState.EFFECT_UNKNOWN or not observation.complete:
            return self._receipt(
                COMMIT_TOOL,
                now,
                claims,
                EffectObservation(
                    state=EffectState.EFFECT_UNKNOWN,
                    commit_oid=observation.commit_oid,
                    branch_head_oid=observation.branch_head_oid,
                    complete=False,
                ),
                native_request_attempts=0,
                issues=(IssueCode.PRIOR_EFFECT_UNKNOWN,),
            )

        try:
            current_head = await self._github.read_branch_head(target)
        except Exception:
            return self._effect_unknown_receipt(
                COMMIT_TOOL,
                now,
                claims,
                native_request_attempts=0,
            )
        if current_head != claims.expected_head_oid:
            return self._receipt(
                COMMIT_TOOL,
                now,
                claims,
                EffectObservation(
                    state=EffectState.NOT_APPLIED,
                    commit_oid=None,
                    branch_head_oid=current_head,
                    complete=True,
                ),
                native_request_attempts=0,
                issues=(IssueCode.BRANCH_HEAD_MOVED,),
                status=ToolStatus.BLOCKED,
            )

        intents = self._claims_intents(claims.raw)
        compilation, issue = await self._materialize(
            target=target,
            expected_head_oid=claims.expected_head_oid,
            intents=intents,
        )
        if issue is not None:
            return self._receipt(
                COMMIT_TOOL,
                now,
                claims,
                EffectObservation(
                    state=EffectState.NOT_APPLIED,
                    commit_oid=None,
                    branch_head_oid=current_head,
                    complete=True,
                ),
                native_request_attempts=0,
                issues=(IssueCode.PRECONDITION_CHANGED,),
                status=ToolStatus.REFUSED,
            )
        assert compilation is not None
        if not self._compilation_matches_claims(compilation, claims.raw):
            return self._receipt(
                COMMIT_TOOL,
                now,
                claims,
                EffectObservation(
                    state=EffectState.NOT_APPLIED,
                    commit_oid=None,
                    branch_head_oid=current_head,
                    complete=True,
                ),
                native_request_attempts=0,
                issues=(IssueCode.PRECONDITION_CHANGED,),
                status=ToolStatus.REFUSED,
            )

        commit_files = tuple(
            CommitFile(
                path=item.path,
                expected_blob_oid=item.before_blob_oid,
                content=item.post_image.decode("utf-8", errors="strict"),
                after_sha256=item.after_sha256,
            )
            for item in compilation.files
        )
        effect_possible = True
        try:
            native_result = await self._github.commit_branch_patch(
                target,
                claims.expected_head_oid,
                claims.operation_key,
                claims.normalized_effect_digest,
                commit_files,
            )
            effect_possible = native_result.request_sent and not native_result.definite_no_effect
        except NativeCommitError as exc:
            effect_possible = exc.effect_possible
        except Exception:
            effect_possible = True

        post = await self._observe(target, claims)
        if post.state is EffectState.APPLIED:
            return self._receipt(
                COMMIT_TOOL,
                now,
                claims,
                post,
                native_request_attempts=1,
            )
        if post.state is EffectState.NOT_APPLIED and post.complete and not effect_possible:
            return self._receipt(
                COMMIT_TOOL,
                now,
                claims,
                post,
                native_request_attempts=1,
                issues=(IssueCode.NATIVE_REQUEST_REFUSED,),
                status=ToolStatus.REFUSED,
            )
        return self._effect_unknown_receipt(
            COMMIT_TOOL,
            now,
            claims,
            native_request_attempts=1,
            observation=post,
        )

    async def _reconcile(self, arguments: dict[str, Any], now: int) -> dict[str, object]:
        if set(arguments) != {
            "operation_key",
            "normalized_effect_digest",
            "prepared_token",
        }:
            return self._refusal(RECONCILE_TOOL, now, IssueCode.PATCH_SCHEMA_INVALID)
        try:
            operation_key = self._operation(arguments["operation_key"])
            effect_digest = self._sha256(arguments["normalized_effect_digest"])
        except ValueError:
            return self._refusal(RECONCILE_TOOL, now, IssueCode.PATCH_SCHEMA_INVALID)

        claims, issue = self._decode_claims(
            arguments.get("prepared_token"),
            now,
            enforce_expiry=False,
        )
        if issue is not None:
            return self._refusal(RECONCILE_TOOL, now, issue)
        assert claims is not None
        if claims.operation_key != operation_key or claims.normalized_effect_digest != effect_digest:
            return self._refusal(RECONCILE_TOOL, now, IssueCode.PREPARED_TOKEN_INVALID)

        principal, refusal = await self._principal(RECONCILE_TOOL, now)
        if refusal is not None:
            return refusal
        assert principal is not None
        if claims.raw["principal_digest"] != principal.principal_digest:
            return self._refusal(RECONCILE_TOOL, now, IssueCode.AUTHENTICATION_REFUSED)

        target, refusal = await self._target(
            RECONCILE_TOOL,
            now,
            claims.operation_key,
            principal,
        )
        if refusal is not None:
            return refusal
        assert target is not None
        if not self._target_matches_claims(target, claims.raw):
            return self._effect_unknown_receipt(
                RECONCILE_TOOL,
                now,
                claims,
                native_request_attempts=0,
                issues=(IssueCode.PRECONDITION_CHANGED,),
            )

        observation = await self._observe(target, claims)
        return self._receipt(
            RECONCILE_TOOL,
            now,
            claims,
            observation,
            native_request_attempts=0,
            issues=(IssueCode.EFFECT_UNKNOWN,)
            if observation.state is EffectState.EFFECT_UNKNOWN or not observation.complete
            else (),
        )

    async def _principal(
        self,
        tool: str,
        now: int,
    ) -> tuple[AuthenticatedPrincipal | None, dict[str, object] | None]:
        try:
            principal = await self._principal_provider.current_principal()
        except Exception:
            return None, self._refusal(tool, now, IssueCode.AUTHENTICATION_REFUSED)
        if (
            not isinstance(principal, AuthenticatedPrincipal)
            or _HEX64_RE.fullmatch(principal.principal_digest) is None
        ):
            return None, self._refusal(tool, now, IssueCode.AUTHENTICATION_REFUSED)
        if self._config.required_scope not in principal.scopes:
            return None, self._refusal(tool, now, IssueCode.SCOPE_REFUSED)
        return principal, None

    async def _target(
        self,
        tool: str,
        now: int,
        operation_key: str,
        principal: AuthenticatedPrincipal,
    ) -> tuple[ResolvedPatchTarget | None, dict[str, object] | None]:
        try:
            target = await self._authority_resolver.resolve_patch_target(
                operation_key,
                principal.principal_digest,
            )
        except Exception:
            return None, self._unknown(tool, now, IssueCode.ACTION_TARGET_UNRESOLVED)
        if not isinstance(target, ResolvedPatchTarget) or target.operation_key != operation_key:
            return None, self._unknown(tool, now, IssueCode.ACTION_TARGET_UNRESOLVED)
        if target.patch_eligibility is PatchEligibility.UNKNOWN:
            issues = target.issues or (IssueCode.ACTION_TARGET_UNRESOLVED,)
            return None, self._envelope(tool, ToolStatus.UNKNOWN, now, {}, issues)
        if target.patch_eligibility is PatchEligibility.REFUSED:
            issues = target.issues or (IssueCode.ORGANIZATIONAL_AUTHORITY_REFUSED,)
            return None, self._envelope(tool, ToolStatus.REFUSED, now, {}, issues)
        if not self._eligible_target_shape(target):
            return None, self._unknown(tool, now, IssueCode.ACTION_TARGET_UNRESOLVED)
        if target.branch in set(target.protected_branches):
            return None, self._refusal(tool, now, IssueCode.PROTECTED_BRANCH_REFUSED)
        return target, None

    async def _materialize(
        self,
        *,
        target: ResolvedPatchTarget,
        expected_head_oid: str,
        intents: tuple[ExactFileEditRequest, ...],
    ) -> tuple[ExactEditCompilation | None, IssueCode | None]:
        snapshots: list[ExactFileSnapshot] = []
        for intent in intents:
            try:
                blob = await self._github.read_blob(target, expected_head_oid, intent.path)
            except Exception:
                return None, IssueCode.SOURCE_TRUNCATED_OR_UNAVAILABLE
            issue = self._blob_issue(blob, intent.path)
            if issue is not None:
                return None, issue
            assert isinstance(blob, GithubBlob)
            snapshots.append(
                ExactFileSnapshot(
                    path=blob.path,
                    blob_oid=blob.oid,
                    mode="100644",
                    content=blob.content.encode("utf-8"),
                )
            )

        assert target.pull_request_number is not None
        authority = ExactEditAuthority(
            operation_key=target.operation_key,
            carrier_ref=f"github:carrier:{target.carrier_digest}",
            source_ref=f"github:source:{target.source_digest}",
            repository=target.repository,
            default_branch=self._default_branch(target),
            branch=target.branch,
            pull_request_number=target.pull_request_number,
            pull_request_state=PullRequestState.OPEN,
            branch_protected=target.branch in set(target.protected_branches),
            carrier_state=CarrierState.EXACT,
            writer_state=WriterState.EXACT,
            observed_head_oid=expected_head_oid,
            allowed_paths=tuple(sorted(set(target.allowed_paths))),
            allowed_paths_complete=True,
        )
        request = ExactEditRequest(
            schema=INPUT_SCHEMA,
            operation_key=target.operation_key,
            expected_head_oid=expected_head_oid,
            files=intents,
        )
        try:
            return compile_exact_edit(request, authority, tuple(snapshots)), None
        except ExactEditError as exc:
            return None, _EXACT_ERROR_MAP.get(exc.code, IssueCode.PATCH_SCHEMA_INVALID)
        except Exception:
            return None, IssueCode.INTERNAL_CONTRACT_ERROR

    async def _observe(
        self,
        target: ResolvedPatchTarget,
        claims: _Claims,
    ) -> EffectObservation:
        try:
            observation = await self._github.reconcile_branch_patch(
                target,
                claims.expected_head_oid,
                claims.operation_key,
                claims.normalized_effect_digest,
                {
                    str(row["path"]): str(row["after_sha256"])
                    for row in claims.raw["files"]
                },
            )
        except Exception:
            return EffectObservation(
                state=EffectState.EFFECT_UNKNOWN,
                commit_oid=None,
                branch_head_oid=None,
                complete=False,
            )
        if not isinstance(observation, EffectObservation):
            return EffectObservation(
                state=EffectState.EFFECT_UNKNOWN,
                commit_oid=None,
                branch_head_oid=None,
                complete=False,
            )
        return observation

    def _decode_claims(
        self,
        token: object,
        now: int,
        *,
        enforce_expiry: bool,
    ) -> tuple[_Claims | None, IssueCode | None]:
        try:
            raw = self._token_codec.decode(token)
            claims = self._validate_claims(raw)
        except (PreparedTokenError, ValueError, KeyError, TypeError):
            return None, IssueCode.PREPARED_TOKEN_INVALID
        if (
            raw["app_id"] != self._config.app_id
            or raw["app_generation"] != self._config.app_generation
            or raw["schema_digest"] != self._config.schema_digest
            or raw["policy_id"] != self._config.policy_id
        ):
            return None, IssueCode.APP_GENERATION_MISMATCH
        if now < claims.issued_at:
            return None, IssueCode.PREPARED_TOKEN_INVALID
        if enforce_expiry and now > claims.expires_at:
            return None, IssueCode.PREPARED_ACTION_EXPIRED
        return claims, None

    def _validate_claims(self, raw: Mapping[str, Any]) -> _Claims:
        if set(raw) != _TOKEN_KEYS or raw.get("token_schema") != TOKEN_SCHEMA:
            raise ValueError("invalid claims")
        for key in (
            "app_id",
            "app_generation",
            "schema_digest",
            "policy_id",
            "principal_digest",
            "repository",
            "branch",
            "carrier_digest",
            "writer_digest",
            "authority_digest",
            "source_digest",
        ):
            if not isinstance(raw[key], str) or not raw[key]:
                raise ValueError("invalid claims")
        operation_key = self._operation(raw["operation_key"])
        expected_head_oid = self._oid(raw["expected_head_oid"])
        effect_digest = self._sha256(raw["normalized_effect_digest"])
        if _HEX64_RE.fullmatch(raw["principal_digest"]) is None:
            raise ValueError("invalid claims")
        if raw["schema_digest"] != SCHEMA_DIGEST:
            raise ValueError("invalid claims")
        pr_number = raw["pull_request_number"]
        if isinstance(pr_number, bool) or not isinstance(pr_number, int) or pr_number <= 0:
            raise ValueError("invalid claims")
        for key in ("protected_branches", "allowed_paths"):
            value = raw[key]
            if (
                not isinstance(value, list)
                or not value
                or any(not isinstance(item, str) or not item for item in value)
                or value != sorted(set(value))
            ):
                raise ValueError("invalid claims")
        files = raw["files"]
        if not isinstance(files, list) or not 1 <= len(files) <= 3:
            raise ValueError("invalid claims")
        paths: list[str] = []
        edit_bytes = 0
        for row in files:
            if not isinstance(row, dict) or set(row) != _TOKEN_FILE_KEYS:
                raise ValueError("invalid claims")
            for key in ("path", "expected_blob_oid", "before_sha256", "after_sha256", "preview_sha256"):
                if not isinstance(row[key], str) or not row[key]:
                    raise ValueError("invalid claims")
            self._oid(row["expected_blob_oid"])
            for key in ("before_sha256", "after_sha256", "preview_sha256"):
                self._sha256(row[key])
            edit_bytes += self._validate_replacements(row["replacements"])
            paths.append(row["path"])
        if paths != sorted(set(paths)) or edit_bytes > MAX_MODEL_EDIT_BYTES:
            raise ValueError("invalid claims")
        issued_at = raw["issued_at"]
        expires_at = raw["expires_at"]
        if (
            isinstance(issued_at, bool)
            or not isinstance(issued_at, int)
            or isinstance(expires_at, bool)
            or not isinstance(expires_at, int)
            or issued_at < 0
            or expires_at <= issued_at
            or expires_at - issued_at != self._config.token_ttl_seconds
        ):
            raise ValueError("invalid claims")
        return _Claims(
            raw=raw,
            operation_key=operation_key,
            expected_head_oid=expected_head_oid,
            normalized_effect_digest=effect_digest,
            issued_at=issued_at,
            expires_at=expires_at,
        )

    def _claims_payload(
        self,
        *,
        now: int,
        expires_at: int,
        principal: AuthenticatedPrincipal,
        target: ResolvedPatchTarget,
        expected_head_oid: str,
        intents: tuple[ExactFileEditRequest, ...],
        compilation: ExactEditCompilation,
    ) -> dict[str, object]:
        by_path = {item.path: item for item in intents}
        return {
            "token_schema": TOKEN_SCHEMA,
            "app_id": self._config.app_id,
            "app_generation": self._config.app_generation,
            "schema_digest": self._config.schema_digest,
            "policy_id": self._config.policy_id,
            "principal_digest": principal.principal_digest,
            "operation_key": target.operation_key,
            "repository": target.repository,
            "branch": target.branch,
            "pull_request_number": target.pull_request_number,
            "protected_branches": sorted(set(target.protected_branches)),
            "allowed_paths": sorted(set(target.allowed_paths)),
            "carrier_digest": target.carrier_digest,
            "writer_digest": target.writer_digest,
            "authority_digest": target.authority_digest,
            "source_digest": target.source_digest,
            "expected_head_oid": expected_head_oid,
            "files": [
                {
                    "path": item.path,
                    "expected_blob_oid": item.before_blob_oid,
                    "replacements": [
                        {
                            "old_text": replacement.old_text,
                            "new_text": replacement.new_text,
                        }
                        for replacement in by_path[item.path].replacements
                    ],
                    "before_sha256": item.before_sha256,
                    "after_sha256": item.after_sha256,
                    "preview_sha256": hashlib.sha256(
                        item.preview_patch.encode("utf-8")
                    ).hexdigest(),
                }
                for item in compilation.files
            ],
            "normalized_effect_digest": compilation.canonical_digest,
            "issued_at": now,
            "expires_at": expires_at,
        }

    def _target_matches_claims(
        self,
        target: ResolvedPatchTarget,
        raw: Mapping[str, Any],
    ) -> bool:
        return (
            target.operation_key == raw["operation_key"]
            and target.repository == raw["repository"]
            and target.branch == raw["branch"]
            and target.pull_request_number == raw["pull_request_number"]
            and sorted(set(target.protected_branches)) == raw["protected_branches"]
            and sorted(set(target.allowed_paths)) == raw["allowed_paths"]
            and target.carrier_digest == raw["carrier_digest"]
            and target.writer_digest == raw["writer_digest"]
            and target.authority_digest == raw["authority_digest"]
            and target.source_digest == raw["source_digest"]
            and target.patch_eligibility is PatchEligibility.ELIGIBLE
        )

    def _compilation_matches_claims(
        self,
        compilation: ExactEditCompilation,
        raw: Mapping[str, Any],
    ) -> bool:
        if compilation.canonical_digest != raw["normalized_effect_digest"]:
            return False
        expected = {
            str(row["path"]): (
                str(row["expected_blob_oid"]),
                str(row["before_sha256"]),
                str(row["after_sha256"]),
                str(row["preview_sha256"]),
            )
            for row in raw["files"]
        }
        actual = {
            item.path: (
                item.before_blob_oid,
                item.before_sha256,
                item.after_sha256,
                hashlib.sha256(item.preview_patch.encode("utf-8")).hexdigest(),
            )
            for item in compilation.files
        }
        return actual == expected

    def _claims_intents(self, raw: Mapping[str, Any]) -> tuple[ExactFileEditRequest, ...]:
        return tuple(
            ExactFileEditRequest(
                path=str(row["path"]),
                expected_blob_oid=str(row["expected_blob_oid"]),
                replacements=tuple(
                    ExactTextReplacement(
                        old_text=str(replacement["old_text"]),
                        new_text=str(replacement["new_text"]),
                    )
                    for replacement in row["replacements"]
                ),
            )
            for row in raw["files"]
        )

    def _parse_file_intents(self, value: object) -> tuple[ExactFileEditRequest, ...]:
        if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
            raise ValueError("invalid files")
        if not 1 <= len(value) <= 3:
            raise ValueError("invalid files")
        rows: list[ExactFileEditRequest] = []
        edit_bytes = 0
        for raw in value:
            if not isinstance(raw, Mapping) or set(raw) != {
                "path",
                "expected_blob_oid",
                "replacements",
            }:
                raise ValueError("invalid file")
            if not isinstance(raw["path"], str) or not isinstance(raw["expected_blob_oid"], str):
                raise ValueError("invalid file")
            replacements_raw = raw["replacements"]
            edit_bytes += self._validate_replacements(replacements_raw)
            if edit_bytes > MAX_MODEL_EDIT_BYTES:
                raise _InputLimitError("edit payload too large")
            rows.append(
                ExactFileEditRequest(
                    path=raw["path"],
                    expected_blob_oid=raw["expected_blob_oid"],
                    replacements=tuple(
                        ExactTextReplacement(
                            old_text=replacement["old_text"],
                            new_text=replacement["new_text"],
                        )
                        for replacement in replacements_raw
                    ),
                )
            )
        return tuple(rows)

    def _validate_replacements(self, value: object) -> int:
        if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
            raise ValueError("invalid replacements")
        if not 1 <= len(value) <= 10:
            raise ValueError("invalid replacements")
        total = 0
        for raw in value:
            if not isinstance(raw, Mapping) or set(raw) != _TOKEN_REPLACEMENT_KEYS:
                raise ValueError("invalid replacement")
            old_text = raw["old_text"]
            new_text = raw["new_text"]
            if not isinstance(old_text, str) or not old_text or not isinstance(new_text, str):
                raise ValueError("invalid replacement")
            total += len(old_text.encode("utf-8")) + len(new_text.encode("utf-8"))
        return total

    def _blob_issue(self, blob: object, expected_path: str) -> IssueCode | None:
        if not isinstance(blob, GithubBlob):
            return IssueCode.SOURCE_TRUNCATED_OR_UNAVAILABLE
        if blob.path != expected_path or blob.truncated:
            return IssueCode.SOURCE_TRUNCATED_OR_UNAVAILABLE
        if blob.object_kind != "REGULAR_FILE" or blob.encoding != "utf-8":
            return IssueCode.SOURCE_KIND_REFUSED
        if not isinstance(blob.content, str) or _OID_RE.fullmatch(blob.oid) is None:
            return IssueCode.SOURCE_TRUNCATED_OR_UNAVAILABLE
        return None

    def _eligible_target_shape(self, target: ResolvedPatchTarget) -> bool:
        return (
            isinstance(target.repository, str)
            and bool(target.repository)
            and isinstance(target.branch, str)
            and bool(target.branch)
            and isinstance(target.pull_request_number, int)
            and not isinstance(target.pull_request_number, bool)
            and target.pull_request_number > 0
            and isinstance(target.protected_branches, tuple)
            and bool(target.protected_branches)
            and all(isinstance(item, str) and item for item in target.protected_branches)
            and isinstance(target.allowed_paths, tuple)
            and bool(target.allowed_paths)
            and all(isinstance(item, str) and item for item in target.allowed_paths)
            and all(
                isinstance(value, str) and _HEX64_RE.fullmatch(value) is not None
                for value in (
                    target.carrier_digest,
                    target.writer_digest,
                    target.authority_digest,
                    target.source_digest,
                )
            )
        )

    @staticmethod
    def _default_branch(target: ResolvedPatchTarget) -> str:
        protected = tuple(sorted(set(target.protected_branches)))
        for candidate in ("master", "main"):
            if candidate in protected:
                return candidate
        return protected[0]

    def _operation(self, value: object) -> str:
        if not isinstance(value, str) or _OPERATION_RE.fullmatch(value) is None:
            raise ValueError("invalid operation")
        return value

    def _oid(self, value: object) -> str:
        if not isinstance(value, str) or _OID_RE.fullmatch(value) is None:
            raise ValueError("invalid oid")
        return value

    def _sha256(self, value: object) -> str:
        if not isinstance(value, str) or _HEX64_RE.fullmatch(value) is None:
            raise ValueError("invalid digest")
        return value

    def _receipt(
        self,
        tool: str,
        now: int,
        claims: _Claims,
        observation: EffectObservation,
        *,
        native_request_attempts: int,
        issues: tuple[IssueCode, ...] = (),
        status: ToolStatus | None = None,
    ) -> dict[str, object]:
        if status is None:
            status = (
                ToolStatus.OK
                if observation.state in {EffectState.APPLIED, EffectState.NOT_APPLIED}
                and observation.complete
                else ToolStatus.UNKNOWN
            )
        return self._envelope(
            tool,
            status,
            now,
            {
                "schema": RECEIPT_SCHEMA,
                "operation_key": claims.operation_key,
                "normalized_effect_digest": claims.normalized_effect_digest,
                "effect_state": observation.state.value,
                "native_request_attempts": native_request_attempts,
                "commit_oid": observation.commit_oid,
                "branch_head_oid": observation.branch_head_oid,
                "reconciled": observation.complete,
            },
            issues,
        )

    def _effect_unknown_receipt(
        self,
        tool: str,
        now: int,
        claims: _Claims,
        *,
        native_request_attempts: int,
        observation: EffectObservation | None = None,
        issues: tuple[IssueCode, ...] = (IssueCode.EFFECT_UNKNOWN,),
    ) -> dict[str, object]:
        observation = observation or EffectObservation(
            state=EffectState.EFFECT_UNKNOWN,
            commit_oid=None,
            branch_head_oid=None,
            complete=False,
        )
        if observation.state is not EffectState.EFFECT_UNKNOWN or observation.complete:
            observation = EffectObservation(
                state=EffectState.EFFECT_UNKNOWN,
                commit_oid=observation.commit_oid,
                branch_head_oid=observation.branch_head_oid,
                complete=False,
            )
        return self._receipt(
            tool,
            now,
            claims,
            observation,
            native_request_attempts=native_request_attempts,
            issues=issues,
            status=ToolStatus.UNKNOWN,
        )

    def _refusal(self, tool: str, now: int, issue: IssueCode) -> dict[str, object]:
        return self._envelope(tool, ToolStatus.REFUSED, now, {}, (issue,))

    def _unknown(self, tool: str, now: int, issue: IssueCode) -> dict[str, object]:
        return self._envelope(tool, ToolStatus.UNKNOWN, now, {}, (issue,))

    def _envelope(
        self,
        tool: str,
        status: ToolStatus,
        now: int,
        data: Mapping[str, object],
        issues: Sequence[IssueCode],
    ) -> dict[str, object]:
        unique_issues = tuple(sorted(set(issues), key=lambda item: item.value))
        return ToolEnvelope(
            tool=tool,
            status=status,
            observed_at=now,
            capability_generation=self._config.app_generation,
            data=data,
            issues=unique_issues,
        ).public_dict()


__all__ = [
    "COMMIT_TOOL",
    "MAX_MODEL_EDIT_BYTES",
    "PREPARE_TOOL",
    "RECONCILE_TOOL",
    "TOKEN_SCHEMA",
    "GithubPatchGateway",
]

"""Bounded prepare/commit/reconcile gateway for GitHub branch patches.

The gateway owns no lifecycle, branch registry, retry queue, prepared-action
store, credential, or GitHub truth. It consumes exact owner ports and the pure
GHP1 kernel. All external failures collapse to stable issue codes without
reflecting source, tokens, credentials, provider payloads, or tracebacks.
"""
from __future__ import annotations

import dataclasses
import re
from collections.abc import Mapping, Sequence
from typing import Any

from control_plane.github_branch_patch import (
    INPUT_SCHEMA,
    BranchPatchError,
    BranchPatchInput,
    BranchPatchPreparation,
    MaterializedFile,
    PatchErrorCode,
    PatchFileIntent,
    prepare_branch_patch,
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


TOKEN_SCHEMA = "mastermind.github_branch_patch_prepared_token.v1"
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
        "unified_diff",
        "before_sha256",
        "after_sha256",
        "patch_sha256",
    }
)

_PATCH_ERROR_MAP: dict[PatchErrorCode, IssueCode] = {
    PatchErrorCode.PROTECTED_BRANCH_REFUSED: IssueCode.PROTECTED_BRANCH_REFUSED,
    PatchErrorCode.PATH_NOT_OWNED: IssueCode.PATCH_TARGET_NOT_OWNED,
    PatchErrorCode.BLOB_OID_MISMATCH: IssueCode.BLOB_OID_MOVED,
    PatchErrorCode.SOURCE_TYPE_REFUSED: IssueCode.SOURCE_KIND_REFUSED,
    PatchErrorCode.SOURCE_EMPTY_REFUSED: IssueCode.SOURCE_KIND_REFUSED,
    PatchErrorCode.SOURCE_TOO_LARGE: IssueCode.PATCH_LIMIT_EXCEEDED,
    PatchErrorCode.SOURCE_NUL_REFUSED: IssueCode.SOURCE_KIND_REFUSED,
    PatchErrorCode.SOURCE_CRLF_REFUSED: IssueCode.SOURCE_KIND_REFUSED,
    PatchErrorCode.SOURCE_FINAL_NEWLINE_REQUIRED: IssueCode.SOURCE_KIND_REFUSED,
    PatchErrorCode.RESULT_TOO_LARGE: IssueCode.PATCH_LIMIT_EXCEEDED,
    PatchErrorCode.PATCH_TOO_LARGE: IssueCode.PATCH_LIMIT_EXCEEDED,
    PatchErrorCode.HUNK_LIMIT_EXCEEDED: IssueCode.PATCH_LIMIT_EXCEEDED,
    PatchErrorCode.CHANGE_LIMIT_EXCEEDED: IssueCode.PATCH_LIMIT_EXCEEDED,
    PatchErrorCode.HUNK_CONTEXT_MISMATCH: IssueCode.PATCH_CONTEXT_MISMATCH,
    PatchErrorCode.HUNK_NEW_POSITION_MISMATCH: IssueCode.PATCH_CONTEXT_MISMATCH,
    PatchErrorCode.HUNK_ORDER_INVALID: IssueCode.PATCH_CONTEXT_MISMATCH,
    PatchErrorCode.HUNK_RANGE_INVALID: IssueCode.PATCH_CONTEXT_MISMATCH,
    PatchErrorCode.NO_EFFECT: IssueCode.PATCH_NO_EFFECT,
    PatchErrorCode.SECRET_SHAPE_REFUSED: IssueCode.PATCH_SECRET_SHAPE_REFUSED,
}


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
        if name == "prepare_branch_patch":
            return await self._prepare(dict(arguments), now)
        if name == "commit_branch_patch":
            return await self._commit(dict(arguments), now)
        return await self._reconcile(dict(arguments), now)

    async def _prepare(self, arguments: dict[str, Any], now: int) -> dict[str, object]:
        if set(arguments) != {"operation_key", "expected_head_oid", "files"}:
            return self._refusal("prepare_branch_patch", now, IssueCode.PATCH_SCHEMA_INVALID)
        try:
            operation_key = self._operation(arguments["operation_key"])
            expected_head_oid = self._oid(arguments["expected_head_oid"])
            intents = self._parse_file_intents(arguments["files"])
        except ValueError:
            return self._refusal("prepare_branch_patch", now, IssueCode.PATCH_SCHEMA_INVALID)

        principal, refusal = await self._principal("prepare_branch_patch", now)
        if refusal is not None:
            return refusal
        assert principal is not None
        target, refusal = await self._target(
            "prepare_branch_patch",
            now,
            operation_key,
            principal,
        )
        if refusal is not None:
            return refusal
        assert target is not None

        try:
            current_head = await self._github.read_branch_head(target)
        except Exception:
            return self._unknown(
                "prepare_branch_patch",
                now,
                IssueCode.SOURCE_TRUNCATED_OR_UNAVAILABLE,
            )
        if current_head != expected_head_oid:
            return self._envelope(
                "prepare_branch_patch",
                ToolStatus.BLOCKED,
                now,
                {"current_head_oid": current_head},
                (IssueCode.BRANCH_HEAD_MOVED,),
            )

        preparation, issue = await self._materialize(
            target=target,
            expected_head_oid=expected_head_oid,
            intents=intents,
        )
        if issue is not None:
            status = (
                ToolStatus.UNKNOWN
                if issue is IssueCode.SOURCE_TRUNCATED_OR_UNAVAILABLE
                else ToolStatus.REFUSED
            )
            return self._envelope("prepare_branch_patch", status, now, {}, (issue,))
        assert preparation is not None

        expires_at = now + self._config.token_ttl_seconds
        data = preparation.public_dict()
        data.update(
            {
                "preview_state": "READY" if self._config.production_armed else "BLOCKED",
                "expires_at": expires_at if self._config.production_armed else None,
                "prepared_token": None,
            }
        )
        if not self._config.production_armed:
            return self._envelope(
                "prepare_branch_patch",
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
            preparation=preparation,
        )
        try:
            token = self._token_codec.encode(claims)
        except PreparedTokenError:
            return self._unknown(
                "prepare_branch_patch",
                now,
                IssueCode.INTERNAL_CONTRACT_ERROR,
            )
        data["prepared_token"] = token
        return self._envelope("prepare_branch_patch", ToolStatus.OK, now, data, ())

    async def _commit(self, arguments: dict[str, Any], now: int) -> dict[str, object]:
        if set(arguments) != {"prepared_token"}:
            return self._refusal("commit_branch_patch", now, IssueCode.PATCH_SCHEMA_INVALID)
        if not self._config.production_armed:
            return self._refusal("commit_branch_patch", now, IssueCode.PRODUCTION_DISARMED)

        claims, issue = self._decode_claims(arguments.get("prepared_token"), now, enforce_expiry=True)
        if issue is not None:
            return self._refusal("commit_branch_patch", now, issue)
        assert claims is not None

        principal, refusal = await self._principal("commit_branch_patch", now)
        if refusal is not None:
            return refusal
        assert principal is not None
        if claims.raw["principal_digest"] != principal.principal_digest:
            return self._refusal("commit_branch_patch", now, IssueCode.AUTHENTICATION_REFUSED)

        target, refusal = await self._target(
            "commit_branch_patch",
            now,
            claims.operation_key,
            principal,
        )
        if refusal is not None:
            return refusal
        assert target is not None
        if not self._target_matches_claims(target, claims.raw):
            return self._refusal("commit_branch_patch", now, IssueCode.PRECONDITION_CHANGED)

        observation = await self._observe(target, claims)
        if observation.state is EffectState.APPLIED:
            return self._receipt(
                "commit_branch_patch",
                now,
                claims,
                observation,
                native_request_attempts=0,
            )
        if observation.state is EffectState.EFFECT_UNKNOWN or not observation.complete:
            return self._receipt(
                "commit_branch_patch",
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
                "commit_branch_patch",
                now,
                claims,
                native_request_attempts=0,
            )
        if current_head != claims.expected_head_oid:
            return self._receipt(
                "commit_branch_patch",
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
        preparation, issue = await self._materialize(
            target=target,
            expected_head_oid=claims.expected_head_oid,
            intents=intents,
        )
        if issue is not None:
            return self._receipt(
                "commit_branch_patch",
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
        assert preparation is not None
        if not self._preparation_matches_claims(preparation, claims.raw):
            return self._receipt(
                "commit_branch_patch",
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
                expected_blob_oid=item.expected_blob_oid,
                content=item.result_content,
                after_sha256=item.after_sha256,
            )
            for item in preparation.files
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
                "commit_branch_patch",
                now,
                claims,
                post,
                native_request_attempts=1,
            )
        if post.state is EffectState.NOT_APPLIED and post.complete and not effect_possible:
            return self._receipt(
                "commit_branch_patch",
                now,
                claims,
                post,
                native_request_attempts=1,
                issues=(IssueCode.NATIVE_REQUEST_REFUSED,),
                status=ToolStatus.REFUSED,
            )
        return self._effect_unknown_receipt(
            "commit_branch_patch",
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
            return self._refusal("reconcile_branch_patch", now, IssueCode.PATCH_SCHEMA_INVALID)
        try:
            operation_key = self._operation(arguments["operation_key"])
            effect_digest = self._sha256(arguments["normalized_effect_digest"])
        except ValueError:
            return self._refusal("reconcile_branch_patch", now, IssueCode.PATCH_SCHEMA_INVALID)

        claims, issue = self._decode_claims(
            arguments.get("prepared_token"),
            now,
            enforce_expiry=False,
        )
        if issue is not None:
            return self._refusal("reconcile_branch_patch", now, issue)
        assert claims is not None
        if claims.operation_key != operation_key or claims.normalized_effect_digest != effect_digest:
            return self._refusal("reconcile_branch_patch", now, IssueCode.PREPARED_TOKEN_INVALID)

        principal, refusal = await self._principal("reconcile_branch_patch", now)
        if refusal is not None:
            return refusal
        assert principal is not None
        if claims.raw["principal_digest"] != principal.principal_digest:
            return self._refusal("reconcile_branch_patch", now, IssueCode.AUTHENTICATION_REFUSED)

        target, refusal = await self._target(
            "reconcile_branch_patch",
            now,
            claims.operation_key,
            principal,
        )
        if refusal is not None:
            return refusal
        assert target is not None
        if not self._target_matches_claims(target, claims.raw):
            return self._effect_unknown_receipt(
                "reconcile_branch_patch",
                now,
                claims,
                native_request_attempts=0,
                issues=(IssueCode.PRECONDITION_CHANGED,),
            )

        observation = await self._observe(target, claims)
        return self._receipt(
            "reconcile_branch_patch",
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
        return target, None

    async def _materialize(
        self,
        *,
        target: ResolvedPatchTarget,
        expected_head_oid: str,
        intents: tuple[PatchFileIntent, ...],
    ) -> tuple[BranchPatchPreparation | None, IssueCode | None]:
        materialized: dict[str, MaterializedFile] = {}
        for intent in intents:
            try:
                blob = await self._github.read_blob(target, expected_head_oid, intent.path)
            except Exception:
                return None, IssueCode.SOURCE_TRUNCATED_OR_UNAVAILABLE
            issue = self._blob_issue(blob, intent.path)
            if issue is not None:
                return None, issue
            materialized[intent.path] = MaterializedFile(
                path=blob.path,
                observed_blob_oid=blob.oid,
                content=blob.content,
            )
        request = BranchPatchInput(
            schema=INPUT_SCHEMA,
            operation_key=target.operation_key,
            repository=target.repository,
            branch=target.branch,
            expected_head_oid=expected_head_oid,
            files=intents,
        )
        try:
            return (
                prepare_branch_patch(
                    request,
                    materialized,
                    allowed_paths=target.allowed_paths,
                    protected_branches=target.protected_branches,
                ),
                None,
            )
        except BranchPatchError as exc:
            return None, _PATCH_ERROR_MAP.get(exc.code, IssueCode.PATCH_SCHEMA_INVALID)
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
        if pr_number is not None and (
            isinstance(pr_number, bool) or not isinstance(pr_number, int) or pr_number <= 0
        ):
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
        for row in files:
            if not isinstance(row, dict) or set(row) != _TOKEN_FILE_KEYS:
                raise ValueError("invalid claims")
            if not all(isinstance(row[key], str) and row[key] for key in _TOKEN_FILE_KEYS):
                raise ValueError("invalid claims")
            self._oid(row["expected_blob_oid"])
            for key in ("before_sha256", "after_sha256", "patch_sha256"):
                self._sha256(row[key])
            paths.append(row["path"])
        if paths != sorted(set(paths)):
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
        intents: tuple[PatchFileIntent, ...],
        preparation: BranchPatchPreparation,
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
                    "expected_blob_oid": item.expected_blob_oid,
                    "unified_diff": by_path[item.path].unified_diff,
                    "before_sha256": item.before_sha256,
                    "after_sha256": item.after_sha256,
                    "patch_sha256": item.patch_sha256,
                }
                for item in preparation.files
            ],
            "normalized_effect_digest": preparation.normalized_effect_digest,
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

    def _preparation_matches_claims(
        self,
        preparation: BranchPatchPreparation,
        raw: Mapping[str, Any],
    ) -> bool:
        if preparation.normalized_effect_digest != raw["normalized_effect_digest"]:
            return False
        expected = {
            str(row["path"]): (
                str(row["expected_blob_oid"]),
                str(row["before_sha256"]),
                str(row["after_sha256"]),
                str(row["patch_sha256"]),
            )
            for row in raw["files"]
        }
        actual = {
            item.path: (
                item.expected_blob_oid,
                item.before_sha256,
                item.after_sha256,
                item.patch_sha256,
            )
            for item in preparation.files
        }
        return actual == expected

    def _claims_intents(self, raw: Mapping[str, Any]) -> tuple[PatchFileIntent, ...]:
        return tuple(
            PatchFileIntent(
                path=str(row["path"]),
                expected_blob_oid=str(row["expected_blob_oid"]),
                unified_diff=str(row["unified_diff"]),
            )
            for row in raw["files"]
        )

    def _parse_file_intents(self, value: object) -> tuple[PatchFileIntent, ...]:
        if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
            raise ValueError("invalid files")
        if not 1 <= len(value) <= 3:
            raise ValueError("invalid files")
        rows: list[PatchFileIntent] = []
        for raw in value:
            if not isinstance(raw, Mapping) or set(raw) != {
                "path",
                "expected_blob_oid",
                "unified_diff",
            }:
                raise ValueError("invalid file")
            if not all(isinstance(raw[key], str) for key in raw):
                raise ValueError("invalid file")
            rows.append(
                PatchFileIntent(
                    path=raw["path"],
                    expected_blob_oid=raw["expected_blob_oid"],
                    unified_diff=raw["unified_diff"],
                )
            )
        return tuple(rows)

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


__all__ = ["TOKEN_SCHEMA", "GithubPatchGateway"]

"""Workbench-bound browser action port over an owner-bound relay.

This module reuses the existing Workbench ActionArtifactStore for browser
modifying-effect receipts. It creates no browser lifecycle registry, retry
queue, or effect database. The signed browser_ref plus OS process identity and
the deterministic relay socket name are enough to address one live resource.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import secrets
import stat
from collections.abc import Callable, Mapping
from typing import Any

from control_plane.browser_resource_contract import (
    ALLOWED_BROWSER_TOOLS,
    READ_ONLY_BROWSER_TOOLS,
)
from control_plane.codex_worker import ProcessIdentityError, ProcessInspector
from integrations.workbench_action_mcp.action_artifacts import (
    ACTION_PURPOSE_BROWSER_ACTION,
    ActionArtifactBusy,
    ActionArtifactError,
    ActionArtifactIdentity,
    ActionArtifactStore,
    ActionArtifactUncertain,
    ActionHostBinding,
    acquire_store_writer,
    claim_action,
    classify_action,
    finalize_action,
    revalidate_artifact_store,
)
from integrations.workbench_action_mcp.contracts import (
    ActionCaller,
    ProjectActionBinding,
)

from .contracts import (
    ACTION_SCHEMA,
    BrowserContractError,
    BrowserRefCodec,
    BrowserResourceRef,
    PreparedBrowserAction,
    canonical_browser_arguments,
)
from .relay import (
    RELAY_REQUEST_SCHEMA,
    RELAY_RESPONSE_SCHEMA,
    BrowserRelayError,
    relay_request,
)


class BrowserPortRefused(RuntimeError):
    """Typed Workbench browser refusal with no implied external effect."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


ResolveBinding = Callable[[ActionCaller, str], ProjectActionBinding | None]
ClockMs = Callable[[], int]
RelayRequester = Callable[..., dict[str, Any]]


def _binding_key(value: ProjectActionBinding) -> tuple[object, ...]:
    scope = value.scope
    return (
        value.project_ref,
        scope.root_device,
        scope.root_inode,
        scope.context_ref,
        scope.responsibility_ref,
        scope.operation_ref,
        scope.owner_ref,
        scope.generation,
        scope.expires_at_ms,
    )


class BrowserActionPort:
    """Read tools plus exactly-once browser action dispatch for one Workbench owner."""

    def __init__(
        self,
        *,
        resolve_binding: ResolveBinding,
        clock_ms: ClockMs,
        codec: BrowserRefCodec,
        artifact_store: ActionArtifactStore,
        host_binding: ActionHostBinding,
        inspector: ProcessInspector,
        relay_root: Path,
        relay_requester: RelayRequester = relay_request,
        action_ttl_ms: int = 5 * 60 * 1000,
        relay_timeout_seconds: float = 30.0,
    ) -> None:
        if not callable(resolve_binding) or not callable(clock_ms) or not callable(relay_requester):
            raise TypeError("browser port callbacks must be callable")
        if not isinstance(codec, BrowserRefCodec):
            raise TypeError("browser codec is required")
        if not isinstance(artifact_store, ActionArtifactStore):
            raise TypeError("browser artifact store is required")
        if not isinstance(host_binding, ActionHostBinding):
            raise TypeError("browser host binding is required")
        if not hasattr(inspector, "inspect"):
            raise TypeError("browser process inspector is required")
        if not isinstance(relay_root, Path) or not relay_root.is_absolute():
            raise TypeError("browser relay root must be absolute")
        try:
            root_stat = relay_root.lstat()
        except OSError as error:
            raise TypeError("browser relay root is unavailable") from error
        if (
            stat.S_ISLNK(root_stat.st_mode)
            or not stat.S_ISDIR(root_stat.st_mode)
            or root_stat.st_uid != os.geteuid()
            or stat.S_IMODE(root_stat.st_mode) & 0o022
        ):
            raise TypeError("browser relay root is unsafe")
        if type(action_ttl_ms) is not int or not 1000 <= action_ttl_ms <= 5 * 60 * 1000:
            raise TypeError("browser action TTL is invalid")
        if not isinstance(relay_timeout_seconds, (int, float)) or not 0 < relay_timeout_seconds <= 120:
            raise TypeError("browser relay timeout is invalid")
        self._resolve_binding = resolve_binding
        self._clock_ms = clock_ms
        self._codec = codec
        self._store = artifact_store
        self._host_binding = host_binding
        self._inspector = inspector
        self._relay_root = relay_root
        self._relay_requester = relay_requester
        self._action_ttl_ms = action_ttl_ms
        self._relay_timeout = float(relay_timeout_seconds)

    @property
    def codec(self) -> BrowserRefCodec:
        return self._codec

    def _now(self) -> int:
        value = self._clock_ms()
        if type(value) is not int or not 0 <= value < 2**63:
            raise BrowserPortRefused("CLOCK_UNAVAILABLE")
        return value

    def _binding(
        self,
        caller: ActionCaller,
        browser: BrowserResourceRef,
    ) -> ProjectActionBinding:
        if type(caller) is not ActionCaller:
            raise BrowserPortRefused("CALLER_INVALID")
        value = self._resolve_binding(caller, browser.project_ref)
        if type(value) is not ProjectActionBinding:
            raise BrowserPortRefused("BROWSER_BINDING_CHANGED")
        scope = value.scope
        if (
            caller.subject_digest != browser.subject_digest
            or caller.client_ref != browser.client_ref
            or caller.resource != browser.resource
            or value.project_ref != browser.project_ref
            or scope.context_ref != browser.context_ref
            or scope.responsibility_ref != browser.responsibility_ref
            or scope.operation_ref != browser.operation_ref
            or scope.owner_ref != browser.owner_ref
            or scope.generation != browser.generation
            or self._host_binding.host_id != browser.host_id
            or self._host_binding.boot_session_id != browser.boot_session_id
        ):
            raise BrowserPortRefused("BROWSER_BINDING_CHANGED")
        return value

    def _resource(
        self,
        caller: ActionCaller,
        browser_ref: object,
    ) -> tuple[BrowserResourceRef, ProjectActionBinding, Path]:
        now_ms = self._now()
        try:
            browser = self._codec.decode_resource(browser_ref, now_ms=now_ms)
        except BrowserContractError as error:
            raise BrowserPortRefused("BROWSER_REF_INVALID") from error
        binding = self._binding(caller, browser)
        try:
            observed = self._inspector.inspect(browser.relay_pid)
        except (ProcessIdentityError, OSError, ValueError) as error:
            raise BrowserPortRefused("PROCESS_IDENTITY_CHANGED") from error
        if (
            observed.start_identity != browser.relay_start_identity
            or observed.pgid != browser.relay_pgid
            or observed.session_id != browser.relay_session_id
            or observed.effective_uid != os.geteuid()
            or observed.real_uid != os.getuid()
            or observed.effective_gid != os.getegid()
            or observed.real_gid != os.getgid()
        ):
            raise BrowserPortRefused("PROCESS_IDENTITY_CHANGED")
        socket_path = self._relay_root / f"{browser.start_action_id}.sock"
        return browser, binding, socket_path

    def _relay(
        self,
        *,
        socket_path: Path,
        browser: BrowserResourceRef,
        request_id: str,
        tool: str,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        response = self._relay_requester(
            socket_path,
            {
                "schema": RELAY_REQUEST_SCHEMA,
                "kind": "tool",
                "request_id": request_id,
                "resource_id": browser.start_action_id,
                "tool": tool,
                "arguments": dict(arguments),
            },
            timeout=self._relay_timeout,
        )
        if (
            type(response) is not dict
            or response.get("schema") != RELAY_RESPONSE_SCHEMA
            or response.get("request_id") != request_id
            or response.get("resource_id") != browser.start_action_id
            or type(response.get("ok")) is not bool
        ):
            raise BrowserRelayError("relay response binding changed")
        return response

    def call_read_tool(
        self,
        caller: ActionCaller,
        browser_ref: object,
        tool: str,
        arguments: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        if tool not in READ_ONLY_BROWSER_TOOLS:
            raise BrowserPortRefused("MUTATING_TOOL_REQUIRES_ACTION_REF")
        try:
            canonical = canonical_browser_arguments(arguments)
        except BrowserContractError as error:
            raise BrowserPortRefused("BROWSER_ARGUMENTS_INVALID") from error
        browser, _binding, socket_path = self._resource(caller, browser_ref)
        request_id = secrets.token_hex(16)
        try:
            response = self._relay(
                socket_path=socket_path,
                browser=browser,
                request_id=request_id,
                tool=tool,
                arguments=json.loads(canonical),
            )
        except BrowserRelayError as error:
            raise BrowserPortRefused("BROWSER_READ_UNAVAILABLE") from error
        if response["ok"] is not True or type(response.get("result")) is not dict:
            raise BrowserPortRefused("BROWSER_READ_REFUSED")
        return response["result"]

    def prepare_action(
        self,
        caller: ActionCaller,
        browser_ref: object,
        tool: str,
        arguments: Mapping[str, Any],
    ) -> str:
        if tool not in ALLOWED_BROWSER_TOOLS:
            raise BrowserPortRefused("BROWSER_TOOL_NOT_GRANTED")
        if tool in READ_ONLY_BROWSER_TOOLS:
            raise BrowserPortRefused("READ_ONLY_TOOL_NEEDS_NO_ACTION_REF")
        if type(browser_ref) is not str:
            raise BrowserPortRefused("BROWSER_REF_INVALID")
        browser, binding, _socket_path = self._resource(caller, browser_ref)
        try:
            arguments_json = canonical_browser_arguments(arguments)
        except BrowserContractError as error:
            raise BrowserPortRefused("BROWSER_ARGUMENTS_INVALID") from error
        now_ms = self._now()
        expires_at_ms = min(
            now_ms + self._action_ttl_ms,
            browser.expires_at_ms,
            binding.scope.expires_at_ms,
            caller.expires_at * 1000,
        )
        if expires_at_ms <= now_ms:
            raise BrowserPortRefused("BROWSER_ACTION_EXPIRED")
        prepared = PreparedBrowserAction(
            schema=ACTION_SCHEMA,
            action_id=secrets.token_hex(16),
            browser_ref_sha256=hashlib.sha256(browser_ref.encode("utf-8")).hexdigest(),
            subject_digest=browser.subject_digest,
            client_ref=browser.client_ref,
            resource=browser.resource,
            project_ref=browser.project_ref,
            context_ref=browser.context_ref,
            responsibility_ref=browser.responsibility_ref,
            operation_ref=browser.operation_ref,
            owner_ref=browser.owner_ref,
            generation=browser.generation,
            host_id=browser.host_id,
            boot_session_id=browser.boot_session_id,
            tool_name=tool,
            arguments_json=arguments_json,
            issued_at_ms=now_ms,
            expires_at_ms=expires_at_ms,
        )
        return self._codec.encode_action(prepared)

    def _action_identity(
        self,
        browser: BrowserResourceRef,
        binding: ProjectActionBinding,
        prepared: PreparedBrowserAction,
    ) -> ActionArtifactIdentity:
        store = revalidate_artifact_store(self._store)
        return ActionArtifactIdentity(
            action_id=prepared.action_id,
            purpose=ACTION_PURPOSE_BROWSER_ACTION,
            subject_digest=prepared.subject_digest,
            client_ref=prepared.client_ref,
            resource=prepared.resource,
            project_ref=prepared.project_ref,
            context_ref=prepared.context_ref,
            responsibility_ref=prepared.responsibility_ref,
            operation_ref=prepared.operation_ref,
            owner_ref=prepared.owner_ref,
            generation=prepared.generation,
            root_device=binding.scope.root_device,
            root_inode=binding.scope.root_inode,
            store_device=store.device,
            store_inode=store.inode,
            host_id=prepared.host_id,
            boot_session_id=prepared.boot_session_id,
            relative_path=f"browser:{browser.start_action_id}:{prepared.tool_name}",
            source_identity=browser.tool_schema_digest,
        )

    def _decode_action(
        self,
        caller: ActionCaller,
        browser_ref: object,
        action_ref: object,
    ) -> tuple[BrowserResourceRef, ProjectActionBinding, Path, PreparedBrowserAction]:
        if type(browser_ref) is not str:
            raise BrowserPortRefused("BROWSER_REF_INVALID")
        browser, binding, socket_path = self._resource(caller, browser_ref)
        try:
            prepared = self._codec.decode_action(action_ref, now_ms=self._now())
        except BrowserContractError as error:
            raise BrowserPortRefused("BROWSER_ACTION_INVALID") from error
        if (
            prepared.browser_ref_sha256
            != hashlib.sha256(browser_ref.encode("utf-8")).hexdigest()
            or prepared.subject_digest != browser.subject_digest
            or prepared.client_ref != browser.client_ref
            or prepared.resource != browser.resource
            or prepared.project_ref != browser.project_ref
            or prepared.context_ref != browser.context_ref
            or prepared.responsibility_ref != browser.responsibility_ref
            or prepared.operation_ref != browser.operation_ref
            or prepared.owner_ref != browser.owner_ref
            or prepared.generation != browser.generation
            or prepared.host_id != browser.host_id
            or prepared.boot_session_id != browser.boot_session_id
        ):
            raise BrowserPortRefused("BROWSER_ACTION_BINDING_CHANGED")
        return browser, binding, socket_path, prepared

    @staticmethod
    def _classification_receipt(classified, *, reconciled: bool) -> dict[str, Any]:
        result = classified.result
        return {
            "status": "OK",
            "effect_state": classified.effect_state,
            "observed_sha256": result.observed_sha256 if result is not None else None,
            "reconciled": reconciled,
        }

    def reconcile_action(
        self,
        caller: ActionCaller,
        browser_ref: object,
        action_ref: object,
    ) -> dict[str, Any]:
        browser, binding, _socket_path, prepared = self._decode_action(
            caller, browser_ref, action_ref
        )
        identity = self._action_identity(browser, binding, prepared)
        classified = classify_action(self._store, identity)
        if classified.evidence_status == "qualified":
            return self._classification_receipt(classified, reconciled=True)
        if classified.evidence_status == "absent":
            return {
                "status": "OK",
                "effect_state": "NOT_APPLIED",
                "observed_sha256": None,
                "reconciled": True,
            }
        return {
            "status": "OK",
            "effect_state": "EFFECT_UNKNOWN",
            "observed_sha256": None,
            "reconciled": True,
        }

    def run_action(
        self,
        caller: ActionCaller,
        browser_ref: object,
        action_ref: object,
    ) -> dict[str, Any]:
        browser, binding, socket_path, prepared = self._decode_action(
            caller, browser_ref, action_ref
        )
        identity = self._action_identity(browser, binding, prepared)
        original_binding = _binding_key(binding)
        try:
            writer = acquire_store_writer(self._store)
        except ActionArtifactBusy as error:
            raise BrowserPortRefused("BROWSER_ACTION_BUSY") from error
        except ActionArtifactUncertain as error:
            raise BrowserPortRefused("BROWSER_ACTION_UNAVAILABLE") from error
        with writer:
            classified = classify_action(self._store, identity)
            if classified.evidence_status == "qualified":
                return self._classification_receipt(classified, reconciled=True)
            if classified.evidence_status != "absent":
                return {
                    "status": "OK",
                    "effect_state": "EFFECT_UNKNOWN",
                    "observed_sha256": None,
                    "reconciled": True,
                }
            outcome = claim_action(
                self._store,
                identity,
                claimed_at_ms=self._now(),
            )
            if not outcome.created:
                return {
                    "status": "OK",
                    "effect_state": "EFFECT_UNKNOWN",
                    "observed_sha256": None,
                    "reconciled": True,
                }

            # Revalidate the owner and exact relay process immediately before
            # crossing the browser-effect boundary.
            current_browser, current_binding, current_socket = self._resource(
                caller, browser_ref
            )
            if (
                _binding_key(current_binding) != original_binding
                or current_browser != browser
                or current_socket != socket_path
                or self._now() >= prepared.expires_at_ms
            ):
                finalize_action(
                    self._store,
                    identity,
                    effect_state="NOT_APPLIED",
                    observed_sha256=None,
                    completed_at_ms=self._now(),
                    durability="durable",
                    details={"reason": "binding_changed_before_dispatch"},
                )
                return {
                    "status": "OK",
                    "effect_state": "NOT_APPLIED",
                    "observed_sha256": None,
                    "reconciled": False,
                }

            try:
                response = self._relay(
                    socket_path=socket_path,
                    browser=browser,
                    request_id=prepared.action_id,
                    tool=prepared.tool_name,
                    arguments=json.loads(prepared.arguments_json),
                )
            except BrowserRelayError:
                # The durable claim already exists. A transport failure after
                # dispatch can never be converted into a retry.
                return {
                    "status": "OK",
                    "effect_state": "EFFECT_UNKNOWN",
                    "observed_sha256": None,
                    "reconciled": False,
                }

            if response["ok"] is not True:
                error = response.get("error")
                if error != "REQUEST_REFUSED":
                    return {
                        "status": "OK",
                        "effect_state": "EFFECT_UNKNOWN",
                        "observed_sha256": None,
                        "reconciled": False,
                    }
                result_record = finalize_action(
                    self._store,
                    identity,
                    effect_state="NOT_APPLIED",
                    observed_sha256=None,
                    completed_at_ms=self._now(),
                    durability="durable",
                    details={"relay_error": "REQUEST_REFUSED"},
                )
                return {
                    "status": "OK",
                    "effect_state": result_record.effect_state,
                    "observed_sha256": None,
                    "reconciled": False,
                }

            result = response.get("result")
            if type(result) is not dict:
                return {
                    "status": "OK",
                    "effect_state": "EFFECT_UNKNOWN",
                    "observed_sha256": None,
                    "reconciled": False,
                }
            try:
                result_bytes = json.dumps(
                    result,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                    allow_nan=False,
                ).encode("utf-8")
            except (TypeError, ValueError):
                return {
                    "status": "OK",
                    "effect_state": "EFFECT_UNKNOWN",
                    "observed_sha256": None,
                    "reconciled": False,
                }
            observed_sha256 = hashlib.sha256(result_bytes).hexdigest()
            effect_state = (
                "APPLIED" if result.get("isError") is False else "EFFECT_UNKNOWN"
            )
            result_record = finalize_action(
                self._store,
                identity,
                effect_state=effect_state,
                observed_sha256=observed_sha256,
                completed_at_ms=self._now(),
                durability="durable",
                details={
                    "tool": prepared.tool_name,
                    "browser_tool_effect_only": True,
                },
            )
            response_receipt: dict[str, Any] = {
                "status": "OK",
                "effect_state": result_record.effect_state,
                "observed_sha256": observed_sha256,
                "reconciled": False,
            }
            if effect_state == "APPLIED":
                response_receipt["result"] = result
            return response_receipt


__all__ = [
    "BrowserActionPort",
    "BrowserPortRefused",
]

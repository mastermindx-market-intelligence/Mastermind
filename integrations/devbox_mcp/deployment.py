"""Exact caller/target binding for one attended DevBox deployment.

This layer projects an already-approved subject/client/resource lease onto one
already-open runtime. It creates no target registry, account election, retry,
lifecycle state, credential, Codespace, process, or source writer.
"""
from __future__ import annotations

import dataclasses
import re
from collections.abc import Callable, Mapping
from typing import Any

from .codespace_runtime import CodespaceBinding, DevBoxRuntimeError
from .contracts import TOOL_NAMES
from .port import DevBoxCaller, DevBoxPortRefused

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_REF_PATTERNS = {
    "target_ref": re.compile(r"^target:[0-9a-f]{64}$"),
    "generation": re.compile(r"^generation:[0-9a-f]{64}$"),
    "owner_ref": re.compile(r"^owner:[0-9a-f]{64}$"),
}
_RUNTIME_TO_PORT = {
    "BINDING_CHANGED": "BINDING_CHANGED",
    "OPERATION_CONFLICT": "OPERATION_CONFLICT",
    "PROCESS_NOT_FOUND": "PROCESS_NOT_FOUND",
    "PROCESS_IDENTITY_UNKNOWN": "PROCESS_IDENTITY_UNKNOWN",
    "EFFECT_UNKNOWN": "EFFECT_UNKNOWN",
    "CANCEL_UNCERTAIN": "CANCEL_UNCERTAIN",
}


@dataclasses.dataclass(frozen=True)
class StableDevBoxLease:
    expected_subject_digest: str
    expected_client_ref: str
    resource: str
    required_scopes: tuple[str, ...]
    target_ref: str
    generation: str
    owner_ref: str
    repository: str
    committed_head: str
    lease_expires_at: int

    def __post_init__(self) -> None:
        if (
            type(self.expected_subject_digest) is not str
            or _HEX64.fullmatch(self.expected_subject_digest) is None
            or type(self.expected_client_ref) is not str
            or _HEX64.fullmatch(self.expected_client_ref) is None
        ):
            raise ValueError("lease caller identity is invalid")
        if (
            type(self.resource) is not str
            or not self.resource.startswith("https://")
            or not self.resource.endswith("/mcp")
            or self.resource != self.resource.strip()
        ):
            raise ValueError("lease resource is invalid")
        if self.required_scopes != ("workbench.execute",):
            raise ValueError("lease requires exact workbench.execute scope")
        for name, pattern in _REF_PATTERNS.items():
            value = getattr(self, name)
            if type(value) is not str or pattern.fullmatch(value) is None:
                raise ValueError(f"lease {name} is invalid")
        if (
            type(self.repository) is not str
            or not self.repository
            or len(self.repository) > 256
            or any(ord(ch) < 32 or ord(ch) == 127 for ch in self.repository)
        ):
            raise ValueError("lease repository identity is invalid")
        if type(self.committed_head) is not str or _HEX40.fullmatch(self.committed_head) is None:
            raise ValueError("lease committed head is invalid")
        if type(self.lease_expires_at) is not int or self.lease_expires_at <= 0:
            raise ValueError("lease expiry is invalid")


class BoundDevBoxPort:
    """Bind one exact authenticated caller lease to one exact runtime target."""

    def __init__(
        self,
        *,
        runtime: object,
        lease: StableDevBoxLease,
        now: Callable[[], int],
    ) -> None:
        if type(lease) is not StableDevBoxLease or not callable(now):
            raise TypeError("exact lease and clock are required")
        binding = getattr(runtime, "binding", None)
        if type(binding) is not CodespaceBinding:
            raise ValueError("runtime binding is unavailable")
        expected = CodespaceBinding(
            target_ref=lease.target_ref,
            generation=lease.generation,
            owner_ref=lease.owner_ref,
            repository=lease.repository,
            committed_head=lease.committed_head,
        )
        if binding != expected:
            raise ValueError("runtime binding does not match stable lease")
        for method in ("status", "start_command", "read_process", "cancel_process"):
            if not callable(getattr(runtime, method, None)):
                raise TypeError("runtime does not implement the DevBox execution port")
        self._runtime = runtime
        self._lease = lease
        self._now = now

    def _authorize(self, caller: object) -> None:
        try:
            current = self._now()
        except Exception as exc:
            raise DevBoxPortRefused("DEVBOX_REFUSED") from None
        if type(current) is not int or current < 0:
            raise DevBoxPortRefused("DEVBOX_REFUSED")
        if type(caller) is not DevBoxCaller:
            raise DevBoxPortRefused("DEVBOX_REFUSED")
        lease = self._lease
        if (
            caller.subject_digest != lease.expected_subject_digest
            or caller.client_ref != lease.expected_client_ref
            or caller.resource != lease.resource
            or caller.scopes != lease.required_scopes
            or type(caller.expires_at) is not int
            or caller.expires_at <= current
            or lease.lease_expires_at <= current
        ):
            raise DevBoxPortRefused("DEVBOX_REFUSED")

    async def call(
        self,
        caller: DevBoxCaller,
        tool_name: str,
        arguments: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        self._authorize(caller)
        if tool_name not in TOOL_NAMES:
            raise DevBoxPortRefused("DEVBOX_REFUSED")
        methods = {
            "devbox_status": self._runtime.status,
            "start_devbox_command": self._runtime.start_command,
            "read_devbox_process": self._runtime.read_process,
            "cancel_devbox_process": self._runtime.cancel_process,
        }
        try:
            result = await methods[tool_name](arguments)
        except DevBoxRuntimeError as error:
            raise DevBoxPortRefused(
                _RUNTIME_TO_PORT.get(error.code, "DEVBOX_REFUSED")
            ) from None
        except Exception:
            raise DevBoxPortRefused("DEVBOX_REFUSED") from None
        if not isinstance(result, Mapping):
            raise DevBoxPortRefused("DEVBOX_REFUSED")
        return result


__all__ = ["BoundDevBoxPort", "StableDevBoxLease"]

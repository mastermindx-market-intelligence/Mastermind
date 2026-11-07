"""Two-stage live owner acquisition for Session Truth / Context Fabric.

The surrounding authenticated plugin/service owns credentials and API clients. This
module only coordinates injected read-only owner ports, preserves exact source schemas,
and composes one Session Truth input document. It creates no client, retry plane,
cache, persistence layer, lifecycle state, identity registry, or source mutation.

Acquisition order is intentional:
1. base protected Skillpack + Agent OS and GitHub can be read concurrently;
2. exact Linear identities exposed by scoped GitHub rows are added to caller seeds;
3. Linear/Slack/Executive/identity ports run concurrently using the derived exact scope.

Every returned owner document is normalized by the existing Session Truth normalizers.
"""

from __future__ import annotations

import asyncio
import dataclasses
import re
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from control_plane.session_truth_contract import INPUT_SCHEMA
from control_plane.session_truth_snapshots import (
    normalize_executive,
    normalize_github,
    normalize_identities,
    normalize_linear,
    normalize_slack,
)

_WS_RE = re.compile(r"^WS:[A-Z0-9][A-Z0-9-]*$")
_MAS_RE = re.compile(r"^MAS-[0-9]+$")
_REPO_RE = re.compile(r"^[^/\s]+/[^/\s]+$")
_OPERATION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
MAX_IDENTITIES = 32


class LiveAcquisitionError(ValueError):
    """Injected live owner evidence is malformed or inconsistent."""


@dataclasses.dataclass(frozen=True)
class LiveScope:
    workstreams: tuple[str, ...]
    linear: tuple[str, ...]
    repositories: tuple[str, ...]
    operation_key: str | None
    requires_executive: bool

    def __post_init__(self) -> None:
        if (
            type(self.workstreams) is not tuple
            or not self.workstreams
            or len(self.workstreams) > MAX_IDENTITIES
            or len(self.workstreams) != len(set(self.workstreams))
            or any(_WS_RE.fullmatch(item) is None for item in self.workstreams)
        ):
            raise LiveAcquisitionError("workstreams are invalid")
        if (
            type(self.linear) is not tuple
            or len(self.linear) > MAX_IDENTITIES
            or len(self.linear) != len(set(self.linear))
            or any(_MAS_RE.fullmatch(item) is None for item in self.linear)
        ):
            raise LiveAcquisitionError("Linear identities are invalid")
        if (
            type(self.repositories) is not tuple
            or not self.repositories
            or len(self.repositories) > MAX_IDENTITIES
            or len(self.repositories) != len(set(self.repositories))
            or any(_REPO_RE.fullmatch(item) is None for item in self.repositories)
        ):
            raise LiveAcquisitionError("repositories are invalid")
        if self.operation_key is not None and (
            type(self.operation_key) is not str
            or _OPERATION_RE.fullmatch(self.operation_key) is None
        ):
            raise LiveAcquisitionError("operation_key is invalid")
        if type(self.requires_executive) is not bool:
            raise LiveAcquisitionError("requires_executive must be boolean")


@dataclasses.dataclass(frozen=True)
class ExternalScope:
    workstreams: tuple[str, ...]
    linear: tuple[str, ...]
    repositories: tuple[str, ...]
    operation_key: str | None
    requires_executive: bool


BasePort = Callable[[LiveScope], Awaitable[Mapping[str, Any]]]
OwnerPort = Callable[[ExternalScope], Awaitable[Mapping[str, Any]]]


@dataclasses.dataclass(frozen=True)
class LiveOwnerPorts:
    base: BasePort
    github: OwnerPort
    linear: OwnerPort
    slack: OwnerPort
    executive: OwnerPort
    identities: OwnerPort

    def __post_init__(self) -> None:
        if any(
            not callable(value)
            for value in (
                self.base,
                self.github,
                self.linear,
                self.slack,
                self.executive,
                self.identities,
            )
        ):
            raise LiveAcquisitionError("all live owner ports must be callable")


def _external_scope(
    scope: LiveScope, *, linear: tuple[str, ...] | None = None
) -> ExternalScope:
    return ExternalScope(
        workstreams=scope.workstreams,
        linear=scope.linear if linear is None else linear,
        repositories=scope.repositories,
        operation_key=scope.operation_key,
        requires_executive=scope.requires_executive,
    )


async def _await_port(call, label: str) -> Mapping[str, Any]:
    try:
        value = await call
    except Exception as exc:
        raise LiveAcquisitionError(f"{label} owner read failed") from exc
    if not isinstance(value, Mapping):
        raise LiveAcquisitionError(f"{label} owner read must return an object")
    return value


def _normalize_base(value: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if set(value) != {"skillpack", "agentos"}:
        raise LiveAcquisitionError("base owner read shape is invalid")
    skillpack = value["skillpack"]
    agentos = value["agentos"]
    if not isinstance(skillpack, Mapping) or not isinstance(agentos, Mapping):
        raise LiveAcquisitionError("base owner read values are invalid")
    # Existing collect_skillpack/collect_agentos own their deeper schemas. Do not
    # reinterpret them here; Session Truth performs its canonical validation.
    return dict(skillpack), dict(agentos)


def _scoped_github_linear_ids(
    github: Mapping[str, Any],
    scope: LiveScope,
) -> tuple[str, ...]:
    result = set(scope.linear)
    if github.get("available") is not True:
        return tuple(sorted(result))
    rows = github.get("pull_requests")
    if not isinstance(rows, list):
        raise LiveAcquisitionError("normalized GitHub observation is malformed")
    for row in rows:
        if not isinstance(row, Mapping):
            raise LiveAcquisitionError("normalized GitHub PR row is malformed")
        bound = row.get("linear")
        if not isinstance(bound, str):
            continue
        if (
            row.get("workstream") in scope.workstreams
            or (
                scope.operation_key is not None
                and row.get("operation_key") == scope.operation_key
            )
            or bound in scope.linear
        ):
            result.add(bound)
    if len(result) > MAX_IDENTITIES:
        raise LiveAcquisitionError("derived Linear scope exceeds bound")
    return tuple(sorted(result))


async def acquire_live_session_truth_inputs(
    *,
    scope: LiveScope,
    ports: LiveOwnerPorts,
) -> dict[str, Any]:
    """Acquire one current Session Truth input document through injected owner reads."""

    if type(scope) is not LiveScope or type(ports) is not LiveOwnerPorts:
        raise LiveAcquisitionError("exact LiveScope and LiveOwnerPorts are required")

    initial_external = _external_scope(scope)
    base_raw, github_raw = await asyncio.gather(
        _await_port(ports.base(scope), "base"),
        _await_port(ports.github(initial_external), "github"),
    )
    skillpack, agentos = _normalize_base(base_raw)
    try:
        github = normalize_github(github_raw)
    except Exception as exc:
        raise LiveAcquisitionError("GitHub observation normalization failed") from exc

    derived_linear = _scoped_github_linear_ids(github, scope)
    derived_scope = _external_scope(scope, linear=derived_linear)

    linear_raw, slack_raw, executive_raw, identities_raw = await asyncio.gather(
        _await_port(ports.linear(derived_scope), "linear"),
        _await_port(ports.slack(derived_scope), "slack"),
        _await_port(ports.executive(derived_scope), "executive"),
        _await_port(ports.identities(derived_scope), "identities"),
    )
    try:
        linear = normalize_linear(linear_raw)
        slack = normalize_slack(slack_raw)
        executive = normalize_executive(executive_raw)
        identities = normalize_identities(identities_raw)
    except Exception as exc:
        raise LiveAcquisitionError("external observation normalization failed") from exc

    return {
        "schema": INPUT_SCHEMA,
        "scope": {
            "workstreams": list(scope.workstreams),
            "linear": list(scope.linear),
            "repositories": list(scope.repositories),
            "operation_key": scope.operation_key,
            "requires_executive": scope.requires_executive,
        },
        "skillpack": skillpack,
        "agentos": agentos,
        "github": github,
        "linear": linear,
        "slack": slack,
        "executive": executive,
        "identities": identities,
    }

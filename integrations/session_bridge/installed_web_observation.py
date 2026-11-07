"""Installed, explicitly granted profile observation on the existing read owners.

No enrollment, browser impersonation, alternate socket, history store, retry or
control capability lives here. The network side uses only the existing private
Session Bridge. Only its original profile-owning process can collect a census.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable
from threading import Event
from time import monotonic
from uuid import UUID

from common.session_bridge_private_contract import BridgeError
from control_plane.principal_projection import NeutralPrincipalProjection

CONFIG_SCHEMA = "mastermind.session_web_observation_install.v1"
RESULT_SCHEMA = "mastermind.session_web_observation_private.v1"
PRIVATE_TOOL = "session_web_census"
READ_SCOPE = "mastermind.executive.read"
_HEX = re.compile(r"^[0-9a-f]{64}$")
_GRANT_KEYS = frozenset({
    "policy_id", "issuer_digest", "resource", "subject_digest", "client_ref",
    "adapter_instance_id",
})
_MAX_CONFIG_BYTES = 32768
_MAX_PRINCIPALS = 16
_UNAVAILABLE = "authorized profile-local observation is unavailable"


def _digest(value):
    return type(value) is str and _HEX.fullmatch(value) is not None


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


@dataclass(frozen=True, slots=True)
class ProfileSource:
    binding_id: str
    adapter_instance_id: str
    profile_owner_uid: int


@dataclass(frozen=True, slots=True)
class ObservationGrant:
    policy_id: str
    issuer: str
    issuer_digest: str
    resource: str
    subject_digest: str
    client_ref: str
    scopes: tuple[str, ...]
    max_token_lifetime_seconds: int


@dataclass(frozen=True, slots=True)
class ObservationState:
    revision: str
    source: ProfileSource
    grants: tuple[ObservationGrant, ...]

    def __post_init__(self):
        if (not _digest(self.revision) or type(self.source) is not ProfileSource
                or type(self.grants) is not tuple
                or any(type(g) is not ObservationGrant for g in self.grants)):
            raise ValueError("invalid observation owner state")


def parse_configuration(value, policies):
    """Validate this projection against the *existing* frozen OAuth policies."""
    from integrations.business_mcp_auth.contracts import (
        ResourcePolicy, validate_resource_policy,
    )
    try:
        if (type(value) is not dict
                or set(value) != {"schema", "source", "permissions"}
                or value["schema"] != CONFIG_SCHEMA
                or len(_canonical(value)) > _MAX_CONFIG_BYTES):
            raise ValueError()
        source, permissions = value["source"], value["permissions"]
        if (type(source) is not dict or set(source) != {
                "binding_id", "adapter_instance_id", "profile_owner_uid"}
                or type(source["binding_id"]) is not str
                or str(UUID(source["binding_id"])) != source["binding_id"]
                or not _digest(source["adapter_instance_id"])
                or type(source["profile_owner_uid"]) is not int
                or not 0 < source["profile_owner_uid"] <= 2**31 - 1
                or type(permissions) is not dict
                or set(permissions) != {"generation", "principals"}
                or not _digest(permissions["generation"])
                or type(permissions["principals"]) is not list
                or len(permissions["principals"]) > _MAX_PRINCIPALS):
            raise ValueError()
        trusted = {}
        for policy in policies:
            if type(policy) is not ResourcePolicy:
                raise ValueError()
            policy = validate_resource_policy(policy)
            if READ_SCOPE not in policy.required_scopes:
                raise ValueError()
            key = (policy.policy_id, policy.resource)
            if key in trusted and trusted[key] != policy:
                raise ValueError()
            trusted[key] = policy
        seen, grants = set(), []
        for row in permissions["principals"]:
            if (type(row) is not dict or set(row) != _GRANT_KEYS
                    or any(type(row[key]) is not str for key in _GRANT_KEYS)
                    or not all(_digest(row[key]) for key in (
                        "issuer_digest", "subject_digest", "client_ref", "adapter_instance_id"))
                    or row["adapter_instance_id"] != source["adapter_instance_id"]):
                raise ValueError()
            policy = trusted.get((row["policy_id"], row["resource"]))
            identity = tuple(row[key] for key in sorted(_GRANT_KEYS))
            if (policy is None or identity in seen
                    or row["issuer_digest"] != hashlib.sha256(policy.issuer.encode()).hexdigest()
                    or row["subject_digest"] not in policy.allowed_subject_digests):
                raise ValueError()
            seen.add(identity)
            grants.append(ObservationGrant(
                policy.policy_id, policy.issuer, row["issuer_digest"], policy.resource,
                row["subject_digest"], row["client_ref"], policy.required_scopes,
                policy.max_token_lifetime_seconds))
        return ProfileSource(**source), tuple(grants)
    except Exception:
        raise ValueError("installed observation configuration is invalid") from None


def observation_state(value, policies, revision):
    source, grants = parse_configuration(value, policies)
    return ObservationState(revision, source, grants)


class ObservationPermissionReader:
    """Ephemeral, uncached readback of the one root-sealed install owner."""

    def __init__(self, *, load_state: Callable, clock: Callable | None = None):
        if not callable(load_state) or (clock is not None and not callable(clock)):
            raise TypeError("the existing current installation owner is required")
        self._load_state = load_state
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def select(self, principal, *, required=False):
        now = self._clock()
        if (type(principal) is not NeutralPrincipalProjection
                or not isinstance(now, datetime) or now.utcoffset() is None
                or type(principal.issued_at) is not int or type(principal.expires_at) is not int
                or not principal.issued_at <= now.timestamp() < principal.expires_at
                or type(principal.scopes) is not tuple
                or READ_SCOPE not in principal.scopes
                or not all(type(s) is str for s in principal.scopes)
                or not all(_digest(x) for x in (principal.issuer_digest,
                    principal.subject_digest, principal.client_ref))
                or type(principal.issuer) is not str
                or principal.issuer_digest != hashlib.sha256(principal.issuer.encode()).hexdigest()
                or (principal.jti_digest is not None and not _digest(principal.jti_digest))):
            raise BridgeError("authority_refused", _UNAVAILABLE)
        state = self._load_state()
        after_load = self._clock()
        if (not isinstance(after_load, datetime) or after_load.utcoffset() is None
                or not principal.issued_at <= after_load.timestamp() < principal.expires_at):
            raise BridgeError("authority_refused", _UNAVAILABLE)
        if type(state) is not ObservationState:
            raise BridgeError("authority_refused", _UNAVAILABLE)
        allowed = any(
            all(getattr(principal, key) == getattr(grant, key) for key in (
                "policy_id", "issuer", "issuer_digest", "resource", "subject_digest",
                "client_ref", "scopes"))
            and principal.expires_at - principal.issued_at <= grant.max_token_lifetime_seconds
            for grant in state.grants)
        if required and not allowed:
            raise BridgeError("authority_refused", _UNAVAILABLE)
        return state, allowed

    def public_scope(self, principal):
        from integrations.business_mcp_auth.principal_projection import principal_projection
        from .web_observation_tools import WebSessionReadScope
        state, allowed = self.select(principal_projection(principal))
        return WebSessionReadScope(state.revision,
            (state.source.adapter_instance_id,) if allowed else ())

    def network_tools(self, session_client, *, clock=None):
        """Use the incumbent private client, never a browser collector here."""
        from integrations.business_mcp_auth.principal_projection import principal_projection
        from integrations.chairman_surfaces.web_sol_census_protocol import validate_census_receipt
        from .web_observation_tools import WebSessionReadTools

        async def read_one(principal, authorized_adapters):
            projected = principal_projection(principal)
            before, _ = self.select(projected, required=True)
            if authorized_adapters != (before.source.adapter_instance_id,):
                raise BridgeError("authority_refused", _UNAVAILABLE)
            try:
                result = await session_client.web_census(principal)
            except BridgeError as exc:
                if exc.code == "output_too_large":
                    from .web_observation import ObservationBudgetError
                    raise ObservationBudgetError("private observation budget exceeded") from None
                raise
            after, _ = self.select(projected, required=True)
            if (before != after or type(result) is not dict
                    or set(result) != {"schema", "owner_revision", "receipt"}
                    or result["schema"] != RESULT_SCHEMA
                    or result["owner_revision"] != before.revision):
                raise BridgeError("authority_refused", _UNAVAILABLE)
            receipt = validate_census_receipt(result["receipt"])
            if receipt["adapter_instance_id"] != before.source.adapter_instance_id:
                raise BridgeError("authority_refused", _UNAVAILABLE)
            return [receipt]

        return WebSessionReadTools(scope_reader=self.public_scope, census_reader=read_one,
                                   clock=clock or self._clock)


def _file_identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _profile_home(uid):
    # No setuid, HOME changes, inferred users, or caller-selected profile roots.
    import pwd
    home = Path(pwd.getpwuid(uid).pw_dir)
    if not home.is_absolute() or Path.home() != home:
        raise BridgeError("backend_unavailable", _UNAVAILABLE)
    return home


def _path_custody(path, uid, home, *, socket=False):
    from control_plane.fs_security import (
        has_macos_acl, has_macos_everyone_deny_delete_only_acl,
    )
    info, parent = path.lstat(), path.parent.lstat()
    kind = stat.S_ISSOCK if socket else stat.S_ISREG
    if (not kind(info.st_mode) or not stat.S_ISDIR(parent.st_mode)
            or info.st_uid != uid or parent.st_uid != uid
            or info.st_nlink != 1 or info.st_mode & 0o077 or parent.st_mode & 0o077
            or (not socket and info.st_size > 512 * 1024)):
        raise BridgeError("backend_unavailable", _UNAVAILABLE)
    # The original C2 owner may use its already-private short socket root.
    # Otherwise check the full profile ancestry through the authenticated home.
    nodes = [path, path.parent]
    if path.is_relative_to(home):
        nodes.extend(node for node in path.parents if node.is_relative_to(home))
    identities = []
    for node in dict.fromkeys(nodes):
        current = node.lstat()
        if (stat.S_ISLNK(current.st_mode) or current.st_uid != uid
                or current.st_mode & 0o022):
            raise BridgeError("backend_unavailable", _UNAVAILABLE)
        # Unix sockets cannot be opened as regular descriptors for the ACL
        # observer. Their owner-only parent is checked instead; no other user
        # can traverse that parent even if a socket ACL would otherwise allow it.
        if not (socket and node == path) and has_macos_acl(node, expected_identity=current):
            accepted_home = False
            if node == home:
                descriptor = os.open(node, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
                try:
                    accepted_home = has_macos_everyone_deny_delete_only_acl(
                        descriptor=descriptor, expected_identity=current)
                finally:
                    os.close(descriptor)
            if not accepted_home:
                raise BridgeError("backend_unavailable", _UNAVAILABLE)
        identities.append((str(node), _file_identity(current)))
    return tuple(identities)


def _current_source(source):
    # This check precedes all profile, binding and socket I/O, including HOME.
    if (source.profile_owner_uid <= 0
            or os.getuid() != source.profile_owner_uid
            or os.geteuid() != source.profile_owner_uid):
        raise BridgeError("backend_unavailable", _UNAVAILABLE)
    from control_plane import surface_bindings
    from integrations.chairman_surfaces import web_sol_instance
    home = _profile_home(source.profile_owner_uid)
    canonical = surface_bindings.DEFAULT_PATH
    if type(canonical) is not str or not canonical.startswith("~/"):
        raise BridgeError("backend_unavailable", _UNAVAILABLE)
    path = home / canonical[2:]
    before = _path_custody(path, source.profile_owner_uid, home)
    document, warnings = surface_bindings.load_bindings(path)
    after = _path_custody(path, source.profile_owner_uid, home)
    if before != after or warnings or type(document) is not dict:
        raise BridgeError("backend_unavailable", _UNAVAILABLE)
    selected = [row for row in document["bindings"] if row["binding_id"] == source.binding_id]
    if len(selected) != 1 or web_sol_instance.adapter_instance_id(selected[0]) != source.adapter_instance_id:
        raise BridgeError("backend_unavailable", _UNAVAILABLE)
    # Original derivation only: no new root or socket selector is passed.
    socket_path = web_sol_instance.socket_path(source.adapter_instance_id)
    socket_identity = _path_custody(socket_path, source.profile_owner_uid, home, socket=True)
    binding = copy.deepcopy(selected[0])
    return binding, (before, socket_identity, hashlib.sha256(_canonical(binding)).hexdigest())


class InstalledProfileCensus:
    """Private owner: one bounded original C2 read with before/after custody."""

    def __init__(self, permissions: ObservationPermissionReader, *, current_guard: Callable):
        if type(permissions) is not ObservationPermissionReader or not callable(current_guard):
            raise TypeError("existing permission and current Runtime owners are required")
        self._permissions, self._guard = permissions, current_guard

    def _read(self, principal, *, deadline, wall_expiry, cancelled):
        from integrations.chairman_surfaces.web_sol_client import census_via_extension

        def current():
            if cancelled.is_set() or monotonic() >= deadline:
                raise BridgeError("backend_unavailable", _UNAVAILABLE)

        try:
            current()
            before, _ = self._permissions.select(principal, required=True)
            if self._guard() is not True:
                raise BridgeError("backend_unavailable", _UNAVAILABLE)
            current()
            binding, custody = _current_source(before.source)
            current()
            now = datetime.now(timezone.utc)
            # Custody/preflight consumes the original request budget. A blocked
            # thread may never renew a full window after its caller has left.
            expires = min(wall_expiry, now + timedelta(seconds=deadline - monotonic()))
            nonce = secrets.token_hex(16)
            current()
            receipt = census_via_extension(binding,
                operation_key="session-web-read-" + nonce, nonce=nonce,
                issued_at=now.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                expires_at=expires.isoformat(timespec="milliseconds").replace("+00:00", "Z"))
            current()
            after, _ = self._permissions.select(principal, required=True)
            if before != after or self._guard() is not True:
                raise BridgeError("authority_refused", _UNAVAILABLE)
            current()
            binding_after, custody_after = _current_source(after.source)
            if custody != custody_after or binding != binding_after:
                raise BridgeError("backend_unavailable", _UNAVAILABLE)
            current()
            final, _ = self._permissions.select(principal, required=True)
            if final != before or self._guard() is not True:
                raise BridgeError("authority_refused", _UNAVAILABLE)
            # The actual C2 client owns nonce, window, transport and receipt validation.
            result = {"schema": RESULT_SCHEMA, "owner_revision": before.revision, "receipt": receipt}
            from control_plane.executive_ceo_ingress import MAX_RESPONSE_BYTES
            # Preserve the existing 32-KiB private carrier. Reserve its framing
            # overhead; never silently trim the closed native census receipt.
            if len(_canonical(result)) > MAX_RESPONSE_BYTES - 2048:
                raise BridgeError("output_too_large", _UNAVAILABLE)
            current()
            return result
        except BridgeError:
            raise
        except Exception:
            raise BridgeError("backend_unavailable", _UNAVAILABLE) from None

    async def __call__(self, principal, arguments):
        if type(arguments) is not dict or arguments:
            raise BridgeError("invalid_input", "profile census takes no selectors")
        # One eight-second end-to-end budget, captured before thread dispatch,
        # stays inside the incumbent ten-second private carrier. Cancellation
        # cannot kill a blocked filesystem call; the request-local fence prevents
        # it from subsequently initiating a new census or releasing late data.
        deadline = monotonic() + 8
        wall_expiry = datetime.now(timezone.utc) + timedelta(seconds=8)
        cancelled = Event()
        try:
            async with asyncio.timeout(8):
                return await asyncio.to_thread(self._read, principal,
                    deadline=deadline, wall_expiry=wall_expiry, cancelled=cancelled)
        finally:
            cancelled.set()

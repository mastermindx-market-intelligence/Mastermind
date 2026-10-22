"""Explicit Research Read composition; importing this module performs no I/O.

The launcher owns the factories and HTTP lifecycle. Deployment parsing and
composition do not install a service, start a listener or create an OAuth client.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from typing import Callable, Mapping

from . import CONTRACT

DEPLOYMENT_SCHEMA = "mastermind.research_read_mcp.deployment.v1"
READ_PORT_CONTRACT = "research_vault.read.v1"
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost"})
_FIELDS = frozenset({
    "schema", "mode", "mastermind_release", "mastermind_commit", "mastermind_tree",
    "macro_release", "macro_commit", "macro_tree", "bind_host", "bind_port",
    "policy_path", "grant_path", "policy_id", "server_contract", "read_port_contract",
    "allowed_hosts", "allowed_origins",
})


class RuntimeRefused(ValueError):
    """Fixed refusal with no caller/configuration values in the message."""

    def __init__(self, code: str = "RUNTIME_CONFIG_REFUSED") -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class Deployment:
    mastermind_release: str
    mastermind_commit: str
    mastermind_tree: str
    macro_release: str
    macro_commit: str
    macro_tree: str
    bind_host: str
    bind_port: int
    policy_path: str
    grant_path: str
    policy_id: str
    allowed_hosts: tuple[str, ...]
    allowed_origins: tuple[str, ...]


def _closed_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RuntimeRefused()
        result[key] = value
    return result


def _invalid_constant(_value):
    raise RuntimeRefused()


def _json(raw: bytes, maximum: int):
    try:
        if type(raw) is not bytes or not 0 < len(raw) <= maximum:
            raise RuntimeRefused()
        return json.loads(raw.decode("utf-8", errors="strict"),
                          object_pairs_hook=_closed_pairs, parse_constant=_invalid_constant)
    except Exception:
        raise RuntimeRefused() from None


def _absolute(value):
    if (type(value) is not str or not value or len(value) > 4096
            or "\x00" in value or "\\" in value):
        raise RuntimeRefused()
    path = Path(value)
    if not path.is_absolute() or str(path) != value or ".." in path.parts:
        raise RuntimeRefused()
    return value


def parse_deployment(raw: bytes) -> Deployment:
    value = _json(raw, 32768)
    if type(value) is not dict or set(value) != _FIELDS:
        raise RuntimeRefused()
    if (value["schema"] != DEPLOYMENT_SCHEMA or value["mode"] != "production"
            or value["server_contract"] != CONTRACT
            or value["read_port_contract"] != READ_PORT_CONTRACT):
        raise RuntimeRefused()
    for project in ("mastermind", "macro"):
        commit, tree = value[project + "_commit"], value[project + "_tree"]
        if any(type(item) is not str or _SHA.fullmatch(item) is None for item in (commit, tree)):
            raise RuntimeRefused()
        release = _absolute(value[project + "_release"])
        if release != f"/opt/{project}-research/releases/{commit}":
            raise RuntimeRefused()
    if type(value["bind_host"]) is not str or value["bind_host"] not in _LOOPBACK:
        raise RuntimeRefused()
    if type(value["bind_port"]) is not int or not 1 <= value["bind_port"] <= 65535:
        raise RuntimeRefused()
    for key in ("policy_path", "grant_path"):
        _absolute(value[key])
    if (type(value["policy_id"]) is not str or not 0 < len(value["policy_id"]) <= 120
            or not re.fullmatch(r"[A-Za-z0-9_.:-]+", value["policy_id"])):
        raise RuntimeRefused()
    for key in ("allowed_hosts", "allowed_origins"):
        rows = value[key]
        if type(rows) is not list or len(rows) > 16 or (key == "allowed_hosts" and not rows):
            raise RuntimeRefused()
        if any(type(row) is not str or not row or len(row) > 500
               or any(char in row for char in ("*", "\r", "\n", "\x00")) for row in rows):
            raise RuntimeRefused()
        if len(set(rows)) != len(rows):
            raise RuntimeRefused()
        if key == "allowed_origins" and any(not row.startswith("https://") for row in rows):
            raise RuntimeRefused()
    return Deployment(**{key: tuple(value[key]) if key in {"allowed_hosts", "allowed_origins"}
                         else value[key] for key in Deployment.__dataclass_fields__})


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def read_secure_json(path: str, *, expected_owner_uid: int, maximum: int = 65536):
    """Read a bounded owner-only regular file without following any symlinks."""
    descriptor = None
    try:
        _absolute(path)
        if type(expected_owner_uid) is not int or expected_owner_uid < 0:
            raise RuntimeRefused()
        if type(maximum) is not int or not 0 < maximum <= 4 * 1024 * 1024:
            raise RuntimeRefused()
        target = Path(path)
        for ancestor in (target, *target.parents):
            if ancestor.is_symlink():
                raise RuntimeRefused()
        before = target.stat(follow_symlinks=False)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != expected_owner_uid
                or before.st_mode & 0o077 or before.st_nlink != 1
                or not 0 < before.st_size <= maximum):
            raise RuntimeRefused()
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        opened = os.fstat(descriptor)
        if _identity(before) != _identity(opened):
            raise RuntimeRefused()
        raw = os.read(descriptor, maximum + 1)
        after = os.fstat(descriptor)
        final = target.stat(follow_symlinks=False)
        if (len(raw) != before.st_size or _identity(before) != _identity(after)
                or _identity(before) != _identity(final)
                or any(ancestor.is_symlink() for ancestor in (target, *target.parents))):
            raise RuntimeRefused()
        return raw
    except Exception:
        raise RuntimeRefused() from None
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                raise RuntimeRefused("CONFIG_CLOSE_UNCERTAIN") from None


def load_deployment(path: str, *, expected_owner_uid: int) -> Deployment:
    return parse_deployment(read_secure_json(path, expected_owner_uid=expected_owner_uid, maximum=32768))


def verify_git_release(path: str, commit: str, tree: str) -> None:
    """Qualify a pinned checkout. Archive releases need a separately qualified verifier."""
    try:
        target = Path(_absolute(path))
        if (target.name != commit or not target.is_dir()
                or any(ancestor.is_symlink() for ancestor in (target, *target.parents))
                or (target / ".env").exists()):
            raise RuntimeRefused("RELEASE_IDENTITY_REFUSED")
        environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        environment["GIT_OPTIONAL_LOCKS"] = "0"
        for revision, expected in (("HEAD", commit), ("HEAD^{tree}", tree)):
            observed = subprocess.run(["git", "-C", path, "rev-parse", revision],
                                      capture_output=True, text=True, timeout=15, check=True,
                                      env=environment)
            if observed.stdout.strip() != expected:
                raise RuntimeRefused("RELEASE_IDENTITY_REFUSED")
        status = subprocess.run(["git", "-C", path, "status", "--porcelain", "--untracked-files=all"],
                                capture_output=True, text=True, timeout=15, check=True,
                                env=environment)
        if status.stdout:
            raise RuntimeRefused("RELEASE_IDENTITY_REFUSED")
    except Exception:
        raise RuntimeRefused("RELEASE_IDENTITY_REFUSED") from None


class CurrentGrantOwner:
    """Reuse the secure grant loader; never cache or create a second policy store."""

    def __init__(self, deployment: Deployment, *, clock: Callable[[], int], owner_uid: int):
        self.deployment = deployment
        self.clock = clock
        self.owner_uid = owner_uid

    def _load(self):
        from .entitlement import load_research_grant
        now = self.clock()
        if type(now) is not int:
            raise RuntimeRefused("GRANT_REFUSED")
        grant = load_research_grant(self.deployment.grant_path,
                                   expected_policy_id=self.deployment.policy_id,
                                   now=now, expected_owner_uid=self.owner_uid)
        return grant, now

    def entitlement(self, projection):
        from .entitlement import GrantRefused, entitlement_for
        try:
            grant, now = self._load()
            return entitlement_for(projection, grant, now=now)
        except (GrantRefused, RuntimeRefused):
            return None

    def quote_limit(self, principal_id: str) -> int:
        from .contracts import ContractViolation
        try:
            if type(principal_id) is not str or _DIGEST.fullmatch(principal_id) is None:
                raise ValueError()
            grant, now = self._load()
            entries = [entry for entry in grant.entries
                       if entry.subject_digest == principal_id and entry.expires_at > now]
            if len(entries) != 1 or "evidence_passage" not in entries[0].content_classes:
                raise ValueError()
            return entries[0].quote_limit_chars
        except Exception:
            raise ContractViolation("NOT_ENTITLED") from None


def compose_runtime(deployment: Deployment, *, release_verifier=verify_git_release,
                    policy_loader=None, authenticator_factory, read_service_factory,
                    adapter_factory, context_factory, readiness, mount_health_routes, audit_sink, clock,
                    owner_uid: int, compatibility_factory=None):
    """Compose the existing app with owner-supplied actual adapter/service factories.

    Factories are explicit until their real source closure is integrated. No
    fallback port, fake context or speculative Macro import exists here.
    """
    from .app import create_authenticated_research_server
    from integrations.business_mcp_auth.contracts import load_resource_policy
    if type(deployment) is not Deployment:
        raise RuntimeRefused()
    # A caller can manually construct a dataclass; it is not a parser receipt.
    observed = asdict(deployment)
    observed.update(schema=DEPLOYMENT_SCHEMA, mode="production", server_contract=CONTRACT,
                    read_port_contract=READ_PORT_CONTRACT)
    observed["allowed_hosts"] = list(deployment.allowed_hosts)
    observed["allowed_origins"] = list(deployment.allowed_origins)
    deployment = parse_deployment(json.dumps(observed, allow_nan=False).encode())
    for path, commit, tree in ((deployment.mastermind_release, deployment.mastermind_commit,
                                deployment.mastermind_tree),
                               (deployment.macro_release, deployment.macro_commit, deployment.macro_tree)):
        if release_verifier(path, commit, tree) is not None:
            raise RuntimeRefused("RELEASE_IDENTITY_REFUSED")
    if policy_loader is None:
        raw = read_secure_json(deployment.policy_path, expected_owner_uid=owner_uid)
        policy = load_resource_policy(_json(raw, 65536))
    else:
        policy = policy_loader(deployment.policy_path)
    if policy.policy_id != deployment.policy_id:
        raise RuntimeRefused("POLICY_REFUSED")
    owner = CurrentGrantOwner(deployment, clock=clock, owner_uid=owner_uid)
    service = read_service_factory(deployment)
    port = adapter_factory(service, owner.quote_limit, deployment)
    compatibility_port = None
    if compatibility_factory is not None:
        from .compatibility_v1 import CompatibilityPortV1
        if not callable(compatibility_factory):
            raise RuntimeRefused("COMPATIBILITY_COMPOSITION_REFUSED")
        compatibility_port = compatibility_factory(port)
        # Explicit owner opt-in only. Both callbacks retain this adapter and its
        # context type; no second service, grant owner or resolver is created.
        if (type(compatibility_port) is not CompatibilityPortV1
                or compatibility_port.context_type is not getattr(port, "context_type", None)
                or getattr(compatibility_port.search_items, "__self__", None) is not port
                or getattr(compatibility_port.resolve_item, "__self__", None) is not port):
            raise RuntimeRefused("COMPATIBILITY_COMPOSITION_REFUSED")
    app = create_authenticated_research_server(
        policy=policy, authenticator=authenticator_factory(policy), now=clock,
        audit_sink=audit_sink, port=port, entitlement_resolver=owner.entitlement,
        context_builder=context_factory, allowed_hosts=deployment.allowed_hosts,
        allowed_origins=deployment.allowed_origins, compatibility_port=compatibility_port,
        selection_scope=getattr(port, "capture_selection", None),
    )

    def health():
        return {"ok": True}, 200

    def ready():
        try:
            qualified = readiness(service) is True
        except Exception:
            qualified = False
        return {"ready": qualified}, 200 if qualified else 503

    # The launcher/HTTP edge owns SDK routes; runtime does not import an SDK.
    mount_health_routes(app, health, ready)
    app.state.research_grant_owner = owner
    return app

#!/usr/bin/env python3
"""Owned, transactional component update for the installed Executive MCP gateway.

This replaces the unowned 2026-09-27 ``mcp-component-*`` update procedure whose
code was never in the repository. It changes exactly two installed files of the
gateway role and nothing else:

* ``config/executive-mcp.json`` - ``release_sha`` and, only when asked,
  ``public_mcp_resource`` (exactly the public ``/mcp`` audience);
* ``/Library/LaunchDaemons/com.mastermind.executive.mcp.plist`` - the release
  substitution of the closed installed gateway profile.

Verbs (run as root through ``service-control.sh``; this tool never calls it):

``plan``       read-only: compile the candidate, verify the sealed target
               release and network closure, print the plan and its digest.
``apply``      execute exactly the plan whose digest the operator passes.
``reconcile``  observe-only recovery of an interrupted transaction.

Safety contract:

* One transaction marker is persisted *before* every launchd effect. A recorded
  ``stop`` or ``start`` dispatch is never replayed. The compensating
  ``launchctl enable`` is dispatched once and its completion is recorded
  (``recover_enable_done``); a recovery pass that finds the completion recorded
  never runs ``enable`` again.
* The tool is observation driven: every re-entry classifies the live config,
  plist and launchd state against the preserved before-images and the planned
  after-images, then continues forward or stops in ``EFFECT_UNKNOWN``.
* Kill switch, as far as it can be honored: a gateway whose launchd label is
  already disabled is refused (``GATEWAY_DISABLED``) at ``apply`` and again before
  the stop is dispatched, with no effect. After the tool's own stop the disable flag
  is the tool's own ``disable``, so an operator ``disable`` made in that window (before
  ``start`` or before the compensating ``enable`` has completed) cannot be told apart
  from it and is undone by the ``start``/``enable`` this tool already owes. Once
  ``recover_enable_done`` is recorded the tool never enables again: a label found
  disabled then is ``EFFECT_UNKNOWN`` (``GATEWAY_DISABLED_AFTER_RECOVERY``) and needs
  the operator to ``enable`` it (and ``bootstrap`` it if it was also booted out), then
  ``reconcile``; the tool cannot close a transaction while leaving the label disabled.
  A crash between the ``enable`` returning and that record
  being written leaves one more ``enable`` to run on the next pass.
* The only compensating act is ``launchctl enable`` when the stop did not take
  effect and both files are provably still the before-images.
* There is NO automatic rollback after a file was replaced. A failed start or
  verification stays ``EFFECT_UNKNOWN``; the before-images are preserved for a
  separately approved human restore: copy ``mcp-update-<plan12>.config.before`` and
  ``.plist.before`` from ``installation-receipts/`` back over the two installed
  files (root, mode and owner as installed), then ``launchctl enable`` and
  ``launchctl bootstrap system <plist>`` by hand. ``START_NOT_PROVEN`` (the start
  was dispatched but the label is still absent) needs only that last
  ``enable``/``bootstrap`` pair against the after-images.
* Probes are loopback, unauthenticated and read-only. They prove the challenge
  and metadata boundary, not an authenticated MCP session. COMPLETE additionally
  requires the launchd-observed process, and that proof brackets the probes: the
  process must be running with argv and working directory equal to the after-image
  plist, the gateway user and one pid across repeated polls BEFORE the probes; the
  probes run; the same pid must then still be observed running (with the same
  identity) on every poll of a hold window that outlasts launchd's 10 s
  ``ThrottleInterval``, the probes are repeated, and a final observation must match
  again. A new release that dies, is respawned under another pid, or changes identity
  within that window after answering the probes, and a before-image process, are
  refused as ``EFFECT_UNKNOWN``. What this does NOT establish: it does not tie the
  listener pid to the port (an old or foreign process that holds the port while the
  new release stays alive but unbound is not detected), it does not cover a failure
  later than the hold window, and the throttle behavior itself is unverified.

Exit codes: 0 COMPLETE (or PLANNED), 1 refused with no effect, 2 EFFECT_UNKNOWN,
3 unchanged (nothing was left changed), 64 usage.
"""

from __future__ import annotations

import copy
import dataclasses
import errno
import fcntl
import hashlib
import http.client
import json
import os
import plistlib
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

_ROOT = Path(__file__).resolve().parents[2]
if os.fspath(_ROOT) not in sys.path:
    sys.path.insert(0, os.fspath(_ROOT))

from control_plane import executive_installed_peer as installed
from control_plane.executive_peer_identity import PeerIdentityError
from integrations.business_mcp_auth.contracts import AuthError
from integrations.business_mcp_auth.metadata import protected_resource_metadata
from integrations.executive_mcp.web_ceo_v3 import WEB_CEO_V3_PROFILE
from integrations.mastermind_executive_app.gateway import load_app_policies
from ops.executive_os import gateway_refresh_preflight
from ops.executive_os.executive_mcp_entry import (
    PUBLIC_MCP_RESOURCE,
    build_additional_policies,
    build_public_policies,
    validate_document,
)

PLAN_SCHEMA = "mastermind.mcp_component_update_plan.v1"
MARKER_SCHEMA = "mastermind.mcp_component_update_transaction.v1"
RECEIPT_SCHEMA = "mastermind.mcp_component_update_receipt.v1"

RECEIPTS_DIR = installed._SERVICE_ROOT + "/installation-receipts"
CONFIG_PATH = installed._GATEWAY_CONFIG_PATH
PLIST_PATH = installed._LAUNCHD_ROLES["gateway"].plist_path
LABEL = installed._LAUNCHD_ROLES["gateway"].label
LAUNCHD_ROOT = installed._LAUNCHD_ROLES["gateway"].root
LAUNCHCTL = "/bin/launchctl"

MARKER_NAME = "mcp-update-txn.json"
LOCK_NAME = "mcp-update.lock"

MCP_PLIST_ENTRY_ARGUMENT = "/ops/executive_os/executive_mcp_entry.py"
GATEWAY_PLIST_PROFILE = installed._EXPECTED_PLIST_PROFILES["gateway"]
MAX_CONFIG_BYTES = 65_536
MAX_PLIST_BYTES = 262_144
MAX_LAUNCHCTL_OUTPUT_BYTES = 262_144
# The row grammar of `launchctl print-disabled`, identical to ``require_gateway_enabled`` in ``service-control.sh``.
_DISABLED_ROW_LABEL = re.compile(r'"[A-Za-z0-9._-]+"')
_DISABLED_ROW_VERDICTS = ("enabled", "disabled", "true", "false")
HEX40 = re.compile(r"[0-9a-f]{40}")
HEX64 = re.compile(r"[0-9a-f]{64}")

KINDS = ("config", "plist")
PHASES = ("INTENT", "STAGED", "STOP_DISPATCHED", "REPLACED", "START_DISPATCHED", "VERIFIED")
DISPATCH_NAMES = ("stop", "start", "recover_enable", "recover_enable_done")
SETTLE_POLLS = 31
VERIFY_ATTEMPTS = 20
PROCESS_POLLS = 12
PROCESS_STABLE_POLLS = 3
# The gateway plist profile carries ThrottleInterval 10, so launchd respawns a dying service no
# sooner than 10 s later: a hold of 12 one-second polls spans one full throttle interval.
PROCESS_HOLD_POLLS = 12
PROBE_RECHECK_ATTEMPTS = 3
GATEWAY_USER = installed._LAUNCHD_ROLES["gateway"].username

INITIALIZE_BODY = json.dumps(
    {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "component-update-probe", "version": "1"},
        },
    },
    separators=(",", ":"),
).encode("utf-8")

WARNINGS = (
    "the gateway is stopped and restarted: the endpoint is briefly unavailable",
    "with --set-public-mcp-resource the single gateway process serves the public /mcp audience only; "
    "the tunnel-audience entrypoint of this process is retired",
    "there is no automatic rollback after a file is replaced; before-images are preserved for a "
    "separately approved human restore",
    "probes are loopback and unauthenticated: they prove the challenge and metadata boundary, "
    "not an authenticated MCP session",
    "COMPLETE needs a running, pid-stable launchd process with the after-image argv and working "
    "directory before the probes, an unchanged pid for a hold window after them and a repeat probe; "
    "the listener pid is not tied to the port and a failure later than the window is not covered",
)


class UpdateRefused(RuntimeError):
    """Refused before any launchd or installed-file effect."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class TransactionEffectUnknown(RuntimeError):
    """An effect may have happened; the marker is preserved, nothing is replayed."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


# --- helpers mirrored from os_gateway_publication.py (kept local on purpose) ---


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def _strict_json(raw: bytes, code: str) -> Any:
    require(type(raw) is bytes and 0 < len(raw) <= MAX_CONFIG_BYTES, "component update JSON byte budget")
    try:
        return installed._load_strict_json(raw, code=code)
    except PeerIdentityError:
        raise ValueError("component update JSON refused") from None


def _strict_plist(raw: bytes) -> Any:
    require(type(raw) is bytes and 0 < len(raw) <= MAX_PLIST_BYTES, "component update plist byte budget")
    try:
        return installed._load_strict_plist(raw, code="MCP_COMPONENT_PLIST_MALFORMED")
    except PeerIdentityError:
        raise ValueError("component update plist refused") from None


def _sha(value: Any, pattern: re.Pattern[str], message: str) -> str:
    require(type(value) is str and pattern.fullmatch(value) is not None, message)
    return value


def _proposed_plist(prior_plist: dict, *, prior_release: str, expected_release_sha: str) -> dict:
    releases: list[str] = []
    require(installed._profile_matches(GATEWAY_PLIST_PROFILE, prior_plist, releases),
            "prior MCP plist is not the closed installed gateway profile")
    require(len(releases) == 1 and releases[0] == prior_release,
            "prior MCP plist release join differs")
    release_root = installed._SERVICE_RELEASES + "/" + expected_release_sha
    proposed = copy.deepcopy(prior_plist)
    proposed["WorkingDirectory"] = release_root
    argv = list(proposed["ProgramArguments"])
    require(len(argv) == 6, "prior MCP plist argv shape differs")
    argv[3] = release_root + MCP_PLIST_ENTRY_ARGUMENT
    proposed["ProgramArguments"] = argv
    require(set(proposed) == set(prior_plist), "proposed MCP plist fields differ")
    for key, value in prior_plist.items():
        if key == "WorkingDirectory":
            continue
        if key != "ProgramArguments":
            require(proposed[key] == value, "proposed MCP plist changed an unrelated installed field")
    prior_argv = prior_plist["ProgramArguments"]
    require(len(prior_argv) == len(argv)
            and all(proposed_arg == prior_arg for index, (proposed_arg, prior_arg)
                    in enumerate(zip(argv, prior_argv)) if index != 3),
            "proposed MCP plist argv differs beyond the release entry")
    require(proposed["WorkingDirectory"] == release_root
            and proposed["ProgramArguments"][3] == release_root + MCP_PLIST_ENTRY_ARGUMENT,
            "proposed MCP plist release substitution differs")
    require(installed._profile_matches(GATEWAY_PLIST_PROFILE, proposed, [expected_release_sha]),
            "proposed MCP plist is not the closed installed gateway profile")
    return proposed


# --- candidate compilation (pure) ---


@dataclasses.dataclass(frozen=True)
class Probe:
    name: str
    method: str
    path: str
    headers: tuple[tuple[str, str], ...]
    body: bytes | None
    expect_status: int
    expect_json: Any = None
    challenge_resource_metadata: str | None = None


@dataclasses.dataclass(frozen=True)
class ProbeResult:
    status: int
    headers: dict[str, str]
    body: bytes


@dataclasses.dataclass(frozen=True)
class Candidate:
    release_sha: str
    prior_release_sha: str
    port: int
    set_public_mcp_resource: bool
    public_mode_after: bool
    config_before: bytes
    config_after: bytes
    plist_before: bytes
    plist_after: bytes
    probes_before: tuple[Probe, ...]
    probes_after: tuple[Probe, ...]

    @property
    def config_before_sha256(self) -> str:
        return digest(self.config_before)

    @property
    def config_after_sha256(self) -> str:
        return digest(self.config_after)

    @property
    def plist_before_sha256(self) -> str:
        return digest(self.plist_before)

    @property
    def plist_after_sha256(self) -> str:
        return digest(self.plist_after)


def _semantic(document: dict) -> tuple[Any, Any]:
    value = copy.deepcopy(document)
    value = validate_document(value)
    policies = load_app_policies(value["policies"])
    additional = build_additional_policies(value, policies)
    public = build_public_policies(value, policies, additional)
    return policies, public


def build_probes(document: dict) -> tuple[Probe, ...]:
    """Loopback probes derived from the validated gateway document."""
    policies, public = _semantic(document)
    challenge = public if public is not None else policies
    metadata_url = challenge.read.resource_metadata_url
    metadata_path = urlsplit(metadata_url).path or "/"
    expected = json.loads(json.dumps(protected_resource_metadata(challenge.submit)))
    probes = [
        Probe("metadata", "GET", metadata_path, (), None, 200, expect_json=expected),
        Probe(
            "challenge", "POST", "/mcp",
            (("accept", "application/json, text/event-stream"), ("content-type", "application/json")),
            INITIALIZE_BODY, 401, challenge_resource_metadata=metadata_url,
        ),
    ]
    if public is not None:
        primary_path = urlsplit(policies.read.resource_metadata_url).path or "/"
        if primary_path != metadata_path:
            probes.append(Probe("primary-metadata-absent", "GET", primary_path, (), None, 404))
    return tuple(probes)


def compile_candidate(prior_config: bytes, prior_plist: bytes, *, release_sha: str,
                      set_public_mcp_resource: bool) -> Candidate:
    """Compile the only permitted change set, or raise UpdateRefused."""
    try:
        return _compile_candidate(prior_config, prior_plist, release_sha, set_public_mcp_resource)
    except UpdateRefused:
        raise
    except AuthError as error:
        raise UpdateRefused("CANDIDATE_REFUSED: auth policy " + str(error.code.value)[:80]) from None
    except (ValueError, KeyError, TypeError) as error:
        raise UpdateRefused("CANDIDATE_REFUSED: " + str(error)[:160]) from None


def _compile_candidate(prior_config: bytes, prior_plist_bytes: bytes, release_sha: str,
                       set_public: bool) -> Candidate:
    _sha(release_sha, HEX40, "target release sha shape")
    prior = _strict_json(prior_config, "MCP_COMPONENT_CONFIG_MALFORMED")
    prior_plist = _strict_plist(prior_plist_bytes)
    require(isinstance(prior, dict) and isinstance(prior_plist, dict), "prior installed documents are not objects")
    _semantic(prior)
    require(prior.get("executive_mcp_profile", "legacy") == WEB_CEO_V3_PROFILE,
            "prior installed gateway profile is not web_ceo_v3")
    prior_release = _sha(prior["release_sha"], HEX40, "prior release sha shape")
    require(release_sha != prior_release, "target release equals the installed release")
    proposed = copy.deepcopy(prior)
    proposed["release_sha"] = release_sha
    if set_public:
        require("public_mcp_resource" not in prior, "public_mcp_resource is already configured")
        proposed["public_mcp_resource"] = PUBLIC_MCP_RESOURCE
    changed = {key for key in set(prior) | set(proposed) if prior.get(key, _MISSING) != proposed.get(key, _MISSING)}
    require(changed <= {"release_sha", "public_mcp_resource"}, "candidate changed an unrelated config field")
    _, public_after = _semantic(proposed)
    config_after = canonical(proposed) + b"\n"
    require(_strict_json(config_after, "MCP_COMPONENT_CONFIG_MALFORMED") == proposed, "config round trip differs")
    plist_document = _proposed_plist(prior_plist, prior_release=prior_release, expected_release_sha=release_sha)
    plist_after = plistlib.dumps(plist_document)
    require(_strict_plist(plist_after) == plist_document, "plist round trip differs")
    port = prior["port"]
    require(type(port) is int and proposed["port"] == port, "gateway port differs")
    return Candidate(
        release_sha=release_sha,
        prior_release_sha=prior_release,
        port=port,
        set_public_mcp_resource=bool(set_public),
        public_mode_after=public_after is not None,
        config_before=prior_config,
        config_after=config_after,
        plist_before=prior_plist_bytes,
        plist_after=plist_after,
        probes_before=build_probes(prior),
        probes_after=build_probes(proposed),
    )


_MISSING = object()


def plan_document(candidate: Candidate, *, manifest_sha256: str, closure_sha256: str) -> dict:
    return {
        "schema": PLAN_SCHEMA,
        "release_sha": candidate.release_sha,
        "prior_release_sha": candidate.prior_release_sha,
        "set_public_mcp_resource": candidate.set_public_mcp_resource,
        "public_mode_after": candidate.public_mode_after,
        "port": candidate.port,
        "config": {"path": CONFIG_PATH, "before_sha256": candidate.config_before_sha256,
                   "after_sha256": candidate.config_after_sha256},
        "plist": {"path": PLIST_PATH, "before_sha256": candidate.plist_before_sha256,
                  "after_sha256": candidate.plist_after_sha256},
        "release_manifest_sha256": manifest_sha256,
        "network_closure_sha256": closure_sha256,
        "probes_before": [probe.name for probe in candidate.probes_before],
        "probes_after": [probe.name for probe in candidate.probes_after],
        "effects": [
            "launchctl disable+bootout " + LAUNCHD_ROOT,
            "replace " + CONFIG_PATH,
            "replace " + PLIST_PATH,
            "launchctl enable+bootstrap " + LAUNCHD_ROOT,
        ],
    }


def plan_digest(plan: dict) -> str:
    return digest(canonical(plan))


# --- probe evaluation (pure) ---


def probe_failure(probe: Probe, result: ProbeResult) -> str | None:
    if result.status != probe.expect_status:
        return "STATUS"
    if probe.expect_json is not None:
        try:
            if json.loads(result.body) != probe.expect_json:
                return "BODY"
        except ValueError:
            return "BODY"
    if probe.challenge_resource_metadata is not None:
        challenge = result.headers.get("www-authenticate", "")
        if not challenge.startswith("Bearer ") or \
                'resource_metadata="' + probe.challenge_resource_metadata + '"' not in challenge:
            return "CHALLENGE"
    return None


def probe_failures(host: "Host", port: int, probes: tuple[Probe, ...], *, attempts: int) -> list[str]:
    failures: list[str] = []
    for attempt in range(attempts):
        failures = []
        for probe in probes:
            try:
                result = host.probe(port, probe)
            except (OSError, http.client.HTTPException):
                failures.append(probe.name + ":UNREACHABLE")
                continue
            failure = probe_failure(probe, result)
            if failure is not None:
                failures.append(probe.name + ":" + failure)
        if not failures:
            return []
        if attempt + 1 < attempts:
            host.sleep(1.0)
    return failures


# --- host seam ---


class Host(Protocol):
    def require_root(self) -> None: ...
    def receipts_ready(self) -> None: ...
    def acquire_lock(self) -> None: ...
    def release_lock(self) -> None: ...
    def read_config(self) -> bytes: ...
    def read_plist(self) -> bytes: ...
    def verify_release(self, release_sha: str) -> str: ...
    def verify_closure(self) -> str: ...
    def readback(self, release_sha: str) -> dict: ...
    def marker_read(self) -> dict | None: ...
    def marker_create(self, marker: dict) -> None: ...
    def marker_write(self, marker: dict) -> None: ...
    def marker_remove(self) -> None: ...
    def preserve(self, kind: str, tag: str, data: bytes) -> None: ...
    def read_preserved(self, kind: str, tag: str) -> bytes | None: ...
    def discard_preserved(self, tag: str) -> None: ...
    def stage(self, kind: str, tag: str, data: bytes) -> None: ...
    def staged_digest(self, kind: str, tag: str) -> str | None: ...
    def replace(self, kind: str, tag: str) -> None: ...
    def discard_staged(self, tag: str) -> None: ...
    def receipt_exists(self, name: str) -> bool: ...
    def receipt_write(self, name: str, document: dict) -> None: ...
    def service_state(self) -> str: ...
    def stop_service(self) -> None: ...
    def start_service(self) -> None: ...
    def recover_enable(self) -> None: ...
    def service_enabled(self) -> bool: ...
    def observe_process(self) -> dict: ...
    def probe(self, port: int, probe: Probe) -> ProbeResult: ...
    def now(self) -> str: ...
    def sleep(self, seconds: float) -> None: ...


def _open_dir(path: str) -> int:
    return os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        view = view[written:]


def _write_new(dfd: int, name: str, data: bytes, mode: int) -> None:
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, mode, dir_fd=dfd)
    try:
        _write_all(fd, data)
        os.fchmod(fd, mode)
        os.fchown(fd, 0, 0)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.fsync(dfd)


def _unlink(dfd: int, name: str) -> None:
    try:
        os.unlink(name, dir_fd=dfd)
    except FileNotFoundError:
        pass


def _staged_name(kind: str, tag: str) -> tuple[str, str]:
    parent, base = os.path.split(CONFIG_PATH if kind == "config" else PLIST_PATH)
    # Dot-prefixed so launchd never enumerates a staged plist as a job definition.
    return parent, "." + base + ".mcp-component-" + tag + ".new"


def _before_name(kind: str, tag: str) -> str:
    return "mcp-update-" + tag + "." + kind + ".before"


class ProductionHost:
    """The only class that touches the real installed state. Source-only until a go-ahead."""

    def __init__(self) -> None:
        self._lock_fd: int | None = None

    # identity and trust
    def require_root(self) -> None:
        if sys.platform != "darwin":
            raise UpdateRefused("PLATFORM_UNSUPPORTED")
        if os.geteuid() != 0:
            raise UpdateRefused("ROOT_REQUIRED")

    def _budget(self) -> Any:
        return installed._Budget(installed._SERVICE_BUDGET_SECONDS)

    def receipts_ready(self) -> None:
        try:
            installed._observe_ancestors(RECEIPTS_DIR + "/" + MARKER_NAME, self._budget())
        except PeerIdentityError as error:
            raise UpdateRefused("RECEIPTS_DIR_UNTRUSTED:" + str(error)) from None

    def _trusted(self, path: str, maximum: int, mode: int) -> bytes:
        budget = self._budget()
        try:
            before = installed._observe_ancestors(path, budget)
            data, _ = installed._read_trusted_bytes(
                path, budget=budget, maximum=maximum, expected_mode=mode, expected_gid=0)
            after = installed._observe_ancestors(path, budget)
        except PeerIdentityError as error:
            raise UpdateRefused("TRUSTED_READ_REFUSED:" + str(error)) from None
        if before != after:
            raise UpdateRefused("TRUSTED_READ_ANCESTORS_CHANGED")
        return data

    def acquire_lock(self) -> None:
        dfd = _open_dir(RECEIPTS_DIR)
        try:
            fd = os.open(LOCK_NAME, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=dfd)
        finally:
            os.close(dfd)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            os.close(fd)
            if error.errno in (errno.EWOULDBLOCK, errno.EAGAIN):
                raise UpdateRefused("LOCK_HELD") from None
            raise
        self._lock_fd = fd

    def release_lock(self) -> None:
        if self._lock_fd is not None:
            os.close(self._lock_fd)
            self._lock_fd = None

    # installed images
    def read_config(self) -> bytes:
        return self._trusted(CONFIG_PATH, MAX_CONFIG_BYTES, installed._role_topology("gateway").config_mode)

    def read_plist(self) -> bytes:
        return self._trusted(PLIST_PATH, MAX_PLIST_BYTES, 0o644)

    def verify_release(self, release_sha: str) -> str:
        try:
            topology = installed._role_topology("gateway")
            budget = self._budget()
            observed = installed._verify_release(topology, release_sha, budget)
            installed._recheck_release(observed, budget)
        except PeerIdentityError as error:
            raise UpdateRefused("RELEASE_UNVERIFIED:" + str(error)) from None
        return observed.manifest_digest

    def verify_closure(self) -> str:
        try:
            budget = self._budget()
            observed = installed._verify_network_closure(budget)
            installed._recheck_network_closure(observed, budget)
        except PeerIdentityError as error:
            raise UpdateRefused("CLOSURE_UNVERIFIED:" + str(error)) from None
        return observed.aggregate

    def readback(self, release_sha: str) -> dict:
        return gateway_refresh_preflight.qualify_gateway_refresh(release_sha)

    # marker
    def marker_read(self) -> dict | None:
        dfd = _open_dir(RECEIPTS_DIR)
        try:
            os.lstat(MARKER_NAME, dir_fd=dfd)
        except FileNotFoundError:
            return None
        finally:
            os.close(dfd)
        document = _strict_json(self._trusted(RECEIPTS_DIR + "/" + MARKER_NAME, MAX_CONFIG_BYTES, 0o600),
                                "MCP_COMPONENT_MARKER_MALFORMED")
        require(isinstance(document, dict), "marker is not an object")
        return document

    def marker_create(self, marker: dict) -> None:
        dfd = _open_dir(RECEIPTS_DIR)
        try:
            _write_new(dfd, MARKER_NAME, canonical(marker) + b"\n", 0o600)
        except FileExistsError:
            raise UpdateRefused("TRANSACTION_PRESENT") from None
        finally:
            os.close(dfd)

    def marker_write(self, marker: dict) -> None:
        dfd = _open_dir(RECEIPTS_DIR)
        temporary = MARKER_NAME + ".tmp"
        try:
            _unlink(dfd, temporary)
            _write_new(dfd, temporary, canonical(marker) + b"\n", 0o600)
            os.rename(temporary, MARKER_NAME, src_dir_fd=dfd, dst_dir_fd=dfd)
            os.fsync(dfd)
        finally:
            os.close(dfd)

    def marker_remove(self) -> None:
        dfd = _open_dir(RECEIPTS_DIR)
        try:
            _unlink(dfd, MARKER_NAME)
            os.fsync(dfd)
        finally:
            os.close(dfd)

    # before-images
    def preserve(self, kind: str, tag: str, data: bytes) -> None:
        dfd = _open_dir(RECEIPTS_DIR)
        try:
            _write_new(dfd, _before_name(kind, tag), data, 0o600)
        finally:
            os.close(dfd)

    def read_preserved(self, kind: str, tag: str) -> bytes | None:
        dfd = _open_dir(RECEIPTS_DIR)
        try:
            os.lstat(_before_name(kind, tag), dir_fd=dfd)
        except FileNotFoundError:
            return None
        finally:
            os.close(dfd)
        limit = MAX_CONFIG_BYTES if kind == "config" else MAX_PLIST_BYTES
        return self._trusted(RECEIPTS_DIR + "/" + _before_name(kind, tag), limit, 0o600)

    def discard_preserved(self, tag: str) -> None:
        dfd = _open_dir(RECEIPTS_DIR)
        try:
            for kind in KINDS:
                _unlink(dfd, _before_name(kind, tag))
            os.fsync(dfd)
        finally:
            os.close(dfd)

    # staged images
    def stage(self, kind: str, tag: str, data: bytes) -> None:
        parent, name = _staged_name(kind, tag)
        dfd = _open_dir(parent)
        try:
            _write_new(dfd, name, data, 0o644)
        finally:
            os.close(dfd)

    def staged_digest(self, kind: str, tag: str) -> str | None:
        parent, name = _staged_name(kind, tag)
        dfd = _open_dir(parent)
        try:
            os.lstat(name, dir_fd=dfd)
        except FileNotFoundError:
            return None
        finally:
            os.close(dfd)
        limit = MAX_CONFIG_BYTES if kind == "config" else MAX_PLIST_BYTES
        return digest(self._trusted(parent + "/" + name, limit, 0o644))

    def replace(self, kind: str, tag: str) -> None:
        parent, name = _staged_name(kind, tag)
        target = os.path.basename(CONFIG_PATH if kind == "config" else PLIST_PATH)
        dfd = _open_dir(parent)
        try:
            os.rename(name, target, src_dir_fd=dfd, dst_dir_fd=dfd)
            os.fsync(dfd)
        finally:
            os.close(dfd)

    def discard_staged(self, tag: str) -> None:
        for kind in KINDS:
            parent, name = _staged_name(kind, tag)
            dfd = _open_dir(parent)
            try:
                _unlink(dfd, name)
                os.fsync(dfd)
            finally:
                os.close(dfd)

    # receipts
    def receipt_exists(self, name: str) -> bool:
        dfd = _open_dir(RECEIPTS_DIR)
        try:
            os.lstat(name, dir_fd=dfd)
        except FileNotFoundError:
            return False
        finally:
            os.close(dfd)
        return True

    def receipt_write(self, name: str, document: dict) -> None:
        dfd = _open_dir(RECEIPTS_DIR)
        temporary = name + ".tmp"
        try:
            _unlink(dfd, temporary)
            _write_new(dfd, temporary, canonical(document) + b"\n", 0o600)
            try:
                os.link(temporary, name, src_dir_fd=dfd, dst_dir_fd=dfd)
            except FileExistsError:
                pass
            _unlink(dfd, temporary)
            os.fsync(dfd)
        finally:
            os.close(dfd)

    # launchd
    def _launchctl(self, *argv: str) -> int:
        try:
            completed = subprocess.run(
                (LAUNCHCTL, *argv), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=10, check=False, env={"PATH": "/usr/bin:/bin"})
        except (subprocess.TimeoutExpired, OSError):
            raise UpdateRefused("LAUNCHCTL_UNAVAILABLE") from None
        return completed.returncode

    def _launchctl_output(self, *argv: str) -> str:
        try:
            completed = subprocess.run(
                (LAUNCHCTL, *argv), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, timeout=10, check=False, env={"PATH": "/usr/bin:/bin"})
        except (subprocess.TimeoutExpired, OSError):
            raise UpdateRefused("LAUNCHCTL_UNAVAILABLE") from None
        if completed.returncode != 0 or len(completed.stdout) > MAX_LAUNCHCTL_OUTPUT_BYTES:
            raise UpdateRefused("LAUNCHCTL_PRINT_DISABLED_UNEXPECTED")
        return completed.stdout.decode("utf-8", errors="replace")

    def service_enabled(self) -> bool:
        """False only when launchd carries an explicit disable override for the label.

        ``print-disabled`` is an override table, not an inventory: a structurally complete table with
        no row for the label means enabled. Output that is not exactly one header, rows and one
        footer is unreadable and refused (fail closed), the stance of ``require_gateway_enabled``
        in ``service-control.sh``; an empty or header-less listing must not read as "enabled".
        Every row must match that parser's grammar exactly: three fields, a quoted label from
        ``[A-Za-z0-9._-]``, ``=>`` and a known verdict, and a label may appear only once. A row in any
        other shape (an unquoted or re-spaced label, a trailing comma) is refused, never skipped.
        """
        quoted = '"' + LABEL + '"'
        position = 0  # 0 before the header, 1 inside the table, 2 after the footer
        verdicts = []
        labels = set()
        for line in self._launchctl_output("print-disabled", "system").splitlines():
            fields = line.split()
            if not fields:
                continue
            if position == 0 and fields == ["disabled", "services", "=", "{"]:
                position = 1
            elif position == 1 and fields == ["}"]:
                position = 2
            elif (position == 1 and len(fields) == 3 and _DISABLED_ROW_LABEL.fullmatch(fields[0])
                  and fields[1] == "=>" and fields[2] in _DISABLED_ROW_VERDICTS
                  and fields[0] not in labels):
                labels.add(fields[0])
                if fields[0] == quoted:
                    verdicts.append(fields[2])
            else:
                raise UpdateRefused("LAUNCHCTL_PRINT_DISABLED_UNEXPECTED")
        if position != 2:
            raise UpdateRefused("LAUNCHCTL_PRINT_DISABLED_UNEXPECTED")
        if not verdicts:
            return True
        if len(verdicts) != 1 or verdicts[0] not in ("disabled", "enabled", "true", "false"):
            raise UpdateRefused("LAUNCHCTL_PRINT_DISABLED_UNEXPECTED")
        return verdicts[0] in ("enabled", "false")

    def observe_process(self) -> dict:
        """The launchd-observed gateway process, or raise; never cached."""
        try:
            seen = installed._observe_launchd_service("gateway")
        except PeerIdentityError as error:
            raise UpdateRefused("PROCESS_OBSERVATION_REFUSED: " + str(error)[:120]) from None
        return {
            "state": seen.state,
            "program": seen.program,
            "argv": list(seen.argv),
            "working_directory": seen.working_directory,
            "username": seen.username,
            "pid": seen.pid,
        }

    def service_state(self) -> str:
        code = self._launchctl("print", LAUNCHD_ROOT)
        if code == 0:
            return "REGISTERED"
        if code == 113:
            return "ABSENT"
        raise UpdateRefused("LAUNCHCTL_PRINT_UNEXPECTED")

    def stop_service(self) -> None:
        if self._launchctl("disable", LAUNCHD_ROOT) != 0:
            raise UpdateRefused("LAUNCHCTL_DISABLE_FAILED")
        self._launchctl("bootout", LAUNCHD_ROOT)

    def start_service(self) -> None:
        if self._launchctl("enable", LAUNCHD_ROOT) != 0:
            raise UpdateRefused("LAUNCHCTL_ENABLE_FAILED")
        if self._launchctl("bootstrap", "system", PLIST_PATH) != 0:
            raise UpdateRefused("LAUNCHCTL_BOOTSTRAP_FAILED")

    def recover_enable(self) -> None:
        if self._launchctl("enable", LAUNCHD_ROOT) != 0:
            raise UpdateRefused("LAUNCHCTL_ENABLE_FAILED")

    # probes and clock
    def probe(self, port: int, probe: Probe) -> ProbeResult:
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            connection.request(probe.method, probe.path, body=probe.body, headers=dict(probe.headers))
            response = connection.getresponse()
            body = response.read(65_537)
            headers: dict[str, str] = {}
            for key, value in response.getheaders():
                key = key.lower()
                headers[key] = value if key not in headers else headers[key] + ", " + value
            return ProbeResult(response.status, headers, body)
        finally:
            connection.close()

    def now(self) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


# --- transaction engine ---

_MARKER_KEYS = frozenset({
    "schema", "plan_sha256", "release_sha", "prior_release_sha", "set_public_mcp_resource", "phase",
    "dispatched", "config_before_sha256", "config_after_sha256", "plist_before_sha256",
    "plist_after_sha256", "manifest_sha256", "closure_sha256", "started_at", "last_verify",
})


def _unknown(code: str) -> TransactionEffectUnknown:
    return TransactionEffectUnknown(code)


def _validate_marker(marker: Any) -> None:
    try:
        require(isinstance(marker, dict) and set(marker) == _MARKER_KEYS, "marker keys")
        require(marker["schema"] == MARKER_SCHEMA, "marker schema")
        for key in ("plan_sha256", "config_before_sha256", "config_after_sha256", "plist_before_sha256",
                    "plist_after_sha256", "manifest_sha256", "closure_sha256"):
            _sha(marker[key], HEX64, "marker digest")
        for key in ("release_sha", "prior_release_sha"):
            _sha(marker[key], HEX40, "marker release")
        require(marker["phase"] in PHASES, "marker phase")
        require(isinstance(marker["dispatched"], list)
                and all(name in DISPATCH_NAMES for name in marker["dispatched"])
                and len(set(marker["dispatched"])) == len(marker["dispatched"]), "marker dispatched")
        if "recover_enable_done" in marker["dispatched"]:
            # The completion is only ever recorded after its own recorded dispatch.
            require("recover_enable" in marker["dispatched"]
                    and marker["dispatched"].index("recover_enable")
                    < marker["dispatched"].index("recover_enable_done"), "marker recover order")
        require(type(marker["set_public_mcp_resource"]) is bool, "marker flag")
        require(isinstance(marker["last_verify"], list), "marker verify")
    except (ValueError, KeyError):
        raise _unknown("MARKER_MALFORMED") from None


def _tag(marker: dict) -> str:
    return marker["plan_sha256"][:12]


def _receipt_name(marker: dict, suffix: str = "") -> str:
    # One name per attempt: the marker's started_at is persisted, so a re-entry derives the same
    # name, while a later re-apply of the same plan after an abort cannot be mistaken for it.
    stamp = re.sub(r"[^0-9]", "", str(marker["started_at"]))[:14] or "0"
    return "mcp-component-" + marker["release_sha"][:12] + "-" + _tag(marker) + "-" + stamp + suffix + "-v1.json"


def _mark(host: Host, marker: dict, phase: str) -> None:
    marker["phase"] = phase
    host.marker_write(marker)


def _dispatch(host: Host, marker: dict, name: str, phase: str) -> None:
    """Persist the dispatch BEFORE the effect; a recorded dispatch is never replayed."""
    marker["dispatched"].append(name)
    marker["phase"] = phase
    host.marker_write(marker)


def _classify(raw: bytes, before: str, after: str) -> str:
    value = digest(raw)
    return "BEFORE" if value == before else "AFTER" if value == after else "OTHER"


def _observe(host: Host, marker: dict) -> tuple[str, str, str]:
    config = _classify(host.read_config(), marker["config_before_sha256"], marker["config_after_sha256"])
    plist = _classify(host.read_plist(), marker["plist_before_sha256"], marker["plist_after_sha256"])
    return config, plist, host.service_state()


def _settle(host: Host, wanted: str) -> bool:
    for poll in range(SETTLE_POLLS):
        if host.service_state() == wanted:
            return True
        if poll + 1 < SETTLE_POLLS:
            host.sleep(1.0)
    return False


def _discard(host: Host, marker: dict, code: str) -> dict:
    """Pre-effect cleanup: never touches a live installed file or launchd."""
    host.discard_staged(_tag(marker))
    host.discard_preserved(_tag(marker))
    host.marker_remove()
    return {"ok": False, "outcome": "DISCARDED_NO_EFFECT", "code": code}


def _begin_stop(host: Host, marker: dict) -> dict | None:
    """Last pre-effect gate; persists the stop dispatch. Returns a result when it discarded instead."""
    try:
        config, plist, state = _observe(host, marker)
        if config != "BEFORE" or plist != "BEFORE":
            return _discard(host, marker, "FILES_CHANGED_BEFORE_STOP")
        if state != "REGISTERED":
            return _discard(host, marker, "SERVICE_NOT_REGISTERED")
        if not host.service_enabled():
            # An operator-disabled gateway is a kill switch: our stop would be the second disable
            # and our start would re-enable it. Refuse before any effect.
            return _discard(host, marker, "GATEWAY_DISABLED")
        for kind in KINDS:
            expected = marker["config_after_sha256" if kind == "config" else "plist_after_sha256"]
            if host.staged_digest(kind, _tag(marker)) != expected:
                return _discard(host, marker, "STAGED_IMAGE_MISSING_OR_DRIFTED")
        _dispatch(host, marker, "stop", "STOP_DISPATCHED")
    except Exception:
        if "stop" in marker["dispatched"]:
            raise
        return _discard(host, marker, "PRE_STOP_GATE_FAILED")
    return None


def _drive(host: Host, marker: dict, candidate: Candidate) -> dict:
    try:
        return _drive_inner(host, marker, candidate)
    except TransactionEffectUnknown:
        raise
    except UpdateRefused as error:
        # Refused after a recorded dispatch: the effect may or may not have happened.
        raise _unknown("REFUSED_AFTER_DISPATCH:" + error.code) from None
    except Exception as error:
        raise _unknown("UNEXPECTED_" + type(error).__name__.upper()) from None


def _drive_inner(host: Host, marker: dict, candidate: Candidate) -> dict:
    dispatched = marker["dispatched"]
    waited = False
    if "stop" not in dispatched:
        discarded = _begin_stop(host, marker)
        if discarded is not None:
            return discarded
        host.stop_service()
        waited = True
        _settle(host, "ABSENT")
    for _ in range(8):
        config, plist, state = _observe(host, marker)
        if "OTHER" in (config, plist):
            raise _unknown("FOREIGN_IMAGE")
        if state == "REGISTERED":
            if config == "AFTER" and plist == "AFTER":
                return _verify(host, marker, candidate)
            if config == "BEFORE" and plist == "BEFORE":
                if not waited:
                    waited = True
                    if _settle(host, "ABSENT"):
                        continue
                return _recover(host, marker, candidate)
            raise _unknown("MIXED_IMAGE_WHILE_REGISTERED")
        for kind, observed in (("config", config), ("plist", plist)):
            if observed == "BEFORE":
                expected = marker["config_after_sha256" if kind == "config" else "plist_after_sha256"]
                if host.staged_digest(kind, _tag(marker)) != expected:
                    raise _unknown("STAGED_IMAGE_MISSING_OR_DRIFTED")
                host.replace(kind, _tag(marker))
        if "start" in dispatched:
            # A recorded start is never replayed; only observe whether it took effect. The marker
            # already says START_DISPATCHED: do not regress it to REPLACED.
            if _settle(host, "REGISTERED"):
                continue
            raise _unknown("START_NOT_PROVEN")
        _mark(host, marker, "REPLACED")
        _dispatch(host, marker, "start", "START_DISPATCHED")
        host.start_service()
        if not _settle(host, "REGISTERED"):
            raise _unknown("START_NOT_OBSERVED")
    raise _unknown("DRIVE_DID_NOT_CONVERGE")


def _recover(host: Host, marker: dict, candidate: Candidate) -> dict:
    """The stop did not take effect and both files are the before-images: undo only the disable."""
    if "recover_enable_done" in marker["dispatched"]:
        # The compensating enable already completed. Do not run it again: after that point a label
        # found disabled was disabled by someone else (the kill switch), and re-enabling it would
        # override that decision. It needs the operator to enable it before reconcile can close.
        if not host.service_enabled():
            raise _unknown("GATEWAY_DISABLED_AFTER_RECOVERY")
    else:
        if "recover_enable" not in marker["dispatched"]:
            _dispatch(host, marker, "recover_enable", "STOP_DISPATCHED")
        # A crash between the recorded dispatch and the call must not leave the label disabled:
        # without the completion record the next pass runs ``enable`` (it only clears a flag).
        host.recover_enable()
        _dispatch(host, marker, "recover_enable_done", "STOP_DISPATCHED")
    if host.service_state() != "REGISTERED":
        raise _unknown("RECOVER_NOT_PROVEN")
    if probe_failures(host, candidate.port, candidate.probes_before, attempts=VERIFY_ATTEMPTS):
        raise _unknown("RECOVER_NOT_PROVEN")
    if host.service_state() != "REGISTERED":
        # The probes answered, but the label left launchd meanwhile (crash, operator): not proven.
        raise _unknown("RECOVER_NOT_PROVEN")
    name = _receipt_name(marker, "-aborted")
    if not host.receipt_exists(name):
        host.receipt_write(name, _receipt(host, marker, candidate, "ABORTED_UNCHANGED", {}))
    return _close_abort(host, marker)


def _close_abort(host: Host, marker: dict) -> dict:
    host.discard_staged(_tag(marker))
    # Both installed files are provably the before-images, so the copies are redundant, and a
    # leftover set would make a later re-apply of the same plan refuse on an existing before-image.
    host.discard_preserved(_tag(marker))
    host.marker_remove()
    return {"ok": False, "outcome": "ABORTED_UNCHANGED", "code": "STOP_DID_NOT_TAKE_EFFECT"}


def _finish_abort(host: Host, marker: dict) -> dict:
    """Re-entry after the abort receipt exists: only the cleanup is left, and it needs no before-image.

    The aborted receipt is written only after the compensating enable and the prior-release probes
    were proven, so a crash between the image cleanup and the marker removal must not strand a
    marker whose before-images are already gone. The installed state is re-observed, never assumed.
    """
    config, plist, state = _observe(host, marker)
    if (config, plist, state) != ("BEFORE", "BEFORE", "REGISTERED"):
        raise _unknown("ABORT_STATE_CHANGED")
    return _close_abort(host, marker)


def _process_mismatches(observed: dict, expected: dict) -> list[str]:
    mismatches = []
    if observed.get("state") != "running":
        mismatches.append("STATE")
    if list(observed.get("argv", ())) != expected["argv"] or observed.get("program") != expected["argv"][0]:
        mismatches.append("ARGV")
    if observed.get("working_directory") != expected["working_directory"]:
        mismatches.append("WORKING_DIRECTORY")
    if observed.get("username") != GATEWAY_USER:
        mismatches.append("USER")
    if type(observed.get("pid")) is not int or observed["pid"] <= 0:
        mismatches.append("PID")
    return mismatches


def _process_expectation(candidate: Candidate) -> dict:
    document = _strict_plist(candidate.plist_after)
    return {"argv": list(document["ProgramArguments"]), "working_directory": document["WorkingDirectory"]}


def _observe_process_once(host: Host, expected: dict) -> tuple[dict | None, list[str]]:
    """One launchd observation: the matching process, or the reasons it does not match."""
    try:
        observed = host.observe_process()
    except UpdateRefused as error:
        return None, ["OBSERVATION:" + error.code]
    mismatches = _process_mismatches(observed, expected)
    if mismatches:
        return None, mismatches
    return observed, []


def _await_stable_process(host: Host, expected: dict) -> dict:
    """Bounded wait for launchd to run the AFTER image under one pid, not a bystander.

    Read-only; the caller never rolls back on failure. Require a launchd-observed running process
    whose argv and working directory equal the after-image plist, the gateway user, and one pid
    across consecutive polls. This runs BEFORE the probes; ``_hold_process`` and
    ``_confirm_process`` re-check the same pid AFTER them.
    """
    run = 0
    last_pid: int | None = None
    reasons: list[str] = ["NOT_OBSERVED"]
    for poll in range(PROCESS_POLLS):
        observed, problems = _observe_process_once(host, expected)
        if observed is None:
            reasons, run, last_pid = problems, 0, None
        elif observed["pid"] == last_pid:
            run += 1
        else:
            # The first matching poll, or a pid change: restart the stability run.
            if last_pid is not None:
                reasons = ["PID_CHANGED"]
            run, last_pid = 1, observed["pid"]
        if observed is not None and run >= PROCESS_STABLE_POLLS:
            return {"pid": observed["pid"], "program": observed["program"]}
        if poll + 1 < PROCESS_POLLS:
            host.sleep(1.0)
    raise TransactionEffectUnknown("PROCESS_IDENTITY_NOT_PROVEN:" + ",".join(reasons)[:120])


def _confirm_process(host: Host, expected: dict, pid: int) -> None:
    """The same process, still running with the after-image identity, observed AFTER the probes."""
    observed, problems = _observe_process_once(host, expected)
    if observed is None:
        reasons = problems
    elif observed["pid"] != pid:
        reasons = ["PID_CHANGED"]
    else:
        return
    raise TransactionEffectUnknown("PROCESS_IDENTITY_NOT_PROVEN:AFTER_PROBES:" + ",".join(reasons)[:90])


def _hold_process(host: Host, expected: dict, pid: int) -> None:
    """Keep observing the answering pid past launchd's 10 s throttle interval, one poll a second.

    The probes cannot say which process answered. Watching the launchd pid for a window that
    outlasts the throttle interval after the probes catches a release that answered and then dies
    or is respawned; it does not tie the answering listener to that pid.
    """
    for _ in range(PROCESS_HOLD_POLLS):
        host.sleep(1.0)
        _confirm_process(host, expected, pid)


def _record_verify_failure(host: Host, marker: dict, details: list[str]) -> None:
    marker["last_verify"] = details
    host.marker_write(marker)


def _verify(host: Host, marker: dict, candidate: Candidate) -> dict:
    """Read-only and repeatable; a failure never rolls anything back.

    Order: readback join; a stable launchd process; the probes; a hold window on that same pid; the
    probes again; a final observation of that pid. The process proof therefore brackets the probes.
    """
    readback = host.readback(marker["release_sha"])
    joined = (
        readback.get("release_sha") == marker["release_sha"]
        and readback.get("config_sha256") == marker["config_after_sha256"]
        and readback.get("release_manifest_sha256") == marker["manifest_sha256"]
        and readback.get("network_closure_sha256") == marker["closure_sha256"]
    )
    if not joined:
        raise _unknown("READBACK_JOIN_FAILED")
    expected = _process_expectation(candidate)
    try:
        process = _await_stable_process(host, expected)
    except TransactionEffectUnknown as error:
        _record_verify_failure(host, marker, [error.code[:140]])
        raise
    failures = probe_failures(host, candidate.port, candidate.probes_after, attempts=VERIFY_ATTEMPTS)
    if failures:
        _record_verify_failure(host, marker, failures)
        raise _unknown("VERIFY_FAILED")
    try:
        _hold_process(host, expected, process["pid"])
    except TransactionEffectUnknown as error:
        _record_verify_failure(host, marker, [error.code[:140]])
        raise
    failures = probe_failures(host, candidate.port, candidate.probes_after, attempts=PROBE_RECHECK_ATTEMPTS)
    if failures:
        _record_verify_failure(host, marker, failures)
        raise _unknown("VERIFY_FAILED")
    try:
        _confirm_process(host, expected, process["pid"])
    except TransactionEffectUnknown as error:
        _record_verify_failure(host, marker, [error.code[:140]])
        raise
    _mark(host, marker, "VERIFIED")
    name = _receipt_name(marker)
    if not host.receipt_exists(name):
        host.receipt_write(name, _receipt(host, marker, candidate, "COMPLETE", readback, process))
    host.marker_remove()
    return {"ok": True, "outcome": "COMPLETE", "release_sha": marker["release_sha"],
            "plan_sha256": marker["plan_sha256"]}


def _receipt(host: Host, marker: dict, candidate: Candidate, outcome: str, readback: dict,
             process: dict | None = None) -> dict:
    return {
        "schema": RECEIPT_SCHEMA,
        "outcome": outcome,
        "release_sha": marker["release_sha"],
        "prior_release_sha": marker["prior_release_sha"],
        "plan_sha256": marker["plan_sha256"],
        "set_public_mcp_resource": marker["set_public_mcp_resource"],
        "config": {"before_sha256": marker["config_before_sha256"], "after_sha256": marker["config_after_sha256"]},
        "plist": {"before_sha256": marker["plist_before_sha256"], "after_sha256": marker["plist_after_sha256"]},
        "release_manifest_sha256": marker["manifest_sha256"],
        "network_closure_sha256": marker["closure_sha256"],
        "readback": readback,
        "process": dict(process or {}),
        "dispatched": list(marker["dispatched"]),
        "probes_after": [probe.name for probe in candidate.probes_after],
        # An aborted attempt discards its copies (both files are provably the before-images).
        "before_images": [] if outcome == "ABORTED_UNCHANGED" else [_before_name(kind, _tag(marker)) for kind in KINDS],
        "recorded_at": host.now(),
    }


def build_plan(host: Host, release_sha: str, set_public: bool) -> tuple[dict, Candidate]:
    candidate = compile_candidate(host.read_config(), host.read_plist(), release_sha=release_sha,
                                  set_public_mcp_resource=set_public)
    manifest = host.verify_release(release_sha)
    closure = host.verify_closure()
    return plan_document(candidate, manifest_sha256=manifest, closure_sha256=closure), candidate


def plan(host: Host, *, release_sha: str, set_public: bool) -> dict:
    host.require_root()
    host.receipts_ready()
    document, _ = build_plan(host, release_sha, set_public)
    return {"ok": True, "outcome": "PLANNED", "plan": document, "plan_sha256": plan_digest(document),
            "warnings": list(WARNINGS)}


def apply(host: Host, *, release_sha: str, set_public: bool, plan_sha256: str) -> dict:
    host.require_root()
    host.receipts_ready()
    host.acquire_lock()
    try:
        if host.marker_read() is not None:
            raise UpdateRefused("TRANSACTION_PRESENT")
        document, candidate = build_plan(host, release_sha, set_public)
        if plan_digest(document) != plan_sha256:
            raise UpdateRefused("PLAN_DIGEST_MISMATCH")
        tag = plan_sha256[:12]
        for kind in KINDS:
            if host.staged_digest(kind, tag) is not None:
                raise UpdateRefused("STAGED_PRESENT")
            if host.read_preserved(kind, tag) is not None:
                raise UpdateRefused("PRESERVED_PRESENT")
        if host.service_state() != "REGISTERED":
            raise UpdateRefused("SERVICE_NOT_REGISTERED")
        if not host.service_enabled():
            raise UpdateRefused("GATEWAY_DISABLED")
        if probe_failures(host, candidate.port, candidate.probes_before, attempts=1):
            raise UpdateRefused("PRIOR_UNHEALTHY")
        marker = {
            "schema": MARKER_SCHEMA,
            "plan_sha256": plan_sha256,
            "release_sha": release_sha,
            "prior_release_sha": candidate.prior_release_sha,
            "set_public_mcp_resource": candidate.set_public_mcp_resource,
            "phase": "INTENT",
            "dispatched": [],
            "config_before_sha256": candidate.config_before_sha256,
            "config_after_sha256": candidate.config_after_sha256,
            "plist_before_sha256": candidate.plist_before_sha256,
            "plist_after_sha256": candidate.plist_after_sha256,
            "manifest_sha256": document["release_manifest_sha256"],
            "closure_sha256": document["network_closure_sha256"],
            "started_at": host.now(),
            "last_verify": [],
        }
        host.marker_create(marker)
        try:
            host.preserve("config", tag, candidate.config_before)
            host.preserve("plist", tag, candidate.plist_before)
            host.stage("config", tag, candidate.config_after)
            host.stage("plist", tag, candidate.plist_after)
            _mark(host, marker, "STAGED")
        except Exception:
            return _discard(host, marker, "STAGE_FAILED")
        return _drive(host, marker, candidate)
    finally:
        host.release_lock()


def _candidate_from_marker(host: Host, marker: dict) -> Candidate:
    try:
        tag = _tag(marker)
        config = host.read_preserved("config", tag)
        plist = host.read_preserved("plist", tag)
        if config is None or plist is None:
            raise _unknown("BEFORE_IMAGE_MISSING")
        if digest(config) != marker["config_before_sha256"] or digest(plist) != marker["plist_before_sha256"]:
            raise _unknown("BEFORE_IMAGE_DRIFTED")
        candidate = compile_candidate(config, plist, release_sha=marker["release_sha"],
                                      set_public_mcp_resource=marker["set_public_mcp_resource"])
        if (candidate.config_after_sha256 != marker["config_after_sha256"]
                or candidate.plist_after_sha256 != marker["plist_after_sha256"]):
            raise _unknown("AFTER_IMAGE_DRIFTED")
        return candidate
    except TransactionEffectUnknown:
        raise
    except Exception as error:
        raise _unknown("CANDIDATE_UNAVAILABLE_" + type(error).__name__.upper()) from None


def reconcile(host: Host, *, release_sha: str) -> dict:
    host.require_root()
    host.receipts_ready()
    host.acquire_lock()
    try:
        try:
            marker = host.marker_read()
        except Exception:
            raise _unknown("MARKER_UNREADABLE") from None
        if marker is None:
            raise UpdateRefused("NO_TRANSACTION")
        _validate_marker(marker)
        if marker["release_sha"] != release_sha:
            raise UpdateRefused("RELEASE_DIFFERS_FROM_TRANSACTION")
        if "stop" not in marker["dispatched"]:
            return _discard(host, marker, "RECONCILE_NO_EFFECT")
        if "recover_enable" in marker["dispatched"] and host.receipt_exists(_receipt_name(marker, "-aborted")):
            try:
                return _finish_abort(host, marker)
            except TransactionEffectUnknown:
                raise
            except Exception as error:
                raise _unknown("UNEXPECTED_" + type(error).__name__.upper()) from None
        return _drive(host, marker, _candidate_from_marker(host, marker))
    finally:
        host.release_lock()


# --- closed command line ---

_VERBS: dict[str, dict[str, bool]] = {
    "plan": {"--release-sha": True, "--set-public-mcp-resource": False},
    "apply": {"--release-sha": True, "--set-public-mcp-resource": False, "--plan-sha256": True},
    "reconcile": {"--release-sha": True},
}


class UsageError(ValueError):
    pass


def parse_arguments(argv: list[str]) -> tuple[str, dict[str, Any]]:
    if not argv or argv[0] not in _VERBS:
        raise UsageError("verb")
    verb = argv[0]
    allowed = _VERBS[verb]
    values: dict[str, Any] = {}
    index = 1
    while index < len(argv):
        flag = argv[index]
        if flag not in allowed or flag in values:
            raise UsageError("flag")
        if allowed[flag]:
            if index + 1 >= len(argv):
                raise UsageError("value")
            values[flag] = argv[index + 1]
            index += 2
        else:
            values[flag] = True
            index += 1
    release = values.get("--release-sha")
    if not isinstance(release, str) or HEX40.fullmatch(release) is None:
        raise UsageError("release")
    if verb == "apply":
        plan_value = values.get("--plan-sha256")
        if not isinstance(plan_value, str) or HEX64.fullmatch(plan_value) is None:
            raise UsageError("plan")
    return verb, values


def _emit(document: dict) -> None:
    sys.stdout.write(json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def main(argv: list[str] | None = None, host: Host | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        verb, values = parse_arguments(arguments)
    except UsageError:
        sys.stderr.write("usage: mcp_component_update.py plan|apply|reconcile --release-sha <40hex> "
                         "[--set-public-mcp-resource] [--plan-sha256 <64hex>]\n")
        return 64
    host = host if host is not None else ProductionHost()
    release = values["--release-sha"]
    public = bool(values.get("--set-public-mcp-resource", False))
    try:
        if verb == "plan":
            result = plan(host, release_sha=release, set_public=public)
        elif verb == "apply":
            result = apply(host, release_sha=release, set_public=public, plan_sha256=values["--plan-sha256"])
        else:
            result = reconcile(host, release_sha=release)
    except UpdateRefused as error:
        _emit({"ok": False, "outcome": "REFUSED", "code": error.code})
        return 1
    except TransactionEffectUnknown as error:
        _emit({"ok": False, "outcome": "EFFECT_UNKNOWN", "code": error.code,
               "note": "marker and before-images preserved; nothing is replayed; no automatic rollback: a "
                       "restore is a separately approved manual copy of the before-images, and "
                       "START_NOT_PROVEN needs only a manual launchctl enable + bootstrap (see the module docs)"})
        return 2
    except Exception as error:
        _emit({"ok": False, "outcome": "REFUSED", "code": "UNEXPECTED_" + type(error).__name__.upper()})
        return 1
    _emit(result)
    if result["ok"]:
        return 0
    return 3


if __name__ == "__main__":
    sys.exit(main())

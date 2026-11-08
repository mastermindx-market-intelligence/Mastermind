#!/usr/bin/env python3
"""Owned, transactional component update for the installed Executive MCP gateway.

This replaces the unowned 2026-09-27 ``mcp-component-*`` update procedure whose
code was never in the repository. It changes exactly two installed files of the
gateway role and nothing else:

* ``config/executive-mcp.json`` - ``release_sha`` and, only when asked,
  ``public_mcp_resource`` (exactly the public ``/mcp`` audience);
* ``/Library/LaunchDaemons/com.mastermind.executive.mcp.plist`` - the release
  substitution of the closed installed gateway profile.

OPTIONALLY, and only when the caller supplies the PAIRED selected-child
publication selection: the one frozen ``selected_child_target`` projection of
the installed gateway configuration.  The selection is ONE optional input to
the SAME verbs: both coordinates absent preserve the source-only behaviour
byte-for-byte, and exactly one of them refuses.  The publication is
non-secret, is qualified by its own closed validator, and is retained in the
transaction marker so a reconciliation recovers THAT candidate and never
reopens a replacement input.  A source-only release update carries an
installed publication forward byte for byte.

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

import asyncio
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
    # The one frozen selected-child publication this candidate installs.
    # Absent preserves the existing source-only behaviour byte for byte.
    selected_child_target: dict[str, Any] | None = None
    # The FROZEN capability-profile digest map this candidate applied, taken
    # from the exact sealed target release registry at plan time.  It is
    # bound into the plan identity and retained in the transaction marker so
    # a recovery reproduces THIS after-image and never a re-derived one.
    capability_profile_digests: dict[str, str] | None = None

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
                      set_public_mcp_resource: bool,
                      selected_child_target: dict[str, Any] | None = None,
                      capability_profile_digests: dict[str, str] | None = None) -> Candidate:
    """Compile the only permitted change set, or raise UpdateRefused."""
    try:
        return _compile_candidate(prior_config, prior_plist, release_sha, set_public_mcp_resource,
                                  selected_child_target, capability_profile_digests)
    except UpdateRefused:
        raise
    except AuthError as error:
        raise UpdateRefused("CANDIDATE_REFUSED: auth policy " + str(error.code.value)[:80]) from None
    except (ValueError, KeyError, TypeError) as error:
        raise UpdateRefused("CANDIDATE_REFUSED: " + str(error)[:160]) from None


def _preserved_profile_ids(prior: dict[str, Any]) -> set[str]:
    """The exact capability-profile ids of the preserved installed missions."""

    block = prior.get("coo")
    missions = block.get("missions") if isinstance(block, dict) else None
    if not isinstance(missions, list):
        return set()
    return {row["capability_profile_id"] for row in missions
            if isinstance(row, dict) and type(row.get("capability_profile_id")) is str}


def _validate_capability_profile_map(
    digests: Any, profile_ids: set[str],
) -> dict[str, str]:
    """The exact frozen map: one lowercase64hex digest per preserved profile.

    The keys correspond EXACTLY to the relevant original preserved mission
    profile ids: an extra entry, a missing entry or a malformed value is a
    refusal, never a partial rewrite.
    """

    if type(digests) is not dict:
        raise ValueError("capability profile digest map is not an object")
    if set(digests) != set(profile_ids):
        raise ValueError("capability profile digest map does not match the preserved missions")
    for key, value in digests.items():
        if type(key) is not str or not key:
            raise ValueError("capability profile digest key is invalid")
        if type(value) is not str or HEX64.fullmatch(value) is None:
            raise ValueError("capability profile digest value is invalid")
    return {key: digests[key] for key in sorted(digests)}


def derive_sealed_capability_profile_digests(
    release_sha: str, profile_ids: tuple[str, ...], budget: Any,
) -> dict[str, str]:
    """Reuse the sealed target registry proof for component and gateway owners."""
    from control_plane.executive_agent_capabilities import ExecutionCapabilityRegistry
    root = Path(installed._SERVICE_RELEASES) / release_sha
    policy = root / "config" / "executive_claude_principal_capabilities.json"
    try:
        before = installed._observe_ancestors(str(policy), budget)
        registry = ExecutionCapabilityRegistry.load(policy, source_root=root)
        after = installed._observe_ancestors(str(policy), budget)
    except Exception as error:
        raise UpdateRefused(
            "CAPABILITY_PROFILE_UNAVAILABLE:" + type(error).__name__.upper()) from None
    if before != after:
        raise UpdateRefused("CAPABILITY_PROFILE_UNAVAILABLE:ANCESTORS_CHANGED")
    digests: dict[str, str] = {}
    for profile_id in profile_ids:
        profile = registry.profiles.get(profile_id)
        if profile is None or not profile.enabled:
            raise UpdateRefused("CAPABILITY_PROFILE_UNAVAILABLE")
        digests[profile_id] = profile.profile_digest
    return digests


def _apply_capability_profile_digests(
    prior: dict[str, Any], proposed: dict[str, Any],
    digests: dict[str, str] | None,
) -> None:
    """Re-derive the installed missions' capability-profile digests.

    The exact replacement comes from the TARGET sealed release registry, so
    a legitimate tool-projection change moves the mission's stored digest
    with it. ONLY that one field changes: every other mission field,
    principal action, scope and binding is preserved byte for byte, and no
    principal realm or permission is created.

    ``None`` is the LEGACY no-rewrite compilation: it reproduces the
    original behaviour byte for byte and is what a marker without the frozen
    map member recovers with.  A supplied map is the frozen map of the
    original transaction and is validated against the preserved missions
    before a single field is rewritten.
    """

    if digests is None:
        # The legacy no-rewrite compilation: the installed digests stay
        # exactly as they are.  This is the pre-C30 recovery behaviour and
        # it is reproduced exactly, never approximated.
        return
    frozen = _validate_capability_profile_map(digests, _preserved_profile_ids(prior))
    if not frozen:
        # An installation without a preserved mission profile has nothing to
        # rewrite.  The source-only behaviour is preserved byte for byte.
        return
    prior_block = prior.get("coo")
    proposed_block = proposed.get("coo")
    if not isinstance(prior_block, dict) or not isinstance(proposed_block, dict):
        raise ValueError("candidate changed the installed COO block")
    prior_missions = prior_block.get("missions")
    missions = proposed_block.get("missions")
    if not isinstance(prior_missions, list) or not isinstance(missions, list):
        raise ValueError("candidate changed the installed mission set")
    if len(missions) != len(prior_missions):
        raise ValueError("candidate changed the installed mission set")
    for row, prior_row in zip(missions, prior_missions):
        if not isinstance(row, dict) or not isinstance(prior_row, dict):
            raise ValueError("candidate changed the installed mission set")
        profile_id = row.get("capability_profile_id")
        digest = frozen.get(profile_id) if type(profile_id) is str else None
        if digest is None:
            continue
        if row.get("capability_profile_digest") != prior_row.get("capability_profile_digest"):
            raise ValueError("candidate changed an installed capability-profile digest")
        row["capability_profile_digest"] = digest
    left = copy.deepcopy(proposed_block)
    right = copy.deepcopy(prior_block)
    for block in (left, right):
        for mission in block.get("missions") or []:
            if isinstance(mission, dict):
                mission["capability_profile_digest"] = None
    if left != right:
        raise ValueError("candidate changed an unrelated installed COO field")


def _compile_candidate(prior_config: bytes, prior_plist_bytes: bytes, release_sha: str,
                       set_public: bool, selected_child_target: dict[str, Any] | None = None,
                       capability_profile_digests: dict[str, str] | None = None) -> Candidate:
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
    if selected_child_target is not None:
        # The frozen publication is qualified by its own closed validator
        # before it reaches the candidate, and it may only be installed or
        # replaced: a candidate never withdraws an installed target.
        proposed["selected_child_target"] = copy.deepcopy(selected_child_target)
    elif "selected_child_target" in prior:
        # A source-only release update carries the INSTALLED publication
        # forward byte for byte. It is never withdrawn and never rewritten.
        proposed["selected_child_target"] = copy.deepcopy(prior["selected_child_target"])
    _apply_capability_profile_digests(prior, proposed, capability_profile_digests)
    frozen_digests = (None if capability_profile_digests is None
                      else _validate_capability_profile_map(
                          capability_profile_digests, _preserved_profile_ids(prior)))
    changed = {key for key in set(prior) | set(proposed) if prior.get(key, _MISSING) != proposed.get(key, _MISSING)}
    require(changed <= {"release_sha", "public_mcp_resource", "selected_child_target", "coo"},
            "candidate changed an unrelated config field")
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
        selected_child_target=copy.deepcopy(proposed.get("selected_child_target")),
        capability_profile_digests=(None if frozen_digests is None
                                    else dict(frozen_digests)),
    )


_MISSING = object()


def plan_document(candidate: Candidate, *, manifest_sha256: str, closure_sha256: str) -> dict:
    document = {
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
    if candidate.selected_child_target is not None:
        # The frozen publication's identity, not its content: the operator
        # approves this exact work scope, root and material digest.
        document["selected_child_target"] = {
            "work_ref": candidate.selected_child_target["work_ref"],
            "root_job_id": candidate.selected_child_target["root_job_id"],
            "material_digest": candidate.selected_child_target["material_digest"],
        }
    # The frozen capability-profile transform is part of the plan identity:
    # the operator approves THIS exact map, and the after-image it produces
    # is the one a recovery reproduces.  An empty map is still recorded.
    document["capability_profile_digests"] = dict(
        candidate.capability_profile_digests or {})
    return document


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
    def read_selected_child_input(self, path: str, sha256: str) -> bytes: ...
    def installed_coo_source(self) -> Any: ...
    def begin_selected_child_preparation(self) -> bytes: ...
    def preparation_destination_available(self, destination: str) -> None: ...
    def request_selected_child_capture(self, frame: dict[str, Any]) -> dict[str, Any]: ...
    def recheck_selected_child_preparation(self) -> None: ...
    def ceo_ingress_socket_path(self) -> str: ...
    def preparation_input_path(self, work_ref: str) -> str: ...
    def write_selected_child_input(self, publication: dict[str, Any],
                                   destination: str) -> dict[str, Any]: ...
    def derive_capability_profile_digests(
        self, release_sha: str, profile_ids: tuple[str, ...]
    ) -> dict[str, str]: ...
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
        self._preparation: _PreparationQualification | None = None

    # identity and trust
    def require_root(self) -> None:
        if sys.platform != "darwin":
            raise UpdateRefused("PLATFORM_UNSUPPORTED")
        if os.geteuid() != 0:
            raise UpdateRefused("ROOT_REQUIRED")

    def _budget(self) -> Any:
        if self._preparation is not None:
            return self._preparation.budget
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
        if self._preparation is not None:
            current = _preparation_config(self._preparation.topology, self._preparation.budget)
            if current != self._preparation.config:
                raise UpdateRefused("PREPARATION_SOURCE_CHANGED")
            return current[0]
        return self._trusted(CONFIG_PATH, MAX_CONFIG_BYTES, installed._role_topology("gateway").config_mode)

    def read_plist(self) -> bytes:
        return self._trusted(PLIST_PATH, MAX_PLIST_BYTES, 0o644)

    def read_selected_child_input(self, path: str, sha256: str) -> bytes:
        """Read the PAIRED capture input through the incumbent trusted read.

        The read is the existing no-follow, bounded, single-link,
        root-controlled-ancestor pattern: the same custody the installed
        configuration and plist already use. The supplied digest binds
        those bytes to the caller's selection; it is never on its own a
        proof of source authenticity, which comes from this custody read
        together with the closed validator on the content and the derived
        material digest over the frozen coordinates.
        """
        if type(path) is not str or not path or "\x00" in path or not path.startswith("/"):
            raise UpdateRefused("SELECTED_CHILD_INPUT_PATH_INVALID")
        if type(sha256) is not str or HEX64.fullmatch(sha256) is None:
            raise UpdateRefused("SELECTED_CHILD_INPUT_DIGEST_INVALID")
        data = self._trusted(path, MAX_CONFIG_BYTES, 0o600)
        if digest(data) != sha256:
            raise UpdateRefused("SELECTED_CHILD_INPUT_DIGEST_MISMATCH")
        return data


    def begin_selected_child_preparation(self) -> bytes:
        if os.getegid() != 0:
            raise UpdateRefused("PREPARATION_ROOT_GROUP_REQUIRED")
        try:
            self._preparation = _PreparationQualification()
            return self._preparation.config[0]
        except (PeerIdentityError, ValueError, TypeError, KeyError, OSError):
            raise UpdateRefused("PREPARATION_SOURCE_UNAVAILABLE") from None

    def preparation_destination_available(self, destination: str) -> None:
        try:
            os.lstat(destination)
        except FileNotFoundError:
            return
        except OSError:
            raise UpdateRefused("PREPARATION_INPUT_REFUSED:unavailable") from None
        raise UpdateRefused("PREPARATION_INPUT_REFUSED:already exists")

    def request_selected_child_capture(self, frame: dict[str, Any]) -> dict[str, Any]:
        from integrations.mastermind_workspace_app.contract import MAX_RESPONSE_BYTES
        qualification = self._preparation
        if qualification is None:
            raise UpdateRefused("PREPARATION_SOURCE_UNAVAILABLE")
        qualification.check()
        packet = canonical({
            "schema": _PREPARATION_CHILD_SCHEMA,
            "release_sha": qualification.release_sha,
            "config_sha256": hashlib.sha256(qualification.config[0]).hexdigest(),
            "deadline": qualification.budget.caller_deadline, "frame": frame,
        }) + b"\n"
        if len(packet) > MAX_CONFIG_BYTES:
            raise UpdateRefused("PREPARATION_SELECTOR_INVALID")
        _name, uid, gid, groups = qualification.account
        process = subprocess.Popen(
            [installed._NETWORK_RUNTIME_LAUNCHER, "-I", "-B",
             str(qualification.helper), _PREPARATION_CHILD_VERB],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            close_fds=True, bufsize=0, cwd=str(qualification.root),
            env={"LANG": "C", "PYTHONDONTWRITEBYTECODE": "1"},
            user=uid, group=gid, extra_groups=list(groups))
        return _exchange_preparation_child(
            process, packet, budget=qualification.budget, maximum=MAX_RESPONSE_BYTES)

    def recheck_selected_child_preparation(self) -> None:
        try:
            if self._preparation is None:
                raise UpdateRefused("PREPARATION_SOURCE_UNAVAILABLE")
            self._preparation.check()
        except (PeerIdentityError, ValueError, TypeError, KeyError, OSError):
            raise UpdateRefused("PREPARATION_SOURCE_CHANGED") from None

    def installed_coo_source(self) -> Any:
        """The installed COO source of the sealed gateway configuration.

        The source is the incumbent installed composition over the sealed
        release: it re-proves the document, the mission, the capability
        registry and the binding.  A changed, unreadable or withdrawn
        installation is unavailable, never an inferred permission.
        """
        from ops.executive_os.coo_principal_host import CooInstalledSource
        document = _strict_json(self.read_config(), "MCP_COMPONENT_CONFIG_MALFORMED")
        release = document.get("release_sha") if type(document) is dict else None
        if type(release) is not str or HEX40.fullmatch(release) is None:
            raise UpdateRefused("PREPARATION_CONFIG_INVALID")
        root = Path(installed._SERVICE_RELEASES) / release
        try:
            return CooInstalledSource.from_path(
                CONFIG_PATH, root, expected_uid=os.geteuid())
        except (ValueError, TypeError, KeyError, OSError):
            raise UpdateRefused("PREPARATION_SOURCE_UNAVAILABLE") from None

    def ceo_ingress_socket_path(self) -> str:
        """The canonical CeoIngress socket of the installed configuration."""

        document = _strict_json(self.read_config(), "MCP_COMPONENT_CONFIG_MALFORMED")
        path = document.get("ceo_ingress_socket_path") if type(document) is dict else None
        if type(path) is not str or not path.startswith("/"):
            raise UpdateRefused("PREPARATION_CONFIG_INVALID")
        return path

    def preparation_input_path(self, work_ref: str) -> str:
        """The one installed destination of a preparation."""

        return preparation_destination(work_ref)

    def write_selected_child_input(self, publication: dict[str, Any],
                                   destination: str) -> dict[str, Any]:
        """Materialize the closed publication with the exclusive writer.

        The writer is the incumbent one: an exclusive, no-follow create of a
        root-owned, single-link, group-0 file under a root-controlled parent
        chain, with an exact readback.  It never overwrites an existing
        file.
        """
        from ops.executive_os.coo_principal_host import write_selected_child_target_input
        try:
            os.makedirs(PREPARATION_CAPTURE_DIR, mode=0o755, exist_ok=True)
        except OSError:
            raise UpdateRefused("PREPARATION_INPUT_REFUSED") from None
        try:
            return write_selected_child_target_input(publication, destination)
        except ValueError as error:
            raise UpdateRefused("PREPARATION_INPUT_REFUSED:" + str(error)[:80]) from None

    def verify_release(self, release_sha: str) -> str:
        try:
            topology = installed._role_topology("gateway")
            budget = self._budget()
            observed = installed._verify_release(topology, release_sha, budget)
            installed._recheck_release(observed, budget)
        except PeerIdentityError as error:
            raise UpdateRefused("RELEASE_UNVERIFIED:" + str(error)) from None
        return observed.manifest_digest

    def derive_capability_profile_digests(
        self, release_sha: str, profile_ids: tuple[str, ...]
    ) -> dict[str, str]:
        """The exact capability-profile digests of the TARGET sealed release.

        The registry inside the sealed target release is the only source of
        the replacement digest. A hand-authored digest, a copied prior digest
        or a hardcoded tool-schema digest is never accepted, and no new
        principal realm or permission is created here.
        """
        try:
            budget = self._budget()
        except Exception as error:
            raise UpdateRefused(
                "CAPABILITY_PROFILE_UNAVAILABLE:" + type(error).__name__.upper()) from None
        return derive_sealed_capability_profile_digests(release_sha, profile_ids, budget)

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
# The selected-child publication is OPTIONAL in the marker: a transaction
# that carries none keeps the original marker shape byte for byte.
#
# The frozen capability-profile digest map is OPTIONAL for the same reason:
# an AUTHENTIC OLD marker predates the map and is recovered with the legacy
# no-rewrite compilation.  Every NEW transaction records the exact chosen
# map, including ``{}`` where there is no mission to rewrite, so the
# after-image of a recovery never depends on the CURRENT registry.
_MARKER_OPTIONAL_KEYS = frozenset({"selected_child_target", "capability_profile_digests"})


def _unknown(code: str) -> TransactionEffectUnknown:
    return TransactionEffectUnknown(code)


def _validate_marker(marker: Any) -> None:
    try:
        require(isinstance(marker, dict), "marker shape")
        keys = set(marker)
        require(_MARKER_KEYS <= keys and keys <= (_MARKER_KEYS | _MARKER_OPTIONAL_KEYS),
                "marker keys")
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
        if "selected_child_target" in marker:
            # The original captured publication, retained in the transaction
            # so a reconciliation recovers THIS candidate and never a
            # replacement input.
            from control_plane.coo_principal_host import validate_selected_child_target
            publication = marker["selected_child_target"]
            if publication is not None:
                validate_selected_child_target(publication)
        if "capability_profile_digests" in marker:
            # The FROZEN map of the original transaction: one lowercase64hex
            # digest per preserved mission profile id.  A malformed entry, an
            # extra entry or a missing entry is a malformed marker, never a
            # partially rewritten candidate.
            frozen = marker["capability_profile_digests"]
            if type(frozen) is not dict:
                raise ValueError("marker capability profile map")
            for key, value in frozen.items():
                if type(key) is not str or not key:
                    raise ValueError("marker capability profile key")
                if type(value) is not str or HEX64.fullmatch(value) is None:
                    raise ValueError("marker capability profile value")
    except (ValueError, KeyError, TypeError):
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
    receipt = {
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
    if candidate.selected_child_target is not None:
        # The published publication's identity for the parent's readback.
        receipt["selected_child_target"] = {
            "work_ref": candidate.selected_child_target["work_ref"],
            "root_job_id": candidate.selected_child_target["root_job_id"],
            "material_digest": candidate.selected_child_target["material_digest"],
        }
    return receipt


def selected_child_selector(input_path: str | None, input_sha256: str | None) -> tuple[str, str] | None:
    """The PAIRED selected-child publication input, or NOTHING.

    The two coordinates are ONE selection: the exact qualified input path
    and the exact digest of its raw bytes. Both absent preserve the
    existing source-only behaviour byte for byte; exactly one of them is a
    refusal and is never treated as an absent selection.
    """

    if input_path is None and input_sha256 is None:
        return None
    if input_path is None or input_sha256 is None:
        raise UpdateRefused("SELECTED_CHILD_INPUT_INCOMPLETE")
    if type(input_path) is not str or not input_path:
        raise UpdateRefused("SELECTED_CHILD_INPUT_PATH_INVALID")
    if type(input_sha256) is not str or HEX64.fullmatch(input_sha256) is None:
        raise UpdateRefused("SELECTED_CHILD_INPUT_DIGEST_INVALID")
    return (input_path, input_sha256)


def _selected_child_publication(host: Host, selector: tuple[str, str] | None) -> dict[str, Any] | None:
    """Qualify the paired capture input with the closed publication validator."""

    if selector is None:
        return None
    raw = host.read_selected_child_input(selector[0], selector[1])
    document = _strict_json(raw, "MCP_COMPONENT_SELECTED_CHILD_MALFORMED")
    if type(document) is not dict:
        raise UpdateRefused("SELECTED_CHILD_INPUT_INVALID")
    from control_plane.coo_principal_host import validate_selected_child_target
    try:
        return validate_selected_child_target(document)
    except (ValueError, TypeError, KeyError):
        raise UpdateRefused("SELECTED_CHILD_INPUT_INVALID") from None


def _mission_capability_profile_digests(
    host: Host, release_sha: str, config: bytes
) -> dict[str, str]:
    """The target release's exact digests for the installed missions' profiles.

    Derived from the sealed target release registry. An installation without
    COO missions has no profile to re-derive and the source-only behaviour is
    preserved byte for byte.
    """

    try:
        document = _strict_json(config, "MCP_COMPONENT_CONFIG_MALFORMED")
    except ValueError:
        # An unreadable prior document is the candidate compiler's refusal,
        # not a second trust decision here.
        return {}
    if not isinstance(document, dict):
        return {}
    block = document.get("coo")
    missions = block.get("missions") if isinstance(block, dict) else None
    if not isinstance(missions, list):
        return {}
    profile_ids = {row.get("capability_profile_id") for row in missions
                    if isinstance(row, dict) and type(row.get("capability_profile_id")) is str}
    if not profile_ids:
        return {}
    return host.derive_capability_profile_digests(release_sha, tuple(sorted(profile_ids)))


def build_plan(host: Host, release_sha: str, set_public: bool,
               selector: tuple[str, str] | None = None) -> tuple[dict, Candidate]:
    publication = _selected_child_publication(host, selector)
    prior = host.read_config()
    digests = _mission_capability_profile_digests(host, release_sha, prior)
    candidate = compile_candidate(prior, host.read_plist(), release_sha=release_sha,
                                  set_public_mcp_resource=set_public,
                                  selected_child_target=publication,
                                  capability_profile_digests=digests)
    manifest = host.verify_release(release_sha)
    closure = host.verify_closure()
    return plan_document(candidate, manifest_sha256=manifest, closure_sha256=closure), candidate


def plan(host: Host, *, release_sha: str, set_public: bool,
         selected_child_input: str | None = None,
         selected_child_sha256: str | None = None) -> dict:
    host.require_root()
    host.receipts_ready()
    selector = selected_child_selector(selected_child_input, selected_child_sha256)
    document, _ = build_plan(host, release_sha, set_public, selector)
    return {"ok": True, "outcome": "PLANNED", "plan": document, "plan_sha256": plan_digest(document),
            "warnings": list(WARNINGS)}


def apply(host: Host, *, release_sha: str, set_public: bool, plan_sha256: str,
          selected_child_input: str | None = None,
          selected_child_sha256: str | None = None) -> dict:
    host.require_root()
    host.receipts_ready()
    selector = selected_child_selector(selected_child_input, selected_child_sha256)
    host.acquire_lock()
    try:
        if host.marker_read() is not None:
            raise UpdateRefused("TRANSACTION_PRESENT")
        document, candidate = build_plan(host, release_sha, set_public, selector)
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
        if candidate.selected_child_target is not None:
            # The ORIGINAL captured publication is retained in the
            # transaction, so a reconciliation recovers THIS candidate and
            # never reopens a replacement input.
            marker["selected_child_target"] = copy.deepcopy(candidate.selected_child_target)
        # EVERY new transaction records the exact chosen capability-profile
        # map, including the empty map.  The recovery then reproduces THIS
        # after-image from the frozen map and never from the CURRENT
        # registry, so an authentic old transaction is never re-derived.
        marker["capability_profile_digests"] = dict(
            candidate.capability_profile_digests or {})
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
        # The ORIGINAL captured publication comes from the transaction
        # itself. A reconciliation never reopens an input, never recaptures
        # and never reselects a child.
        #
        # The capability-profile transform is the FROZEN map of the original
        # transaction.  The registry is NEVER reopened here: a new marker
        # carries its own map, and an authentic OLD marker without the
        # member is recovered with the legacy no-rewrite compilation, which
        # reproduces the original after-image byte for byte.
        if "capability_profile_digests" in marker:
            frozen = dict(marker["capability_profile_digests"])
        else:
            frozen = None
        candidate = compile_candidate(config, plist, release_sha=marker["release_sha"],
                                      set_public_mcp_resource=marker["set_public_mcp_resource"],
                                      selected_child_target=marker.get("selected_child_target"),
                                      capability_profile_digests=frozen)
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


# --- the finite selected-child preparation entry -------------------------------
#
# One operator entry that makes the frozen selected-child publication
# REACHABLE through the installed owner.  It qualifies the installed
# source/config/principal association, issues EXACTLY ONE request through
# the existing admitted App identity on the incumbent principal-facts
# transport, and materializes the closed returned capture with the existing
# exclusive root-owned 0600 input writer.
#
# It dispatches no Job, previews no CooCycle, opens no other Runtime,
# creates no daemon and no auth store, and never recaptures an uncertain
# answer.  The kernel peer check of the incumbent socket is untouched: only
# an admitted peer is served, and a peer refusal is a refusal here too.

PREPARATION_CAPTURE_DIR = installed._SERVICE_ROOT + "/captures"
MAX_PREPARATION_CHILDREN = 16



# A single, private, read-only child joins the installed App identity to the
# existing FACT socket. It is neither an enrollment nor a second control plane.
_PREPARATION_CHILD_VERB = "_capture-selected-child"
_PREPARATION_CHILD_SCHEMA = "mastermind.selected_child_capture_process.v1"
_PREPARATION_CHILD_CLEANUP_SECONDS = 1.0


def _preparation_account(topology):
    import grp
    import pwd
    account = pwd.getpwnam(topology.username)
    group = grp.getgrnam(topology.group)
    if (account.pw_uid != topology.service_uid or account.pw_uid == 0
            or account.pw_gid != group.gr_gid or group.gr_gid == 0):
        raise UpdateRefused("PREPARATION_APP_IDENTITY_UNAVAILABLE")
    groups = tuple(sorted(set(os.getgrouplist(account.pw_name, account.pw_gid))))
    if account.pw_gid not in groups or 0 in groups:
        raise UpdateRefused("PREPARATION_APP_IDENTITY_UNAVAILABLE")
    return account.pw_name, account.pw_uid, account.pw_gid, groups


def _preparation_config(topology, budget):
    before = installed._observe_ancestors(CONFIG_PATH, budget)
    raw, info = installed._read_trusted_bytes(
        CONFIG_PATH, budget=budget, maximum=MAX_CONFIG_BYTES,
        expected_mode=topology.config_mode, expected_gid=topology.config_gid)
    if installed._observe_ancestors(CONFIG_PATH, budget) != before:
        raise UpdateRefused("PREPARATION_SOURCE_CHANGED")
    return raw, installed._object_identity(info), before


class _PreparationQualification:
    def __init__(self):
        endpoint = time.monotonic_ns() + int(installed._SERVICE_BUDGET_SECONDS * 1_000_000_000)
        self.budget = installed._Budget(
            installed._SERVICE_BUDGET_SECONDS, deadline_monotonic_ns=endpoint)
        self.topology = installed._role_topology("gateway")
        self.account = _preparation_account(self.topology)
        self.config = _preparation_config(self.topology, self.budget)
        document = _strict_json(self.config[0], "MCP_COMPONENT_CONFIG_MALFORMED")
        self.release_sha = document.get("release_sha") if type(document) is dict else None
        if type(self.release_sha) is not str or HEX40.fullmatch(self.release_sha) is None:
            raise UpdateRefused("PREPARATION_CONFIG_INVALID")
        self.root = Path(installed._SERVICE_RELEASES) / self.release_sha
        self.helper = self.root / "ops/executive_os/mcp_component_update.py"
        if _ROOT != self.root or os.path.abspath(__file__) != str(self.helper):
            raise UpdateRefused("PREPARATION_HELPER_RELEASE_MISMATCH")
        self.plist = installed._verify_role_plist(
            self.topology, self.budget, expected_release=self.release_sha)
        self.release = installed._verify_release(self.topology, self.release_sha, self.budget)
        self.runtime = installed._verify_python_runtime(self.budget)
        self.closure = installed._verify_network_closure(self.budget)
        self.check()

    def check(self):
        self.budget.check()
        if (_preparation_account(self.topology) != self.account
                or _preparation_config(self.topology, self.budget) != self.config
                or installed._verify_role_plist(
                    self.topology, self.budget,
                    expected_release=self.release_sha) != self.plist):
            raise UpdateRefused("PREPARATION_SOURCE_CHANGED")
        installed._recheck_release(self.release, self.budget)
        installed._recheck_python_runtime(self.runtime, self.budget)
        installed._recheck_network_closure(self.closure, self.budget)
        # The potentially expensive inventories are bracketed by the original
        # configuration, account and plist observations.
        if (_preparation_account(self.topology) != self.account
                or installed._verify_role_plist(
                    self.topology, self.budget,
                    expected_release=self.release_sha) != self.plist
                or _preparation_config(self.topology, self.budget) != self.config):
            raise UpdateRefused("PREPARATION_SOURCE_CHANGED")
        self.budget.check()


def _preparation_json(raw, maximum):
    if type(raw) is not bytes or not 0 < len(raw) <= maximum:
        raise UpdateRefused("PREPARATION_RESPONSE_INVALID")
    try:
        value = installed._load_strict_json(raw, code="PREPARATION_RESPONSE_INVALID")
    except (PeerIdentityError, ValueError):
        raise UpdateRefused("PREPARATION_RESPONSE_INVALID") from None
    if type(value) is not dict or canonical(value) + b"\n" != raw:
        raise UpdateRefused("PREPARATION_RESPONSE_INVALID")
    return value


def _exchange_preparation_child(process, packet, *, budget, maximum):
    """Bound both pipes, EOF, exit and cleanup on the original held Popen."""
    import selectors
    reply = bytearray()
    pending = memoryview(packet)
    selector = None
    try:
        selector = selectors.DefaultSelector()
        for pipe, event in ((process.stdin, selectors.EVENT_WRITE),
                            (process.stdout, selectors.EVENT_READ)):
            os.set_blocking(pipe.fileno(), False)
            selector.register(pipe, event)
        while selector.get_map():
            remaining = budget.check() - _PREPARATION_CHILD_CLEANUP_SECONDS
            if remaining <= 0:
                raise UpdateRefused("PREPARATION_CHILD_TIMEOUT")
            ready = selector.select(remaining)
            if not ready:
                raise UpdateRefused("PREPARATION_CHILD_TIMEOUT")
            for key, _event in ready:
                pipe = key.fileobj
                try:
                    if pipe is process.stdin:
                        count = os.write(pipe.fileno(), pending[:16384])
                        if count <= 0:
                            raise UpdateRefused("PREPARATION_CHILD_INPUT_UNAVAILABLE")
                        pending = pending[count:]
                        if not pending:
                            selector.unregister(pipe)
                            pipe.close()
                    else:
                        block = os.read(pipe.fileno(), min(65536, maximum + 1 - len(reply)))
                        if not block:
                            selector.unregister(pipe)
                            pipe.close()
                        else:
                            reply.extend(block)
                            if len(reply) > maximum:
                                raise UpdateRefused("PREPARATION_RESPONSE_INVALID")
                except BlockingIOError:
                    continue
        remaining = budget.check() - _PREPARATION_CHILD_CLEANUP_SECONDS
        if remaining <= 0:
            raise UpdateRefused("PREPARATION_CHILD_TIMEOUT")
        try:
            returncode = process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            raise UpdateRefused("PREPARATION_CHILD_TIMEOUT") from None
        if returncode != 0:
            raise UpdateRefused("PREPARATION_REQUEST_UNAVAILABLE")
        return _preparation_json(bytes(reply), maximum)
    finally:
        cleanup_unproven = False
        if selector is not None:
            try:
                selector.close()
            except Exception:
                cleanup_unproven = True
        for pipe in (process.stdin, process.stdout):
            try:
                if pipe is not None and not pipe.closed:
                    pipe.close()
            except Exception:
                cleanup_unproven = True
        # A selector or pipe-close failure cannot bypass original-child cleanup.
        try:
            if process.poll() is None:
                try:
                    process.kill()
                except OSError:
                    cleanup_unproven = True
                # Even a failed signal cannot skip the original wait/reap.
                try:
                    process.wait(timeout=max(0.0, budget.remaining()))
                except (OSError, subprocess.TimeoutExpired):
                    cleanup_unproven = True
            if process.poll() is None:
                cleanup_unproven = True
        except (OSError, subprocess.TimeoutExpired):
            cleanup_unproven = True
        if cleanup_unproven:
            raise UpdateRefused("PREPARATION_CHILD_CLEANUP_UNPROVEN") from None


def _preparation_child_pipe(fd, *, budget, maximum=None, output=None):
    """One finite stdin read or stdout write; no inherited file access."""
    import selectors
    original_blocking = os.get_blocking(fd)
    selector = selectors.DefaultSelector()
    data = bytearray()
    pending = memoryview(output) if output is not None else None
    try:
        os.set_blocking(fd, False)
        selector.register(fd, selectors.EVENT_WRITE if pending is not None else selectors.EVENT_READ)
        while True:
            if not selector.select(budget.check()):
                raise UpdateRefused("PREPARATION_CHILD_TIMEOUT")
            try:
                if pending is not None:
                    count = os.write(fd, pending[:16384])
                    if count <= 0:
                        raise UpdateRefused("PREPARATION_CHILD_OUTPUT_UNAVAILABLE")
                    pending = pending[count:]
                    if not pending:
                        return None
                else:
                    block = os.read(fd, min(65536, maximum + 1 - len(data)))
                    if not block:
                        return bytes(data)
                    data.extend(block)
                    if len(data) > maximum:
                        raise UpdateRefused("PREPARATION_RESPONSE_INVALID")
            except BlockingIOError:
                continue
    finally:
        selector.close()
        os.set_blocking(fd, original_blocking)


def _run_preparation_child():
    from control_plane.coo_principal_host import FACT_SCHEMA, validate_facts_frame
    from integrations.mastermind_workspace_app.contract import MAX_RESPONSE_BYTES
    from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
    if sys.platform != "darwin":
        raise UpdateRefused("PLATFORM_UNSUPPORTED")
    topology = installed._role_topology("gateway")
    account = _preparation_account(topology)
    if (os.getuid() != account[1] or os.geteuid() != account[1]
            or os.getgid() != account[2] or os.getegid() != account[2]
            or tuple(sorted(set(os.getgroups()))) != account[3]):
        raise UpdateRefused("PREPARATION_APP_IDENTITY_UNAVAILABLE")
    startup_deadline = time.monotonic_ns() + int(installed._SERVICE_BUDGET_SECONDS * 1_000_000_000)
    budget = installed._Budget(
        installed._SERVICE_BUDGET_SECONDS, deadline_monotonic_ns=startup_deadline)
    packet = _preparation_json(
        _preparation_child_pipe(0, budget=budget, maximum=MAX_CONFIG_BYTES),
        MAX_CONFIG_BYTES)
    if (set(packet) != {"schema", "release_sha", "config_sha256", "deadline", "frame"}
            or packet["schema"] != _PREPARATION_CHILD_SCHEMA
            or type(packet["deadline"]) is not int or packet["deadline"] <= 0):
        raise UpdateRefused("PREPARATION_CONFIG_INVALID")
    budget = installed._Budget(
        installed._SERVICE_BUDGET_SECONDS,
        deadline_monotonic_ns=min(startup_deadline, packet["deadline"]))
    original = _preparation_config(topology, budget)
    document = _strict_json(original[0], "MCP_COMPONENT_CONFIG_MALFORMED")
    validate_document(document)
    release = document["release_sha"]
    root = Path(installed._SERVICE_RELEASES) / release
    if (packet["release_sha"] != release or _ROOT != root
            or os.path.abspath(__file__) != str(root / "ops/executive_os/mcp_component_update.py")
            or packet["config_sha256"] != hashlib.sha256(original[0]).hexdigest()):
        raise UpdateRefused("PREPARATION_SOURCE_CHANGED")
    frame = packet["frame"]
    validate_facts_frame(frame)
    if (frame.get("schema") != FACT_SCHEMA or frame.get("operation") != "mission"
            or set(frame) != {"schema", "operation", "work_ref", "principal", "preparation"}
            or frame["principal"] != _preparation_principal(document, frame["work_ref"])):
        raise UpdateRefused("PREPARATION_SELECTOR_INVALID")
    socket_path = document["ceo_ingress_socket_path"]
    if type(socket_path) is not str or not socket_path.startswith("/"):
        raise UpdateRefused("PREPARATION_CONFIG_INVALID")
    timeout = min(10.0, budget.check())
    if timeout < 0.1:
        raise UpdateRefused("PREPARATION_CHILD_TIMEOUT")
    response = asyncio.run(CeoIngressWorkspaceClient(
        socket_path, timeout_seconds=timeout).request(frame))
    if (_preparation_config(topology, budget) != original
            or _preparation_account(topology) != account):
        raise UpdateRefused("PREPARATION_SOURCE_CHANGED")
    raw = canonical(response) + b"\n"
    if len(raw) > MAX_RESPONSE_BYTES:
        raise UpdateRefused("PREPARATION_RESPONSE_INVALID")
    _preparation_child_pipe(1, budget=budget, output=raw)


def preparation_destination(work_ref: str) -> str:
    """The one installed destination of a preparation.

    The destination is DERIVED from the work reference, never accepted from
    the caller: no path, account, label or port is ever taken from the
    command line.  It is deterministic, so a second preparation of the same
    work scope finds the destination occupied and refuses.
    """

    name = "selected-child-target-" + hashlib.sha256(
        work_ref.encode("utf-8")).hexdigest()[:16] + ".json"
    return PREPARATION_CAPTURE_DIR + "/" + name


def _preparation_principal(document: dict[str, Any], work_ref: str) -> dict[str, Any]:
    """Select the exact enrolled v1/v2 binding owned by this mission."""
    from integrations.business_mcp_auth.contracts import load_resource_policy
    from integrations.mastermind_executive_app.coo_binding import coo_binding_records, _digest
    block = document.get("coo")
    missions = block.get("missions") if type(block) is dict else None
    rows = [row for row in missions or []
            if type(row) is dict and row.get("work_ref") == work_ref]
    if len(rows) != 1 or rows[0].get("enabled") is not True:
        raise UpdateRefused("PREPARATION_MISSION_UNAVAILABLE")
    try:
        records = coo_binding_records(block["binding"], load_resource_policy(block["policy"]))
        matches = [record for record in records
                   if _digest(record) == rows[0]["principal_binding_digest"]]
    except (ValueError, TypeError, KeyError, AuthError):
        raise UpdateRefused("PREPARATION_BINDING_UNAVAILABLE") from None
    if len(matches) != 1:
        raise UpdateRefused("PREPARATION_BINDING_UNAVAILABLE")
    inner = matches[0]
    return {key: inner[key] for key in (
        "policy_id", "issuer_digest", "subject_digest", "client_ref", "resource", "scopes")}



def prepare_selected_child(host: Host, *, work_ref: str, root_job_id: str,
                           child_job_ids: list[str]) -> dict[str, Any]:
    """One App-identity FACT capture, then one exclusive root-owned input."""
    from common.executive_workspace_contract import _check_job_id, _check_work_ref
    from control_plane.coo_principal_host import (
        FACT_PREPARATION_SCHEMA, FACT_SCHEMA, build_selected_child_publication,
        validate_facts_frame,
    )
    if (not _check_work_ref(work_ref) or not _check_job_id(root_job_id)
            or type(child_job_ids) is not list
            or not 1 <= len(child_job_ids) <= MAX_PREPARATION_CHILDREN
            or any(type(item) is not str or not _check_job_id(item) for item in child_job_ids)
            or len(set(child_job_ids)) != len(child_job_ids)):
        raise UpdateRefused("PREPARATION_SELECTOR_INVALID")
    host.require_root()
    config_bytes = host.begin_selected_child_preparation()
    document = _strict_json(config_bytes, "MCP_COMPONENT_CONFIG_MALFORMED")
    try:
        validate_document(document)
    except (ValueError, TypeError, KeyError):
        raise UpdateRefused("PREPARATION_CONFIG_INVALID") from None
    principal = _preparation_principal(document, work_ref)
    installed_source = host.installed_coo_source()
    from copy import deepcopy
    original = deepcopy(installed_source.for_principal(principal, work_ref))
    row, _fact, _authority = original
    if type(row) is not dict or row.get("enabled") is not True:
        raise UpdateRefused("PREPARATION_MISSION_UNAVAILABLE")
    destination = host.preparation_input_path(work_ref)
    # An occupied original destination is a refusal before another capture.
    host.preparation_destination_available(destination)
    frame = {
        "schema": FACT_SCHEMA, "operation": "mission", "work_ref": work_ref,
        "principal": principal,
        "preparation": {"schema": FACT_PREPARATION_SCHEMA,
                        "root_job_id": root_job_id, "child_job_ids": list(child_job_ids)},
    }
    validate_facts_frame(frame)
    try:
        response = host.request_selected_child_capture(frame)
    except UpdateRefused:
        raise
    except Exception:
        raise UpdateRefused("PREPARATION_REQUEST_UNAVAILABLE") from None
    if type(response) is not dict or response.get("ok") is not True:
        error = response.get("error") if type(response) is dict else None
        code = error.get("code") if type(error) is dict else None
        if type(code) is str and re.fullmatch(r"[a-zA-Z0-9_]{1,80}", code):
            raise UpdateRefused("PREPARATION_REQUEST_" + code.upper())
        raise UpdateRefused("PREPARATION_REQUEST_REFUSED")
    capture = response.get("result")
    if (set(response) != {"ok", "result"} or type(capture) is not dict
            or set(capture) != {"work_ref", "root_job_id", "children", "source"}
            or capture["work_ref"] != work_ref or capture["root_job_id"] != root_job_id):
        raise UpdateRefused("PREPARATION_RESPONSE_INVALID")
    try:
        publication = build_selected_child_publication(
            work_ref=capture["work_ref"], root_job_id=capture["root_job_id"],
            children=capture["children"], source=capture["source"])
        if [child["job_id"] for child in publication["children"]] != child_job_ids:
            raise ValueError("foreign or reordered selected child")
    except (ValueError, TypeError, KeyError):
        raise UpdateRefused("PREPARATION_RESPONSE_INVALID") from None
    # Rejoin the same source, mission, registry and principal immediately before
    # publication. No changed capture is retried or substituted.
    try:
        host.recheck_selected_child_preparation()
        if (installed_source.for_principal(principal, work_ref) != original
                or host.read_config() != config_bytes):
            raise UpdateRefused("PREPARATION_SOURCE_CHANGED")
    except UpdateRefused:
        raise
    except Exception:
        raise UpdateRefused("PREPARATION_SOURCE_CHANGED") from None
    try:
        written = host.write_selected_child_input(publication, destination)
        return {
            "ok": True, "outcome": "PREPARED", "input_path": written["path"],
            "sha256": written["sha256"],
            "selected_child_target": {
                "work_ref": publication["work_ref"], "root_job_id": publication["root_job_id"],
                "material_digest": publication["material_digest"],
            },
        }
    except Exception:
        # Creation may have happened before a short write/fsync/readback error.
        # Preserve and report the ORIGINAL path; never overwrite or recapture.
        raise TransactionEffectUnknown("PREPARATION_INPUT_EFFECT_UNKNOWN:" + destination) from None



# --- closed command line ---

_VERBS: dict[str, dict[str, bool]] = {
    "plan": {"--release-sha": True, "--set-public-mcp-resource": False,
             "--selected-child-target-input": True, "--selected-child-target-sha256": True},
    "apply": {"--release-sha": True, "--set-public-mcp-resource": False, "--plan-sha256": True,
              "--selected-child-target-input": True, "--selected-child-target-sha256": True},
    "reconcile": {"--release-sha": True},
}

#: The closed argv walk of the preparation entry.  Every flag is bounded and
#: explicit; the child selector may repeat, every other flag may not.  No
#: destination, path, account, label, port or release is ever accepted.
_PREPARATION_FLAGS = ("--work-ref", "--root-job-id", "--child-job-id")


class UsageError(ValueError):
    pass


def parse_preparation_arguments(argv: list[str]) -> dict[str, Any]:
    """The closed argv walk of the finite preparation entry."""

    if not argv or argv[0] != "prepare-selected-child":
        raise UsageError("verb")
    values: dict[str, Any] = {"--work-ref": None, "--root-job-id": None,
                               "--child-job-id": []}
    index = 1
    while index < len(argv):
        flag = argv[index]
        if flag not in _PREPARATION_FLAGS:
            raise UsageError("flag")
        index += 1
        if index >= len(argv):
            raise UsageError("value")
        value = argv[index]
        index += 1
        if flag == "--child-job-id":
            values[flag].append(value)
        elif values[flag] is not None:
            raise UsageError("flag")
        else:
            values[flag] = value
    if values["--work-ref"] is None or values["--root-job-id"] is None:
        raise UsageError("value")
    if not values["--child-job-id"]:
        raise UsageError("value")
    return values


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
    # The selected-child publication input is PAIRED: the exact qualified
    # input path and the exact digest of its raw bytes are ONE selection.
    # Both absent preserve the source-only behaviour; exactly one refuses.
    has_input = "--selected-child-target-input" in values
    has_digest = "--selected-child-target-sha256" in values
    if has_input != has_digest:
        raise UsageError("selected child target input")
    if has_input:
        path_value = values["--selected-child-target-input"]
        digest_value = values["--selected-child-target-sha256"]
        if (not isinstance(path_value, str) or not path_value.startswith("/")
                or "\x00" in path_value or ".." in path_value.split("/")):
            raise UsageError("selected child target input")
        if not isinstance(digest_value, str) or HEX64.fullmatch(digest_value) is None:
            raise UsageError("selected child target input")
    return verb, values


def _emit(document: dict) -> None:
    sys.stdout.write(json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def main(argv: list[str] | None = None, host: Host | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments[:1] == [_PREPARATION_CHILD_VERB]:
        if arguments != [_PREPARATION_CHILD_VERB] or host is not None:
            return 64
        try:
            _run_preparation_child()
        except Exception:
            return 1
        return 0
    if arguments[:1] == ["prepare-selected-child"]:
        try:
            selection = parse_preparation_arguments(arguments)
        except UsageError:
            sys.stderr.write("usage: mcp_component_update.py prepare-selected-child "
                             "--work-ref <work ref> --root-job-id <job id> "
                             "--child-job-id <job id> [--child-job-id <job id> ...]\n")
            return 64
        host = host if host is not None else ProductionHost()
        try:
            result = prepare_selected_child(
                host, work_ref=selection["--work-ref"],
                root_job_id=selection["--root-job-id"],
                child_job_ids=list(selection["--child-job-id"]))
        except TransactionEffectUnknown as error:
            _emit({"ok": False, "outcome": "EFFECT_UNKNOWN", "code": error.code,
                   "note": "Preserve and inspect the original input path; no overwrite or automatic recapture."})
            return 2
        except UpdateRefused as error:
            _emit({"ok": False, "outcome": "REFUSED", "code": error.code})
            return 1
        except Exception as error:
            _emit({"ok": False, "outcome": "REFUSED",
                   "code": "UNEXPECTED_" + type(error).__name__.upper()})
            return 1
        _emit(result)
        return 0
    try:
        verb, values = parse_arguments(arguments)
    except UsageError:
        sys.stderr.write("usage: mcp_component_update.py plan|apply|reconcile --release-sha <40hex> "
                         "[--set-public-mcp-resource] [--plan-sha256 <64hex>] "
                         "[--selected-child-target-input <absolute path> "
                         "--selected-child-target-sha256 <64hex>]\n")
        return 64
    host = host if host is not None else ProductionHost()
    release = values["--release-sha"]
    public = bool(values.get("--set-public-mcp-resource", False))
    child_input = values.get("--selected-child-target-input")
    child_digest = values.get("--selected-child-target-sha256")
    try:
        if verb == "plan":
            result = plan(host, release_sha=release, set_public=public,
                          selected_child_input=child_input,
                          selected_child_sha256=child_digest)
        elif verb == "apply":
            result = apply(host, release_sha=release, set_public=public, plan_sha256=values["--plan-sha256"],
                           selected_child_input=child_input,
                           selected_child_sha256=child_digest)
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

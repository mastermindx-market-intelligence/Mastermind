"""CAP-S1 real-provider canary runner (Mastermind operator four-Skill journey).

Implements the vertical amendment's §9 real canary journey and the protocol-
attestation amendment's schema-source precedence (§2), exact source-root
modes (§4) and fresh-process causal isolation (§5) on top of the already-
built primitives this module composes but never re-implements:

- ``control_plane.executive_agent_capabilities`` (V4 registry, profile);
- ``control_plane.executive_capability_packages`` (package generation);
- ``scripts.ohf.capability_skill_projection`` (attempt-local Skill staging);
- ``control_plane.codex_operator_adapter`` (binding-gated causal launch,
  the closed structured Skill turn-input seam, and read/collect/stop);
- ``scripts.ohf.protocol`` (strict ``skills/list`` parsing helpers).

This module never launches the real Codex binary itself in tests: the
``backend="fake"`` path is driven entirely by an injected ``client_factory``
(the same fake-App-Server-subprocess harness pattern the adapter's own tests
use) and an injected ``run_command`` for schema generation. The
``backend="live"`` path is real-binary-shaped but is only ever exercised by
the operation principal, later, against a dedicated non-default
``CODEX_HOME`` -- never by this module's own test suite.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import importlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from control_plane.codex_operator_adapter import (
    CodexAdapterError,
    CodexOperatorAdapter,
    CodexProtocolAttestationReceipt,
    CodexSkillCanaryBinding,
    CodexSkillTurnInput,
    CodexTurnInputEnvelope,
    build_protocol_attestation_receipt,
)
from control_plane.executive_agent_capabilities import (
    CapabilityPolicyError,
    ExecutionCapabilityRegistry,
    NativeHelperPolicy,
)
from control_plane.executive_capability_packages import (
    CapabilityPackageError,
    build_capability_package_generation,
)
from control_plane.operator_harness_contract import (
    EventCursor,
    LaunchDecision,
    OperationId,
    ProcessGenerationRef,
    ProcessLiveness,
    RequestedExecutionProfile,
    SessionEpochRef,
    TurnRef,
    WorkspaceIdentity,
    compare_launch,
)
from scripts.ohf.capability_skill_projection import (
    ORIGIN_VERIFIED_EPHEMERAL_GIT_ARCHIVE,
    EphemeralGitOriginReceipt,
    SkillProjectionError,
    cleanup_skill_projection,
    create_ephemeral_archive_origin,
    stage_skill_projection,
)
from scripts.ohf.laboratory import AppServerClient, default_user_codex_home, validate_live_codex_home
from scripts.ohf.protocol import (
    SkillProtocolShapeError,
    enabled_skill_names,
    extra_roots_set_params,
    parse_skills_list_strict,
    skills_list_params,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

V4_FIXTURE_RELATIVE_PATH = Path(
    "scripts/ohf/fixtures/executive_agent_capabilities_v4_mastermind_operator.json"
)
PACKAGE_CAPABILITY_ID = "mastermind-operator.p1"
PROFILE_ID = "operator.appserver.readonly.mastermind-operator.v1"

CANARY_WORKER_ID = "cap-s1-canary"
CANARY_REQUESTED_MODEL = "gpt-5.6-sol"
FAKE_HARNESS_VERSION = "ohf-fake-app-server/p0b"
_CANARY_AUTHORITY_POLICY_HASH = "c" * 64

SYNTHETIC_OPERATION_ID = "cap-s1-synthetic-op"
SYNTHETIC_DECISION_BRANCH = "branch-alpha"

CANARY_CLEANUP_SCHEMA_VERSION = "mastermind.cap_s1_canary_cleanup/v1"
CANARY_EVIDENCE_SCHEMA_VERSION = "mastermind.cap_s1_canary_evidence/v1"

# CAP-S1 Sol review item 1 (single-binary law): the fake realm's schema
# fixture and its App Server used to be two DIFFERENT files -- a print/write
# schema stub, and the running Python interpreter launched with ``-m
# scripts.ohf.fake_app_server``. A receipt attesting one could never be
# honestly bound to the adapter launching the other. ``fake_codex_binary.py``
# (committed, real, executable) is now the ONE file used for both: schema
# generation, ``--version``, and (via an internal ``os.execv`` passthrough
# into the real fake-App-Server implementation) the App Server itself. See
# that module's own docstring for the exact CLI shapes it answers.
FAKE_CODEX_BINARY_PATH = Path(__file__).resolve().parent / "fake_codex_binary.py"
_SCHEMA_FIXTURE_BINARY_SOURCE = FAKE_CODEX_BINARY_PATH.read_text(encoding="utf-8")

FROZEN_STOP_CODES = (
    "SKILL_PROTOCOL_SCHEMA_UNATTESTED",
    "SKILL_PATH_ATTESTATION_UNAVAILABLE",
    "AMBIENT_SKILL_SURFACE_NOT_EMPTY",
    "SKILL_SET_CAUSALITY_FAILED",
    "SKILLS_CHANGED_DURING_CANARY",
    "EFFECT_UNKNOWN",
    "PROVIDER_REALM_UNAVAILABLE",
)

# Frozen four-turn order (also the Skill runtime names / capability ids'
# name segment) per the vertical amendment §3/§9.
TURN_ORDER = (
    "receive-commission",
    "return-progress",
    "escalate-decision",
    "finish-operation",
)

_TURN_TEXTS: dict[str, str] = {
    "receive-commission": (
        f"$receive-commission Acknowledge pickup of synthetic operation "
        f"{SYNTHETIC_OPERATION_ID} (decision branch {SYNTHETIC_DECISION_BRANCH}). "
        "Confirm receipt only; do not claim the work has started."
    ),
    "return-progress": (
        f"$return-progress Report bounded progress on synthetic operation "
        f"{SYNTHETIC_OPERATION_ID} without claiming it is complete."
    ),
    "escalate-decision": (
        f"$escalate-decision Ambiguity reached on synthetic operation "
        f"{SYNTHETIC_OPERATION_ID} at decision branch {SYNTHETIC_DECISION_BRANCH}; "
        "request an explicit decision rather than deciding unilaterally."
    ),
    "finish-operation": (
        f"Sol ruling (synthetic, bounded): proceed with decision branch "
        f"{SYNTHETIC_DECISION_BRANCH} for {SYNTHETIC_OPERATION_ID}. "
        "$finish-operation Report the RESULT of the synthetic operation without "
        "claiming Sol acceptance or STOP."
    ),
}

# (required literal tokens, forbidden literal tokens) per model-output turn,
# per the vertical amendment §9 closed-marker law.
_TURN_MARKER_RULES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "receive-commission": (("PICKUP-ACK",), ("STARTED",)),
    "return-progress": (("PROGRESS",), ("COMPLETE",)),
    "escalate-decision": (("DECISION-REQUEST",), ("DECIDED",)),
    "finish-operation": (("RESULT",), ("ACCEPTED", "STOPPED")),
}

# Global live-authority identifiers that must never appear in bounded,
# synthetic model output (vertical amendment §9).
_GLOBAL_FORBIDDEN_TOKENS = (
    "mastermindx-market-intelligence",
    "chriswong",
    "Slack",
    "PR #",
    "credential",
    "auth.json",
)


class CanaryStop(RuntimeError):
    """One closed, frozen refusal token (protocol-attestation amendment §11)."""

    def __init__(self, code: str, detail: str = "") -> None:
        if code not in FROZEN_STOP_CODES:
            raise ValueError(f"unknown canary stop code: {code!r}")
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


class _SeamProbeRefusal(RuntimeError):
    """Deterministic, network-free refusal raised by ``_seam_probe_client_factory``
    once it has proven the live client-construction wiring was reached."""


def _seam_probe_client_factory(argv: list, env: Mapping[str, str], cwd: Path):
    """Live-CLI wiring seam probe (CAP-S1 addendum, finding 3; Sol review
    item 2 residual: a callback-only substitute is not the production seam).

    Constructs the REAL ``scripts.ohf.laboratory.AppServerClient`` -- the
    exact class the adapter's own default ``client_factory`` would have
    constructed -- and starts it, so a harmless local process (the
    single-binary fixture named by ``--binary-path``, never the real Codex
    binary) is genuinely spawned through the genuine subprocess-construction
    path. No JSON-RPC call is ever issued (no ``initialize``, no
    ``thread/start``, no turn): the probe records that REAL construction was
    reached -- the exact class name and the ``argv``/``cwd`` the adapter
    would have launched -- to the file named by ``OHF_SEAM_PROBE_RECORD_PATH``
    (when set), shuts the harmless process down, then raises deterministically
    before any provider effect. Wired in ONLY via an explicit
    ``CAP_S1_LIVE_CLIENT_FACTORY=scripts.ohf.
    cap_s1_mastermind_operator_canary:_seam_probe_client_factory`` override
    (see ``main``'s live-backend client-factory resolution), always against a
    disposable, non-default ``--codex-home``.
    """

    probe_client = AppServerClient(list(argv), env=env, cwd=cwd, start_new_session=True)
    try:
        probe_client.start()
        record_path = os.environ.get("OHF_SEAM_PROBE_RECORD_PATH")
        if record_path:
            Path(record_path).write_text(
                json.dumps(
                    {
                        "constructed": type(probe_client).__name__,
                        "argv": list(probe_client.argv),
                        "argv0": str(probe_client.argv[0]) if probe_client.argv else "",
                        "cwd": str(probe_client.cwd),
                        "pid": probe_client.pid,
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
    finally:
        try:
            probe_client.close()
        except Exception:  # noqa: BLE001 -- best-effort probe teardown
            pass
    raise _SeamProbeRefusal(
        "cap-s1 live client-construction seam probe: refusing before any provider effect"
    )


SCHEMA_ATTESTATION_DIR_NAME = "schema-attestation"

_PROBE_CLIENT_INFO = {
    "name": "cap-s1-canary-probe",
    "title": "CAP-S1 Protocol Attestation Probe",
    "version": "p1b",
}


@dataclasses.dataclass(frozen=True, kw_only=True)
class CanaryCleanupRecord:
    """Frozen, immutable teardown outcome (Sol wave-3 review finding B4).

    Replaces the earlier mutable ``dict`` -- ``artifacts`` is a closed tuple
    of ``(kind, removed, verified_absent)`` rows, one per registered
    resource, appended in LIFO teardown order by ``run_canary``'s own
    finally-block cleanup ledger. ``removed``/``verified_absent`` are always
    computed together here (a resource is only ever considered removed once
    its absence has been freshly re-checked).
    """

    schema_version: str = CANARY_CLEANUP_SCHEMA_VERSION
    artifacts: tuple[tuple[str, bool, bool], ...] = ()

    @property
    def all_removed(self) -> bool:
        return all(removed and verified_absent for _kind, removed, verified_absent in self.artifacts)


@dataclasses.dataclass(frozen=True, kw_only=True)
class CanaryEvidence:
    schema_version: str = CANARY_EVIDENCE_SCHEMA_VERSION
    candidate_commit: str
    candidate_tree: str
    canary_operation_id: str
    workspace_root: str
    process_generation: str
    v4_policy_digest: str
    package_source_digest: str
    package_generation_digest: str
    skill_grant_digests: tuple[tuple[str, str], ...]
    skill_closure_digests: tuple[tuple[str, str], ...]
    projection_receipt_digest: str
    binary_digest: str
    binary_version: str
    origin_mode: str
    origin_authentication: str
    skills_root: str
    app_server_config_digest: "str | None"
    extra_roots_set_outcomes: tuple[str, ...]
    skills_list_raw_shape_digest: str
    baseline_enabled_names: tuple[str, ...]
    after_add_enabled_names: tuple[str, ...]
    observed_enabled_names: tuple[str, ...]
    after_clear_enabled_names: tuple[str, ...]
    protocol_receipt_digest: str
    launch_decision: str
    turn_marker_results: tuple[tuple[str, bool], ...]
    served_model: "str | None"
    terminal_process_state: str
    artifact_inventory: tuple[str, ...]
    cleanup: CanaryCleanupRecord


# ---------------------------------------------------------------------------
# Canonical digesting (same discipline as control_plane.executive_capability_packages)
# ---------------------------------------------------------------------------


def _canonical_digest(value: object) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# attest_protocol_schema (protocol-attestation amendment §2)
# ---------------------------------------------------------------------------


def _inventory_digest_and_docs(directory: Path) -> tuple[str, list[Any]]:
    rows: list[tuple[str, str]] = []
    docs: list[Any] = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        rel = str(path.relative_to(directory))
        data = path.read_bytes()
        rows.append((rel, hashlib.sha256(data).hexdigest()))
        if path.suffix == ".json":
            try:
                docs.append(json.loads(data.decode("utf-8")))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise CanaryStop(
                    "SKILL_PROTOCOL_SCHEMA_UNATTESTED", "schema output is not valid JSON"
                ) from exc
    if not rows:
        raise CanaryStop(
            "SKILL_PROTOCOL_SCHEMA_UNATTESTED", "schema generation produced no files"
        )
    digest = _canonical_digest(sorted(rows))
    return digest, docs


def _node_declares_skill_input(node: Any) -> bool:
    if isinstance(node, dict):
        properties = node.get("properties")
        if isinstance(properties, dict) and "name" in properties and "path" in properties:
            type_prop = properties.get("type")
            if isinstance(type_prop, dict):
                values: list[str] = []
                const = type_prop.get("const")
                if isinstance(const, str):
                    values.append(const)
                enum = type_prop.get("enum")
                if isinstance(enum, list):
                    values.extend(item for item in enum if isinstance(item, str))
                if "skill" in values:
                    return True
        return any(_node_declares_skill_input(child) for child in node.values())
    if isinstance(node, list):
        return any(_node_declares_skill_input(item) for item in node)
    return False


def _schema_supports_skill_input_path(docs: list[Any]) -> bool:
    return any(_node_declares_skill_input(doc) for doc in docs)


def attest_protocol_schema(
    *,
    binary_path: Path,
    scratch_root: Path,
    run_command: Callable[..., Any] = subprocess.run,
    probe_env: "Mapping[str, str] | None" = None,
    probe_cwd: "Path | None" = None,
    app_server_argv: "Sequence[str] | None" = None,
) -> CodexProtocolAttestationReceipt:
    """The ONLY producer of :class:`CodexProtocolAttestationReceipt` (CAP-S1
    Sol review item 1): generates the stable/experimental schema dumps, then
    proves the receipt is bound to a real, launchable binary by starting
    that SAME binary as an App Server (single-binary law) via the real
    :class:`~scripts.ohf.laboratory.AppServerClient`, performing one bounded
    ``initialize`` (never a full session -- no ``thread/start``, no turn),
    and capturing the exact ``userAgent`` it reports. ``binary_version`` is
    set to that same value (one truth) and the probe process is shut down
    cleanly before this function ever returns. No field is ever trusted from
    a caller: every value here is either freshly measured over the real
    binary on disk or freshly observed over a real subprocess boundary.
    """

    binary_path = Path(binary_path)
    scratch_root = Path(scratch_root)
    scratch_root.mkdir(parents=True, exist_ok=True)
    resolved_probe_env = dict(probe_env) if probe_env is not None else dict(os.environ)
    resolved_probe_cwd = Path(probe_cwd) if probe_cwd is not None else scratch_root

    try:
        binary_digest = _sha256_file(binary_path)
    except OSError as exc:
        raise CanaryStop(
            "SKILL_PROTOCOL_SCHEMA_UNATTESTED", "binary is not observable"
        ) from exc

    # Deterministic name (Sol wave-3 review finding B4 self-cleanup is
    # preserved): every call to this function operates on its own
    # ``scratch_root``, so a fixed subdirectory name needs no random suffix
    # -- a second call against the SAME scratch_root correctly raises
    # ``FileExistsError`` rather than silently shadowing a prior run's
    # evidence.
    sealed_dir = scratch_root / SCHEMA_ATTESTATION_DIR_NAME
    sealed_dir.mkdir(parents=False, exist_ok=False)
    # Sol wave-3 review finding B4: everything from here on operates on the
    # exclusively-created sealed_dir. ANY CanaryStop raised below is a
    # schema-attestation failure boundary -- the sealed_dir is removed,
    # best-effort, before the stop propagates, so a partial (or fully
    # written but unsupportive) schema dump never leaks past this function.
    try:
        stable_dir = sealed_dir / "stable"
        experimental_dir = sealed_dir / "experimental"
        stable_dir.mkdir()
        experimental_dir.mkdir()

        for argv, out_dir in (
            (
                [str(binary_path), "app-server", "generate-json-schema", "--out", str(stable_dir)],
                stable_dir,
            ),
            (
                [
                    str(binary_path),
                    "app-server",
                    "generate-json-schema",
                    "--experimental",
                    "--out",
                    str(experimental_dir),
                ],
                experimental_dir,
            ),
        ):
            try:
                completed = run_command(argv, capture_output=True, text=True, timeout=120)
            except (OSError, subprocess.SubprocessError) as exc:
                raise CanaryStop(
                    "SKILL_PROTOCOL_SCHEMA_UNATTESTED", "schema generation command failed"
                ) from exc
            if getattr(completed, "returncode", None) != 0:
                raise CanaryStop(
                    "SKILL_PROTOCOL_SCHEMA_UNATTESTED", "schema generation exited nonzero"
                )
            if not any(path.is_file() for path in out_dir.rglob("*")):
                raise CanaryStop(
                    "SKILL_PROTOCOL_SCHEMA_UNATTESTED", "schema generation produced no output"
                )

        stable_digest, stable_docs = _inventory_digest_and_docs(stable_dir)
        experimental_digest, experimental_docs = _inventory_digest_and_docs(experimental_dir)
        supports = _schema_supports_skill_input_path(
            stable_docs
        ) or _schema_supports_skill_input_path(experimental_docs)

        # --- protocol-attestation amendment §2 item 4: the REAL initialize
        # probe (CAP-S1 Sol review item 1). Launches the SAME binary as an
        # App Server (single-binary law) via the real AppServerClient,
        # performs one bounded ``initialize``, and shuts the probe process
        # down cleanly. For the live realm this is genuinely the only RPC
        # the probe process ever answers -- no thread/turn is ever started.
        probe_argv = list(app_server_argv or (str(binary_path), "app-server"))
        probe_client = AppServerClient(
            probe_argv,
            env=resolved_probe_env,
            cwd=resolved_probe_cwd,
            start_new_session=True,
        )
        try:
            probe_client.start()
            initialized = probe_client.request(
                "initialize",
                {"clientInfo": _PROBE_CLIENT_INFO, "capabilities": {"experimentalApi": True}},
            )
        except Exception as exc:  # noqa: BLE001 -- any probe failure is unattested
            raise CanaryStop(
                "SKILL_PROTOCOL_SCHEMA_UNATTESTED", "protocol initialize probe failed"
            ) from exc
        finally:
            try:
                probe_client.close()
            except Exception:  # noqa: BLE001 -- best-effort probe teardown
                pass
        probe_user_agent = str(initialized.get("userAgent") or "").strip()
        if not probe_user_agent:
            raise CanaryStop(
                "SKILL_PROTOCOL_SCHEMA_UNATTESTED",
                "protocol initialize probe returned no userAgent",
            )

        return build_protocol_attestation_receipt(
            binary_path=str(binary_path),
            binary_digest=binary_digest,
            binary_version=probe_user_agent,
            stable_inventory_digest=stable_digest,
            experimental_inventory_digest=experimental_digest,
            supports_skill_input_path=supports,
            skill_input_schema_evidence=(
                "skill_turn_input_schema_node_detected" if supports else ""
            ),
            probe_user_agent=probe_user_agent,
        )
    except CanaryStop:
        shutil.rmtree(sealed_dir, ignore_errors=True)
        raise


# ---------------------------------------------------------------------------
# build_synthetic_workspace (protocol-attestation amendment §5)
# ---------------------------------------------------------------------------

_AMBIENT_SURFACE_NAMES = (".agents", ".codex", "plugins", "marketplace", "skills")

_HEX40_RE = re.compile(r"[0-9a-f]{40}")


def _run_workspace_git(argv: list[str], run_command: Callable[..., Any]) -> "subprocess.CompletedProcess | Any":
    try:
        completed = run_command(argv, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        raise CanaryStop(
            "PROVIDER_REALM_UNAVAILABLE", "synthetic workspace git command failed"
        ) from exc
    if getattr(completed, "returncode", None) != 0:
        raise CanaryStop(
            "PROVIDER_REALM_UNAVAILABLE", "synthetic workspace git command exited nonzero"
        )
    return completed


def _init_real_git_repo(workspace: Path, run_command: Callable[..., Any]) -> str:
    """A REAL git repo, sealed local identity, one real commit (Sol wave-3
    review finding B2): the sealed base sha is that real commit -- never the
    ``"0" * 40`` fabrication a fresh, non-Git directory used to hand the
    adapter's ``base_sha_resolver``. Every step goes through the same
    injectable ``run_command`` seam ``attest_protocol_schema`` uses, so this
    is exercised by an injected fake in the in-process test suite and by a
    real ``git`` binary everywhere else."""

    for args in (
        ("init", "--quiet"),
        ("config", "user.name", "cap-s1-canary"),
        ("config", "user.email", "canary@synthetic.invalid"),
        ("add", "README.md"),
        ("commit", "--quiet", "-m", "cap-s1 synthetic canary workspace"),
    ):
        _run_workspace_git(["git", "-C", str(workspace), *args], run_command)
    completed = _run_workspace_git(
        ["git", "-C", str(workspace), "rev-parse", "HEAD"], run_command
    )
    sha = (getattr(completed, "stdout", "") or "").strip()
    if _HEX40_RE.fullmatch(sha) is None:
        raise CanaryStop(
            "PROVIDER_REALM_UNAVAILABLE", "synthetic workspace base commit is not a real sha"
        )
    return sha


def _apply_workspace_read_only(workspace: Path) -> bool:
    ok = True
    try:
        for dirpath, _dirnames, filenames in os.walk(str(workspace), topdown=False):
            for name in filenames:
                try:
                    os.chmod(os.path.join(dirpath, name), 0o444)
                except OSError:
                    ok = False
            try:
                os.chmod(dirpath, 0o555)
            except OSError:
                ok = False
    except OSError:
        ok = False
    return ok


def build_synthetic_workspace(
    scratch_root: Path,
    *,
    operation_id: str,
    run_command: Callable[..., Any] = subprocess.run,
) -> "tuple[Path, str, bool]":
    """Build the sealed synthetic workspace: a real, freshly-committed git
    repo (base sha = the real commit), then made read-only best-effort.

    Returns ``(workspace, base_sha, read_only_applied)``. Self-cleans on any
    ``CanaryStop`` raised after the workspace directory itself is created --
    a mid-init failure never leaves an orphan tree the caller must know
    about independently (mirrors ``attest_protocol_schema``'s own B4
    self-cleanup).
    """

    scratch_root = Path(scratch_root)
    scratch_root.mkdir(parents=True, exist_ok=True)
    workspace = scratch_root / "synthetic-workspace"
    workspace.mkdir(parents=False, exist_ok=False)
    try:
        (workspace / "README.md").write_text(
            f"CAP-S1 synthetic canary workspace\noperation: {operation_id}\n",
            encoding="utf-8",
        )
        for name in _AMBIENT_SURFACE_NAMES:
            assert not (workspace / name).exists()
        base_sha = _init_real_git_repo(workspace, run_command)
        read_only_applied = _apply_workspace_read_only(workspace)
        return workspace, base_sha, read_only_applied
    except CanaryStop:
        _remove_tree(workspace)
        raise


# ---------------------------------------------------------------------------
# Adapter-error -> CanaryStop mapping
# ---------------------------------------------------------------------------


def _mapped_stop_for_adapter_error(exc: CodexAdapterError) -> "CanaryStop | None":
    message = str(exc)
    if "ambient_skill_surface_not_empty" in message:
        return CanaryStop("AMBIENT_SKILL_SURFACE_NOT_EMPTY", message)
    if "skill_set_causality_failed" in message or "duplicate_skill_row" in message:
        return CanaryStop("SKILL_SET_CAUSALITY_FAILED", message)
    if "skill_path_attestation_unavailable" in message:
        return CanaryStop("SKILL_PATH_ATTESTATION_UNAVAILABLE", message)
    if "skills_changed_during_canary" in message:
        return CanaryStop("SKILLS_CHANGED_DURING_CANARY", message)
    if exc.effect_unknown:
        return CanaryStop("EFFECT_UNKNOWN", message)
    return None


def _reraise_mapped(exc: CodexAdapterError) -> None:
    mapped = _mapped_stop_for_adapter_error(exc)
    if mapped is not None:
        raise mapped from exc
    raise


# ---------------------------------------------------------------------------
# Marker parsing (vertical amendment §9)
# ---------------------------------------------------------------------------


_STANDALONE_TOKEN_PATTERNS: dict[str, "re.Pattern[str]"] = {}


def _standalone_token_pattern(token: str) -> "re.Pattern[str]":
    """Closed grammar (Sol wave-3 review finding B5): a required/forbidden
    marker token must match as a standalone word, never as a bare substring
    -- ``COMPLETE`` must not fire inside ``COMPLETED``, and ``RESULT`` must
    not fire inside ``RESULTING``. The frozen regex shape is
    ``(?<![A-Z0-9-])TOKEN(?![A-Z0-9-])``; every marker token in
    ``_TURN_MARKER_RULES`` is drawn from the same closed
    uppercase-kebab vocabulary, so this boundary class is exact for them.
    (``_GLOBAL_FORBIDDEN_TOKENS`` are UNCHANGED plain substring checks --
    they are not uppercase-kebab tokens and the amendment does not ask for
    them to become standalone-word matches.)
    """

    pattern = _STANDALONE_TOKEN_PATTERNS.get(token)
    if pattern is None:
        pattern = re.compile(r"(?<![A-Z0-9-])" + re.escape(token) + r"(?![A-Z0-9-])")
        _STANDALONE_TOKEN_PATTERNS[token] = pattern
    return pattern


def _turn_markers_satisfied(skill_name: str, text: "str | None") -> bool:
    if not isinstance(text, str) or not text:
        return False
    if any(token in text for token in _GLOBAL_FORBIDDEN_TOKENS):
        return False
    required, forbidden = _TURN_MARKER_RULES[skill_name]
    if not all(_standalone_token_pattern(token).search(text) for token in required):
        return False
    if any(_standalone_token_pattern(token).search(text) for token in forbidden):
        return False
    return True


# ---------------------------------------------------------------------------
# Small filesystem/git helpers
# ---------------------------------------------------------------------------


def _remove_tree(path: Path) -> bool:
    """Best-effort removal, tolerant of a read-only tree.

    ``build_synthetic_workspace`` may have chmodded everything under
    ``path`` down to 0o444/0o555 -- a plain ``shutil.rmtree`` cannot unlink
    entries out of a non-writable directory, so every directory/file mode is
    forced back to writable first (mirrors
    ``capability_skill_projection._force_remove_tree``'s own discipline).
    """

    try:
        if path.is_dir() and not path.is_symlink():
            for dirpath, _dirnames, filenames in os.walk(str(path)):
                try:
                    os.chmod(dirpath, 0o700)
                except OSError:
                    pass
                for name in filenames:
                    try:
                        os.chmod(os.path.join(dirpath, name), 0o600)
                    except OSError:
                        pass
            shutil.rmtree(path, ignore_errors=True)
        elif path.exists():
            path.unlink()
    except OSError:
        pass
    return not path.exists()


def _resolve_repo_git_dir(repo_root: Path) -> Path:
    """The exact ``.git`` dir for ``repo_root`` -- a worktree-specific dir is
    a lawful answer (the shared object store remains reachable through it)."""

    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=str(repo_root),
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise CanaryStop(
            "PROVIDER_REALM_UNAVAILABLE", "repository git dir is not resolvable"
        ) from exc
    git_dir = Path(completed.stdout.strip())
    if not git_dir.is_absolute():
        git_dir = (repo_root / git_dir).resolve()
    return git_dir


def _cleanup_dir_action(path: Path) -> "tuple[bool, bool]":
    removed = _remove_tree(path)
    return removed, removed


def _cleanup_projection_action(projection) -> "tuple[bool, bool]":
    try:
        result = cleanup_skill_projection(projection)
    except SkillProjectionError:
        return False, False
    return bool(result.removed), bool(result.verified_absent)


def _teardown_process_action(
    adapter: CodexOperatorAdapter,
    generation_ref: ProcessGenerationRef,
    process_result: dict,
) -> "tuple[bool, bool]":
    """Attempted exactly once, never retried (Sol wave-3 review finding B4):
    the sole caller is ``run_canary``'s own finally-block cleanup ledger,
    which invokes every registered action exactly once regardless of which
    exit path was taken."""

    try:
        stopped = adapter.graceful_stop(
            generation_ref, operation_id=OperationId("ohf-op:cap-s1-stop")
        )
    except CodexAdapterError as exc:
        process_result["terminal_process_state"] = "UNKNOWN"
        process_result["stop_error"] = str(exc)
        return False, False
    process_result["terminal_process_state"] = stopped.process_liveness.value
    dead = stopped.process_liveness is ProcessLiveness.PROVEN_DEAD
    return dead, dead


def _grant_by_runtime_name(binding: CodexSkillCanaryBinding, runtime_name: str):
    for grant in binding.profile.skill_grants:
        if grant.runtime_name == runtime_name:
            return grant
    raise KeyError(runtime_name)


def _build_envelope(
    binding: CodexSkillCanaryBinding, runtime_name: str, text: str
) -> CodexTurnInputEnvelope:
    grant = _grant_by_runtime_name(binding, runtime_name)
    final_path = f"{binding.projection.skills_root}/{grant.runtime_name}/SKILL.md"
    return CodexTurnInputEnvelope(
        text=text,
        skills=(
            CodexSkillTurnInput(
                capability_id=grant.capability_id,
                runtime_name=grant.runtime_name,
                skill_md_path=final_path,
                skill_content_digest=grant.skill_content_digest,
                package_generation_digest=binding.generation.package_generation_digest,
            ),
        ),
    )


def _default_fake_client_factory(argv: list[str], env: Mapping[str, str], cwd: Path):
    return AppServerClient(argv, env=env, cwd=cwd, start_new_session=True)


# ---------------------------------------------------------------------------
# run_canary
# ---------------------------------------------------------------------------


def run_canary(
    *,
    backend: str,
    binary_path: "Path | None",
    codex_home: "Path | None",
    repo_root: Path,
    scratch_root: Path,
    operation_id: str,
    client_factory=None,
    run_command: Callable[..., Any] = subprocess.run,
) -> CanaryEvidence:
    if backend not in ("fake", "live"):
        raise ValueError(f"unsupported backend: {backend!r}")

    repo_root = Path(repo_root)
    scratch_root = Path(scratch_root)
    scratch_root.mkdir(parents=True, exist_ok=True)

    # --- backend-specific realm/schema/binary/codex_home wiring ------------
    #
    # Single-binary law (CAP-S1 Sol review item 1): in BOTH realms exactly
    # ONE file is the schema generator, the ``--version``/initialize-probe
    # target, AND the App Server the adapter launches -- ``single_binary_
    # path``. The live realm already satisfied this (the operator-supplied
    # real Codex binary); the fake realm used to launch a DIFFERENT file
    # (the running Python interpreter, via ``-m scripts.ohf.fake_app_server``)
    # than the one the schema probe ran against, which is exactly the gap
    # that let a receipt attest one binary while authorizing another.
    if backend == "live":
        if binary_path is None or codex_home is None:
            raise CanaryStop(
                "PROVIDER_REALM_UNAVAILABLE", "live backend requires binary_path and codex_home"
            )
        codex_home = Path(codex_home)
        if codex_home == default_user_codex_home():
            raise CanaryStop(
                "PROVIDER_REALM_UNAVAILABLE", "live mode refuses the implicit default CODEX_HOME"
            )
        try:
            validate_live_codex_home(codex_home)
        except RuntimeError as exc:
            raise CanaryStop("PROVIDER_REALM_UNAVAILABLE", str(exc)) from exc
        single_binary_path = Path(binary_path)
        adapter_codex_home = codex_home
        adapter_argv = None
        # ``PYTHONPATH`` is in the adapter's own safe-env-key allowlist and
        # is inert for a real Codex binary; it is required for the addendum
        # finding-3 seam-probe test's own single-binary fixture (a Python
        # script whose App Server mode execs into ``-m scripts.ohf.
        # fake_app_server``) to be genuinely launchable under this realm's
        # otherwise-minimal environment.
        extra_env: dict[str, str] = {"PYTHONPATH": str(repo_root)}
        if client_factory is None:
            raise ValueError("live backend requires an explicit client_factory")
    else:
        if client_factory is None:
            raise ValueError("fake backend requires an explicit client_factory")
        if binary_path is not None:
            single_binary_path = Path(binary_path)
            if not single_binary_path.exists():
                single_binary_path.write_text(_SCHEMA_FIXTURE_BINARY_SOURCE, encoding="utf-8")
                single_binary_path.chmod(0o755)
        else:
            single_binary_path = FAKE_CODEX_BINARY_PATH
        adapter_codex_home = Path(codex_home) if codex_home is not None else (
            scratch_root / "codex-home"
        )
        adapter_codex_home.mkdir(parents=True, exist_ok=True)
        adapter_codex_home.chmod(0o700)
        auth_path = adapter_codex_home / "auth.json"
        if not auth_path.exists():
            auth_path.write_text("fixture credential bytes", encoding="utf-8")
        auth_path.chmod(0o600)
        adapter_argv = (str(single_binary_path), "app-server")
        extra_env = {
            "PYTHONPATH": str(repo_root),
            "OHF_FAKE_STATE": str(scratch_root / "fake-state.json"),
            "OHF_FAKE_MODEL": CANARY_REQUESTED_MODEL,
            # The V4 mastermind-operator profile grants no MCP servers; the
            # fake App Server's OHF-probe MCP fixture is unrelated to CAP-S1
            # and must not appear in the observed config/mcp surface.
            "OHF_FAKE_MCP_GONE": "1",
            # This profile carries V4 Skill grants, so its
            # ``expected_config_digest`` requires ``skills.bundled.enabled=
            # false`` on ``config/read`` (protocol amendment §5). The fake
            # App Server double must echo that block for the config-digest
            # attestation gate to close.
            "OHF_FAKE_BUNDLED_DISABLED": "1",
            # CAP-S1 addendum finding 1: turn-specific, closed-marker-
            # compliant replies keyed by the captured Skill turn-input name
            # -- required for the fake backend's own CLI subprocess journey
            # (which has no scripted-client reply substitution available)
            # to pass the closed marker grammar for all four turns.
            "OHF_FAKE_CAP_S1_TURN_REPLIES": "1",
        }

    cleanup_actions: list[tuple[str, Callable[[], "tuple[bool, bool]"]]] = []
    process_result: dict[str, Any] = {}
    evidence_local: "CanaryEvidence | None" = None

    try:
        # The probe environment mirrors the adapter's own env-building logic
        # (``CodexOperatorAdapter._env``) closely enough to launch the SAME
        # single binary the adapter will later launch, without yet needing
        # the synthetic workspace (which does not exist at this point in the
        # sequence) -- the probe only ever issues ``initialize``, which never
        # touches the workspace.
        # Base on the caller's own environment -- exactly what schema
        # generation above already implicitly inherits by not passing an
        # explicit ``env=`` to ``run_command``'s default ``subprocess.run``
        # -- then layer the same adapter-consistent overrides
        # ``CodexOperatorAdapter._env`` would apply. A real Codex binary
        # ignores the extra inherited keys; the fake realm's single-binary
        # fixture genuinely needs ``PYTHONPATH`` (carried in ``extra_env``)
        # to exec into ``scripts.ohf.fake_app_server``.
        probe_env = dict(os.environ)
        probe_env.update(
            {
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "HOME": str(adapter_codex_home),
                "CODEX_HOME": str(adapter_codex_home),
                "LC_ALL": "C",
            }
        )
        probe_env.update(extra_env)

        receipt = attest_protocol_schema(
            binary_path=single_binary_path,
            scratch_root=scratch_root,
            run_command=run_command,
            probe_env=probe_env,
            probe_cwd=scratch_root,
            app_server_argv=(str(single_binary_path), "app-server"),
        )
        cleanup_actions.append(
            ("schema", lambda: _cleanup_dir_action(scratch_root / SCHEMA_ATTESTATION_DIR_NAME))
        )

        # Harness-version binding (CAP-S1 Sol review item 1): the receipt's
        # ``probe_user_agent`` -- the exact userAgent the SAME binary just
        # reported over a real ``initialize`` call -- is the ONE truth for
        # both realms now; ``receipt.binary_version`` is set to this same
        # value by ``attest_protocol_schema``. The runner seals
        # ``expected_harness_version`` from it so the adapter's own launch-
        # time ``initialize`` userAgent equality check closes the loop.
        harness_version = receipt.probe_user_agent
        if not harness_version:
            raise CanaryStop(
                "SKILL_PROTOCOL_SCHEMA_UNATTESTED", "harness version could not be sealed"
            )
        adapter_binary_path = single_binary_path
        adapter_binary_digest = receipt.binary_digest

        # --- synthetic workspace: real sealed git identity (Sol B2) -------
        workspace, workspace_base_sha, _workspace_read_only_applied = build_synthetic_workspace(
            scratch_root, operation_id=operation_id, run_command=run_command
        )
        cleanup_actions.append(("workspace", lambda: _cleanup_dir_action(workspace)))
        if backend == "fake":
            extra_env["OHF_FAKE_WORKSPACE"] = str(workspace)

        # --- exact reviewed source package + V4 profile -------------------
        # Residual refusal row (CAP-S1 Sol review item 3): every step here
        # that can raise ``CapabilityPackageError`` -- including an empty or
        # malformed ``source_commit``/``source_tree_sha`` in a doctored
        # fixture -- is now a TYPED, deterministic ``CanaryStop`` rather than
        # an uncaught internal exception escaping the runner's own closed
        # failure vocabulary, and fires before the provider process ever
        # starts.
        try:
            fixture_path = repo_root / V4_FIXTURE_RELATIVE_PATH
            registry = ExecutionCapabilityRegistry.load(fixture_path, source_root=repo_root)
            profile = registry.resolve(PROFILE_ID)
            raw_document = json.loads(fixture_path.read_text(encoding="utf-8"))
            raw_package = raw_document["capability_packages"][PACKAGE_CAPABILITY_ID]
            generation = build_capability_package_generation(
                capability_id=PACKAGE_CAPABILITY_ID, raw=raw_package
            )
        except (
            CapabilityPackageError,
            CapabilityPolicyError,
            KeyError,
            OSError,
            json.JSONDecodeError,
        ) as exc:
            raise CanaryStop(
                "PROVIDER_REALM_UNAVAILABLE", "candidate source package is unattested"
            ) from exc
        # Candidate identities are pinned from the already-verified fixture
        # generation BEFORE the provider process ever starts (Sol wave-3
        # review finding B5) -- never a ``git rev-parse HEAD`` read of this
        # repository's own moving working tree after execution.
        candidate_commit = generation.source_commit
        candidate_tree = generation.source_tree_sha
        if not _HEX40_RE.fullmatch(candidate_commit) or not _HEX40_RE.fullmatch(candidate_tree):
            raise CanaryStop(
                "PROVIDER_REALM_UNAVAILABLE", "candidate identity is empty or malformed"
            )

        attempt_root = scratch_root / "cap-s1-attempt-root"
        attempt_root.mkdir(parents=True, exist_ok=True)
        process_generation_id = f"{operation_id}-gen1"

        # Sol wave-3 review (5087345399, finding B2): the origin is now a
        # verified, ephemeral archive of the EXACT reviewed commit/tree from
        # this repository's own git object store -- never a writable,
        # non-Git ``cap-s1-release-root/<commit>`` copy mislabeled
        # INSTALLED_RELEASE.
        git_dir = _resolve_repo_git_dir(repo_root)
        try:
            origin_receipt = create_ephemeral_archive_origin(
                repository_git_dir=git_dir,
                source_commit=generation.source_commit,
                package_root=generation.package_root,
                scratch_root=scratch_root,
                expected_package_tree_sha=generation.source_tree_sha,
            )
        except SkillProjectionError as exc:
            raise CanaryStop(
                "PROVIDER_REALM_UNAVAILABLE", "ephemeral origin archive unavailable"
            ) from exc
        cleanup_actions.append(
            ("archive_origin", lambda: _cleanup_dir_action(Path(origin_receipt.origin_root)))
        )

        projection = stage_skill_projection(
            generation=generation,
            origin_mode=ORIGIN_VERIFIED_EPHEMERAL_GIT_ARCHIVE,
            origin_root=Path(origin_receipt.origin_root),
            attempt_root=attempt_root,
            owning_operation_id=operation_id,
            owning_process_generation=process_generation_id,
            origin_receipt=origin_receipt,
        )
        cleanup_actions.append(("projection", lambda: _cleanup_projection_action(projection)))

        # The binding carries the EXACT receipt ``attest_protocol_schema``
        # produced -- never a fresh construction (CAP-S1 Sol review item 1:
        # ``attest_protocol_schema`` is the ONLY producer of
        # ``CodexProtocolAttestationReceipt`` in production code).
        binding = CodexSkillCanaryBinding(
            generation=generation,
            profile=profile,
            projection=projection,
            protocol_receipt=receipt,
        )

        # --- adapter construction --------------------------------------------
        adapter = CodexOperatorAdapter(
            binary_path=adapter_binary_path,
            codex_home=adapter_codex_home,
            workspace_root=workspace,
            worker_id=CANARY_WORKER_ID,
            app_server_argv=adapter_argv,
            app_server_config_overrides=profile.app_server_config_overrides(),
            expected_harness_version=harness_version,
            # Config-digest attestation gate (protocol amendment §5): the
            # observed-config projection helper
            # (``app_server_security_config_projection``) now observes
            # ``skills.bundled`` the same way the policy-config projection
            # helper (``ExecutionCapabilityProfile.app_server_config_projection``)
            # emits it, so this V4 skill-grant profile's own
            # ``expected_config_digest`` is attestable and the gate is armed
            # for real. The fake backend's App Server double echoes the
            # matching ``bundled`` block (``OHF_FAKE_BUNDLED_DISABLED=1``,
            # set above); the live backend's real binary is launched with
            # the profile's overrides regardless, and whether it echoes the
            # ``bundled`` table back on ``config/read`` is phase-13 evidence
            # for Sol -- an honest CONFIG_DRIFT refusal there is the correct
            # outcome, never special-cased away here.
            expected_config_digest=profile.expected_config_digest,
            network_policy="disabled",
            base_sha_resolver=lambda _path: workspace_base_sha,
            client_factory=client_factory,
            extra_env=extra_env,
            skill_canary_binding=binding,
        )

        ws_stat = adapter.workspace_root.stat()
        # Sol wave-3 review finding B2: the profile's OWN fail-closed
        # manifest is used exactly as returned -- never re-wrapped with a
        # fabricated read-only unclassified-capability escape hatch.
        manifest = profile.capability_manifest(harness_binary_digest=adapter.binary_digest)
        session_epoch_id = f"{operation_id}-epoch"
        attempt_id = f"{operation_id}-attempt"

        requested = RequestedExecutionProfile(
            worker_id=CANARY_WORKER_ID,
            provider="openai-codex",
            requested_model=CANARY_REQUESTED_MODEL,
            harness_kind="codex-app-server",
            harness_binary_digest=adapter.binary_digest,
            harness_version=harness_version,
            workspace=WorkspaceIdentity(
                str(adapter.workspace_root),
                workspace_base_sha,
                ws_stat.st_dev,
                ws_stat.st_ino,
                ws_stat.st_uid,
                ws_stat.st_gid,
            ),
            sandbox_policy="read-only",
            approval_policy="never",
            network_policy="disabled",
            capabilities=manifest,
            native_helper_policy=NativeHelperPolicy.DISABLED,
            expected_config_digest=profile.expected_config_digest,
            authority_policy_hash=_CANARY_AUTHORITY_POLICY_HASH,
        )

        epoch = SessionEpochRef(session_epoch_id, attempt_id, CANARY_WORKER_ID, 1)
        generation_ref = ProcessGenerationRef(
            process_generation_id, session_epoch_id, 1, CANARY_WORKER_ID
        )

        try:
            adapter.start_session(
                operation_id=OperationId("ohf-op:cap-s1-start"),
                requested=requested,
                epoch=epoch,
                generation=generation_ref,
            )
        except CodexAdapterError as exc:
            _reraise_mapped(exc)
        except _SeamProbeRefusal as exc:
            raise CanaryStop("PROVIDER_REALM_UNAVAILABLE", str(exc)) from exc

        # The process is now registered with the adapter -- schedule its
        # exactly-once teardown attempt via the cleanup ledger (Sol wave-3
        # review finding B4). Every exit path below this point tears the
        # process down exactly once, never retried, before the schema/
        # workspace/archive/projection resources it may still be touching.
        cleanup_actions.append(
            ("process", lambda: _teardown_process_action(adapter, generation_ref, process_result))
        )

        observed = adapter.observed_attestation(generation_ref)
        launch = compare_launch(requested, observed)

        state = adapter._state(generation_ref)  # noqa: SLF001 -- runner owns process teardown (see module docstring below the class)
        client = state.client

        try:
            raw_launch_skills = client.request(
                "skills/list", skills_list_params(str(adapter.workspace_root))
            )
        except Exception as exc:  # noqa: BLE001 -- transport/timeout, never retried
            raise CanaryStop("EFFECT_UNKNOWN", "post-launch skills/list read failed") from exc
        skills_list_raw_shape_digest = _canonical_digest(raw_launch_skills)
        try:
            launch_rows = parse_skills_list_strict(
                raw_launch_skills, expected_cwd=str(adapter.workspace_root)
            )
            baseline_enabled_names: tuple[str, ...] = tuple(
                sorted(enabled_skill_names(launch_rows))
            )
        except SkillProtocolShapeError as exc:
            raise CanaryStop(
                "SKILL_SET_CAUSALITY_FAILED", "post-launch skills/list shape refused"
            ) from exc

        observed_enabled_names = baseline_enabled_names

        turn_marker_results: tuple[tuple[str, bool], ...] = ()
        after_add_enabled_names: tuple[str, ...] = ()
        served_model = observed.served_model

        if launch.decision is LaunchDecision.ALLOW:
            cursor = EventCursor(attempt_id, session_epoch_id, process_generation_id, local_sequence=0)
            results: list[tuple[str, bool]] = []
            for skill_name in TURN_ORDER:
                turn_ref = TurnRef(
                    f"cap-s1-turn-{skill_name}", session_epoch_id, process_generation_id, attempt_id
                )
                envelope = _build_envelope(binding, skill_name, _TURN_TEXTS[skill_name])
                adapter.turn_input_loader = lambda _turn, _env=envelope: _env
                try:
                    adapter.begin_turn(
                        operation_id=OperationId(f"ohf-op:cap-s1-turn-{skill_name}"),
                        turn=turn_ref,
                        generation=generation_ref,
                        launch=launch,
                    )
                except CodexAdapterError as exc:
                    _reraise_mapped(exc)
                cursor = EventCursor(
                    attempt_id,
                    session_epoch_id,
                    process_generation_id,
                    local_sequence=cursor.local_sequence,
                    turn_id=turn_ref.turn_id,
                )
                try:
                    _events, cursor = adapter.read_events(cursor)
                except CodexAdapterError as exc:
                    _reraise_mapped(exc)
                try:
                    candidate = adapter.collect_candidate_result(turn_ref)
                except CodexAdapterError as exc:
                    _reraise_mapped(exc)
                results.append((skill_name, _turn_markers_satisfied(skill_name, candidate.summary)))
            turn_marker_results = tuple(results)

            # A genuine NEW read (Sol wave-3 review finding B5): re-confirm
            # the skill surface right after the whole turn loop, before the
            # extraRoots/set [] clear -- closing the gap between the
            # launch-time baseline and the final clear that the
            # notification-based ``skills_changed`` check alone might miss.
            try:
                post_turns_raw = client.request(
                    "skills/list", skills_list_params(str(adapter.workspace_root))
                )
                post_turns_rows = parse_skills_list_strict(
                    post_turns_raw, expected_cwd=str(adapter.workspace_root)
                )
                after_add_enabled_names = tuple(sorted(enabled_skill_names(post_turns_rows)))
            except SkillProtocolShapeError as exc:
                raise CanaryStop(
                    "SKILL_SET_CAUSALITY_FAILED", "post-turn skills/list shape refused"
                ) from exc
            except Exception as exc:  # noqa: BLE001 -- transport/timeout, never retried
                raise CanaryStop("EFFECT_UNKNOWN", "post-turn skills/list read failed") from exc

        # --- clear: extraRoots/set [] and re-verify empty --------------------
        after_clear_enabled_names: tuple[str, ...] = ()
        try:
            client.request("skills/extraRoots/set", extra_roots_set_params([]))
            extra_roots_set_outcomes = ("cleared",)
            clear_raw = client.request(
                "skills/list", skills_list_params(str(adapter.workspace_root))
            )
            clear_rows = parse_skills_list_strict(
                clear_raw, expected_cwd=str(adapter.workspace_root)
            )
        except SkillProtocolShapeError as exc:
            raise CanaryStop(
                "SKILL_SET_CAUSALITY_FAILED", "post-clear skills/list shape refused"
            ) from exc
        except CodexAdapterError as exc:
            _reraise_mapped(exc)
            raise  # pragma: no cover -- _reraise_mapped always raises
        except Exception as exc:  # noqa: BLE001 -- transport/timeout during teardown
            raise CanaryStop("EFFECT_UNKNOWN", "post-clear teardown call failed") from exc
        else:
            after_clear_enabled_names = tuple(sorted(enabled_skill_names(clear_rows)))
            if enabled_skill_names(clear_rows):
                raise CanaryStop(
                    "SKILL_SET_CAUSALITY_FAILED", "post-clear skill surface is not empty"
                )

        # --- artifact inventory (computed BEFORE teardown removes anything) --
        schema_dir = scratch_root / SCHEMA_ATTESTATION_DIR_NAME
        artifact_inventory = tuple(
            sorted(
                [f"schema:{p.relative_to(schema_dir)}" for p in schema_dir.rglob("*") if p.is_file()]
                + [f"workspace:{p.relative_to(workspace)}" for p in workspace.rglob("*") if p.is_file()]
                + [f"projection:file_count={len(projection.file_rows)}"]
            )
        )

        skill_grant_digests = tuple(
            sorted((grant.capability_id, grant.grant_digest) for grant in profile.skill_grants)
        )

        evidence_local = CanaryEvidence(
            candidate_commit=candidate_commit,
            candidate_tree=candidate_tree,
            canary_operation_id=operation_id,
            workspace_root=str(adapter.workspace_root),
            process_generation=process_generation_id,
            v4_policy_digest=registry.policy_digest,
            package_source_digest=generation.package_source_digest,
            package_generation_digest=generation.package_generation_digest,
            skill_grant_digests=skill_grant_digests,
            skill_closure_digests=tuple(projection.skill_content_digests),
            projection_receipt_digest=_canonical_digest(dataclasses.asdict(projection)),
            binary_digest=adapter.binary_digest,
            binary_version=harness_version,
            origin_mode=projection.origin_mode,
            origin_authentication=projection.origin_authentication,
            skills_root=projection.skills_root,
            app_server_config_digest=observed.effective_config_digest,
            extra_roots_set_outcomes=extra_roots_set_outcomes,
            skills_list_raw_shape_digest=skills_list_raw_shape_digest,
            baseline_enabled_names=baseline_enabled_names,
            after_add_enabled_names=after_add_enabled_names,
            observed_enabled_names=observed_enabled_names,
            after_clear_enabled_names=after_clear_enabled_names,
            protocol_receipt_digest=_canonical_digest(
                dataclasses.asdict(binding.protocol_receipt)
            ),
            launch_decision=launch.decision.value,
            turn_marker_results=turn_marker_results,
            served_model=served_model,
            terminal_process_state="UNKNOWN",
            artifact_inventory=artifact_inventory,
            cleanup=CanaryCleanupRecord(),
        )
    finally:
        # Sol wave-3 review finding B4: EVERYTHING created after scratch
        # setup is torn down here, on EVERY exit path -- happy, CanaryStop,
        # adapter error, or unexpected exception -- in the exact reverse of
        # its registration order, each action attempted exactly once.
        artifacts: list[tuple[str, bool, bool]] = []
        for kind, action in reversed(cleanup_actions):
            try:
                removed, verified_absent = action()
            except Exception:  # noqa: BLE001 -- a cleanup action must never mask the original error
                removed, verified_absent = False, False
            artifacts.append((kind, removed, verified_absent))
        cleanup_record = CanaryCleanupRecord(artifacts=tuple(artifacts))

    return dataclasses.replace(
        evidence_local,
        cleanup=cleanup_record,
        terminal_process_state=process_result.get("terminal_process_state", "UNKNOWN"),
    )


# ---------------------------------------------------------------------------
# Closed CAP-S1 result contract (CAP-S1 Sol review item 5)
# ---------------------------------------------------------------------------
#
# Before this commission no closed result validator existed at all, and
# ``CanaryEvidence`` alone accepted an empty candidate identity anywhere it
# was hand-assembled outside ``run_canary``. This section delivers the
# closed validator + constructor only -- the principal assembles the real
# packet (from a completed ``run_canary`` call, hosted CI evidence, review
# state, etc.) later; this module never itself calls
# ``build_cap_s1_result``.

RESULT_CONTRACT_MARKER = "cap-s1-result-contract-v1"
RESULT_CONTRACT_SCHEMA = "mastermind.cap_s1_result/v1"

_RESULT_HEX40_RE = re.compile(r"[0-9a-f]{40}")
_RESULT_HEX64_RE = re.compile(r"[0-9a-f]{64}")

_PROVIDER_ATTEMPT_HOLD_CODES = frozenset(FROZEN_STOP_CODES) | {"GATES_NOT_GREEN"}


class CapS1ResultError(ValueError):
    """Bounded, non-echoing refusal for the closed CAP-S1 result contract.

    Never echoes the caller-supplied value that failed validation -- only a
    fixed, closed reason token -- mirroring ``CanaryStop``'s own discipline.
    """


@dataclasses.dataclass(frozen=True, kw_only=True)
class CapS1Result:
    """The closed ``mastermind.cap_s1_result/v1`` contract.

    Construct only via :func:`build_cap_s1_result`, which validates before
    ever returning an instance -- a bare ``CapS1Result(...)`` call is a valid
    Python object but is never itself proof the contract holds; only a value
    that has passed :func:`validate_cap_s1_result` may be trusted downstream.
    """

    schema_version: str
    marker: str
    operation: str
    receiver: str
    carrier: str
    exact_head: str
    exact_tree: str
    current_protected_join: str
    changed_path_census: tuple[str, ...]
    package_identities: dict
    canary_evidence: dict
    provider_attempt: dict
    local_proof: dict
    hosted_proof: dict
    security_proof: dict
    mutation_proof: dict
    cleanup_proof: dict
    review_state: dict
    held_non_goals: tuple[str, ...]


def _result_is_hex40(value: object) -> bool:
    return isinstance(value, str) and _RESULT_HEX40_RE.fullmatch(value) is not None


def _result_is_hex64(value: object) -> bool:
    return isinstance(value, str) and _RESULT_HEX64_RE.fullmatch(value) is not None


def _result_leaf_strings_are_hex64(value: object) -> bool:
    """Every STRING leaf reachable from ``value`` must be a full 64-hex
    digest -- ``package_identities`` is documented as "digests + closures",
    so anything else nested inside it is not a lawful member."""

    if isinstance(value, str):
        return _result_is_hex64(value)
    if isinstance(value, dict):
        return all(_result_leaf_strings_are_hex64(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return all(_result_leaf_strings_are_hex64(item) for item in value)
    return True


def validate_cap_s1_result(result: CapS1Result) -> None:
    """Refuse anything not conforming to the closed
    ``mastermind.cap_s1_result/v1`` contract. Every refusal is a fixed,
    bounded, non-echoing reason string."""

    if type(result) is not CapS1Result:
        raise CapS1ResultError("cap_s1_result_type_invalid")
    if result.schema_version != RESULT_CONTRACT_SCHEMA:
        raise CapS1ResultError("cap_s1_result_schema_mismatch")
    if result.marker != RESULT_CONTRACT_MARKER:
        raise CapS1ResultError("cap_s1_result_marker_mismatch")

    for field_name in ("operation", "receiver", "carrier"):
        value = getattr(result, field_name)
        if not isinstance(value, str) or not value.strip():
            raise CapS1ResultError(f"cap_s1_result_{field_name}_invalid")

    for field_name in ("exact_head", "exact_tree", "current_protected_join"):
        if not _result_is_hex40(getattr(result, field_name)):
            raise CapS1ResultError(f"cap_s1_result_{field_name}_invalid")

    census = result.changed_path_census
    if not isinstance(census, tuple) or not census:
        raise CapS1ResultError("cap_s1_result_changed_path_census_empty")
    if not all(isinstance(item, str) and item for item in census):
        raise CapS1ResultError("cap_s1_result_changed_path_census_invalid")
    if len(set(census)) != len(census):
        raise CapS1ResultError("cap_s1_result_changed_path_census_duplicate")
    if list(census) != sorted(census):
        raise CapS1ResultError("cap_s1_result_changed_path_census_unsorted")

    if not isinstance(result.package_identities, dict) or not result.package_identities:
        raise CapS1ResultError("cap_s1_result_package_identities_invalid")
    if not _result_leaf_strings_are_hex64(result.package_identities):
        raise CapS1ResultError("cap_s1_result_package_identities_digest_invalid")

    provider_attempt = result.provider_attempt
    if not isinstance(provider_attempt, dict):
        raise CapS1ResultError("cap_s1_result_provider_attempt_invalid")
    state = provider_attempt.get("state")
    if state not in ("COMPLETED", "HOLD"):
        raise CapS1ResultError("cap_s1_result_provider_attempt_state_invalid")
    if state == "HOLD":
        hold_code = provider_attempt.get("hold_code")
        if hold_code not in _PROVIDER_ATTEMPT_HOLD_CODES:
            raise CapS1ResultError("cap_s1_result_provider_attempt_hold_code_invalid")
        detail = provider_attempt.get("detail")
        if not isinstance(detail, str) or not detail.strip():
            raise CapS1ResultError("cap_s1_result_provider_attempt_detail_invalid")
        if result.canary_evidence:
            raise CapS1ResultError("cap_s1_result_canary_evidence_must_be_empty_on_hold")
    else:  # COMPLETED
        if not isinstance(result.canary_evidence, dict) or not result.canary_evidence:
            raise CapS1ResultError("cap_s1_result_canary_evidence_required_on_completed")
        if result.canary_evidence.get("schema_version") != CANARY_EVIDENCE_SCHEMA_VERSION:
            raise CapS1ResultError("cap_s1_result_canary_evidence_schema_mismatch")

    for field_name in (
        "security_proof",
        "mutation_proof",
        "cleanup_proof",
        "review_state",
    ):
        if not isinstance(getattr(result, field_name), dict):
            raise CapS1ResultError(f"cap_s1_result_{field_name}_invalid")

    local_proof = result.local_proof
    if not isinstance(local_proof, dict) or not local_proof:
        raise CapS1ResultError("cap_s1_result_local_proof_empty")
    for suite_name, counts in local_proof.items():
        if not isinstance(suite_name, str) or not suite_name:
            raise CapS1ResultError("cap_s1_result_local_proof_invalid")
        if (
            not isinstance(counts, dict)
            or "passed" not in counts
            or "skipped" not in counts
            or isinstance(counts.get("passed"), bool)
            or isinstance(counts.get("skipped"), bool)
            or not isinstance(counts.get("passed"), int)
            or not isinstance(counts.get("skipped"), int)
        ):
            raise CapS1ResultError("cap_s1_result_local_proof_invalid")

    hosted_proof = result.hosted_proof
    if not isinstance(hosted_proof, dict) or not hosted_proof:
        raise CapS1ResultError("cap_s1_result_hosted_proof_empty")
    run_id = hosted_proof.get("run_id")
    conclusion = hosted_proof.get("conclusion")
    if not isinstance(run_id, str) or not run_id.strip():
        raise CapS1ResultError("cap_s1_result_hosted_proof_run_id_invalid")
    if not isinstance(conclusion, str) or not conclusion.strip():
        raise CapS1ResultError("cap_s1_result_hosted_proof_conclusion_invalid")

    held = result.held_non_goals
    if not isinstance(held, tuple) or not held:
        raise CapS1ResultError("cap_s1_result_held_non_goals_empty")
    if not all(isinstance(item, str) and item.strip() for item in held):
        raise CapS1ResultError("cap_s1_result_held_non_goals_invalid")


def build_cap_s1_result(**kwargs: Any) -> CapS1Result:
    """Construct, then validate, a :class:`CapS1Result` -- the one lawful
    way to obtain an instance believed to satisfy the closed contract."""

    kwargs.setdefault("schema_version", RESULT_CONTRACT_SCHEMA)
    kwargs.setdefault("marker", RESULT_CONTRACT_MARKER)
    result = CapS1Result(**kwargs)
    validate_cap_s1_result(result)
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description="CAP-S1 Mastermind operator canary runner")
    parser.add_argument("--backend", choices=("fake", "live"), required=True)
    parser.add_argument("--codex-home", type=Path, default=None)
    parser.add_argument("--binary-path", type=Path, default=None)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--operation-id", required=True)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    args = parser.parse_args(argv)

    if args.backend == "fake":
        client_factory = _default_fake_client_factory
    else:
        # CAP-S1 addendum (5087373998, finding 3): an explicit, opt-in
        # ``CAP_S1_LIVE_CLIENT_FACTORY=module:attr`` override lets the live
        # wiring be exercised end to end by a non-network test double (see
        # ``_seam_probe_client_factory``) without ever touching the real
        # adapter default. Only consulted for backend=live; the fake
        # backend above is never affected.
        override = os.environ.get("CAP_S1_LIVE_CLIENT_FACTORY", "").strip()
        if override:
            module_name, _sep, attr_name = override.partition(":")
            client_factory = None
            if module_name and attr_name:
                try:
                    # A ``-m`` entry point runs this file as ``__main__`` --
                    # re-importing it by its dotted path would mint a SECOND,
                    # distinct module object (and a distinct
                    # ``_SeamProbeRefusal`` class the ``except`` clause in
                    # ``run_canary`` could never match). When the override
                    # names THIS module, reuse the already-loaded one instead.
                    if module_name in (__name__, "scripts.ohf.cap_s1_mastermind_operator_canary"):
                        module = sys.modules[__name__]
                    else:
                        module = importlib.import_module(module_name)
                    client_factory = getattr(module, attr_name)
                except (ImportError, AttributeError, KeyError):
                    client_factory = None
            if client_factory is None:
                print("CANARY_STOP:PROVIDER_REALM_UNAVAILABLE")
                print(
                    json.dumps(
                        {
                            "canary_stop": "PROVIDER_REALM_UNAVAILABLE",
                            "detail": "live client factory override is not importable",
                        },
                        sort_keys=True,
                    )
                )
                return 1
        else:
            # Live realm: the adapter's own default factory spawns the
            # exact real App Server process; run_canary refuses a None
            # factory either way.
            from control_plane.codex_operator_adapter import _default_client_factory

            client_factory = _default_client_factory

    try:
        evidence = run_canary(
            backend=args.backend,
            binary_path=args.binary_path,
            codex_home=args.codex_home,
            repo_root=args.repo_root,
            scratch_root=args.scratch,
            operation_id=args.operation_id,
            client_factory=client_factory,
        )
    except CanaryStop as stop:
        print(f"CANARY_STOP:{stop.code}")
        print(json.dumps({"canary_stop": stop.code, "detail": stop.detail}, sort_keys=True))
        return 1

    payload = dataclasses.asdict(evidence)
    print(json.dumps(payload, indent=2, sort_keys=True))

    markers_ok = all(ok for _name, ok in evidence.turn_marker_results)
    cleanup_ok = evidence.cleanup.all_removed
    launch_ok = evidence.launch_decision == LaunchDecision.ALLOW.value
    return 0 if (markers_ok and cleanup_ok and launch_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())

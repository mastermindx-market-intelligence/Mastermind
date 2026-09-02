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
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Mapping

from control_plane.codex_operator_adapter import (
    CodexAdapterError,
    CodexOperatorAdapter,
    CodexProtocolAttestationReceipt,
    CodexSkillCanaryBinding,
    CodexSkillTurnInput,
    CodexTurnInputEnvelope,
)
from control_plane.executive_agent_capabilities import (
    ExecutionCapabilityRegistry,
    NativeHelperPolicy,
)
from control_plane.executive_capability_packages import (
    build_capability_package_generation,
)
from control_plane.operator_harness_contract import (
    CapabilityManifest,
    EventCursor,
    LaunchDecision,
    OperationId,
    ProcessGenerationRef,
    RequestedExecutionProfile,
    SessionEpochRef,
    TurnRef,
    WorkspaceIdentity,
    compare_launch,
)
from scripts.ohf.capability_skill_projection import (
    ORIGIN_INSTALLED_RELEASE,
    cleanup_skill_projection,
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
_CANARY_BASE_SHA = "0" * 40
_CANARY_AUTHORITY_POLICY_HASH = "c" * 64

SYNTHETIC_OPERATION_ID = "cap-s1-synthetic-op"
SYNTHETIC_DECISION_BRANCH = "branch-alpha"

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


@dataclasses.dataclass(frozen=True)
class SchemaAttestation:
    binary_path: str
    binary_digest: str
    stable_inventory_digest: str
    experimental_inventory_digest: str
    supports_skill_input_path: bool
    generated_at_dir: str


@dataclasses.dataclass(frozen=True)
class CanaryEvidence:
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
    app_server_config_digest: "str | None"
    extra_roots_set_outcomes: tuple[str, ...]
    skills_list_raw_shape_digest: str
    observed_enabled_names: tuple[str, ...]
    launch_decision: str
    turn_marker_results: tuple[tuple[str, bool], ...]
    served_model: "str | None"
    terminal_process_state: str
    artifact_inventory: tuple[str, ...]
    cleanup: dict


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
    *, binary_path: Path, scratch_root: Path, run_command: Callable[..., Any] = subprocess.run
) -> SchemaAttestation:
    binary_path = Path(binary_path)
    scratch_root = Path(scratch_root)
    scratch_root.mkdir(parents=True, exist_ok=True)

    try:
        binary_digest = _sha256_file(binary_path)
    except OSError as exc:
        raise CanaryStop(
            "SKILL_PROTOCOL_SCHEMA_UNATTESTED", "binary is not observable"
        ) from exc

    import secrets as _secrets

    sealed_dir = scratch_root / f"schema-attestation-{_secrets.token_hex(8)}"
    sealed_dir.mkdir(parents=False, exist_ok=False)
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

    return SchemaAttestation(
        binary_path=str(binary_path),
        binary_digest=binary_digest,
        stable_inventory_digest=stable_digest,
        experimental_inventory_digest=experimental_digest,
        supports_skill_input_path=supports,
        generated_at_dir=str(sealed_dir),
    )


# ---------------------------------------------------------------------------
# build_synthetic_workspace (protocol-attestation amendment §5)
# ---------------------------------------------------------------------------

_AMBIENT_SURFACE_NAMES = (".agents", ".codex", "plugins", "marketplace", "skills")


def build_synthetic_workspace(scratch_root: Path) -> Path:
    scratch_root = Path(scratch_root)
    scratch_root.mkdir(parents=True, exist_ok=True)
    workspace = scratch_root / "synthetic-workspace"
    workspace.mkdir(parents=False, exist_ok=False)
    (workspace / "README.md").write_text(
        "CAP-S1 synthetic canary workspace\n", encoding="utf-8"
    )
    for name in _AMBIENT_SURFACE_NAMES:
        assert not (workspace / name).exists()
    return workspace


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


def _turn_markers_satisfied(skill_name: str, text: "str | None") -> bool:
    if not isinstance(text, str) or not text:
        return False
    if any(token in text for token in _GLOBAL_FORBIDDEN_TOKENS):
        return False
    required, forbidden = _TURN_MARKER_RULES[skill_name]
    if not all(token in text for token in required):
        return False
    if any(token in text for token in forbidden):
        return False
    return True


# ---------------------------------------------------------------------------
# Small filesystem/git helpers
# ---------------------------------------------------------------------------


def _remove_tree(path: Path) -> bool:
    try:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path, ignore_errors=True)
        elif path.exists():
            path.unlink()
    except OSError:
        pass
    return not path.exists()


def _git_rev(repo_root: Path, rev: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", rev],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
    return completed.stdout.strip()


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
        schema_binary_path = Path(binary_path)
        adapter_binary_path = Path(binary_path)
        adapter_codex_home = codex_home
        adapter_argv = None
        harness_version = f"codex-app-server/{_sha256_file(schema_binary_path)[:12]}"
        extra_env: dict[str, str] = {}
        if client_factory is None:
            raise ValueError("live backend requires an explicit client_factory")
    else:
        if client_factory is None:
            raise ValueError("fake backend requires an explicit client_factory")
        schema_binary_path = Path(binary_path) if binary_path is not None else (
            scratch_root / "fixture-codex-binary"
        )
        if not schema_binary_path.exists():
            schema_binary_path.write_bytes(b"#!/bin/sh\necho fixture codex binary\n")
            schema_binary_path.chmod(0o755)
        adapter_binary_path = Path(sys.executable).resolve()
        adapter_codex_home = Path(codex_home) if codex_home is not None else (
            scratch_root / "codex-home"
        )
        adapter_codex_home.mkdir(parents=True, exist_ok=True)
        adapter_codex_home.chmod(0o700)
        auth_path = adapter_codex_home / "auth.json"
        if not auth_path.exists():
            auth_path.write_text("fixture credential bytes", encoding="utf-8")
        auth_path.chmod(0o600)
        adapter_argv = (str(adapter_binary_path), "-m", "scripts.ohf.fake_app_server")
        harness_version = FAKE_HARNESS_VERSION
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
        }

    schema = attest_protocol_schema(
        binary_path=schema_binary_path, scratch_root=scratch_root, run_command=run_command
    )

    # The protocol receipt binds to the binary the ADAPTER actually launches,
    # never the (possibly distinct, fake-backend-only) binary the schema
    # probe ran against -- ``schema.binary_digest`` is the schema probe's own
    # evidence and is deliberately NOT reused here (CAP-S1 Sol wave-3 review
    # finding B3).
    try:
        adapter_binary_digest = _sha256_file(adapter_binary_path)
    except OSError as exc:
        raise CanaryStop(
            "SKILL_PROTOCOL_SCHEMA_UNATTESTED", "adapter binary is not observable"
        ) from exc

    # --- synthetic workspace -------------------------------------------
    workspace = build_synthetic_workspace(scratch_root)
    readme_path = workspace / "README.md"
    readme_path.write_text(
        readme_path.read_text(encoding="utf-8") + f"operation: {operation_id}\n",
        encoding="utf-8",
    )
    if backend == "fake":
        extra_env["OHF_FAKE_WORKSPACE"] = str(workspace)

    # --- exact reviewed source package + V4 profile ----------------------
    fixture_path = repo_root / V4_FIXTURE_RELATIVE_PATH
    registry = ExecutionCapabilityRegistry.load(fixture_path, source_root=repo_root)
    profile = registry.resolve(PROFILE_ID)
    raw_document = json.loads(fixture_path.read_text(encoding="utf-8"))
    raw_package = raw_document["capability_packages"][PACKAGE_CAPABILITY_ID]
    generation = build_capability_package_generation(
        capability_id=PACKAGE_CAPABILITY_ID, raw=raw_package
    )

    attempt_root = scratch_root / "cap-s1-attempt-root"
    attempt_root.mkdir(parents=True, exist_ok=True)
    process_generation_id = f"{operation_id}-gen1"

    # Sol wave-3 review (5087139217, finding M6): INSTALLED_RELEASE now
    # requires the origin root's own basename to equal the generation's
    # exact ``source_commit`` (the Executive installer's
    # ``releases/<sha>`` layout) -- a bare checkout root no longer
    # authenticates. This canary runs from an ordinary checkout, so it
    # builds a small, real (non-symlink) release-shaped origin by copying
    # only the already-reviewed, tiny package subtree (7 files) into a
    # freshly named ``<scratch>/cap-s1-release-root/<source_commit>/...``
    # directory -- never the whole repository -- immediately before
    # staging. This is the one call-site adaptation this commission makes;
    # every other runner behavior is unchanged.
    release_root = scratch_root / "cap-s1-release-root" / generation.source_commit
    release_package_dest = release_root / generation.package_root
    release_package_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(repo_root / generation.package_root, release_package_dest)

    projection = stage_skill_projection(
        generation=generation,
        origin_mode=ORIGIN_INSTALLED_RELEASE,
        origin_root=release_root,
        attempt_root=attempt_root,
        owning_operation_id=operation_id,
        owning_process_generation=process_generation_id,
    )

    binding = CodexSkillCanaryBinding(
        generation=generation,
        profile=profile,
        projection=projection,
        protocol_receipt=CodexProtocolAttestationReceipt(
            binary_path=str(adapter_binary_path),
            binary_digest=adapter_binary_digest,
            binary_version=harness_version,
            stable_inventory_digest=schema.stable_inventory_digest,
            experimental_inventory_digest=schema.experimental_inventory_digest,
            supports_skill_input_path=schema.supports_skill_input_path,
            skill_input_schema_evidence=(
                "skill_turn_input_schema_node_detected"
                if schema.supports_skill_input_path
                else ""
            ),
            # The fake backend's own App Server double always echoes
            # ``initialize``'s userAgent as exactly this ``harness_version``
            # (asserted by the adapter's own attestation gate), so "" is the
            # lawful fake-backend value here; the live backend has no
            # independent probe wired by this commission (a separate wave-3
            # runner finding), so it carries the same expected version.
            probe_user_agent=harness_version if backend == "live" else "",
        ),
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
        # set below); the live backend's real binary is launched with the
        # profile's overrides regardless, and whether it echoes the
        # ``bundled`` table back on ``config/read`` is phase-13 evidence
        # for Sol -- an honest CONFIG_DRIFT refusal there is the correct
        # outcome, never special-cased away here.
        expected_config_digest=profile.expected_config_digest,
        network_policy="disabled",
        base_sha_resolver=lambda _path: _CANARY_BASE_SHA,
        client_factory=client_factory,
        extra_env=extra_env,
        skill_canary_binding=binding,
    )

    ws_stat = adapter.workspace_root.stat()
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
            _CANARY_BASE_SHA,
            ws_stat.st_dev,
            ws_stat.st_ino,
            ws_stat.st_uid,
            ws_stat.st_gid,
        ),
        sandbox_policy="read-only",
        approval_policy="never",
        network_policy="disabled",
        capabilities=CapabilityManifest(
            required=manifest.required, unclassified_policy="lab_allow_unclassified_readonly"
        ),
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
        observed_enabled_names: tuple[str, ...] = tuple(sorted(enabled_skill_names(launch_rows)))
    except SkillProtocolShapeError as exc:
        raise CanaryStop(
            "SKILL_SET_CAUSALITY_FAILED", "post-launch skills/list shape refused"
        ) from exc

    turn_marker_results: tuple[tuple[str, bool], ...] = ()
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

    # --- clear: extraRoots/set [] and re-verify empty --------------------
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
        if enabled_skill_names(clear_rows):
            raise CanaryStop(
                "SKILL_SET_CAUSALITY_FAILED", "post-clear skill surface is not empty"
            )

    try:
        stopped = adapter.graceful_stop(
            generation_ref, operation_id=OperationId("ohf-op:cap-s1-stop")
        )
    except CodexAdapterError as exc:
        _reraise_mapped(exc)
        raise  # pragma: no cover

    terminal_process_state = stopped.process_liveness.value

    # --- cleanup + artifact inventory -------------------------------------
    schema_dir = Path(schema.generated_at_dir)
    artifact_inventory = tuple(
        sorted(
            [f"schema:{p.relative_to(schema_dir)}" for p in schema_dir.rglob("*") if p.is_file()]
            + [f"workspace:{p.relative_to(workspace)}" for p in workspace.rglob("*") if p.is_file()]
            + [f"projection:file_count={len(projection.file_rows)}"]
        )
    )

    projection_cleanup = cleanup_skill_projection(projection)
    schema_dir_removed = _remove_tree(schema_dir)
    workspace_removed = _remove_tree(workspace)

    cleanup = {
        "projection_removed": projection_cleanup.removed,
        "projection_verified_absent": projection_cleanup.verified_absent,
        "schema_dir_removed": schema_dir_removed,
        "workspace_removed": workspace_removed,
    }

    try:
        candidate_commit = _git_rev(repo_root, "HEAD")
        candidate_tree = _git_rev(repo_root, "HEAD^{tree}")
    except (OSError, subprocess.SubprocessError):
        candidate_commit = ""
        candidate_tree = ""

    skill_grant_digests = tuple(
        sorted((grant.capability_id, grant.grant_digest) for grant in profile.skill_grants)
    )

    return CanaryEvidence(
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
        app_server_config_digest=observed.effective_config_digest,
        extra_roots_set_outcomes=extra_roots_set_outcomes,
        skills_list_raw_shape_digest=skills_list_raw_shape_digest,
        observed_enabled_names=observed_enabled_names,
        launch_decision=launch.decision.value,
        turn_marker_results=turn_marker_results,
        served_model=served_model,
        terminal_process_state=terminal_process_state,
        artifact_inventory=artifact_inventory,
        cleanup=cleanup,
    )


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
        # Live realm: the adapter's own default factory spawns the exact real
        # App Server process; run_canary refuses a None factory either way.
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
    cleanup_ok = all(bool(value) for value in evidence.cleanup.values())
    launch_ok = evidence.launch_decision == LaunchDecision.ALLOW.value
    return 0 if (markers_ok and cleanup_ok and launch_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())

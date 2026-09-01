"""Fresh-Sol Evaluation Harness F0 (EVAL-OHF1).

Production-inert OHF runner: launches genuinely fresh ``gpt-5.6-sol`` App
Server contexts against immutable Sol Skillpack bytes and emits verbatim,
identity-bound behavioral evidence for MAS-136.

Spec: docs/superpowers/specs/2026-08-26-fresh-sol-evaluation-harness-f0-design.md
Plan: docs/superpowers/plans/2026-08-26-fresh-sol-evaluation-harness-f0.md

This module owns no Executive lifecycle, scheduling, retry, or grading
authority.  It extends the existing ``scripts/ohf/**`` live-laboratory
substrate only (``scripts.ohf.laboratory``, ``scripts.ohf.protocol``,
``scripts.ohf.redaction``, ``scripts.ohf.p1a_capability_policy``).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

import yaml

from scripts.ohf.laboratory import (
    AppServerClient,
    AppServerStopProof,
    binary_digest,
    validate_live_codex_home,
)
from scripts.ohf.p1a_capability_policy import LAUNCH_OK, classify_observed, launch_decision
from scripts.ohf.protocol import (
    config_mcp_names,
    config_plugin_names,
    parse_account_read,
    parse_config_read,
    skill_names,
    skills_list_params,
    thread_turns,
)
from scripts.ohf.redaction import evidence_contains_secret

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
REQUIRED_MODEL = "gpt-5.6-sol"
CLIENT_INFO = {
    "name": "mastermind_fresh_sol_eval",
    "title": "Mastermind fresh-Sol evaluation harness (EVAL-OHF1)",
    "version": "0.1.0",
}

# ---------------------------------------------------------------------------
# Immutable arm identity / closed failure vocabulary (plan Task 1, Step 2)
# ---------------------------------------------------------------------------

RUN_SCHEMA = "mastermind.fresh_sol_eval_run/v1"
MANIFEST_SCHEMA = "mastermind.fresh_sol_eval_manifest/v1"
MAS136_SCENARIOS = ("S2", "S6", "S7", "S8")
EVAL_WRAPPER_VERSION = "mastermind.fresh_sol_eval_wrapper/v1"

SKILLPACK_SCHEMA = "mastermind.sol_skillpack.v1"
SUPPORTED_BOOTSTRAP_MAJOR = 1


@dataclass(frozen=True)
class SkillpackArm:
    name: str
    commit_sha: str
    skillpack_version: str


MAS136_ARMS: dict[str, SkillpackArm] = {
    "control-1.0.0": SkillpackArm(
        "control-1.0.0", "51f9942733b86e550bb9169d2a43462bd28e774f", "1.0.0"
    ),
    "amended-1.1.0": SkillpackArm(
        "amended-1.1.0", "8209e1f31da15f8effc23a9899a5c5a02d30cab4", "1.1.0"
    ),
}


FAILURE_CODES = frozenset(
    {
        "SOURCE_COMMIT_UNAVAILABLE",
        "SKILLPACK_IDENTITY_MISMATCH",
        "PROCEDURE_SOURCE_UNAVAILABLE",
        "PROTOCOL_INVALID",
        "AUTH_REALM_INVALID",
        "HARNESS_BINARY_UNAVAILABLE",
        "HARNESS_INITIALIZE_FAILED",
        "CAPABILITY_ATTESTATION_INVALID",
        "SERVED_MODEL_MISMATCH",
        "THREAD_START_FAILED",
        "TURN_EFFECT_UNKNOWN",
        "THREAD_READ_FAILED",
        "EVIDENCE_SECRET_SHAPE_REFUSED",
        "CLEANUP_UNPROVEN",
        "EVIDENCE_COLLISION",
    }
)


class FreshSolEvalError(RuntimeError):
    """A closed, named F0 failure.  ``code`` is always one of FAILURE_CODES."""

    def __init__(self, code: str, message: str) -> None:
        if code not in FAILURE_CODES:
            raise ValueError("unknown fresh-Sol failure code")
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------------------
# Git-object materialization, zero network (plan Task 1, Steps 3-4)
# ---------------------------------------------------------------------------


def _git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
    )


@dataclass(frozen=True)
class ProcedureSource:
    path: str
    blob_sha: str
    content: bytes


@dataclass(frozen=True)
class ProcedureBundle:
    arm: SkillpackArm
    sources: tuple[ProcedureSource, ...]
    context_sha256: str


def _aggregate_context_sha256(sources: tuple[ProcedureSource, ...]) -> str:
    hasher = hashlib.sha256()
    for source in sources:
        hasher.update(source.path.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(source.blob_sha.encode("ascii"))
        hasher.update(b"\0")
        hasher.update(source.content)
        hasher.update(b"\0")
    return hasher.hexdigest()


def _extract_yaml_frontmatter(content: bytes) -> dict[str, Any] | None:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if not text.startswith("---"):
        return None
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    end_index = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end_index = idx
            break
    if end_index is None:
        return None
    front_text = "\n".join(lines[1:end_index])
    try:
        parsed = yaml.safe_load(front_text)
    except yaml.YAMLError:
        return None
    return parsed if isinstance(parsed, dict) else None


def materialize_skillpack(repo_root: Path, arm: SkillpackArm) -> ProcedureBundle:
    """Materialize the exact immutable Skillpack bytes for ``arm``.

    Reads only Git objects for ``arm.commit_sha`` -- never the working tree.
    Performs no network fetch.
    """

    repo_root = Path(repo_root)
    commit = arm.commit_sha

    exists = _git(repo_root, "cat-file", "-e", f"{commit}^{{commit}}")
    if exists.returncode != 0:
        raise FreshSolEvalError(
            "SOURCE_COMMIT_UNAVAILABLE",
            f"commit is not available in the local object database: {commit}",
        )

    listing = _git(repo_root, "ls-tree", "-r", "--name-only", commit, "--", "docs/sol_skills")
    if listing.returncode != 0:
        raise FreshSolEvalError(
            "PROCEDURE_SOURCE_UNAVAILABLE",
            f"could not list docs/sol_skills at {commit}",
        )
    paths = sorted(
        line
        for line in listing.stdout.decode("utf-8", errors="strict").splitlines()
        if line.endswith(".md")
    )
    if "docs/sol_skills/INDEX.md" not in paths:
        raise FreshSolEvalError(
            "PROCEDURE_SOURCE_UNAVAILABLE",
            f"docs/sol_skills/INDEX.md is missing at {commit}",
        )

    sources: list[ProcedureSource] = []
    for path in paths:
        blob = _git(repo_root, "rev-parse", f"{commit}:{path}")
        if blob.returncode != 0:
            raise FreshSolEvalError(
                "PROCEDURE_SOURCE_UNAVAILABLE", f"could not resolve blob for {path} at {commit}"
            )
        blob_sha = blob.stdout.decode("ascii", errors="strict").strip()
        show = _git(repo_root, "show", f"{commit}:{path}")
        if show.returncode != 0:
            raise FreshSolEvalError(
                "PROCEDURE_SOURCE_UNAVAILABLE", f"could not read {path} at {commit}"
            )
        sources.append(ProcedureSource(path=path, blob_sha=blob_sha, content=show.stdout))

    index_source = next(s for s in sources if s.path == "docs/sol_skills/INDEX.md")
    front = _extract_yaml_frontmatter(index_source.content)
    if front is None:
        raise FreshSolEvalError(
            "SKILLPACK_IDENTITY_MISMATCH", "INDEX.md has no readable YAML frontmatter"
        )
    if front.get("schema") != SKILLPACK_SCHEMA:
        raise FreshSolEvalError(
            "SKILLPACK_IDENTITY_MISMATCH",
            f"INDEX.md schema {front.get('schema')!r} != {SKILLPACK_SCHEMA!r}",
        )
    if str(front.get("skillpack_version")) != arm.skillpack_version:
        raise FreshSolEvalError(
            "SKILLPACK_IDENTITY_MISMATCH",
            f"INDEX.md skillpack_version {front.get('skillpack_version')!r} "
            f"!= expected {arm.skillpack_version!r}",
        )
    bootstrap_major = front.get("minimum_bootstrap_major")
    if (
        not isinstance(bootstrap_major, int)
        or isinstance(bootstrap_major, bool)
        or bootstrap_major <= 0
        or bootstrap_major > SUPPORTED_BOOTSTRAP_MAJOR
    ):
        raise FreshSolEvalError(
            "SKILLPACK_IDENTITY_MISMATCH",
            f"INDEX.md minimum_bootstrap_major {bootstrap_major!r} is not "
            f"compatible with supported major {SUPPORTED_BOOTSTRAP_MAJOR}",
        )

    ordered_sources = tuple(sorted(sources, key=lambda item: item.path))
    return ProcedureBundle(
        arm=arm,
        sources=ordered_sources,
        context_sha256=_aggregate_context_sha256(ordered_sources),
    )


# ---------------------------------------------------------------------------
# Scenario protocol parser + neutral procedure wrapper (plan Task 1, Steps 5-6)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScenarioPacket:
    scenario_id: str
    prompt: str
    pass_requires: str


_HEADING_RE = re.compile(r"^##\s+(.*)$")
_PREAMBLE_TITLE = "Shared scenario preamble"
_SCENARIO_TITLE_RE = re.compile(r"^(S2|S6|S7|S8)\s+—\s+\S.*$")
_SCENARIO_ID_PREFIX_RE = re.compile(r"^(S2|S6|S7|S8)\b")
_PASS_REQUIRES_RE = re.compile(r"^PASS requires:\s*(.*)$")


def _split_sections(text: str) -> list[tuple[str, str]]:
    """Return ``[(heading_title, body_text), ...]`` for every ``## `` heading."""

    lines = text.splitlines()
    sections: list[tuple[str, str]] = []
    current_title: str | None = None
    current_body: list[str] = []
    for line in lines:
        match = _HEADING_RE.match(line)
        if match:
            if current_title is not None:
                sections.append((current_title, "\n".join(current_body)))
            current_title = match.group(1).strip()
            current_body = []
        elif current_title is not None:
            current_body.append(line)
    if current_title is not None:
        sections.append((current_title, "\n".join(current_body)))
    return sections


def parse_protocol(path: Path) -> dict[str, ScenarioPacket]:
    """Parse the #147 evidence protocol Markdown into scenario packets.

    Fails closed with ``PROTOCOL_INVALID`` unless there is exactly one shared
    preamble section and exactly one section for each required MAS-136
    scenario, each with a ``PASS requires:`` boundary.  Never reconstructs
    missing wording from a built-in default.
    """

    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise FreshSolEvalError("PROTOCOL_INVALID", f"cannot read protocol file: {exc}") from exc

    sections = _split_sections(text)

    preambles = [body for title, body in sections if title == _PREAMBLE_TITLE]
    if len(preambles) != 1:
        raise FreshSolEvalError(
            "PROTOCOL_INVALID",
            f"expected exactly one {_PREAMBLE_TITLE!r} section, found {len(preambles)}",
        )
    preamble_text = preambles[0].strip("\n")

    by_scenario: dict[str, list[str]] = {scenario_id: [] for scenario_id in MAS136_SCENARIOS}
    for title, body in sections:
        prefix_match = _SCENARIO_ID_PREFIX_RE.match(title)
        if prefix_match is None:
            continue
        scenario_id = prefix_match.group(1)
        if not _SCENARIO_TITLE_RE.match(title):
            raise FreshSolEvalError(
                "PROTOCOL_INVALID", f"malformed scenario heading: {title!r}"
            )
        by_scenario[scenario_id].append(body)

    packets: dict[str, ScenarioPacket] = {}
    for scenario_id in MAS136_SCENARIOS:
        bodies = by_scenario[scenario_id]
        if len(bodies) != 1:
            raise FreshSolEvalError(
                "PROTOCOL_INVALID",
                f"expected exactly one section for {scenario_id}, found {len(bodies)}",
            )
        body = bodies[0]
        body_lines = body.splitlines()
        pass_requires_lines = [
            (idx, m.group(1).strip())
            for idx, line in enumerate(body_lines)
            for m in (_PASS_REQUIRES_RE.match(line.strip()),)
            if m is not None
        ]
        if len(pass_requires_lines) != 1:
            raise FreshSolEvalError(
                "PROTOCOL_INVALID",
                f"expected exactly one 'PASS requires:' line in {scenario_id}, "
                f"found {len(pass_requires_lines)}",
            )
        boundary_idx, pass_requires = pass_requires_lines[0]
        packet_body = "\n".join(body_lines[:boundary_idx]).strip("\n")
        prompt = f"{preamble_text}\n\n{packet_body}"
        if "PASS requires" in prompt:
            raise FreshSolEvalError(
                "PROTOCOL_INVALID",
                f"{scenario_id} prompt unexpectedly retained grading text",
            )
        packets[scenario_id] = ScenarioPacket(
            scenario_id=scenario_id, prompt=prompt, pass_requires=pass_requires
        )
    return packets


_WRAPPER_TEXT = (
    "This is a read-only evaluation of Sol procedure.\n"
    "The exact procedure bundle appended below governs this isolated run.\n"
    "Do not modify external systems.\n"
    "Answer only the supplied scenario in the user turn.\n"
)


def build_eval_agents_md(bundle: ProcedureBundle) -> bytes:
    """Concatenate the fixed neutral wrapper with the exact materialized bytes.

    Arm-neutral: never names Continuation Delta behavior, scenario outcome,
    control/amended expectation, or ``PASS requires``.  The only difference
    between arms is the exact source bytes/paths/blob SHAs themselves.
    """

    parts: list[bytes] = [_WRAPPER_TEXT.encode("utf-8")]
    for source in bundle.sources:
        try:
            decoded = source.content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise FreshSolEvalError(
                "PROCEDURE_SOURCE_UNAVAILABLE",
                f"{source.path} is not valid UTF-8: {exc}",
            ) from exc
        parts.append(
            (
                f"\n----- BEGIN {source.path} @ {source.blob_sha} -----\n"
                f"{decoded}"
                f"\n----- END {source.path} -----\n"
            ).encode("utf-8")
        )
    return b"".join(parts)


# ---------------------------------------------------------------------------
# Fresh process/thread execution + capability attestation (plan Task 2)
# ---------------------------------------------------------------------------


class EvalClient(Protocol):
    """The narrow subset of ``AppServerClient`` that ``run_one`` depends on.

    Tests inject a fake implementing exactly this surface -- see
    ``tests/test_fresh_sol_eval.py::_FakeEvalClient`` -- so unit coverage
    never spawns a subprocess or talks to a provider.
    """

    pid: int | None
    cwd: Path
    notifications: list[dict[str, object]]

    def start(self) -> None: ...

    def request(
        self, method: str, params: dict[str, object] | None = None, timeout: float = 15.0
    ) -> dict[str, object]: ...

    def notify(self, method: str, params: dict[str, object] | None = None) -> None: ...

    def wait_notification(self, method: str, *, timeout: float = 15.0) -> dict[str, object]: ...

    def terminate(self) -> object: ...


ClientFactory = Callable[[Path, Path, Path], "EvalClient"]


@dataclass(frozen=True)
class CapabilityReceipt:
    requested_model: str
    served_model: str
    approval_policy: str
    sandbox_mode: str
    mcp_names: tuple[str, ...]
    plugin_names: tuple[str, ...]
    skill_names: tuple[str, ...]
    auth_type: str
    plan_type: str
    requires_openai_auth: bool | None
    harness_version: str


@dataclass(frozen=True)
class CleanupReceipt:
    controller_returncode: int | None
    private_group_id: int | None
    private_group_empty: bool
    termination_outcome: str


@dataclass(frozen=True)
class RunObservation:
    run_id: str
    arm: str
    scenario_id: str
    workspace: Path
    process_pid: int
    process_pgid: int | None
    process_start_identity: str
    native_thread_id: str
    prompt: str
    output: str
    started_at: str
    completed_at: str
    capability: CapabilityReceipt
    cleanup: CleanupReceipt


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _write_minimal_config(config_path: Path, *, model: str) -> None:
    """Minimal-surface config floor from design §8: no MCP, no bundled skills."""

    config_path.write_text(
        "\n".join(
            [
                f'model = "{model}"',
                'approval_policy = "never"',
                'sandbox_mode = "read-only"',
                "",
                "[features]",
                "apps = false",
                "",
                "[skills.bundled]",
                "enabled = false",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _prepare_run_root(run_root: Path, *, agents_md: bytes, model: str) -> tuple[Path, Path, Path]:
    """Create the fresh, unique (workspace, config, home) triad for one run.

    ``workspace`` deliberately holds only the generated ``AGENTS.md`` and is
    never a Git checkout -- it is not the ``repo_root`` used for Skillpack
    materialization.
    """

    run_root = Path(run_root)
    workspace = run_root / "workspace"
    config_dir = run_root / "config"
    home = run_root / "home"
    for directory in (workspace, config_dir, home):
        directory.mkdir(parents=True, exist_ok=True)
    (workspace / "AGENTS.md").write_bytes(agents_md)
    _write_minimal_config(config_dir / "config.toml", model=model)
    return workspace, config_dir, home


def _assert_empty_capability_surface(names: tuple[str, ...], *, label: str) -> None:
    """Fail closed on any observed name; reuses the P1A classifier, no second one."""

    classification = classify_observed(names, required=(), allowed_ambient=(), forbidden=())
    decision = launch_decision(classification, fail_closed_unclassified=True)
    if decision != LAUNCH_OK:
        raise FreshSolEvalError(
            "CAPABILITY_ATTESTATION_INVALID",
            f"unexpected {label} present: {sorted(names)}",
        )


def _attest_capability(
    client: "EvalClient", *, requested_model: str, harness_version: str
) -> CapabilityReceipt:
    """Query and validate the effective model/config/capability surface.

    Every check here runs before ``thread/start``.  Any RPC failure or
    ambiguous/missing observation is treated as
    ``CAPABILITY_ATTESTATION_INVALID`` rather than silently passing.
    """

    try:
        account_raw = client.request("account/read", {"refreshToken": False})
    except Exception as exc:  # noqa: BLE001 - any transport failure invalidates the run
        raise FreshSolEvalError(
            "CAPABILITY_ATTESTATION_INVALID", f"account/read was unavailable: {exc}"
        ) from exc
    parsed_account = parse_account_read(account_raw)

    try:
        config_raw = client.request("config/read", {"includeLayers": False})
    except Exception as exc:  # noqa: BLE001
        raise FreshSolEvalError(
            "CAPABILITY_ATTESTATION_INVALID", f"config/read was unavailable: {exc}"
        ) from exc
    config_obj = parse_config_read(config_raw)
    if "model" not in config_obj:
        raise FreshSolEvalError(
            "CAPABILITY_ATTESTATION_INVALID", "config/read did not report an observed model"
        )
    served_model = str(config_obj.get("model") or "")
    if served_model != requested_model:
        raise FreshSolEvalError(
            "SERVED_MODEL_MISMATCH",
            f"served model {served_model!r} != requested {requested_model!r}",
        )

    approval_policy = str(config_obj.get("approval_policy") or config_obj.get("approvalPolicy") or "")
    if approval_policy != "never":
        raise FreshSolEvalError(
            "CAPABILITY_ATTESTATION_INVALID", f"approval_policy {approval_policy!r} != 'never'"
        )

    sandbox_mode = str(config_obj.get("sandbox_mode") or config_obj.get("sandboxMode") or "")
    if sandbox_mode != "read-only":
        raise FreshSolEvalError(
            "CAPABILITY_ATTESTATION_INVALID", f"sandbox_mode {sandbox_mode!r} != 'read-only'"
        )

    mcp_cfg = tuple(config_mcp_names(config_obj))
    plugin_cfg = tuple(config_plugin_names(config_obj))

    try:
        skills_raw = client.request("skills/list", skills_list_params(str(client.cwd)))
    except Exception as exc:  # noqa: BLE001
        raise FreshSolEvalError(
            "CAPABILITY_ATTESTATION_INVALID", f"skills/list was unavailable: {exc}"
        ) from exc
    discovered_skills = tuple(skill_names(skills_raw))

    try:
        mcp_status_raw = client.request("mcpServerStatus/list", {"detail": "toolsAndAuthOnly"})
    except Exception as exc:  # noqa: BLE001
        raise FreshSolEvalError(
            "CAPABILITY_ATTESTATION_INVALID", f"mcpServerStatus/list was unavailable: {exc}"
        ) from exc
    mcp_observed = tuple(
        str(row.get("name"))
        for row in (mcp_status_raw.get("data") or [])
        if isinstance(row, dict) and row.get("name")
    )

    mcp_all = tuple(sorted(set(mcp_cfg) | set(mcp_observed)))
    _assert_empty_capability_surface(mcp_all, label="MCP server")
    _assert_empty_capability_surface(plugin_cfg, label="plugin")
    _assert_empty_capability_surface(discovered_skills, label="model-visible skill")

    return CapabilityReceipt(
        requested_model=requested_model,
        served_model=served_model,
        approval_policy=approval_policy,
        sandbox_mode=sandbox_mode,
        mcp_names=mcp_all,
        plugin_names=plugin_cfg,
        skill_names=discovered_skills,
        auth_type=parsed_account["auth_type"],
        plan_type=parsed_account["plan_type"],
        requires_openai_auth=parsed_account["requires_openai_auth"],
        harness_version=harness_version,
    )


def _thread_id_from(result: dict[str, Any]) -> str:
    thread = result.get("thread") if isinstance(result, dict) else None
    if isinstance(thread, dict):
        return str(thread.get("id") or "")
    return ""


def _extract_final_output(read_result: dict[str, Any], *, thread_id: str) -> str:
    """Extract the one unambiguous final assistant text from a canonical read.

    Never reconstructs an answer from notification fragments.  If the
    canonical thread does not contain exactly one discoverable text, this
    fails closed with ``THREAD_READ_FAILED``.
    """

    turns = thread_turns(read_result)
    if not turns:
        raise FreshSolEvalError(
            "THREAD_READ_FAILED", f"thread/read returned no turns for thread {thread_id}"
        )
    last_turn = turns[-1]
    text = last_turn.get("text")
    if isinstance(text, str) and text.strip():
        return text
    item_texts: list[str] = []
    for item in last_turn.get("items") or []:
        if (
            isinstance(item, dict)
            and item.get("type") in ("agentMessage", "agent_message")
            and item.get("text")
        ):
            item_texts.append(str(item["text"]))
    unique_texts = sorted(set(item_texts))
    if len(unique_texts) == 1:
        return unique_texts[0]
    raise FreshSolEvalError(
        "THREAD_READ_FAILED",
        f"thread/read did not produce one unambiguous final assistant text for {thread_id} "
        f"(candidates={unique_texts!r})",
    )


def _terminate_and_prove(client: "EvalClient") -> CleanupReceipt:
    outcome = client.terminate()
    if isinstance(outcome, AppServerStopProof):
        if not outcome.private_group_empty:
            raise FreshSolEvalError(
                "CLEANUP_UNPROVEN", "process group was not proven empty after termination"
            )
        return CleanupReceipt(
            controller_returncode=outcome.controller_returncode,
            private_group_id=outcome.private_group_id,
            private_group_empty=outcome.private_group_empty,
            termination_outcome=outcome.termination_outcome,
        )
    if isinstance(outcome, CleanupReceipt):
        if not outcome.private_group_empty:
            raise FreshSolEvalError(
                "CLEANUP_UNPROVEN", "cleanup receipt reported a non-empty process group"
            )
        return outcome
    raise FreshSolEvalError(
        "CLEANUP_UNPROVEN", f"terminate() returned an unrecognized cleanup proof: {outcome!r}"
    )


def run_one(
    *,
    repo_root: Path,
    arm: SkillpackArm,
    scenario: ScenarioPacket,
    run_root: Path,
    client_factory: "ClientFactory",
    harness_kind: str = "codex-app-server",
    harness_version: str = "unknown",
) -> RunObservation:
    """Execute exactly one fully isolated fresh-Sol evaluation sample.

    Fresh workspace, fresh App Server process/private group, exactly one
    ``thread/start`` (never ``resume``/``fork``), exactly one scenario turn,
    canonical thread read, proven cleanup.  Raises ``FreshSolEvalError`` with
    a closed failure code on any isolation/evidence law violation.
    """

    del harness_kind  # recorded by the caller into evidence; not used to branch here
    run_id = uuid.uuid4().hex
    started_at = _utc_now()

    bundle = materialize_skillpack(repo_root, arm)
    agents_md = build_eval_agents_md(bundle)
    workspace, config_dir, home = _prepare_run_root(run_root, agents_md=agents_md, model=REQUIRED_MODEL)

    client = client_factory(workspace, config_dir, home)
    client.start()
    if client.pid is None:
        raise FreshSolEvalError(
            "HARNESS_INITIALIZE_FAILED", "app-server process did not report a pid"
        )

    try:
        client.request(
            "initialize",
            {"clientInfo": CLIENT_INFO, "capabilities": {"experimentalApi": True}},
        )
    except Exception as exc:  # noqa: BLE001
        raise FreshSolEvalError("HARNESS_INITIALIZE_FAILED", f"initialize failed: {exc}") from exc
    client.notify("initialized", {})

    capability = _attest_capability(
        client, requested_model=REQUIRED_MODEL, harness_version=harness_version
    )

    try:
        started = client.request(
            "thread/start",
            {
                "model": REQUIRED_MODEL,
                "cwd": str(workspace),
                "approvalPolicy": "never",
                "sandbox": "read-only",
            },
        )
    except Exception as exc:  # noqa: BLE001
        raise FreshSolEvalError("THREAD_START_FAILED", f"thread/start failed: {exc}") from exc
    thread_id = _thread_id_from(started)
    if not thread_id:
        raise FreshSolEvalError(
            "THREAD_START_FAILED", "thread/start did not return a native thread id"
        )

    try:
        client.request(
            "turn/start",
            {
                "threadId": thread_id,
                "input": [{"type": "text", "text": scenario.prompt}],
                "cwd": str(workspace),
                "approvalPolicy": "never",
            },
            timeout=60.0,
        )
        client.wait_notification("turn/completed", timeout=60.0)
    except Exception as exc:  # noqa: BLE001
        raise FreshSolEvalError(
            "TURN_EFFECT_UNKNOWN",
            f"the scenario turn dispatch/completion is effect-unknown: {exc}",
        ) from exc

    try:
        read_result = client.request("thread/read", {"threadId": thread_id, "includeTurns": True})
    except Exception as exc:  # noqa: BLE001
        raise FreshSolEvalError("THREAD_READ_FAILED", f"thread/read failed: {exc}") from exc
    output = _extract_final_output(read_result, thread_id=thread_id)

    completed_at = _utc_now()
    cleanup = _terminate_and_prove(client)

    process_pid = client.pid
    assert process_pid is not None
    return RunObservation(
        run_id=run_id,
        arm=arm.name,
        scenario_id=scenario.scenario_id,
        workspace=workspace,
        process_pid=process_pid,
        process_pgid=cleanup.private_group_id,
        process_start_identity=f"{process_pid}:{cleanup.private_group_id}:{run_id}",
        native_thread_id=thread_id,
        prompt=scenario.prompt,
        output=output,
        started_at=started_at,
        completed_at=completed_at,
        capability=capability,
        cleanup=cleanup,
    )


# ---------------------------------------------------------------------------
# Live App Server client factory (plan Task 2, Steps 3-5)
#
# Exercised only by the CLI (Task 3) against a real ``codex`` binary; unit
# tests never call the returned factory's ``request``/``terminate`` -- they
# inject ``_FakeEvalClient`` into ``run_one`` directly instead.
# ---------------------------------------------------------------------------


def build_live_client_factory(
    *, codex_home: Path, model: str, codex_binary: str | None = None
) -> "ClientFactory":
    """Build a ``ClientFactory`` bound to one dedicated, independently
    authenticated, non-default Codex realm.

    Validates the realm eagerly (fails closed on the implicit ``~/.codex``
    default or a missing ``auth.json`` marker) without ever opening,
    reading, copying, or serializing credential bytes -- see
    ``scripts.ohf.laboratory.validate_live_codex_home``, reused verbatim.

    Does not mutate ``codex_home``'s persistent ``config.toml``: the minimal
    surface (model/approval/sandbox/no-MCP/no-bundled-skills) is applied as
    ``-c`` App Server CLI overrides layered on top of the dedicated realm's
    own configuration, never written into it.
    """

    codex_home = Path(codex_home).expanduser().resolve()
    try:
        validate_live_codex_home(codex_home)
    except RuntimeError as exc:
        raise FreshSolEvalError("AUTH_REALM_INVALID", str(exc)) from exc

    def factory(workspace: Path, config_dir: Path, home: Path) -> "EvalClient":
        exe = codex_binary or shutil.which("codex")
        if not exe:
            raise FreshSolEvalError("HARNESS_BINARY_UNAVAILABLE", "codex CLI is not installed")
        del config_dir  # the dedicated realm's own config.toml is not overwritten
        argv = [
            exe,
            "app-server",
            "-c",
            f'model="{model}"',
            "-c",
            'approval_policy="never"',
            "-c",
            'sandbox_mode="read-only"',
            "-c",
            "features.apps=false",
            "-c",
            "skills.bundled.enabled=false",
        ]
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(home),
            "CODEX_HOME": str(codex_home),
            "PYTHONPATH": str(REPO_ROOT),
            "LC_ALL": "C",
        }
        return AppServerClient(argv, env=env, cwd=workspace, start_new_session=True)

    return factory


# ---------------------------------------------------------------------------
# Create-only evidence + MAS-136 matrix + CLI (plan Task 3)
# ---------------------------------------------------------------------------

_EVIDENCE_METADATA_KEYS = (
    "schema",
    "scenario_id",
    "arm",
    "run_id",
    "procedure_commit_sha",
    "expected_skillpack_version",
    "procedure_source_blobs",
    "procedure_context_sha256",
    "protocol_sha256",
    "prompt_sha256",
    "model_requested",
    "model_served",
    "harness_kind",
    "harness_version",
    "harness_binary_sha256",
    "provider_auth_type",
    "provider_plan_type",
    "requires_openai_auth",
    "process_pid",
    "process_pgid",
    "process_start_identity",
    "native_thread_id",
    "started_at",
    "completed_at",
    "cleanup_proof",
    "manual_classification",
)


def _cleanup_proof_text(cleanup: CleanupReceipt) -> str:
    return f"{cleanup.termination_outcome}/private_group_empty={cleanup.private_group_empty}"


def _evidence_metadata(
    *,
    observation: RunObservation,
    bundle: ProcedureBundle,
    protocol_sha256: str,
    prompt_sha256: str,
    harness_kind: str,
    harness_binary_sha256: str,
) -> dict[str, Any]:
    values = {
        "schema": RUN_SCHEMA,
        "scenario_id": observation.scenario_id,
        "arm": observation.arm,
        "run_id": observation.run_id,
        "procedure_commit_sha": bundle.arm.commit_sha,
        "expected_skillpack_version": bundle.arm.skillpack_version,
        "procedure_source_blobs": [f"{s.path}@{s.blob_sha}" for s in bundle.sources],
        "procedure_context_sha256": bundle.context_sha256,
        "protocol_sha256": protocol_sha256,
        "prompt_sha256": prompt_sha256,
        "model_requested": observation.capability.requested_model,
        "model_served": observation.capability.served_model,
        "harness_kind": harness_kind,
        "harness_version": observation.capability.harness_version,
        "harness_binary_sha256": harness_binary_sha256,
        "provider_auth_type": observation.capability.auth_type,
        "provider_plan_type": observation.capability.plan_type,
        "requires_openai_auth": observation.capability.requires_openai_auth,
        "process_pid": observation.process_pid,
        "process_pgid": observation.process_pgid,
        "process_start_identity": observation.process_start_identity,
        "native_thread_id": observation.native_thread_id,
        "started_at": observation.started_at,
        "completed_at": observation.completed_at,
        "cleanup_proof": _cleanup_proof_text(observation.cleanup),
        "manual_classification": "PENDING_SOL_REVIEW",
    }
    return {key: values[key] for key in _EVIDENCE_METADATA_KEYS}


def _manifest_path(evidence_root: Path) -> Path:
    return Path(evidence_root) / "MANIFEST.json"


def _load_manifest(manifest_path: Path) -> dict[str, Any]:
    if not manifest_path.is_file():
        return {"schema": MANIFEST_SCHEMA, "entries": []}
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, indent=2, sort_keys=False) + "\n")
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def _record_manifest_entry(
    evidence_root: Path,
    *,
    run_id: str,
    arm: str,
    scenario_id: str,
    relative_path: str,
    artifact_sha256: str,
) -> None:
    manifest_path = _manifest_path(evidence_root)
    manifest = _load_manifest(manifest_path)
    entries = [e for e in (manifest.get("entries") or []) if e.get("run_id") != run_id]
    entries.append(
        {
            "run_id": run_id,
            "arm": arm,
            "scenario_id": scenario_id,
            "relative_path": relative_path,
            "artifact_sha256": artifact_sha256,
        }
    )
    entries.sort(key=lambda e: (str(e["arm"]), str(e["scenario_id"]), str(e["run_id"])))
    _atomic_write_json(manifest_path, {"schema": MANIFEST_SCHEMA, "entries": entries})


def write_run_artifact(
    *,
    observation: RunObservation,
    bundle: ProcedureBundle,
    protocol_sha256: str,
    harness_kind: str,
    harness_binary_sha256: str,
    evidence_root: Path,
) -> Path:
    """Persist one run as a create-only Markdown evidence artifact.

    Refuses (``EVIDENCE_SECRET_SHAPE_REFUSED``) without writing anything if
    the exact prompt or output trips the existing repository secret-shape
    detector.  Refuses (``EVIDENCE_COLLISION``) without touching the
    existing bytes if the deterministic target path already exists.  Also
    updates the atomic ``MANIFEST.json`` bookkeeping index.
    """

    if evidence_contains_secret(observation.prompt) or evidence_contains_secret(observation.output):
        raise FreshSolEvalError(
            "EVIDENCE_SECRET_SHAPE_REFUSED",
            f"run {observation.run_id} tripped the secret-shape detector; rerun fresh",
        )

    evidence_root = Path(evidence_root)
    target = evidence_root / "runs" / observation.arm / observation.scenario_id / f"{observation.run_id}.md"
    target.parent.mkdir(parents=True, exist_ok=True)

    prompt_sha256 = hashlib.sha256(observation.prompt.encode("utf-8")).hexdigest()
    metadata = _evidence_metadata(
        observation=observation,
        bundle=bundle,
        protocol_sha256=protocol_sha256,
        prompt_sha256=prompt_sha256,
        harness_kind=harness_kind,
        harness_binary_sha256=harness_binary_sha256,
    )
    front = yaml.safe_dump(metadata, sort_keys=False, default_flow_style=False, allow_unicode=True)
    content = (
        f"---\n{front}---\n\n"
        "## Exact prompt\n\n```text\n" + observation.prompt + "\n```\n\n"
        "## Exact model output\n\n```text\n" + observation.output + "\n```\n"
    )

    try:
        with open(target, "x", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
    except FileExistsError as exc:
        raise FreshSolEvalError(
            "EVIDENCE_COLLISION", f"evidence artifact already exists: {target}"
        ) from exc

    artifact_sha256 = hashlib.sha256(target.read_bytes()).hexdigest()
    _record_manifest_entry(
        evidence_root,
        run_id=observation.run_id,
        arm=observation.arm,
        scenario_id=observation.scenario_id,
        relative_path=target.relative_to(evidence_root).as_posix(),
        artifact_sha256=artifact_sha256,
    )
    return target


def _mas136_sample_plan() -> list[tuple[str, str, int]]:
    """Deterministic 4-control + 12-amended plan grouped by scenario."""

    plan: list[tuple[str, str, int]] = []
    for scenario_id in MAS136_SCENARIOS:
        plan.append(("control-1.0.0", scenario_id, 1))
        for sample_index in (1, 2, 3):
            plan.append(("amended-1.1.0", scenario_id, sample_index))
    return plan


def _verify_and_count_resume(evidence_root: Path, resume_manifest: Path) -> dict[tuple[str, str], int]:
    """Verify every resumed entry's bytes against its recorded digest.

    A missing or mismatched artifact refuses the whole resume attempt as
    ``EVIDENCE_COLLISION`` rather than silently rerunning that sample.
    """

    payload = json.loads(Path(resume_manifest).read_text(encoding="utf-8"))
    counts: dict[tuple[str, str], int] = {}
    for entry in payload.get("entries") or []:
        relative_path = str(entry.get("relative_path") or "")
        artifact_path = Path(evidence_root) / relative_path
        if not artifact_path.is_file():
            raise FreshSolEvalError(
                "EVIDENCE_COLLISION",
                f"resume manifest entry is missing on disk: {relative_path}",
            )
        actual_sha256 = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        if actual_sha256 != entry.get("artifact_sha256"):
            raise FreshSolEvalError(
                "EVIDENCE_COLLISION",
                f"resume manifest entry digest mismatch: {relative_path}",
            )
        key = (str(entry.get("arm")), str(entry.get("scenario_id")))
        counts[key] = counts.get(key, 0) + 1
    return counts


def run_matrix(
    *,
    repo_root: Path,
    protocol_path: Path,
    evidence_root: Path,
    client_factory: "ClientFactory",
    run_root_parent: Path,
    mode: str = "mas-136",
    resume_manifest: Path | None = None,
    harness_kind: str = "codex-app-server",
    harness_version: str = "unknown",
    harness_binary_sha256: str = "",
) -> list[Path]:
    """Run the fixed MAS-136 sample plan.  A convenience wrapper, not a scheduler.

    A failed/invalid sample stops the matrix immediately (no automatic
    retry).  ``resume_manifest`` is the only skip path, and only for
    entries whose artifact bytes still match the manifest exactly.
    """

    if mode != "mas-136":
        raise ValueError(f"unsupported run-matrix mode: {mode!r}")

    plan = _mas136_sample_plan()
    assert len(plan) == 16

    scenarios = parse_protocol(protocol_path)
    protocol_sha256 = hashlib.sha256(Path(protocol_path).read_bytes()).hexdigest()

    skip_counts: dict[tuple[str, str], int] = {}
    if resume_manifest is not None:
        skip_counts = _verify_and_count_resume(evidence_root, resume_manifest)

    consumed: dict[tuple[str, str], int] = {}
    written: list[Path] = []
    for arm_key, scenario_id, _sample_index in plan:
        key = (arm_key, scenario_id)
        consumed[key] = consumed.get(key, 0) + 1
        if consumed[key] <= skip_counts.get(key, 0):
            continue

        arm = MAS136_ARMS[arm_key]
        scenario = scenarios[scenario_id]
        bundle = materialize_skillpack(repo_root, arm)
        run_root = Path(run_root_parent) / f"{arm_key}-{scenario_id}-{uuid.uuid4().hex[:8]}"
        observation = run_one(
            repo_root=repo_root,
            arm=arm,
            scenario=scenario,
            run_root=run_root,
            client_factory=client_factory,
            harness_kind=harness_kind,
            harness_version=harness_version,
        )
        artifact = write_run_artifact(
            observation=observation,
            bundle=bundle,
            protocol_sha256=protocol_sha256,
            harness_kind=harness_kind,
            harness_binary_sha256=harness_binary_sha256,
            evidence_root=evidence_root,
        )
        written.append(artifact)
    return written


def _mas136_expected_counts() -> dict[tuple[str, str], int]:
    expected: dict[tuple[str, str], int] = {}
    for scenario_id in MAS136_SCENARIOS:
        expected[("control-1.0.0", scenario_id)] = 1
        expected[("amended-1.1.0", scenario_id)] = 3
    return expected


def check_corpus(*, evidence_root: Path, mode: str = "mas-136") -> dict[str, Any]:
    """Verify identity/cardinality/digest/cleanup completeness only.

    Never behavioral-grades outputs -- that stays Sol's job.
    """

    if mode != "mas-136":
        raise ValueError(f"unsupported check-corpus mode: {mode!r}")

    evidence_root = Path(evidence_root)
    manifest_path = _manifest_path(evidence_root)
    if not manifest_path.is_file():
        return {
            "ok": False,
            "valid_count": 0,
            "expected": 16,
            "cardinality_ok": False,
            "problems": ["MANIFEST_MISSING"],
        }

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    problems: list[str] = []
    counts: dict[tuple[str, str], int] = {}
    for entry in manifest.get("entries") or []:
        relative_path = str(entry.get("relative_path") or "")
        artifact_path = evidence_root / relative_path
        if not artifact_path.is_file():
            problems.append(f"missing artifact: {relative_path}")
            continue
        actual_sha256 = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        if actual_sha256 != entry.get("artifact_sha256"):
            problems.append(f"digest mismatch: {relative_path}")
            continue
        metadata = _extract_yaml_frontmatter(artifact_path.read_bytes())
        cleanup_proof = str((metadata or {}).get("cleanup_proof") or "")
        if "private_group_empty=True" not in cleanup_proof:
            problems.append(f"cleanup not proven: {relative_path}")
            continue
        key = (str(entry.get("arm")), str(entry.get("scenario_id")))
        counts[key] = counts.get(key, 0) + 1

    expected_counts = _mas136_expected_counts()
    cardinality_ok = counts == expected_counts and not problems
    valid_count = sum(counts.values())
    return {
        "ok": cardinality_ok,
        "valid_count": valid_count,
        "expected": 16,
        "cardinality_ok": cardinality_ok,
        "problems": problems,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fresh_sol_eval",
        description="Fresh-Sol evaluation harness F0 (EVAL-OHF1) -- production-inert.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_one_p = sub.add_parser("run-one", help="Run exactly one isolated sample.")
    run_one_p.add_argument("--repo-root", required=True, type=Path)
    run_one_p.add_argument("--protocol-path", required=True, type=Path)
    run_one_p.add_argument("--codex-home", required=True, type=Path)
    run_one_p.add_argument("--evidence-root", required=True, type=Path)
    run_one_p.add_argument("--arm", required=True, choices=sorted(MAS136_ARMS))
    run_one_p.add_argument("--scenario", required=True, choices=list(MAS136_SCENARIOS))

    run_matrix_p = sub.add_parser("run-matrix", help="Run the fixed MAS-136 sample plan.")
    run_matrix_p.add_argument("--repo-root", required=True, type=Path)
    run_matrix_p.add_argument("--protocol-path", required=True, type=Path)
    run_matrix_p.add_argument("--codex-home", required=True, type=Path)
    run_matrix_p.add_argument("--evidence-root", required=True, type=Path)
    run_matrix_p.add_argument("--mode", default="mas-136", choices=["mas-136"])
    run_matrix_p.add_argument("--resume-manifest", type=Path, default=None)

    check_corpus_p = sub.add_parser("check-corpus", help="Verify corpus identity/cardinality/digest/cleanup.")
    check_corpus_p.add_argument("--evidence-root", required=True, type=Path)
    check_corpus_p.add_argument("--mode", default="mas-136", choices=["mas-136"])

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "run-one":
            arm = MAS136_ARMS[args.arm]
            scenarios = parse_protocol(args.protocol_path)
            scenario = scenarios[args.scenario]
            bundle = materialize_skillpack(args.repo_root, arm)
            protocol_sha256 = hashlib.sha256(Path(args.protocol_path).read_bytes()).hexdigest()
            harness_binary_sha256 = binary_digest(shutil.which("codex"))
            client_factory = build_live_client_factory(codex_home=args.codex_home, model=REQUIRED_MODEL)
            with tempfile.TemporaryDirectory(prefix="fresh-sol-eval-") as tmp:
                observation = run_one(
                    repo_root=args.repo_root,
                    arm=arm,
                    scenario=scenario,
                    run_root=Path(tmp),
                    client_factory=client_factory,
                    harness_version=harness_binary_sha256[:12] or "unknown",
                )
                artifact = write_run_artifact(
                    observation=observation,
                    bundle=bundle,
                    protocol_sha256=protocol_sha256,
                    harness_kind="codex-app-server",
                    harness_binary_sha256=harness_binary_sha256,
                    evidence_root=args.evidence_root,
                )
            print(str(artifact))
            return 0

        if args.command == "run-matrix":
            harness_binary_sha256 = binary_digest(shutil.which("codex"))
            client_factory = build_live_client_factory(codex_home=args.codex_home, model=REQUIRED_MODEL)
            with tempfile.TemporaryDirectory(prefix="fresh-sol-eval-matrix-") as tmp:
                written = run_matrix(
                    repo_root=args.repo_root,
                    protocol_path=args.protocol_path,
                    evidence_root=args.evidence_root,
                    client_factory=client_factory,
                    run_root_parent=Path(tmp),
                    mode=args.mode,
                    resume_manifest=args.resume_manifest,
                    harness_binary_sha256=harness_binary_sha256,
                )
            for path in written:
                print(str(path))
            return 0

        if args.command == "check-corpus":
            result = check_corpus(evidence_root=args.evidence_root, mode=args.mode)
            print(json.dumps(result, indent=2))
            return 0 if result["ok"] else 1
    except FreshSolEvalError as exc:
        print(f"::error title={exc.code}::{exc}", flush=True)
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

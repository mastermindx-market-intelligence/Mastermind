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

import hashlib
import os
import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

import yaml

from scripts.ohf.laboratory import AppServerClient, AppServerStopProof, validate_live_codex_home
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

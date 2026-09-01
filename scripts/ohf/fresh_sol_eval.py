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
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

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

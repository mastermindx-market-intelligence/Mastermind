"""EVAL-R0 create-only artifact store (design §8.3/§8.4, plan Task 6).

Persists immutable JSON under a private, trusted root using the globally
resolvable safe-path law (design §8.3): a canonical ID maps directly to one
schema-derived filesystem path, with no mutable index and no repository-wide
search. Publication is create-only: shape-validate, secret-scan
(``scripts.agent_eval.privacy``, never ``scripts.ohf.redaction`` or
``common.redaction`` per the environment-free amendment), graph-verify,
write to a same-directory private temp file, hard-link-publish, fsync,
read back, and re-verify. Existing identical bytes are idempotent; existing
different bytes are a conflict. The root is private and trusted -- R0 does
not claim defense against a hostile same-user process racing directory
replacement between our own checks and our own writes.
"""
from __future__ import annotations

import enum
import json
import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from scripts.agent_eval import MAX_CANONICAL_ARTIFACT_BYTES, contracts, scoring
from scripts.agent_eval.canonical import canonical_json_bytes
from scripts.agent_eval.errors import ArtifactConflictError, ContractDefect, ContractError, VerificationContextError
from scripts.agent_eval.privacy import assert_public_safe_evidence
from scripts.agent_eval.verification import (
    VerificationResult,
    verify_configuration_graph,
    verify_experiment_graph,
    verify_run_graph,
    verify_scenario_graph,
)
from scripts.agent_eval.scoring import verify_evidence_ref_graph, verify_scorer_pass_graph

_DEVICE_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}
)
_MAX_SEGMENT_LEN = 255


class WriteDisposition(enum.Enum):
    CREATED = "CREATED"
    IDEMPOTENT = "IDEMPOTENT"


@dataclass(frozen=True)
class WriteResult:
    disposition: WriteDisposition
    path: str
    artifact_id: str
    artifact_digest: str


_DIGEST_FIELD_BY_SCHEMA = {
    contracts.SCENARIO_SCHEMA: "scenario_digest",
    contracts.CONFIGURATION_SCHEMA: "configuration_digest",
    contracts.EXPERIMENT_SCHEMA: "experiment_digest",
    contracts.RUN_SCHEMA: "run_digest",
    scoring.SCORER_PASS_SCHEMA: "scorer_pass_digest",
    scoring.EVIDENCE_REF_SCHEMA: "evidence_ref_digest",
}

_ARTIFACT_FILENAME_BY_TOP = {
    "scenarios": "scenario.json",
    "configurations": "configuration.json",
    "experiments": "manifest.json",
    "runs": "receipt.json",
    "scorer-passes": "scorer-pass.json",
    "evidence-refs": "evidence-ref.json",
}


def _validate_path_segment(segment: str, path: str = "$") -> None:
    if not segment:
        raise ContractError([ContractDefect(path, "EMPTY_PATH_SEGMENT", "path segment must not be empty")])
    if len(segment) > _MAX_SEGMENT_LEN:
        raise ContractError([ContractDefect(path, "OVERSIZED_PATH_SEGMENT", "path segment exceeds the maximum length")])
    if "/" in segment or "\\" in segment:
        raise ContractError([ContractDefect(path, "PATH_SEGMENT_HAS_SEPARATOR", "path segment must not contain / or \\")])
    if segment in (".", ".."):
        raise ContractError([ContractDefect(path, "PATH_SEGMENT_IS_DOT", "path segment must not be . or ..")])
    if any(ord(char) < 0x20 for char in segment):
        raise ContractError(
            [ContractDefect(path, "PATH_SEGMENT_HAS_CONTROL_CHAR", "path segment must not contain control characters")]
        )
    if segment != segment.rstrip(". "):
        raise ContractError(
            [ContractDefect(path, "PATH_SEGMENT_TRAILING_DOT_OR_SPACE", "path segment must not end with a dot or space")]
        )
    base_name = segment.split(".")[0].upper()
    if base_name in _DEVICE_NAMES:
        raise ContractError(
            [ContractDefect(path, "PATH_SEGMENT_DEVICE_NAME", "path segment must not be a reserved device name")]
        )


def scenario_path(scenario_id: str, scenario_version: int) -> Path:
    family, case = contracts.parse_scenario_id(scenario_id)
    version_segment = f"v{scenario_version}"
    for segment in (family, case, version_segment):
        _validate_path_segment(segment)
    return Path("scenarios") / family / case / version_segment / "scenario.json"


def _uuid_segment(parsed: UUID) -> str:
    segment = str(parsed)
    _validate_path_segment(segment)
    return segment


def configuration_path(configuration_id: str) -> Path:
    return Path("configurations") / _uuid_segment(contracts.parse_configuration_id(configuration_id)) / "configuration.json"


def experiment_path(experiment_id: str) -> Path:
    return Path("experiments") / _uuid_segment(contracts.parse_experiment_id(experiment_id)) / "manifest.json"


def run_path(run_id: str) -> Path:
    return Path("runs") / _uuid_segment(contracts.parse_run_id(run_id)) / "receipt.json"


def scorer_pass_path(scorer_pass_id: str) -> Path:
    return Path("scorer-passes") / _uuid_segment(scoring.parse_scorer_pass_id(scorer_pass_id)) / "scorer-pass.json"


def evidence_ref_path(evidence_ref_id: str) -> Path:
    return Path("evidence-refs") / _uuid_segment(scoring.parse_evidence_ref_id(evidence_ref_id)) / "evidence-ref.json"


def _artifact_path_for(document: dict) -> tuple[str, Path]:
    schema = document.get("schema")
    if schema == contracts.SCENARIO_SCHEMA:
        return document["scenario_id"], scenario_path(document["scenario_id"], document["scenario_version"])
    if schema == contracts.CONFIGURATION_SCHEMA:
        return document["configuration_id"], configuration_path(document["configuration_id"])
    if schema == contracts.EXPERIMENT_SCHEMA:
        return document["experiment_id"], experiment_path(document["experiment_id"])
    if schema == contracts.RUN_SCHEMA:
        return document["run_id"], run_path(document["run_id"])
    if schema == scoring.SCORER_PASS_SCHEMA:
        return document["scorer_pass_id"], scorer_pass_path(document["scorer_pass_id"])
    if schema == scoring.EVIDENCE_REF_SCHEMA:
        return document["evidence_ref_id"], evidence_ref_path(document["evidence_ref_id"])
    raise ContractError([ContractDefect("$.schema", "UNKNOWN_SCHEMA", f"unknown persisted schema {schema!r}")])


def _graph_verify_for(document: dict, resolver) -> VerificationResult:
    schema = document.get("schema")
    if schema == contracts.SCENARIO_SCHEMA:
        return verify_scenario_graph(document, resolver)
    if schema == contracts.CONFIGURATION_SCHEMA:
        return verify_configuration_graph(document, resolver)
    if schema == contracts.EXPERIMENT_SCHEMA:
        return verify_experiment_graph(document, resolver)
    if schema == contracts.RUN_SCHEMA:
        return verify_run_graph(document, resolver)
    if schema == scoring.SCORER_PASS_SCHEMA:
        return verify_scorer_pass_graph(document, resolver)
    if schema == scoring.EVIDENCE_REF_SCHEMA:
        return verify_evidence_ref_graph(document, resolver)
    raise ContractError([ContractDefect("$.schema", "UNKNOWN_SCHEMA", f"unknown persisted schema {schema!r}")])


class ArtifactStore:
    """Create-only, filesystem-backed evaluation-artifact store. Also
    implements :class:`scripts.agent_eval.resolver.ArtifactResolver` (the
    production resolver -- see plan §5.6 resolver boundary; the test-only
    ``MemoryArtifactResolver`` is a separate, narrower implementation under
    ``tests/agent_eval_factories.py``)."""

    def __init__(self, root: str | Path) -> None:
        root_path = Path(root)
        if root_path.exists() and root_path.is_symlink():
            raise ContractError([ContractDefect("$", "ROOT_IS_SYMLINK", "artifact store root must not be a symlink")])
        if not root_path.exists():
            root_path.mkdir(parents=True, exist_ok=False, mode=0o700)
        elif not root_path.is_dir():
            raise ContractError([ContractDefect("$", "ROOT_NOT_A_DIRECTORY", "artifact store root must be a directory")])
        self._root = root_path.resolve(strict=True)

    @property
    def root(self) -> Path:
        return self._root

    # -- internal filesystem safety -----------------------------------

    def _require_no_symlink_parents(self, path: Path) -> None:
        current = self._root
        for part in path.relative_to(self._root).parts[:-1]:
            current = current / part
            if current.exists() and current.is_symlink():
                raise ContractError(
                    [ContractDefect(str(current), "SYMLINK_PARENT_REJECTED", "a parent directory is a symlink")]
                )

    def _resolve_within_root(self, relative_path: str | Path) -> Path:
        relative = Path(relative_path)
        if relative.is_absolute():
            raise ContractError([ContractDefect(str(relative_path), "PATH_MUST_BE_RELATIVE", "path must be relative to the store root")])
        candidate = (self._root / relative).resolve(strict=False)
        try:
            candidate.relative_to(self._root)
        except ValueError as exc:
            raise ContractError(
                [ContractDefect(str(relative_path), "PATH_ESCAPES_ROOT", "path resolves outside the artifact store root")]
            ) from exc
        return candidate

    def _require_regular_readable(self, path: Path) -> None:
        self._require_no_symlink_parents(path)
        if not path.exists():
            raise FileNotFoundError(str(path))
        if path.is_symlink():
            raise ContractError([ContractDefect(str(path), "SYMLINK_ARTIFACT_REJECTED", "artifact path must not be a symlink")])
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode):
            raise ContractError([ContractDefect(str(path), "NONREGULAR_FILE_REJECTED", "artifact path must be a regular file")])
        if info.st_size > MAX_CANONICAL_ARTIFACT_BYTES:
            raise ContractError(
                [ContractDefect(str(path), "ARTIFACT_TOO_LARGE", "stored artifact exceeds the canonical size bound")]
            )

    def _read_bytes_bounded(self, path: Path) -> bytes:
        with open(path, "rb") as handle:
            raw = handle.read(MAX_CANONICAL_ARTIFACT_BYTES + 1)
        if len(raw) > MAX_CANONICAL_ARTIFACT_BYTES:
            raise ContractError(
                [ContractDefect(str(path), "ARTIFACT_TOO_LARGE", "stored artifact exceeds the canonical size bound")]
            )
        return raw

    def _read_json(self, path: Path) -> dict:
        raw = self._read_bytes_bounded(path)
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ContractError([ContractDefect(str(path), "CORRUPT_JSON", "stored artifact is not valid JSON")]) from exc

    def _read_json_if_present(self, relative_path: Path) -> dict | None:
        full_path = self._root / relative_path
        try:
            self._require_regular_readable(full_path)
        except FileNotFoundError:
            return None
        return self._read_json(full_path)

    # -- read (never claims verification) -------------------------------

    def read_shape(self, relative_path: str | Path) -> dict:
        """Read one stored artifact and shape-validate it. Never graph-
        verifies and never claims any stronger scope than SHAPE_VALID."""
        full_path = self._resolve_within_root(relative_path)
        self._require_regular_readable(full_path)
        document = self._read_json(full_path)
        contracts.validate_document_shape(document)
        return document

    # -- ArtifactResolver protocol (production implementation) ----------

    def resolve_scenario(self, scenario_id: str, scenario_version: int) -> dict | None:
        return self._read_json_if_present(scenario_path(scenario_id, scenario_version))

    def resolve_configuration(self, configuration_id: str) -> dict | None:
        return self._read_json_if_present(configuration_path(configuration_id))

    def resolve_experiment(self, experiment_id: str) -> dict | None:
        return self._read_json_if_present(experiment_path(experiment_id))

    def resolve_run(self, run_id: str) -> dict | None:
        return self._read_json_if_present(run_path(run_id))

    def resolve_scorer_pass(self, scorer_pass_id: str) -> dict | None:
        return self._read_json_if_present(scorer_pass_path(scorer_pass_id))

    def resolve_evidence_ref(self, evidence_ref_id: str) -> dict | None:
        return self._read_json_if_present(evidence_ref_path(evidence_ref_id))

    # -- graph verification -----------------------------------------------

    def verify_graph(self, relative_path: str | Path) -> VerificationResult:
        document = self.read_shape(relative_path)
        return _graph_verify_for(document, self)

    def _enumerate_artifact_files(self) -> tuple[Path, ...]:
        found: list[Path] = []
        for top, filename in _ARTIFACT_FILENAME_BY_TOP.items():
            top_dir = self._root / top
            if not top_dir.is_dir() or top_dir.is_symlink():
                continue
            for path in top_dir.rglob(filename):
                if path.is_file() and not path.is_symlink():
                    found.append(path.relative_to(self._root))
        return tuple(sorted(found))

    def verify_tree_graph(self) -> tuple[ContractDefect, ...]:
        """Stateless, deterministic, sorted enumeration of the artifact root;
        validates and graph-verifies every artifact. Never repairs -- only
        reports. Enumeration itself is not canonical identity or an index."""
        defects: list[ContractDefect] = []
        for relative in self._enumerate_artifact_files():
            try:
                self.verify_graph(relative)
            except (ContractError, VerificationContextError) as exc:
                for defect in exc.defects:
                    defects.append(ContractDefect(f"{relative}::{defect.path}", defect.code, defect.message))
        return tuple(sorted(set(defects)))

    # -- deterministic sorted enumeration (plan §5.6 complete-enumeration law) --

    def enumerate_runs(self) -> tuple[dict, ...]:
        runs_dir = self._root / "runs"
        if not runs_dir.is_dir():
            return ()
        documents = [self.read_shape(path.relative_to(self._root)) for path in sorted(runs_dir.rglob("receipt.json"))]
        return tuple(sorted(documents, key=lambda doc: doc["run_id"]))

    def enumerate_scorer_passes(self) -> tuple[dict, ...]:
        passes_dir = self._root / "scorer-passes"
        if not passes_dir.is_dir():
            return ()
        documents = [
            self.read_shape(path.relative_to(self._root)) for path in sorted(passes_dir.rglob("scorer-pass.json"))
        ]
        return tuple(sorted(documents, key=lambda doc: doc["scorer_pass_id"]))

    # -- create-only publication -----------------------------------------

    def create(self, document: dict) -> WriteResult:
        if not isinstance(document, dict):
            raise ContractError([ContractDefect("$", "NOT_A_DOCUMENT", "document must be a JSON object")])
        if document.get("schema") == contracts.RUN_DRAFT_SCHEMA:
            raise ContractError(
                [ContractDefect("$.schema", "DRAFT_SCHEMA_REJECTED", "a draft is never publishable to the artifact store")]
            )

        # 1. shape-validate
        contracts.validate_document_shape(document)
        # 2. secret policy (amendment §4.4 step 2 -- environment-free, reject-only)
        assert_public_safe_evidence(document)
        # exact canonical artifact size bound (plan §5.7), checked on the
        # freshly built canonical bytes before any filesystem write
        canonical_bytes = canonical_json_bytes(document)
        if len(canonical_bytes) > MAX_CANONICAL_ARTIFACT_BYTES:
            raise ContractError([ContractDefect("$", "ARTIFACT_TOO_LARGE", "canonical document exceeds the size bound")])
        # derive the safe path (pure computation; may itself reject a path hazard)
        artifact_id, relative_path = _artifact_path_for(document)
        # 3. graph-verify (read-only; resolves dependencies already published)
        _graph_verify_for(document, self)

        final_path = self._root / relative_path
        self._require_no_symlink_parents(final_path)
        digest_field = _DIGEST_FIELD_BY_SCHEMA[document["schema"]]

        if final_path.exists():
            if final_path.is_symlink() or not stat.S_ISREG(final_path.lstat().st_mode):
                raise ArtifactConflictError(str(final_path), "existing artifact path is not a regular file")
            existing_bytes = self._read_bytes_bounded(final_path)
            if existing_bytes == canonical_bytes:
                return WriteResult(WriteDisposition.IDEMPOTENT, str(relative_path), artifact_id, document[digest_field])
            raise ArtifactConflictError(str(final_path), "existing artifact bytes differ from the proposed document")

        # 4. create-only filesystem publication
        final_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temp_fd, temp_name = tempfile.mkstemp(dir=str(final_path.parent), prefix=".tmp-write-", suffix=".part")
        try:
            os.chmod(temp_name, 0o600)
            with os.fdopen(temp_fd, "wb") as handle:
                handle.write(canonical_bytes)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temp_name, str(final_path))
            except FileExistsError:
                existing_bytes = self._read_bytes_bounded(final_path)
                if existing_bytes != canonical_bytes:
                    raise ArtifactConflictError(str(final_path), "concurrent publish produced different bytes")
                return WriteResult(WriteDisposition.IDEMPOTENT, str(relative_path), artifact_id, document[digest_field])
            except OSError as exc:
                raise ContractError(
                    [ContractDefect(str(final_path), "HARD_LINK_UNSUPPORTED", f"hard-link publish failed: {exc}")]
                ) from exc
            dir_fd = os.open(str(final_path.parent), os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        finally:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass

        # read back and graph-verify the published artifact
        readback = self.read_shape(relative_path)
        if readback != document:
            raise ContractError(
                [ContractDefect(str(final_path), "READBACK_MISMATCH", "read-back artifact does not match the published document")]
            )
        _graph_verify_for(readback, self)

        return WriteResult(WriteDisposition.CREATED, str(relative_path), artifact_id, document[digest_field])

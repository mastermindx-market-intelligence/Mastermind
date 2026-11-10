"""EVAL-C0 governed corpus / holdout governance (additive to EVAL-R0).

Implements the C0 commission's governance layer over the public-safe corpus
tree committed under ``corpus/agent_eval/``:

- **corpus revision derivation**: a deterministic ``sha256`` digest over the
  corpus tree's byte contents (:func:`compute_corpus_tree_digest`), used for
  tamper detection -- distinct from the ``corpus_revision`` field each
  scenario document carries, which is the immutable *source-qualified git
  anchor* the whole corpus wave is pinned to (design §7.1/§6.2);
- **scenario-vs-corpus consistency validation**
  (:func:`verify_corpus_tree_consistency`): every scenario document's
  declared ``corpus_revision`` matches the corpus manifest's anchor,
  ``temporal.cutoff_at`` is present and well-formed (delegated to the
  existing closed scenario contract -- a missing/malformed cutoff is
  already a shape defect there), ``privacy.classification`` is declared
  ``PUBLIC_SAFE`` for every committed public case, every declared
  ``{artifact_ref, digest}`` fixture pair resolves to a real repository
  file whose bytes match the declared digest, and every holdout seal's
  digest is well-formed and its body stays out of the repository;
- a new closed schema for holdout **seals** (:data:`CORPUS_HOLDOUT_SEAL_SCHEMA`)
  -- a digest-only record that declares a held-out case exists, together
  with a documented private-evidence-root delivery contract, without
  publishing the sealed body itself;
- a new closed schema for the **corpus manifest**
  (:data:`CORPUS_MANIFEST_SCHEMA`) -- the single frozen anchor + tree-digest
  record every scenario/holdout in this wave is checked against.

Both new schemas register with the existing generic dispatcher via
``contracts.register_shape_validator`` -- the same additive-extension
mechanism ``verification.py``/``scoring.py`` already use to extend
``contracts.validate_document_shape`` without a circular import or any edit
to ``contracts.py`` itself (plan §5.1, R0 core, unmodified).

Standard library only. No process/network/environment read -- this module
walks exactly the repository paths its caller hands it (``corpus_root`` /
``repo_root``), never an implicit or ambient location.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.agent_eval import MAX_CANONICAL_ARTIFACT_BYTES, contracts, store
from scripts.agent_eval.errors import ContractDefect, ContractError
from scripts.agent_eval.privacy import assert_public_safe_evidence

# ---------------------------------------------------------------------------
# Schema names
# ---------------------------------------------------------------------------

CORPUS_MANIFEST_SCHEMA = "mastermind.agent_evaluation_corpus_manifest.v1"
CORPUS_HOLDOUT_SEAL_SCHEMA = "mastermind.agent_evaluation_corpus_holdout_seal.v1"

_RISK_TIERS = frozenset({"LOW", "MEDIUM", "HIGH", "CRITICAL"})
_SEALING_METHODS = frozenset({"SHA256_OVER_CANONICAL_BUNDLE"})

# MAJOR-3 repair (principal ruling, 2026-09-01): a holdout seal must state
# HONESTLY whether its sealed_body_digest is backed by a real, recoverable
# private body. PROVENANCE_PLACEHOLDER_BODY_UNRECOVERABLE names a seal whose
# body was computed in-memory and then discarded (no private evidence root
# exists yet to receive it) -- the digest is real and was genuinely computed
# over a real bundle at authoring time, but that exact bundle can never be
# re-derived or delivered. SEALED_BODY_DELIVERABLE is reserved for a future
# seal minted once a real private evidence root exists to actually receive
# the body private_evidence_root_ref names. Consumers (EVAL-E1 and later)
# MUST NOT treat a PROVENANCE_PLACEHOLDER_BODY_UNRECOVERABLE seal as usable
# holdout evidence -- it is a governed intent-to-seal record, not delivered
# evidence.
_SEAL_STATUSES = frozenset({"PROVENANCE_PLACEHOLDER_BODY_UNRECOVERABLE", "SEALED_BODY_DELIVERABLE"})

_SCENARIO_FILENAME = "scenario.json"
_HOLDOUT_SEAL_FILENAME = "holdout_seal.json"
_MANIFEST_FILENAME = "corpus_manifest.json"

# ---------------------------------------------------------------------------
# Corpus manifest contract
# ---------------------------------------------------------------------------

_MANIFEST_ENTRY_FIELDS = {
    "relative_path": contracts.v_str,
    "digest": contracts.v_digest,
}


def _v_manifest_entry(value: Any, path: str) -> dict:
    return contracts.validate_closed_object(value, path, _MANIFEST_ENTRY_FIELDS)


def _v_manifest_entries(value: Any, path: str) -> list[dict]:
    items = contracts.v_list_of(_v_manifest_entry)(value, path)
    paths = [item["relative_path"] for item in items]
    defects: list[ContractDefect] = []
    if paths != sorted(paths):
        defects.append(ContractDefect(path, "LIST_NOT_SORTED", "manifest entries must be sorted by relative_path"))
    if len(set(paths)) != len(paths):
        defects.append(ContractDefect(path, "LIST_HAS_DUPLICATES", "manifest entries must not repeat a relative_path"))
    if defects:
        raise ContractError(defects)
    return items


_CORPUS_MANIFEST_FIELDS = {
    "schema": contracts.v_enum(frozenset({CORPUS_MANIFEST_SCHEMA})),
    "corpus_revision": contracts.v_corpus_revision,
    "entries": _v_manifest_entries,
    "corpus_tree_digest": contracts.v_digest,
    "generated_at": contracts.v_timestamp,
    "manifest_digest": contracts.v_digest,
}


def _check_corpus_manifest_fields(document: Any, *, require_digest: bool) -> dict:
    optional = frozenset({"manifest_digest"}) if not require_digest else frozenset()
    validated = contracts.validate_closed_object(document, "$", _CORPUS_MANIFEST_FIELDS, optional=optional)
    if require_digest:
        contracts.verify_document_digest(document, "manifest_digest")
    return validated


def validate_corpus_manifest_shape(document: Any) -> str:
    """Validate a persisted corpus-manifest document. Returns ``'SHAPE_VALID'``."""
    _check_corpus_manifest_fields(document, require_digest=True)
    return "SHAPE_VALID"


def build_corpus_manifest(fields: dict) -> dict:
    """Assemble, validate, and digest a corpus-manifest document.

    ``fields`` must NOT include ``schema`` or ``manifest_digest``.
    """
    if not isinstance(fields, dict) or "schema" in fields or "manifest_digest" in fields:
        raise ContractError(
            [
                ContractDefect(
                    "$",
                    "BUILD_FIELDS_MUST_EXCLUDE_SCHEMA_AND_DIGEST",
                    "fields must omit schema and manifest_digest",
                )
            ]
        )
    document = {"schema": CORPUS_MANIFEST_SCHEMA, **fields}
    _check_corpus_manifest_fields(document, require_digest=False)
    return contracts.add_document_digest(document, "manifest_digest")


contracts.register_shape_validator(CORPUS_MANIFEST_SCHEMA, validate_corpus_manifest_shape)

# ---------------------------------------------------------------------------
# Holdout seal contract (digest-only; sealed body never enters the repo)
# ---------------------------------------------------------------------------

_HOLDOUT_SEAL_FIELDS = {
    "schema": contracts.v_enum(frozenset({CORPUS_HOLDOUT_SEAL_SCHEMA})),
    "scenario_id": contracts.v_scenario_id,
    "scenario_family": contracts.v_scenario_family,
    "risk_tier": contracts.v_enum(_RISK_TIERS),
    "corpus_revision": contracts.v_corpus_revision,
    "temporal_cutoff": contracts.v_timestamp,
    "sealed_body_digest": contracts.v_digest,
    "sealing_method": contracts.v_enum(_SEALING_METHODS),
    "seal_status": contracts.v_enum(_SEAL_STATUSES),
    "private_evidence_root_ref": contracts.v_str,
    "authorship": lambda value, path: contracts.validate_closed_object(
        value, path, {"author_ref": contracts.v_str, "independent_reviewer_ref": contracts.v_str}
    ),
    "created_at": contracts.v_timestamp,
    "seal_digest": contracts.v_digest,
}


def _holdout_seal_cross_field_defects(document: dict) -> list[ContractDefect]:
    defects: list[ContractDefect] = []
    authorship = document.get("authorship")
    if isinstance(authorship, dict) and authorship.get("author_ref") == authorship.get("independent_reviewer_ref"):
        if authorship.get("author_ref") is not None:
            defects.append(
                ContractDefect(
                    "$.authorship.independent_reviewer_ref",
                    "REVIEWER_NOT_INDEPENDENT",
                    "independent_reviewer_ref must differ from author_ref",
                )
            )
    scenario_id = document.get("scenario_id")
    scenario_family = document.get("scenario_family")
    if isinstance(scenario_id, str) and isinstance(scenario_family, str):
        try:
            id_family, _case = contracts.parse_scenario_id(scenario_id)
        except ContractError:
            pass
        else:
            # the scenario_id's <family> slug and the dotted scenario_family
            # name are two renderings of the same family (contracts.py's own
            # scenario_id grammar forbids dots, so they can never be
            # byte-identical) -- require the dotted name's first segment to
            # equal the slug so a seal cannot silently drift to a different
            # family than the ID it names.
            dotted_first_segment = scenario_family.split(".")[1] if scenario_family.count(".") >= 2 else None
            if dotted_first_segment != id_family:
                defects.append(
                    ContractDefect(
                        "$.scenario_family",
                        "SCENARIO_FAMILY_ID_MISMATCH",
                        "scenario_family must name the same family as scenario_id's <family> slug",
                    )
                )
    return defects


def _check_holdout_seal_fields(document: Any, *, require_digest: bool) -> dict:
    optional = frozenset({"seal_digest"}) if not require_digest else frozenset()
    validated = contracts.validate_closed_object(document, "$", _HOLDOUT_SEAL_FIELDS, optional=optional)
    cross_defects = _holdout_seal_cross_field_defects(document if isinstance(document, dict) else {})
    if cross_defects:
        raise ContractError(cross_defects)
    if require_digest:
        contracts.verify_document_digest(document, "seal_digest")
    return validated


def validate_holdout_seal_shape(document: Any) -> str:
    """Validate a persisted holdout-seal document. Returns ``'SHAPE_VALID'``."""
    _check_holdout_seal_fields(document, require_digest=True)
    return "SHAPE_VALID"


def build_holdout_seal(fields: dict) -> dict:
    """Assemble, validate, and digest a holdout-seal document.

    ``fields`` must NOT include ``schema`` or ``seal_digest``.
    """
    if not isinstance(fields, dict) or "schema" in fields or "seal_digest" in fields:
        raise ContractError(
            [ContractDefect("$", "BUILD_FIELDS_MUST_EXCLUDE_SCHEMA_AND_DIGEST", "fields must omit schema and seal_digest")]
        )
    document = {"schema": CORPUS_HOLDOUT_SEAL_SCHEMA, **fields}
    _check_holdout_seal_fields(document, require_digest=False)
    return contracts.add_document_digest(document, "seal_digest")


contracts.register_shape_validator(CORPUS_HOLDOUT_SEAL_SCHEMA, validate_holdout_seal_shape)


def holdout_seal_path(scenario_id: str) -> Path:
    """Safe corpus-relative path for a holdout seal, mirroring
    ``store.scenario_path``'s safe-path law (design §8.3) but rooted at
    ``holdouts/`` instead of ``scenarios/`` -- a holdout seal has no
    ``scenario_version`` (a sealed case is never superseded/versioned the
    way a published scenario is)."""
    family, case = contracts.parse_scenario_id(scenario_id)
    return Path("holdouts") / family / case / _HOLDOUT_SEAL_FILENAME


# ---------------------------------------------------------------------------
# Bounded, safe file reads (mirrors store.py's own bounded-read discipline)
# ---------------------------------------------------------------------------


def _require_regular_nonsymlink(path: Path) -> None:
    if path.is_symlink():
        raise ContractError([ContractDefect(str(path), "SYMLINK_REJECTED", "corpus path must not be a symlink")])
    if not path.is_file():
        raise ContractError([ContractDefect(str(path), "NOT_A_REGULAR_FILE", "corpus path must be a regular file")])


def read_bounded_bytes(path: Path) -> bytes:
    """Read a regular, non-symlink file, refusing anything over the exact
    canonical artifact size bound (plan §5.7) before it is fully buffered."""
    _require_regular_nonsymlink(path)
    with open(path, "rb") as handle:
        raw = handle.read(MAX_CANONICAL_ARTIFACT_BYTES + 1)
    if len(raw) > MAX_CANONICAL_ARTIFACT_BYTES:
        raise ContractError([ContractDefect(str(path), "ARTIFACT_TOO_LARGE", "corpus file exceeds the canonical size bound")])
    return raw


def file_digest(data: bytes) -> str:
    """``sha256:<64 lower-case hex>`` over raw bytes (not canonical JSON --
    corpus fixture files may be markdown/plain text, not JSON documents)."""
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _read_json(path: Path) -> dict:
    raw = read_bounded_bytes(path)
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError([ContractDefect(str(path), "CORPUS_FILE_CORRUPT_JSON", "corpus file is not valid JSON")]) from exc


# ---------------------------------------------------------------------------
# Corpus-tree digest derivation (tamper detection)
# ---------------------------------------------------------------------------


def enumerate_corpus_files(corpus_root: Path) -> tuple[Path, ...]:
    """Sorted, relative-to-``corpus_root`` paths of every regular,
    non-symlink file under the corpus tree, EXCLUDING the manifest itself
    (the manifest describes the tree; it cannot describe its own bytes)."""
    found: list[Path] = []
    for path in corpus_root.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        relative = path.relative_to(corpus_root)
        if relative == Path(_MANIFEST_FILENAME):
            continue
        found.append(relative)
    return tuple(sorted(found))


def compute_corpus_tree_digest(corpus_root: Path) -> tuple[str, tuple[dict, ...]]:
    """Deterministic ``sha256`` digest over the corpus tree's byte contents.

    Returns ``(corpus_tree_digest, entries)`` where ``entries`` is the
    sorted ``[{relative_path, digest}, ...]`` list the digest is computed
    over. Any single-byte change to any corpus file changes this digest --
    that is the tamper-detection property ``verify_corpus_tree_consistency``
    checks against the frozen manifest.
    """
    entries = []
    for relative in enumerate_corpus_files(corpus_root):
        data = read_bounded_bytes(corpus_root / relative)
        entries.append({"relative_path": str(relative), "digest": file_digest(data)})
    entries.sort(key=lambda item: item["relative_path"])
    tree_digest = contracts.digest_value(entries)
    return tree_digest, tuple(entries)


# ---------------------------------------------------------------------------
# Scenario-vs-corpus consistency validation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CorpusVerificationReport:
    result: str  # "CONSISTENT" | "INCONSISTENT"
    defects: tuple[ContractDefect, ...]
    corpus_revision: str | None
    corpus_tree_digest: str | None
    scenario_count: int
    holdout_count: int

    def __post_init__(self) -> None:
        if self.result not in {"CONSISTENT", "INCONSISTENT"}:
            raise ValueError("CorpusVerificationReport.result must be CONSISTENT or INCONSISTENT")


def _artifact_ref_relative_path(artifact_ref: str, corpus_revision: str) -> str | None:
    """Strip the frozen ``corpus_revision`` + ``#`` prefix from a fixture's
    ``artifact_ref`` to recover the repository-relative path it names. Only
    fixture refs anchored to THIS wave's exact frozen corpus_revision are
    resolvable this way; anything else is left externally
    sealed/unverified (this module never claims EVIDENCE_CONTENT_VERIFIED --
    it only checks the narrower, bounded claim that a corpus fixture's own
    declared bytes match what is actually committed under the corpus tree)."""
    prefix = f"{corpus_revision}#"
    if not artifact_ref.startswith(prefix):
        return None
    return artifact_ref[len(prefix):]


def _collect_scenario_fixture_pairs(document: dict) -> list[tuple[str, dict]]:
    pairs = [("$.input_fixture", document["input_fixture"]), ("$.expected_contract", document["expected_contract"])]
    for index, item in enumerate(document["source_policy"]["allowlist_artifacts"]):
        pairs.append((f"$.source_policy.allowlist_artifacts[{index}]", item))
    return pairs


def _verify_scenario_document(
    path: str,
    document: dict,
    *,
    corpus_root: Path,
    repo_root: Path,
    manifest_corpus_revision: str,
) -> list[ContractDefect]:
    defects: list[ContractDefect] = []
    try:
        contracts.validate_scenario_shape(document)
    except ContractError as exc:
        return [ContractDefect(f"{path}::{d.path}", d.code, d.message) for d in exc.defects]

    try:
        assert_public_safe_evidence(document)
    except ContractError as exc:
        defects.extend(ContractDefect(f"{path}::{d.path}", d.code, d.message) for d in exc.defects)

    if document["corpus_revision"] != manifest_corpus_revision:
        defects.append(
            ContractDefect(path, "CORPUS_REVISION_NOT_ANCHORED", "scenario corpus_revision does not match the corpus manifest anchor")
        )
    if document["privacy"]["classification"] != "PUBLIC_SAFE":
        defects.append(
            ContractDefect(
                f"{path}.privacy.classification",
                "NON_PUBLIC_SAFE_IN_PUBLIC_CORPUS",
                "every scenario committed to the public corpus must declare privacy.classification PUBLIC_SAFE",
            )
        )

    # NB: mislocation (does this document's own scenario_id/version derive
    # the exact repo-relative path it was read from?) is checked by the
    # caller, which knows the real corpus-relative path -- store.scenario_path
    # is pure/no-I/O and reused there to avoid recomputing the safe-path law
    # a second time in this function.

    for fixture_path, pair in _collect_scenario_fixture_pairs(document):
        relative = _artifact_ref_relative_path(pair["artifact_ref"], manifest_corpus_revision)
        if relative is None:
            # not anchored to this wave's frozen corpus_revision -- outside
            # this module's bounded content check; leave it externally
            # sealed/unverified rather than guessing.
            continue
        candidate = repo_root / relative
        try:
            data = read_bounded_bytes(candidate)
        except (ContractError, FileNotFoundError, OSError):
            defects.append(
                ContractDefect(fixture_path, "FIXTURE_FILE_UNRESOLVED", f"declared artifact_ref does not resolve under the repository: {relative}")
            )
            continue
        if file_digest(data) != pair["digest"]:
            defects.append(
                ContractDefect(fixture_path, "FIXTURE_DIGEST_MISMATCH", "fixture file bytes do not match the scenario's declared digest")
            )
    return defects


def verify_corpus_tree_consistency(corpus_root: Path, repo_root: Path) -> CorpusVerificationReport:
    """Full scenario-vs-corpus consistency check over a committed corpus tree.

    Never repairs -- report-only, exactly like ``ArtifactStore.verify_tree_graph``.
    """
    defects: list[ContractDefect] = []
    manifest_path = corpus_root / _MANIFEST_FILENAME
    if not manifest_path.is_file() or manifest_path.is_symlink():
        return CorpusVerificationReport(
            result="INCONSISTENT",
            defects=(ContractDefect(str(manifest_path), "MANIFEST_MISSING", "corpus_manifest.json is missing"),),
            corpus_revision=None,
            corpus_tree_digest=None,
            scenario_count=0,
            holdout_count=0,
        )

    manifest = _read_json(manifest_path)
    try:
        validate_corpus_manifest_shape(manifest)
    except ContractError as exc:
        return CorpusVerificationReport(
            result="INCONSISTENT",
            defects=tuple(ContractDefect(f"{_MANIFEST_FILENAME}::{d.path}", d.code, d.message) for d in exc.defects),
            corpus_revision=None,
            corpus_tree_digest=None,
            scenario_count=0,
            holdout_count=0,
        )

    manifest_corpus_revision = manifest["corpus_revision"]
    recomputed_digest, recomputed_entries = compute_corpus_tree_digest(corpus_root)
    if recomputed_digest != manifest["corpus_tree_digest"] or list(recomputed_entries) != list(manifest["entries"]):
        defects.append(
            ContractDefect(
                _MANIFEST_FILENAME,
                "CORPUS_TREE_DIGEST_MISMATCH",
                "the corpus tree's recomputed digest does not match the frozen manifest -- a committed file was added, removed, or tampered with",
            )
        )

    scenario_count = 0
    holdout_count = 0
    # BLOCKER-2 repair: identity-based overlap, not directory-based. A
    # republished holdout body can land under a DIFFERENT directory name
    # than its own seal (a different family/case slug entirely) and still
    # evade a directory-set intersection -- what must never coexist is the
    # same scenario_id existing as both a public scenario and a sealed
    # holdout, regardless of where each one physically sits in the tree.
    public_scenario_ids: set[str] = set()
    holdout_scenario_ids: set[str] = set()

    for scenario_file in sorted(corpus_root.rglob(_SCENARIO_FILENAME)):
        if scenario_file.is_symlink():
            defects.append(ContractDefect(str(scenario_file), "SYMLINK_REJECTED", "corpus scenario path must not be a symlink"))
            continue
        relative = scenario_file.relative_to(corpus_root)
        scenario_count += 1
        document = _read_json(scenario_file)
        if isinstance(document, dict) and isinstance(document.get("scenario_id"), str):
            public_scenario_ids.add(document["scenario_id"])
        defects.extend(
            _verify_scenario_document(
                str(relative),
                document,
                corpus_root=corpus_root,
                repo_root=repo_root,
                manifest_corpus_revision=manifest_corpus_revision,
            )
        )
        if isinstance(document, dict) and "scenario_id" in document and "scenario_version" in document:
            try:
                expected_relative = store.scenario_path(document["scenario_id"], document["scenario_version"])
            except ContractError:
                expected_relative = None
            if expected_relative is not None and expected_relative != relative:
                defects.append(
                    ContractDefect(
                        str(relative),
                        "SCENARIO_MISLOCATED",
                        f"stored path does not match the canonical path derived from its own scenario_id/version (expected {expected_relative})",
                    )
                )

    # MAJOR-R1 repair: the previous check discovered seals by
    # ``rglob(_HOLDOUT_SEAL_FILENAME)`` and then allowlisted each seal's OWN
    # directory -- a case dir that never got a holdout_seal.json in the
    # first place (an orphan) was simply never visited, so a body dropped
    # there verified CONSISTENT (reviewer B7/B9), and so did a stray file at
    # the family level, one level above any per-seal directory (B8). The
    # fix walks the ENTIRE ``holdouts/`` subtree WHOLESALE: every single
    # file anywhere under it must be exactly
    # ``holdouts/<family>/<case>/holdout_seal.json`` in both path shape and
    # basename, or it is refused -- this subsumes and replaces the old
    # per-seal-directory allowlist (a file that does not match this shape
    # can never coexist with a seal it is "the directory of", because the
    # shape check runs before -- not alongside -- discovery of what counts
    # as a seal).
    holdouts_root = corpus_root / "holdouts"
    if holdouts_root.is_dir():
        for path in sorted(holdouts_root.rglob("*")):
            relative = path.relative_to(corpus_root)
            if path.is_dir():
                continue  # only leaf files are checked; a directory alone is not a body
            if path.is_symlink():
                defects.append(ContractDefect(str(relative), "SYMLINK_REJECTED", "corpus holdouts path must not be a symlink"))
                continue
            parts = relative.parts  # expect exactly ("holdouts", <family>, <case>, "holdout_seal.json")
            if len(parts) != 4 or parts[3] != _HOLDOUT_SEAL_FILENAME:
                defects.append(
                    ContractDefect(
                        str(relative),
                        "UNSEALED_HOLDOUT_BODY_IN_REPO",
                        f"every file under holdouts/ must be exactly holdouts/<family>/<case>/{_HOLDOUT_SEAL_FILENAME}; found {relative}",
                    )
                )
                continue

            seal_file = path
            holdout_count += 1
            document = _read_json(seal_file)
            if isinstance(document, dict) and isinstance(document.get("scenario_id"), str):
                holdout_scenario_ids.add(document["scenario_id"])
            try:
                validate_holdout_seal_shape(document)
            except ContractError as exc:
                defects.extend(ContractDefect(f"{relative}::{d.path}", d.code, d.message) for d in exc.defects)
            else:
                try:
                    assert_public_safe_evidence(document)
                except ContractError as exc:
                    defects.extend(ContractDefect(f"{relative}::{d.path}", d.code, d.message) for d in exc.defects)
                if document["corpus_revision"] != manifest_corpus_revision:
                    defects.append(
                        ContractDefect(str(relative), "CORPUS_REVISION_NOT_ANCHORED", "holdout seal corpus_revision does not match the corpus manifest anchor")
                    )
                if isinstance(document, dict) and "scenario_id" in document:
                    try:
                        expected_relative = holdout_seal_path(document["scenario_id"])
                    except ContractError:
                        expected_relative = None
                    if expected_relative is not None and expected_relative != relative:
                        defects.append(
                            ContractDefect(
                                str(relative),
                                "HOLDOUT_SEAL_MISLOCATED",
                                f"stored path does not match the canonical path derived from its own scenario_id (expected {expected_relative})",
                            )
                        )

    overlap_ids = public_scenario_ids & holdout_scenario_ids
    for scenario_id in sorted(overlap_ids):
        defects.append(
            ContractDefect(
                scenario_id,
                "CASE_DIRECTORY_MIXES_PUBLIC_AND_HOLDOUT",
                "the same scenario_id exists as both a public scenario (under scenarios/) and a sealed holdout (under holdouts/)",
            )
        )

    defects = sorted(set(defects))
    return CorpusVerificationReport(
        result="CONSISTENT" if not defects else "INCONSISTENT",
        defects=tuple(defects),
        corpus_revision=manifest_corpus_revision,
        corpus_tree_digest=manifest["corpus_tree_digest"],
        scenario_count=scenario_count,
        holdout_count=holdout_count,
    )

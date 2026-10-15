"""Read a programme acceptance basis through the existing Agent OS CLI owner.

The model selects no repository, path, interpreter, head, commission or digest.
This bridge creates no producer, parser, grant, registry or lifecycle state.
The configured source root must include the existing qualified workstream CLI;
its absence and an unqualified sealed context runtime are explicit refusals.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from common.commission_ref import (
    CommissionRef,
    CommissionRefError,
    normalize_commission_ref,
)
from control_plane.ceo_boot_packet import bounded_subprocess_runner, git_sha
from control_plane.session_truth_contract import valid_source_records_digest

_SOURCE_ROOT = Path(__file__).resolve().parents[1]
_WORK_REF = re.compile(r"\AWS:[A-Z0-9][A-Z0-9-]{1,63}\Z")
_DIGEST = re.compile(r"\A[0-9a-f]{64}\Z")
_MACRO_REPOSITORY = "mastermindx-market-intelligence/macro"
_MAX_BYTES = 262144


class ProductAcceptanceBasisUnavailable(RuntimeError):
    """Closed missingness, without helper output or a fallback source."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ProductAcceptanceBasisRead:
    """Detached compiler observation; never a grant or issued verdict."""

    macro_commit: str
    source_records_digest: str
    entry: dict[str, Any]


@dataclass(frozen=True)
class ProductAcceptanceBasisContinuity:
    """Comparison of acquired source data, never an acceptance or grant.

    The original issuance and proof keep their exact issued basis digest. The
    receiving owner separately revalidates Runtime results, generations,
    independent review, committed ruling and actual parent consumption.
    """

    issued_basis_digest: str
    current_basis_digest: str
    declaration_digest: str
    disposition: str


_DECLARATION_FIELDS = frozenset(
    {
        "commission_id",
        "commission_ref",
        "continuity_ref",
        "original_intent_ref",
        "original_proof_contract_ref",
        "proof_contract_ref",
        "current_intent_revision",
        "correction_state",
        "correction_chain",
        "criteria_objective",
        "criteria_sources",
        "original_source_status",
        "proof_obligations",
        "execution_commission_refs",
        "workstream",
        "current_intent_text",
        "criteria_objective_sha256",
        "execution_commission_state",
        "proof_obligation_digests",
    }
)
_OBSERVATION_FIELDS = frozenset(
    {
        "acceptance_basis_digest",
        "current_intent_ref",
        "source_record_ref",
        "source_state",
        "reference_observation",
        "snapshot_consistency",
    }
)


def reconcile_unchanged_acceptance_basis(
    issued: ProductAcceptanceBasisRead,
    current: ProductAcceptanceBasisRead,
) -> ProductAcceptanceBasisContinuity:
    """Keep valid issued evidence across unrelated Git/WS progress changes.

    Call only with retained owner-issued material and an independently acquired
    current read. Constructing these DTOs or comparing public hashes grants
    nothing. All declared intent, correction, association and proof fields are
    compared; only the separately validated source observations may differ.
    Unknown fields or missing observations require explicit reconciliation.
    """

    def material(read: ProductAcceptanceBasisRead) -> tuple[str, str]:
        if type(read) is not ProductAcceptanceBasisRead or type(read.entry) is not dict:
            raise ProductAcceptanceBasisUnavailable(
                "SOURCE_REVISION_RECONCILIATION_REQUIRED"
            )
        entry = read.entry
        if (
            set(entry) != _DECLARATION_FIELDS | _OBSERVATION_FIELDS
            or entry.get("source_state") != "CURRENT"
            or entry.get("reference_observation")
            != "DECLARED_REFERENCES_NOT_RETRIEVED_OR_AUTHENTICATED_HERE"
            or entry.get("snapshot_consistency") != "EXISTING_NON_ATOMIC_RECORD_READ"
            or not valid_source_records_digest(read.source_records_digest)
        ):
            raise ProductAcceptanceBasisUnavailable(
                "SOURCE_REVISION_RECONCILIATION_REQUIRED"
            )
        try:
            source = normalize_commission_ref(entry["source_record_ref"])
            current_ref = normalize_commission_ref(entry["current_intent_ref"])
            digest = _canonical_digest(
                {k: v for k, v in entry.items() if k != "acceptance_basis_digest"}
            )
            if (
                source != current_ref
                or source.repository != _MACRO_REPOSITORY
                or source.commit != read.macro_commit
                or not source.path.startswith("agentos/workstreams/WS-")
                or not source.path.endswith(".md")
                or entry["acceptance_basis_digest"] != digest
            ):
                raise ProductAcceptanceBasisUnavailable(
                    "SOURCE_REVISION_RECONCILIATION_REQUIRED"
                )
            return digest, _canonical_digest({k: entry[k] for k in _DECLARATION_FIELDS})
        except (ValueError, TypeError, KeyError, CommissionRefError) as exc:
            raise ProductAcceptanceBasisUnavailable(
                "SOURCE_REVISION_RECONCILIATION_REQUIRED"
            ) from exc

    issued_digest, issued_declaration = material(issued)
    current_digest, current_declaration = material(current)
    if issued_declaration != current_declaration:
        raise ProductAcceptanceBasisUnavailable(
            "SOURCE_REVISION_RECONCILIATION_REQUIRED"
        )
    return ProductAcceptanceBasisContinuity(
        issued_digest,
        current_digest,
        current_declaration,
        (
            "UNCHANGED_SOURCE"
            if issued_digest == current_digest
            else "SOURCE_OBSERVATION_CHANGED_DECLARATION_UNCHANGED"
        ),
    )


def _canonical_digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


class AgentOsProductAcceptanceBasisReader:
    """A bound source consumer, with no caller-selectable command or Runtime."""

    def __init__(self, *, macro_root: Path) -> None:
        root = Path(macro_root)
        if not root.is_absolute():
            raise ValueError("Macro source root must be absolute")
        self._macro_root = root
        # The installed integration owner composes its qualified collector.
        # Core cannot import that outer transport or accept an arbitrary owner.
        self._installed_context_owner = None
        self._installed_context_binding = None

    @staticmethod
    def _context_binding(owner):
        return tuple(getattr(owner, name) for name in (
            "_source_root", "_macro_root", "_code_root", "_python",
            "_expected_source_sha", "_allow_synthetic_fixture",
        ))

    def read(
        self,
        *,
        work_ref: str,
        execution_commission_ref: CommissionRef,
        root_objective: str,
    ) -> ProductAcceptanceBasisRead:
        """Acquire the actual current compiler record before request issuance.

        Inputs come from the existing Runtime/binding owner, never public tool
        arguments. Identical objective text cannot create a commission join.
        The expected Macro HEAD is freshly read from the bound source owner,
        passed to its existing CLI and checked again after the bounded read.
        """
        if type(work_ref) is not str or _WORK_REF.fullmatch(work_ref) is None:
            raise ProductAcceptanceBasisUnavailable("BASIS_BINDING_UNAVAILABLE")
        if type(execution_commission_ref) is not CommissionRef:
            raise ProductAcceptanceBasisUnavailable("BASIS_BINDING_UNAVAILABLE")
        if self._installed_context_owner is not None:
            try:
                if self._context_binding(self._installed_context_owner) != self._installed_context_binding:
                    raise ProductAcceptanceBasisUnavailable("CONTEXT_OWNER_UNAVAILABLE")
                result = self._installed_context_owner.read_product_acceptance_basis(
                    work_ref=work_ref, execution_commission_ref=execution_commission_ref,
                    root_objective=root_objective,
                )
                if self._context_binding(self._installed_context_owner) != self._installed_context_binding:
                    raise ProductAcceptanceBasisUnavailable("CONTEXT_OWNER_UNAVAILABLE")
                return result
            except ProductAcceptanceBasisUnavailable:
                raise
            except Exception:
                raise ProductAcceptanceBasisUnavailable("CONTEXT_OWNER_UNAVAILABLE") from None
        # Without the explicit sealed owner, Control cannot read Macro/PyYAML.
        # Do not select another interpreter or drop isolation on this path.
        if sys.flags.isolated or sys.flags.no_site:
            raise ProductAcceptanceBasisUnavailable("CONTEXT_RUNTIME_UNQUALIFIED")
        expected_sha = git_sha(self._macro_root)
        if expected_sha is None:
            raise ProductAcceptanceBasisUnavailable("CONTEXT_SOURCE_UNAVAILABLE")
        result = bounded_subprocess_runner(
            [
                sys.executable,
                "-B",
                str(_SOURCE_ROOT / "scripts" / "ceo_boot_packet.py"),
                "--workstream",
                work_ref[3:],
                "--macro-root",
                str(self._macro_root),
                "--expected-macro-sha",
                expected_sha,
                "--json",
                "--timeout",
                "10",
            ],
            cwd=_SOURCE_ROOT,
            timeout=15.0,
            max_bytes=_MAX_BYTES,
        )
        if (
            result.get("code") != 0
            or result.get("timed_out") is True
            or result.get("limit_exceeded") is True
            or result.get("invalid_utf8") is True
            or type(result.get("stdout")) is not str
        ):
            raise ProductAcceptanceBasisUnavailable("CONTEXT_OWNER_UNAVAILABLE")
        if git_sha(self._macro_root) != expected_sha:
            raise ProductAcceptanceBasisUnavailable("CONTEXT_SOURCE_CHANGED")
        try:
            bundle = json.loads(result["stdout"])
            selected = self._select(
                bundle,
                expected_sha=expected_sha,
                work_ref=work_ref,
                execution_ref=execution_commission_ref,
                root_objective=root_objective,
            )
            source = normalize_commission_ref(selected.entry["source_record_ref"])
            raw = bounded_subprocess_runner(
                [
                    "git",
                    "-C",
                    str(self._macro_root),
                    "show",
                    f"{source.commit}:{source.path}",
                ],
                cwd=self._macro_root,
                timeout=10.0,
                max_bytes=_MAX_BYTES,
            )
            if (
                raw.get("code") != 0
                or type(raw.get("stdout")) is not str
                or any(
                    raw.get(flag) is True
                    for flag in ("timed_out", "limit_exceeded", "invalid_utf8")
                )
                or hashlib.sha256(raw["stdout"].encode("utf-8")).hexdigest()
                != source.content_sha256
                or git_sha(self._macro_root) != expected_sha
            ):
                raise ProductAcceptanceBasisUnavailable("CONTEXT_SOURCE_CHANGED")
            return selected
        except (ValueError, TypeError, KeyError, CommissionRefError) as exc:
            raise ProductAcceptanceBasisUnavailable("BASIS_UNAVAILABLE") from exc

    @staticmethod
    def _select(
        bundle: Any,
        *,
        expected_sha: str,
        work_ref: str,
        execution_ref: CommissionRef,
        root_objective: str,
    ) -> ProductAcceptanceBasisRead:
        """Check the compiler observation; no same-text authority inference."""
        if (
            type(bundle) is not dict
            or bundle.get("schema") != "context_bundle.v1"
            or bundle.get("repo_sha") != expected_sha
            or type(bundle.get("target")) is not dict
            or bundle["target"].get("workstream") != work_ref
            or not valid_source_records_digest(bundle.get("source_records_digest"))
        ):
            raise ProductAcceptanceBasisUnavailable("CONTEXT_OWNER_UNAVAILABLE")
        basis = bundle.get("acceptance_basis")
        if (
            type(basis) is not dict
            or basis.get("schema") != "agentos.acceptance_basis.v1"
            or basis.get("authoritative") is not False
            or type(basis.get("by_commission")) is not dict
            or len(basis["by_commission"]) > 16
        ):
            raise ProductAcceptanceBasisUnavailable("BASIS_UNAVAILABLE")
        matches = []
        for key, entry in basis["by_commission"].items():
            if type(entry) is not dict or entry.get("workstream") != work_ref:
                continue
            refs = entry.get("execution_commission_refs")
            if type(refs) is not list or len(refs) > 16:
                raise ProductAcceptanceBasisUnavailable("BASIS_UNAVAILABLE")
            normalized_refs = [
                normalize_commission_ref(value).to_dict() for value in refs
            ]
            if len({_canonical_digest(value) for value in normalized_refs}) != len(
                refs
            ):
                raise ProductAcceptanceBasisUnavailable("BASIS_UNAVAILABLE")
            if execution_ref.to_dict() in normalized_refs:
                matches.append((key, entry))
        if not matches:
            raise ProductAcceptanceBasisUnavailable(
                "EXECUTION_COMMISSION_NOT_ASSOCIATED"
            )
        if len(matches) != 1:
            raise ProductAcceptanceBasisUnavailable("BASIS_AMBIGUOUS")
        key, entry = matches[0]
        if (
            entry.get("commission_id") != key
            or entry.get("source_state") != "CURRENT"
            or entry.get("current_intent_text") != root_objective
            or entry.get("criteria_objective") != root_objective
            or entry.get("criteria_objective_sha256")
            != hashlib.sha256(root_objective.encode("utf-8")).hexdigest()
            or entry.get("acceptance_basis_digest")
            != _canonical_digest(
                {
                    name: value
                    for name, value in entry.items()
                    if name != "acceptance_basis_digest"
                }
            )
        ):
            raise ProductAcceptanceBasisUnavailable("BASIS_CURRENT_INTENT_UNPROVEN")
        source = normalize_commission_ref(entry.get("source_record_ref"))
        current = normalize_commission_ref(entry.get("current_intent_ref"))
        if (
            source != current
            or source.repository != _MACRO_REPOSITORY
            or source.commit != expected_sha
            or not source.path.startswith("agentos/workstreams/")
        ):
            raise ProductAcceptanceBasisUnavailable("BASIS_CURRENT_INTENT_UNPROVEN")
        return ProductAcceptanceBasisRead(
            expected_sha, bundle["source_records_digest"], copy.deepcopy(entry)
        )


@dataclass(frozen=True)
class ProductAcceptanceExpectedProof:
    """Complete identities derived from a acquired declaration, not tool input."""

    basis_digest: str
    objective_sha256: str
    criterion_digests: tuple[str, ...]
    obligation_digests: tuple[str, ...]


def expected_product_acceptance_proof(
    read: ProductAcceptanceBasisRead,
    *,
    root_objective: str,
    execution_commission_ref: CommissionRef,
) -> ProductAcceptanceExpectedProof:
    """Derive every row through the sole criterion parser and full source record.

    This is validation of already acquired source data. It confers no issuance,
    evidence truth, principal authority or acceptance. No caller supplies a
    subset of the required identities.
    """
    from control_plane.mission_acceptance_criteria import (
        AcceptanceCriteriaError,
        parse_acceptance_criteria_candidate,
    )

    reconcile_unchanged_acceptance_basis(read, read)
    entry = read.entry
    try:
        candidate = parse_acceptance_criteria_candidate(root_objective)
        refs = entry["execution_commission_refs"]
        if (
            candidate is None
            or type(execution_commission_ref) is not CommissionRef
            or type(refs) is not list
            or not 1 <= len(refs) <= 16
            or execution_commission_ref.to_dict()
            not in [normalize_commission_ref(ref).to_dict() for ref in refs]
            or entry["execution_commission_state"]
            != "ASSOCIATED_SOURCE_REFERENCES_ONLY"
            or entry["criteria_objective"] != root_objective
            or entry["current_intent_text"] != root_objective
            or entry["criteria_objective_sha256"] != candidate.objective_sha256
            or entry["original_source_status"]
            not in {"AUTHENTIC_USER_INPUT_CANDIDATE", "AUTHENTIC_USER_INPUT_PROTECTED"}
        ):
            raise ValueError
        chain, correction = entry["correction_chain"], entry["correction_state"]
        if (
            type(chain) is not list
            or len(chain) > 16
            or correction
            not in {
                "NO_CORRECTION_DECLARED_AT_THIS_REVISION",
                "CORRECTIONS_DECLARED_AT_THIS_REVISION",
            }
            or bool(chain) != (correction == "CORRECTIONS_DECLARED_AT_THIS_REVISION")
        ):
            raise ValueError
        for ref in [
            entry[name]
            for name in (
                "commission_ref",
                "continuity_ref",
                "original_intent_ref",
                "original_proof_contract_ref",
                "proof_contract_ref",
            )
        ] + chain:
            normalize_commission_ref(ref)
        anchors = entry["criteria_sources"]
        if type(anchors) is not list or len(anchors) != len(candidate.criteria):
            raise ValueError
        for index, row in enumerate(anchors):
            if (
                type(row) is not dict
                or set(row) != {"criterion_index", "source_ref", "locators"}
                or type(row["criterion_index"]) is not int
                or row["criterion_index"] != index
                or type(row["locators"]) is not list
                or not 1 <= len(row["locators"]) <= 16
                or any(
                    type(item) is not str
                    or not item.strip()
                    or item != item.strip()
                    or len(item) > 200
                    for item in row["locators"]
                )
            ):
                raise ValueError
            normalize_commission_ref(row["source_ref"])
        obligations = entry["proof_obligations"]
        if type(obligations) is not list or not 1 <= len(obligations) <= 64:
            raise ValueError
        identities = set()
        for row in obligations:
            if type(row) is not dict or set(row) != {
                "source_ref",
                "section",
                "label",
                "required_outcome",
            }:
                raise ValueError
            normalize_commission_ref(row["source_ref"])
            for field, maximum in (
                ("section", 80),
                ("label", 200),
                ("required_outcome", 4000),
            ):
                value = row[field]
                if (
                    type(value) is not str
                    or not value.strip()
                    or value != value.strip()
                    or len(value.encode("utf-8")) > maximum
                ):
                    raise ValueError
            identity = row["section"], row["label"]
            if identity in identities:
                raise ValueError
            identities.add(identity)
        digests = tuple(_canonical_digest(row) for row in obligations)
        if type(entry["proof_obligation_digests"]) is not list or entry[
            "proof_obligation_digests"
        ] != list(digests):
            raise ValueError
        return ProductAcceptanceExpectedProof(
            entry["acceptance_basis_digest"],
            candidate.objective_sha256,
            tuple(row.criterion_digest for row in candidate.criteria),
            digests,
        )
    except (
        ValueError,
        TypeError,
        KeyError,
        UnicodeError,
        CommissionRefError,
        AcceptanceCriteriaError,
    ) as exc:
        raise ProductAcceptanceBasisUnavailable(
            "BASIS_PROOF_REQUIREMENTS_UNAVAILABLE"
        ) from exc

"""Immutable, production-inert evidence ledger for the paired Z0 study.

The ledger is intentionally small and strict: a source generation, every
candidate query trial, and every failure becomes an append-only receipt.  It
does not invoke an indexer or a service; host-owned runners may feed it facts,
but cannot erase an inconvenient failure or turn synthetic proof into a
decision-eligible real evaluation.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Final

from .baseline_search import AnswerKey
from .evaluation_manifest import EvaluationManifest, EvaluationQuery


LEDGER_SCHEMA_VERSION: Final = "mastermind.codeintel_z0_evaluation_ledger.v1"
UNKNOWN_RESOURCE: Final = "UNKNOWN"
_SHA1_RE: Final = re.compile(r"[0-9a-f]{40}\Z")
_SHA256_RE: Final = re.compile(r"[0-9a-f]{64}\Z")
_OUTCOMES: Final = frozenset({"completed", "timeout", "error", "cancelled"})
_GENERATION_STATUSES: Final = frozenset({"succeeded", "failed", "partial"})
_FAILURE_CODES: Final = frozenset(
    {
        "CREDENTIAL_UNAVAILABLE",
        "CORRUPT_INDEX",
        "DISK_BUDGET_EXCEEDED",
        "EXTERNAL_PATH",
        "INCOMPLETE_SOURCE",
        "PROCESS_CRASH",
        "SOURCE_MOVED",
        "SUBMODULE_UNRESOLVED",
        "SYMLINK_REJECTED",
        "TIMEOUT",
        "TOOLCHAIN_UNAVAILABLE",
    }
)


class EvidenceError(ValueError):
    """A receipt would make the empirical evidence ambiguous or self-serving."""


@dataclass(frozen=True)
class ResourceObservation:
    """Measured host resource use, with unknown explicitly distinct from zero."""

    cpu_ms: int | str
    rss_bytes: int | str
    disk_bytes: int | str

    def __post_init__(self) -> None:
        for label, value in (
            ("cpu_ms", self.cpu_ms),
            ("rss_bytes", self.rss_bytes),
            ("disk_bytes", self.disk_bytes),
        ):
            if value != UNKNOWN_RESOURCE and (type(value) is not int or value < 0):
                raise EvidenceError(f"{label} must be a non-negative integer or UNKNOWN")

    @property
    def is_known(self) -> bool:
        return all(
            value != UNKNOWN_RESOURCE
            for value in (self.cpu_ms, self.rss_bytes, self.disk_bytes)
        )

    def to_payload(self) -> dict[str, int | str]:
        return {
            "cpu_ms": self.cpu_ms,
            "rss_bytes": self.rss_bytes,
            "disk_bytes": self.disk_bytes,
        }


@dataclass(frozen=True)
class GenerationReceipt:
    """One repository/ref indexing result, whether it succeeded or failed."""

    generation_id: str
    logical_repo_id: str
    source_commit: str
    source_tree: str
    status: str
    indexed_commit_sha: str | None
    shard_digest: str | None
    failure_code: str | None


@dataclass(frozen=True)
class PublicationReceipt:
    """The explicit result of trying to publish one whole source generation."""

    generation_id: str
    state: str
    active_generation_id: str | None


@dataclass(frozen=True)
class TrialReceipt:
    """One trial from the preregistered alternating candidate order."""

    trial_id: str
    attempt_index: int
    outcome: str
    answer_key_digest: str
    source_census_digest: str
    generation_id: str
    query_completed: bool
    truncated: bool
    returned_identities: tuple[tuple[str, str, str, str, int, int], ...]
    recall: float
    false_positive_count: int
    resource: ResourceObservation
    failure_code: str | None


@dataclass(frozen=True)
class CandidateTrialObservation:
    """The sole candidate-provided facts consumed by the immutable trial record."""

    outcome: str
    query_completed: bool
    truncated: bool
    returned_identities: tuple[tuple[str, str, str, str, int, int], ...]
    resource: ResourceObservation
    failure_code: str | None


TrialExecutor = Callable[[EvaluationQuery], CandidateTrialObservation]


@dataclass(frozen=True)
class TrialGrade:
    """Source-derived grade for a candidate's returned source identities."""

    recall: float
    false_positive_count: int


@dataclass(frozen=True)
class EvaluationEvidence:
    """Frozen summary for the result gate; it is not itself a decision."""

    state: str
    manifest_digest: str
    source_census_digest: str
    ledger_digest: str
    run_kind: str
    active_generation_id: str | None
    required_trial_count: int
    recorded_trial_count: int
    failed_trial_count: int
    all_resources_known: bool
    all_identity_bound: bool
    reasons: tuple[str, ...]
    canonical_bytes: bytes

    @property
    def is_real_complete(self) -> bool:
        return self.state == "ELIGIBLE_REAL_EMPIRICAL_EVIDENCE"

    def to_result_payload(self) -> dict[str, object]:
        return {
            "state": self.state,
            "manifest_digest": self.manifest_digest,
            "source_census_digest": self.source_census_digest,
            "ledger_digest": self.ledger_digest,
            "run_kind": self.run_kind,
            "active_generation_id": self.active_generation_id,
            "required_trial_count": self.required_trial_count,
            "recorded_trial_count": self.recorded_trial_count,
            "failed_trial_count": self.failed_trial_count,
            "all_resources_known": self.all_resources_known,
            "all_identity_bound": self.all_identity_bound,
            "reasons": list(self.reasons),
        }


class EvaluationLedger:
    """Append-only in-memory ledger; its canonical bytes are the durable proof."""

    def __init__(
        self,
        manifest: EvaluationManifest,
        *,
        run_kind: str,
        source_census_digest: str,
    ) -> None:
        if not isinstance(manifest, EvaluationManifest):
            raise EvidenceError("ledger requires an EvaluationManifest")
        if run_kind not in {"real", "synthetic"}:
            raise EvidenceError("run_kind must be real or synthetic")
        _require_sha256(source_census_digest, "source_census_digest")
        self._manifest = manifest
        self._run_kind = run_kind
        self._source_census_digest = source_census_digest
        self._generation_receipts: list[GenerationReceipt] = []
        self._publication_receipts: list[PublicationReceipt] = []
        self._trial_receipts: list[TrialReceipt] = []
        self._active_generation_id: str | None = None

    @property
    def manifest(self) -> EvaluationManifest:
        return self._manifest

    @property
    def generation_receipts(self) -> tuple[GenerationReceipt, ...]:
        return tuple(self._generation_receipts)

    @property
    def publication_receipts(self) -> tuple[PublicationReceipt, ...]:
        return tuple(self._publication_receipts)

    @property
    def trial_receipts(self) -> tuple[TrialReceipt, ...]:
        return tuple(self._trial_receipts)

    @property
    def active_generation_id(self) -> str | None:
        return self._active_generation_id

    def record_generation(self, receipt: GenerationReceipt) -> None:
        """Append one exact build outcome; source movement and omission are errors."""

        if not isinstance(receipt, GenerationReceipt):
            raise EvidenceError("generation receipt must be a GenerationReceipt")
        _require_identifier(receipt.generation_id, "generation_id")
        _require_identifier(receipt.logical_repo_id, "logical_repo_id")
        if receipt.status not in _GENERATION_STATUSES:
            raise EvidenceError("generation status is not in the closed vocabulary")
        expected = self._corpus_by_logical_id().get(receipt.logical_repo_id)
        if expected is None:
            raise EvidenceError("generation names an unregistered repository")
        if receipt.source_commit != expected["commit"]:
            raise EvidenceError("source_commit does not match frozen corpus")
        if receipt.source_tree != expected["tree"]:
            raise EvidenceError("source_tree does not match frozen corpus")
        _require_sha1(receipt.source_commit, "source_commit")
        _require_sha1(receipt.source_tree, "source_tree")
        key = (receipt.generation_id, receipt.logical_repo_id)
        if any(
            (item.generation_id, item.logical_repo_id) == key
            for item in self._generation_receipts
        ):
            raise EvidenceError("duplicate repository receipt in one generation")

        if receipt.status == "succeeded":
            if receipt.indexed_commit_sha is None:
                raise EvidenceError("succeeded generation requires indexed_commit_sha")
            if receipt.indexed_commit_sha != receipt.source_commit:
                raise EvidenceError("indexed_commit_sha does not bind source_commit")
            if receipt.shard_digest is None:
                raise EvidenceError("succeeded generation requires shard_digest")
            if receipt.failure_code is not None:
                raise EvidenceError("succeeded generation cannot have failure_code")
            _require_sha1(receipt.indexed_commit_sha, "indexed_commit_sha")
            _require_sha256(receipt.shard_digest, "shard_digest")
        else:
            if receipt.failure_code not in _FAILURE_CODES:
                raise EvidenceError("failed or partial generation requires known failure_code")
            if receipt.indexed_commit_sha is not None:
                _require_sha1(receipt.indexed_commit_sha, "indexed_commit_sha")
            if receipt.shard_digest is not None:
                _require_sha256(receipt.shard_digest, "shard_digest")
        self._generation_receipts.append(receipt)

    def publish_generation(self, generation_id: str) -> PublicationReceipt:
        """Publish only a complete healthy corpus; retain a prior healthy generation."""

        _require_identifier(generation_id, "generation_id")
        receipts = [
            item for item in self._generation_receipts if item.generation_id == generation_id
        ]
        expected_ids = set(self._corpus_by_logical_id())
        complete = (
            len(receipts) == len(expected_ids)
            and {item.logical_repo_id for item in receipts} == expected_ids
            and all(item.status == "succeeded" for item in receipts)
        )
        if complete:
            self._active_generation_id = generation_id
            receipt = PublicationReceipt(
                generation_id=generation_id,
                state="PUBLISHED",
                active_generation_id=generation_id,
            )
        else:
            receipt = PublicationReceipt(
                generation_id=generation_id,
                state="PUBLISH_REFUSED",
                active_generation_id=self._active_generation_id,
            )
        self._publication_receipts.append(receipt)
        return receipt

    def record_trial(self, receipt: TrialReceipt) -> None:
        """Append exactly one result for each preregistered candidate trial."""

        if not isinstance(receipt, TrialReceipt):
            raise EvidenceError("trial receipt must be a TrialReceipt")
        if receipt.trial_id not in self._manifest.trial_order:
            raise EvidenceError("trial_id is not in the preregistered trial order")
        if any(item.trial_id == receipt.trial_id for item in self._trial_receipts):
            raise EvidenceError("retry is forbidden: every original trial remains evidence")
        if receipt.attempt_index != 1:
            raise EvidenceError("retry is forbidden: attempt_index must be one")
        if self._active_generation_id is None:
            raise EvidenceError("trial requires a published full generation")
        if receipt.generation_id != self._active_generation_id:
            raise EvidenceError("trial generation is not the active published generation")
        case_id, candidate = receipt.trial_id.split(":", 1)
        if candidate not in {"baseline", "zoekt"}:
            raise EvidenceError("trial candidate is not in the closed vocabulary")
        query = next(item for item in self._manifest.queries if item.case_id == case_id)
        if receipt.answer_key_digest != query.answer_key_digest:
            raise EvidenceError("trial answer_key_digest does not match frozen query")
        if receipt.source_census_digest != self._source_census_digest:
            raise EvidenceError("trial source_census_digest does not match ledger")
        _require_sha256(receipt.answer_key_digest, "answer_key_digest")
        _require_sha256(receipt.source_census_digest, "source_census_digest")
        _require_identifier(receipt.generation_id, "generation_id")
        if receipt.outcome not in _OUTCOMES:
            raise EvidenceError("trial outcome is not in the closed vocabulary")
        if type(receipt.query_completed) is not bool or type(receipt.truncated) is not bool:
            raise EvidenceError("query_completed and truncated must be booleans")
        if type(receipt.recall) not in {int, float} or not math.isfinite(receipt.recall):
            raise EvidenceError("recall must be finite")
        if not 0.0 <= receipt.recall <= 1.0:
            raise EvidenceError("recall must be in 0..1")
        if type(receipt.false_positive_count) is not int or receipt.false_positive_count < 0:
            raise EvidenceError("false_positive_count must be non-negative")
        if not isinstance(receipt.resource, ResourceObservation):
            raise EvidenceError("trial resource must be a ResourceObservation")
        _validate_identities(receipt.returned_identities)
        if receipt.outcome == "completed":
            if not receipt.query_completed or receipt.failure_code is not None:
                raise EvidenceError("completed trial must be complete without failure_code")
        else:
            if receipt.query_completed or receipt.failure_code not in _FAILURE_CODES:
                raise EvidenceError("failed trial requires incomplete query and known failure_code")
        self._trial_receipts.append(receipt)

    def freeze(self) -> EvaluationEvidence:
        """Return a deterministic evidence gate without mutating the ledger."""

        payload = self.to_payload()
        canonical = _canonical_json(payload)
        ledger_digest = hashlib.sha256(canonical).hexdigest()
        expected_trial_ids = set(self._manifest.trial_order)
        recorded_ids = {item.trial_id for item in self._trial_receipts}
        queries_by_case = {item.case_id: item for item in self._manifest.queries}
        transport_failed = tuple(
            item
            for item in self._trial_receipts
            if item.outcome != "completed" or not item.query_completed or item.truncated
        )
        grade_failed = tuple(
            item
            for item in self._trial_receipts
            if _trial_grade_fails(
                item,
                queries_by_case[item.trial_id.split(":", 1)[0]],
            )
        )
        failed = tuple(
            item
            for item in self._trial_receipts
            if item in transport_failed or item in grade_failed
        )
        all_resources_known = all(item.resource.is_known for item in self._trial_receipts)
        all_identity_bound = (
            self._active_generation_id is not None
            and all(item.generation_id == self._active_generation_id for item in self._trial_receipts)
            and all(
                item.source_census_digest == self._source_census_digest
                for item in self._trial_receipts
            )
        )
        reasons: list[str] = []
        if recorded_ids != expected_trial_ids:
            reasons.append("MISSING_OR_UNEXPECTED_TRIALS")
        if transport_failed:
            reasons.append("FAILED_OR_TRUNCATED_TRIAL")
        if grade_failed:
            reasons.append("TRIAL_GRADE_FAILURE")
        if not all_resources_known:
            reasons.append("UNKNOWN_RESOURCE_OBSERVATION")
        if not all_identity_bound:
            reasons.append("UNBOUND_GENERATION_OR_SOURCE")
        if self._run_kind == "synthetic":
            state = "NON_DECISION_SYNTHETIC_ONLY"
        elif reasons:
            state = "NON_DECISION_INCOMPLETE_EVIDENCE"
        else:
            state = "ELIGIBLE_REAL_EMPIRICAL_EVIDENCE"
        return EvaluationEvidence(
            state=state,
            manifest_digest=self._manifest.digest,
            source_census_digest=self._source_census_digest,
            ledger_digest=ledger_digest,
            run_kind=self._run_kind,
            active_generation_id=self._active_generation_id,
            required_trial_count=len(expected_trial_ids),
            recorded_trial_count=len(self._trial_receipts),
            failed_trial_count=len(failed),
            all_resources_known=all_resources_known,
            all_identity_bound=all_identity_bound,
            reasons=tuple(reasons),
            canonical_bytes=canonical,
        )

    def to_payload(self) -> dict[str, object]:
        """Render the exact strict-JSON ledger document for schema validation."""

        return {
            "schema_version": LEDGER_SCHEMA_VERSION,
            "manifest_digest": self._manifest.digest,
            "source_census_digest": self._source_census_digest,
            "run_kind": self._run_kind,
            "generation_receipts": [
                _generation_payload(item) for item in self._generation_receipts
            ],
            "publication_receipts": [
                _publication_payload(item) for item in self._publication_receipts
            ],
            "trial_receipts": [_trial_payload(item) for item in self._trial_receipts],
        }

    def _corpus_by_logical_id(self) -> dict[str, dict[str, str]]:
        return {str(item["logical_repo_id"]): dict(item) for item in self._manifest.corpus}


def run_paired_trials(
    ledger: EvaluationLedger,
    *,
    baseline_executor: TrialExecutor,
    zoekt_executor: TrialExecutor,
    answer_keys: Mapping[str, AnswerKey],
) -> tuple[TrialReceipt, ...]:
    """Run the frozen alternating order exactly once and retain every outcome.

    Executors receive the same immutable query declaration for a case. A
    timeout or callback crash becomes a typed failed trial and the remaining
    preregistered trials still run; callers cannot rerun only the bad row.
    """

    if not isinstance(ledger, EvaluationLedger):
        raise EvidenceError("paired harness requires an EvaluationLedger")
    if ledger.trial_receipts:
        raise EvidenceError("paired harness is one-shot; existing trials cannot be retried")
    if ledger.active_generation_id is None:
        raise EvidenceError("paired harness requires a published full generation")
    if not callable(baseline_executor) or not callable(zoekt_executor):
        raise EvidenceError("paired harness requires callable candidate executors")
    executors = {"baseline": baseline_executor, "zoekt": zoekt_executor}
    by_case = {query.case_id: query for query in ledger.manifest.queries}
    if not isinstance(answer_keys, Mapping) or set(answer_keys) != set(by_case):
        raise EvidenceError("paired harness requires one answer key per frozen case")
    for case_id, answer_key in answer_keys.items():
        if not isinstance(answer_key, AnswerKey) or answer_key.case_id != case_id:
            raise EvidenceError("answer key identity does not bind its frozen case")
        if answer_key.digest != by_case[case_id].answer_key_digest:
            raise EvidenceError("answer key bytes do not match the frozen query digest")
    receipts: list[TrialReceipt] = []
    for trial_id in ledger.manifest.trial_order:
        case_id, candidate = trial_id.split(":", 1)
        query = by_case[case_id]
        try:
            observation = executors[candidate](query)
            if not isinstance(observation, CandidateTrialObservation):
                raise TypeError("candidate executor returned an invalid observation")
        except TimeoutError:
            observation = _callback_failure("timeout", "TIMEOUT")
        except Exception:
            observation = _callback_failure("error", "PROCESS_CRASH")
        grade = grade_candidate_result(answer_keys[case_id], observation.returned_identities)
        receipt = TrialReceipt(
            trial_id=trial_id,
            attempt_index=1,
            outcome=observation.outcome,
            answer_key_digest=query.answer_key_digest,
            source_census_digest=ledger._source_census_digest,
            generation_id=ledger.active_generation_id,
            query_completed=observation.query_completed,
            truncated=observation.truncated,
            returned_identities=observation.returned_identities,
            recall=grade.recall,
            false_positive_count=grade.false_positive_count,
            resource=observation.resource,
            failure_code=observation.failure_code,
        )
        ledger.record_trial(receipt)
        receipts.append(receipt)
    return tuple(receipts)


def _callback_failure(outcome: str, failure_code: str) -> CandidateTrialObservation:
    return CandidateTrialObservation(
        outcome=outcome,
        query_completed=False,
        truncated=True,
        returned_identities=(),
        resource=ResourceObservation(
            cpu_ms=UNKNOWN_RESOURCE,
            rss_bytes=UNKNOWN_RESOURCE,
            disk_bytes=UNKNOWN_RESOURCE,
        ),
        failure_code=failure_code,
    )


def grade_candidate_result(
    answer_key: AnswerKey,
    returned_identities: tuple[tuple[str, str, str, str, int, int], ...],
) -> TrialGrade:
    """Independently grade candidate output against direct-source answer bytes."""

    if not isinstance(answer_key, AnswerKey):
        raise EvidenceError("grader requires a source-derived AnswerKey")
    _validate_identities(answer_key.expected_identities)
    _validate_identities(answer_key.forbidden_identities)
    _validate_identities(returned_identities)
    expected = set(answer_key.expected_identities)
    forbidden = set(answer_key.forbidden_identities)
    if expected & forbidden:
        raise EvidenceError("answer key expected and forbidden identities overlap")
    returned = set(returned_identities)
    hits = len(expected & returned)
    recall = 1.0 if not expected else hits / len(expected)
    return TrialGrade(
        recall=recall,
        false_positive_count=len(returned - expected),
    )


def _trial_grade_fails(receipt: TrialReceipt, query: EvaluationQuery) -> bool:
    required_recall = max(query.recall_threshold, query.completeness_threshold)
    return (
        receipt.recall < required_recall
        or receipt.false_positive_count > query.false_positive_ceiling
    )


def _generation_payload(receipt: GenerationReceipt) -> dict[str, object]:
    return {
        "generation_id": receipt.generation_id,
        "logical_repo_id": receipt.logical_repo_id,
        "source_commit": receipt.source_commit,
        "source_tree": receipt.source_tree,
        "status": receipt.status,
        "indexed_commit_sha": receipt.indexed_commit_sha,
        "shard_digest": receipt.shard_digest,
        "failure_code": receipt.failure_code,
    }


def _publication_payload(receipt: PublicationReceipt) -> dict[str, object]:
    return {
        "generation_id": receipt.generation_id,
        "state": receipt.state,
        "active_generation_id": receipt.active_generation_id,
    }


def _trial_payload(receipt: TrialReceipt) -> dict[str, object]:
    return {
        "trial_id": receipt.trial_id,
        "attempt_index": receipt.attempt_index,
        "outcome": receipt.outcome,
        "answer_key_digest": receipt.answer_key_digest,
        "source_census_digest": receipt.source_census_digest,
        "generation_id": receipt.generation_id,
        "query_completed": receipt.query_completed,
        "truncated": receipt.truncated,
        "returned_identities": [list(item) for item in receipt.returned_identities],
        "recall": receipt.recall,
        "false_positive_count": receipt.false_positive_count,
        "resource": receipt.resource.to_payload(),
        "failure_code": receipt.failure_code,
    }


def _validate_identities(
    identities: tuple[tuple[str, str, str, str, int, int], ...]
) -> None:
    if not isinstance(identities, tuple):
        raise EvidenceError("returned_identities must be an immutable tuple")
    if len(identities) != len(set(identities)):
        raise EvidenceError("returned_identities must not contain duplicates")
    for identity in identities:
        if (
            not isinstance(identity, tuple)
            or len(identity) != 6
            or not all(isinstance(value, str) and value for value in identity[:4])
            or type(identity[4]) is not int
            or type(identity[5]) is not int
            or identity[4] < 1
            or identity[5] < identity[4]
        ):
            raise EvidenceError("returned identity has an invalid closed shape")


def _require_identifier(value: str, label: str) -> None:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 256:
        raise EvidenceError(f"{label} must be bounded non-empty text")


def _require_sha1(value: str, label: str) -> None:
    if not isinstance(value, str) or _SHA1_RE.fullmatch(value) is None:
        raise EvidenceError(f"{label} must be a lowercase SHA-1")


def _require_sha256(value: str, label: str) -> None:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise EvidenceError(f"{label} must be a lowercase SHA-256")


def _canonical_json(payload: object) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")

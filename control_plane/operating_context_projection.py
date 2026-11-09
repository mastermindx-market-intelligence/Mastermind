from dataclasses import asdict, dataclass
import hashlib
import json


SCHEMA = "mastermind.operating_context_projection.v1"
INPUT_SHAPE_INVALID = "INPUT_SHAPE_INVALID"
OVER_BUDGET = "OVER_BUDGET"
DUPLICATE_IDENTITY = "DUPLICATE_IDENTITY"
MISSION_CONTEXT_MISMATCH = "MISSION_CONTEXT_MISMATCH"
RECEIPT_CONTEXT_MISMATCH = "RECEIPT_CONTEXT_MISMATCH"
CRITERIA_IDENTITY_MISMATCH = "CRITERIA_IDENTITY_MISMATCH"
REFUSAL_CODES = frozenset(
    {
        INPUT_SHAPE_INVALID,
        OVER_BUDGET,
        DUPLICATE_IDENTITY,
        MISSION_CONTEXT_MISMATCH,
        RECEIPT_CONTEXT_MISMATCH,
        CRITERIA_IDENTITY_MISMATCH,
    }
)
MISSINGNESS_CLASSES = frozenset(
    {"MISSING_PRODUCER", "NULL_BY_DESIGN", "EXCLUDED", "OMITTED", "DEGRADED"}
)
_MAX_ID_LENGTH = 256
_MAX_REASON_LENGTH = 2048
_MAX_ITEM_LENGTH = 4096
_MAX_DEGRADED_LENGTH = 2048
_MAX_SELECTED_ITEMS = 64
_MAX_CONTEXT_ENTRY_ITEMS = 32
_MAX_RECEIPTS = 8
_MAX_TOTAL_INPUT_BYTES = 256 * 1024
_MAX_TOTAL_OUTPUT_BYTES = 128 * 1024
_HEX_LENGTH = 64


class OperatingContextProjectionError(Exception):
    def __init__(self, code, message):
        if code not in REFUSAL_CODES:
            raise ValueError("unknown operating-context refusal code")
        super().__init__(message)
        self.code = code
        self.message = message


def _string(value, field_name, *, max_length=_MAX_ID_LENGTH, code=INPUT_SHAPE_INVALID):
    if type(value) is not str:
        raise OperatingContextProjectionError(code, f"{field_name} must be a string")
    if not value:
        raise OperatingContextProjectionError(code, f"{field_name} must not be empty")
    if len(value.encode("utf-8")) > max_length:
        raise OperatingContextProjectionError(OVER_BUDGET, f"{field_name} exceeds byte bound")
    return value


def _digest(value, field_name):
    if type(value) is not str:
        raise OperatingContextProjectionError(INPUT_SHAPE_INVALID, f"{field_name} must be a digest")
    if len(value) != _HEX_LENGTH:
        raise OperatingContextProjectionError(INPUT_SHAPE_INVALID, f"{field_name} must be SHA-256")
    try:
        int(value, 16)
    except ValueError as error:
        raise OperatingContextProjectionError(INPUT_SHAPE_INVALID, f"{field_name} must be SHA-256") from error
    if value != value.lower():
        raise OperatingContextProjectionError(INPUT_SHAPE_INVALID, f"{field_name} must be lowercase hex")
    return value


def _hex_digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class MissionFact:
    mission_id: str
    job_ref: str
    objective: str

    def __post_init__(self):
        _string(self.mission_id, "mission.mission_id")
        _string(self.job_ref, "mission.job_ref")
        _string(self.objective, "mission.objective", max_length=_MAX_REASON_LENGTH)


@dataclass(frozen=True, slots=True)
class AcceptedCriteriaFact:
    criteria_ref: str
    mission_id: str
    revision: str
    producer: str

    def __post_init__(self):
        _string(self.criteria_ref, "criteria.criteria_ref")
        _string(self.mission_id, "criteria.mission_id")
        _string(self.revision, "criteria.revision")
        _string(self.producer, "criteria.producer")


@dataclass(frozen=True, slots=True)
class MissionContextAssociationFact:
    mission_id: str
    context_bundle_id: str
    revision: str
    context_digest: str
    publisher: str
    association_id: str
    published_at: str

    def __post_init__(self):
        _string(self.mission_id, "association.mission_id")
        _string(self.context_bundle_id, "association.context_bundle_id")
        _string(self.revision, "association.revision")
        _digest(self.context_digest, "association.context_digest")
        _string(self.publisher, "association.publisher")
        _string(self.association_id, "association.association_id")
        _string(self.published_at, "association.published_at")


@dataclass(frozen=True, slots=True)
class ContextBundleFact:
    context_bundle_id: str
    revision: str
    context_digest: str
    selected_items: tuple[str, ...]
    excluded: tuple[str, ...]
    omitted_due_to_budget: tuple[str, ...]
    degraded: tuple[str, ...]

    def __post_init__(self):
        _string(self.context_bundle_id, "bundle.context_bundle_id")
        _string(self.revision, "bundle.revision")
        _digest(self.context_digest, "bundle.context_digest")
        for field_name, values, maximum, item_limit in (
            ("selected_items", self.selected_items, _MAX_ITEM_LENGTH, _MAX_SELECTED_ITEMS),
            ("excluded", self.excluded, _MAX_ITEM_LENGTH, _MAX_CONTEXT_ENTRY_ITEMS),
            ("omitted_due_to_budget", self.omitted_due_to_budget, _MAX_ITEM_LENGTH, _MAX_CONTEXT_ENTRY_ITEMS),
            ("degraded", self.degraded, _MAX_DEGRADED_LENGTH, _MAX_CONTEXT_ENTRY_ITEMS),
        ):
            if type(values) is not tuple:
                raise OperatingContextProjectionError(INPUT_SHAPE_INVALID, f"bundle.{field_name} must be tuple")
            if len(values) > item_limit:
                raise OperatingContextProjectionError(OVER_BUDGET, f"bundle.{field_name} count exceeds bound")
            for value in values:
                _string(value, f"bundle.{field_name}", max_length=maximum)


@dataclass(frozen=True, slots=True)
class SuppliedInputReceiptFact:
    mission_id: str
    context_bundle_id: str
    revision: str
    context_digest: str
    input_digest: str
    provider_turn_ref: str
    receipt_id: str
    producer: str
    published_at: str

    def __post_init__(self):
        _string(self.mission_id, "receipt.mission_id")
        _string(self.context_bundle_id, "receipt.context_bundle_id")
        _string(self.revision, "receipt.revision")
        _digest(self.context_digest, "receipt.context_digest")
        _digest(self.input_digest, "receipt.input_digest")
        _string(self.provider_turn_ref, "receipt.provider_turn_ref")
        _string(self.receipt_id, "receipt.receipt_id")
        _string(self.producer, "receipt.producer")
        _string(self.published_at, "receipt.published_at")


@dataclass(frozen=True, slots=True)
class MissingnessFact:
    missingness_class: str
    target_field: str
    producer_owner: str | None
    reason: str

    def __post_init__(self):
        if self.missingness_class not in MISSINGNESS_CLASSES:
            raise OperatingContextProjectionError(
                INPUT_SHAPE_INVALID, "missingness_class is closed"
            )
        _string(self.target_field, "missingness.target_field")
        if self.producer_owner is not None:
            _string(self.producer_owner, "missingness.producer_owner")
        _string(self.reason, "missingness.reason", max_length=_MAX_REASON_LENGTH)


@dataclass(frozen=True, slots=True)
class SourceDigestFact:
    source_id: str
    digest: str
    producer: str

    def __post_init__(self):
        _string(self.source_id, "source.source_id")
        _digest(self.digest, "source.digest")
        _string(self.producer, "source.producer")


@dataclass(frozen=True, slots=True)
class OperatingContextSnapshot:
    mission: MissionFact
    criteria: AcceptedCriteriaFact | None
    criteria_absent: MissingnessFact | None
    context_bundle: ContextBundleFact | None
    context_association: MissionContextAssociationFact | None
    context_association_absent: MissingnessFact | None
    receipts: tuple[SuppliedInputReceiptFact, ...]
    receipt_absent: MissingnessFact | None
    missingness: tuple[MissingnessFact, ...]
    conversation_ref: str | None
    artifact_ref: str | None
    review_ref: str | None
    source_digests: tuple[SourceDigestFact, ...]

    def __post_init__(self):
        if not isinstance(self.mission, MissionFact):
            raise OperatingContextProjectionError(INPUT_SHAPE_INVALID, "mission must be typed")
        self._validate_absence("criteria", self.criteria, self.criteria_absent, "criteria")
        self._validate_absence(
            "context_association", self.context_association, self.context_association_absent, "context_association"
        )
        self._validate_absence("receipts", self.receipts, self.receipt_absent, "receipt")
        if self.criteria is not None and self.criteria.mission_id != self.mission.mission_id:
            raise OperatingContextProjectionError(
                CRITERIA_IDENTITY_MISMATCH, "criteria belongs to another mission"
            )
        if self.context_association is not None and self.context_bundle is None:
            raise OperatingContextProjectionError(
                MISSION_CONTEXT_MISMATCH, "association has no exact bundle"
            )
        if self.context_bundle is not None and self.context_association is not None:
            association = self.context_association
            bundle = self.context_bundle
            if (
                association.mission_id != self.mission.mission_id
                or association.context_bundle_id != bundle.context_bundle_id
                or association.revision != bundle.revision
                or association.context_digest != bundle.context_digest
            ):
                raise OperatingContextProjectionError(
                    MISSION_CONTEXT_MISMATCH, "association and bundle identities disagree"
                )
        if type(self.receipts) is not tuple or len(self.receipts) > _MAX_RECEIPTS:
            raise OperatingContextProjectionError(INPUT_SHAPE_INVALID, "receipts shape is invalid")
        for receipt in self.receipts:
            if not isinstance(receipt, SuppliedInputReceiptFact):
                raise OperatingContextProjectionError(INPUT_SHAPE_INVALID, "receipt must be typed")
            if self.context_bundle is None:
                raise OperatingContextProjectionError(
                    RECEIPT_CONTEXT_MISMATCH, "receipt has no exact bundle"
                )
            if (
                receipt.mission_id != self.mission.mission_id
                or receipt.context_bundle_id != self.context_bundle.context_bundle_id
                or receipt.revision != self.context_bundle.revision
                or receipt.context_digest != self.context_bundle.context_digest
            ):
                raise OperatingContextProjectionError(
                    RECEIPT_CONTEXT_MISMATCH, "receipt and bundle identities disagree"
                )
        receipt_ids = [receipt.receipt_id for receipt in self.receipts]
        source_ids = [source.source_id for source in self.source_digests]
        if len(receipt_ids) != len(set(receipt_ids)) or len(source_ids) != len(set(source_ids)):
            raise OperatingContextProjectionError(DUPLICATE_IDENTITY, "fixture identity is duplicated")
        if type(self.missingness) is not tuple or type(self.source_digests) is not tuple:
            raise OperatingContextProjectionError(INPUT_SHAPE_INVALID, "snapshot tuple is invalid")
        for item in self.missingness:
            if not isinstance(item, MissingnessFact):
                raise OperatingContextProjectionError(INPUT_SHAPE_INVALID, "missingness must be typed")
        for item in self.source_digests:
            if not isinstance(item, SourceDigestFact):
                raise OperatingContextProjectionError(INPUT_SHAPE_INVALID, "source must be typed")
        for name, value in (
            ("conversation_ref", self.conversation_ref),
            ("artifact_ref", self.artifact_ref),
            ("review_ref", self.review_ref),
        ):
            if value is not None:
                _string(value, name)
        input_bytes = _serialized(asdict(self))
        if len(input_bytes) > _MAX_TOTAL_INPUT_BYTES:
            raise OperatingContextProjectionError(OVER_BUDGET, "total adapter input exceeds byte bound")

    def _validate_absence(self, present_field, present, absent, target_field):
        if present_field != "receipts" and present is not None and absent is not None:
            raise OperatingContextProjectionError(
                INPUT_SHAPE_INVALID, f"{present_field} and explicit absence conflict"
            )
        if absent is not None:
            if not isinstance(absent, MissingnessFact):
                raise OperatingContextProjectionError(INPUT_SHAPE_INVALID, "absence must be typed")
            expected = {
                "criteria": "MISSING_PRODUCER",
                "context_association": "MISSING_PRODUCER",
                "receipts": "SUPPLY_EVIDENCE_MISSING",
            }[present_field]
            if present_field == "receipts":
                if absent.missingness_class not in {"NULL_BY_DESIGN", "SUPPLY_EVIDENCE_MISSING"}:
                    raise OperatingContextProjectionError(
                        INPUT_SHAPE_INVALID, "receipt absence class is invalid"
                    )
            elif absent.missingness_class != expected:
                raise OperatingContextProjectionError(
                    INPUT_SHAPE_INVALID, f"{target_field} absence class is invalid"
                )


@dataclass(frozen=True, slots=True)
class OperatingContextProjection:
    schema: str
    mission_id: str
    job_ref: str
    objective_digest: str
    criteria_ref: str | None
    criteria_state: str
    context_bundle_id: str | None
    context_revision: str | None
    context_digest: str | None
    context_state: str
    selected_items: tuple[str, ...]
    excluded: tuple[str, ...]
    omitted_due_to_budget: tuple[str, ...]
    degraded: tuple[str, ...]
    supply_state: str
    receipt_digests: tuple[str, ...]
    conversation_ref: str | None
    artifact_ref: str | None
    review_ref: str | None
    source_digests: dict[str, dict[str, str]]
    missingness: tuple[dict[str, str | None], ...]

    def to_dict(self):
        return {
            "schema": self.schema,
            "mission_id": self.mission_id,
            "job_ref": self.job_ref,
            "objective_digest": self.objective_digest,
            "criteria_ref": self.criteria_ref,
            "criteria_state": self.criteria_state,
            "context_bundle_id": self.context_bundle_id,
            "context_revision": self.context_revision,
            "context_digest": self.context_digest,
            "context_state": self.context_state,
            "selected_items": list(self.selected_items),
            "excluded": list(self.excluded),
            "omitted_due_to_budget": list(self.omitted_due_to_budget),
            "degraded": list(self.degraded),
            "supply_state": self.supply_state,
            "receipt_digests": list(self.receipt_digests),
            "conversation_ref": self.conversation_ref,
            "artifact_ref": self.artifact_ref,
            "review_ref": self.review_ref,
            "source_digests": self.source_digests,
            "missingness": [dict(item) for item in self.missingness],
        }


def _serialized(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def serialize_operating_context(value):
    serialized = _serialized(value)
    if len(serialized) > _MAX_TOTAL_OUTPUT_BYTES:
        raise OperatingContextProjectionError(OVER_BUDGET, "serialized output exceeds byte bound")
    return serialized


def _source_digest(snapshot):
    mission_identity = "\0".join(
        (snapshot.mission.mission_id, snapshot.mission.job_ref, snapshot.mission.objective)
    )
    payload = {
        "mission": {
            "digest": _hex_digest(mission_identity),
            "producer_digest": _hex_digest("mission-owner"),
        },
        "context_bundle": {
            "digest": snapshot.context_bundle.context_digest,
            "producer_digest": _hex_digest("context-owner"),
        },
        "selection_policy": {
            "digest": _hex_digest("selected\0excluded\0omitted\0degraded"),
            "producer_digest": _hex_digest("selection-policy-owner"),
        },
    }
    for source in snapshot.source_digests:
        payload[source.source_id] = {
            "digest": source.digest,
            "producer_digest": _hex_digest(source.producer),
        }
    return payload


def project_operating_context(snapshot):
    """Purely project one immutable, already-published OC-F01/OC-F02 snapshot."""
    if not isinstance(snapshot, OperatingContextSnapshot):
        raise OperatingContextProjectionError(INPUT_SHAPE_INVALID, "snapshot must be typed")
    criteria_present = snapshot.criteria is not None
    context_present = snapshot.context_bundle is not None and snapshot.context_association is not None
    missingness = list(snapshot.missingness)
    if snapshot.criteria_absent is not None:
        missingness.append(snapshot.criteria_absent)
    if snapshot.context_association_absent is not None:
        missingness.append(snapshot.context_association_absent)
    if snapshot.receipt_absent is not None:
        missingness.append(snapshot.receipt_absent)
    for name, value in (
        ("conversation_ref", snapshot.conversation_ref),
        ("artifact_ref", snapshot.artifact_ref),
        ("review_ref", snapshot.review_ref),
    ):
        if value is None:
            missingness.append(
                MissingnessFact(
                    missingness_class="NULL_BY_DESIGN",
                    target_field=name,
                    producer_owner=None,
                    reason="optional reference is explicitly null",
                )
            )
    projected_missingness = tuple(
        {
            "missingness_class": item.missingness_class,
            "target_field": item.target_field,
            "producer_owner": item.producer_owner,
            "reason": item.reason,
        }
        for item in missingness
    )
    context_bundle = snapshot.context_bundle if context_present else None
    projection = OperatingContextProjection(
        schema=SCHEMA,
        mission_id=snapshot.mission.mission_id,
        job_ref=snapshot.mission.job_ref,
        objective_digest=_hex_digest(snapshot.mission.objective),
        criteria_ref=snapshot.criteria.criteria_ref if criteria_present else None,
        criteria_state="PRESENT" if criteria_present else "CRITERIA_RECORD_MISSING",
        context_bundle_id=context_bundle.context_bundle_id if context_bundle else None,
        context_revision=context_bundle.revision if context_bundle else None,
        context_digest=context_bundle.context_digest if context_bundle else None,
        context_state="ASSOCIATED" if context_present else "MISSION_CONTEXT_UNPUBLISHED",
        selected_items=tuple(
            _hex_digest(item) for item in context_bundle.selected_items
        ) if context_bundle else (),
        excluded=tuple(
            _hex_digest(item) for item in context_bundle.excluded
        ) if context_bundle else (),
        omitted_due_to_budget=tuple(
            _hex_digest(item) for item in context_bundle.omitted_due_to_budget
        ) if context_bundle else (),
        degraded=tuple(
            _hex_digest(item) for item in context_bundle.degraded
        ) if context_bundle else (),
        supply_state=(
            "SUPPLIED_CONFIRMED" if snapshot.receipts else
            "SUPPLY_EVIDENCE_MISSING" if snapshot.receipt_absent is not None else
            "SELECTED_ONLY"
        ),
        receipt_digests=tuple(_hex_digest(
            receipt.mission_id + "\0" + receipt.context_bundle_id + "\0" + receipt.revision + "\0"
            + receipt.context_digest + "\0" + receipt.input_digest + "\0" + receipt.provider_turn_ref + "\0"
            + receipt.receipt_id + "\0" + receipt.producer + "\0" + receipt.published_at
        ) for receipt in snapshot.receipts),
        conversation_ref=snapshot.conversation_ref,
        artifact_ref=snapshot.artifact_ref,
        review_ref=snapshot.review_ref,
        source_digests=_source_digest(snapshot),
        missingness=projected_missingness,
    )
    serialized = serialize_operating_context(projection.to_dict())
    return projection

"""OCR-3 Task 1 — closed continuation draft, capsule and ACK contracts.

Pure production-inert architecture layer.  This module must not:

* write Executive SQLite or any other store
* read a clock, mint a timestamp, or generate randomness
* spawn subprocesses, call providers, or open network sockets
* read credential bytes
* mutate Job/Attempt lifecycle, Wake state, capacity or placement
* import Executive Runtime, Operator Harness, Wake or session-target modules

Design law (``docs/superpowers/specs/2026-08-27-operator-continuation-idempotency-amendment.md``)
-----------------------------------------------------------------------------------------------

A target Attempt has **at most one** prepared continuation capsule identity.
Continuation therefore splits in two:

``OperatorContinuationDraft``
    Every semantic field, and nothing else.  It carries no ``schema``, no
    ``generated_at`` and no ``capsule_id``.  A draft is rebuilt from current
    canonical sources immediately before PREPARE and is not durable state.

``OperatorContinuation``
    The finalized closed wire: ``schema`` + every draft field +
    ``generated_at`` + ``capsule_id``.  ``capsule_id`` is SHA-256 over the
    canonical JSON of the finalized capsule excluding only ``capsule_id``
    itself, so the capsule is content-addressed and tamper-evident.

``generated_at`` is Executive-minted preparation evidence, never caller
entropy.  :func:`finalize_continuation` accepts it **only** from the trusted
Executive PREPARE transaction (OCR-3 Task 4).  It is deliberately not part of
any current-source builder API; ``build_current_continuation_draft()``
(OCR-3 Task 2) takes no timestamp or id parameter at all.

Closedness
----------

Two different senses of "closed" apply, and the plan requires both:

* the **top level** of each wire is an exact key set — unknown, missing or
  forbidden fields refuse;
* the **nested** values (``github_state``, ``prior_attempt_receipt``,
  ``checkpoint``, ``slack_dialogue_ref``) are a closed *grammar* rather than a
  frozen key set: bounded depth, bounded key/entry counts, canonical key
  names, a closed leaf type set, no control characters, and no secret-shaped
  leaves.  Freezing their business keys here would put source-shape authority
  in the contract layer instead of OCR-3 Task 2, which owns them.

Shape versus sufficiency
------------------------

This module enforces *shape, bounds, canonicity and secret-freedom*.
``control_plane.operator_continuation_sources`` (OCR-3 Task 2) owns
*sufficiency* — which refs and receipts a particular source->target transition
must carry.  The single exception is ``source_revisions``, which must be
non-empty here: a capsule with no Git source revision is not source-grounded,
so its immutability claim would be vacuous.

Mirrored patterns
-----------------

The identifier patterns below mirror their canonical owners so this pure
module imports neither the Executive Runtime nor the Wake-owned session-target
path.  This follows the existing precedent in
``control_plane.operator_harness_contract`` (``COMMAND_ID_RE``), and
``tests/test_operator_continuation.py`` pins each mirror equal to its source.

Schemas: ``mastermind.operator_continuation.v1``,
``mastermind.operator_continuation_ack.v1``.
"""
from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any


OPERATOR_CONTINUATION_SCHEMA = "mastermind.operator_continuation.v1"
OPERATOR_CONTINUATION_ACK_SCHEMA = "mastermind.operator_continuation_ack.v1"

# Mirrors control_plane.wake_events.JOB_ID_RE / ATTEMPT_ID_RE.  Attempt ids are
# minted as f"ATT-{uuid4().hex}" (control_plane/executive_runtime.py:8986); the
# ``ATT-target`` spelling in the plan text is placeholder prose, not a format.
JOB_ID_RE = re.compile(r"^JOB-\d{3,}$")
ATTEMPT_ID_RE = re.compile(r"^ATT-[0-9a-f]{32}$")
# Mirrors control_plane.session_targets.SESSION_ALIAS_RE.
SESSION_ALIAS_RE = re.compile(r"^[A-Z][A-Z0-9]*(-[A-Z0-9]+)+$")
# Mirrors control_plane.ceo_request._OPERATION_KEY_RE / MAX_OPERATION_KEY_CHARS.
OPERATION_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,95}$")
# Mirrors control_plane.executive_orchestration_principal._ID_RE.
PROVIDER_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
# Mirrors control_plane.wake_events.SEATS.
SEATS = frozenset({"chairman", "ceo", "coo"})

#: Lowercase SHA-256 hex.
DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
#: Full SHA-1 or SHA-256 Git object id.  Abbreviated ids are refused.
GIT_OBJECT_ID_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
#: Executive-minted preparation instant.  Exactly one canonical spelling is
#: accepted: UTC, ``Z`` suffix, exactly three fractional digits.  ``+00:00``
#: and second-precision spellings are refused because two spellings of one
#: instant would content-address to two capsule ids.
GENERATED_AT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")

_REF_RE = re.compile(r"^[^\x00-\x1f\x7f]{1,256}$")
_TEXT_RE = re.compile(r"^[^\x00-\x1f\x7f]{1,512}$")
_MAPPING_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_REVISION_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")

MAX_REFS = 32
MAX_KNOWN_UNKNOWNS = 16
MAX_SOURCE_REVISIONS = 16
MAX_MAPPING_KEYS = 32
MAX_MAPPING_DEPTH = 4
MAX_SEQUENCE_ITEMS = 32
MAX_LEAF_CHARS = 512
#: JSON integers are bounded to the exactly-representable range so a capsule
#: never depends on a consumer's float behaviour.
MAX_INT = 2**53 - 1
#: Bound on the finalized canonical capsule so it fits an existing Executive
#: Event payload.  No capsule table, file cache or blob store is introduced.
MAX_CAPSULE_BYTES = 16384

#: Semantic draft fields, in the order frozen by the OCR-3 plan.
DRAFT_FIELDS: tuple[str, ...] = (
    "root_job_id",
    "job_id",
    "source_attempt_id",
    "target_attempt_id",
    "operation_key",
    "target_seat",
    "session_alias",
    "effective_grant_digest",
    "source_authority_refs",
    "agentos_refs",
    "github_state",
    "prior_attempt_receipt",
    "checkpoint",
    "slack_dialogue_ref",
    "accepted_ruling_refs",
    "next_action",
    "known_unknowns",
    "source_revisions",
)
DRAFT_KEYS: frozenset[str] = frozenset(DRAFT_FIELDS)

#: The finalized wire adds exactly these three keys and nothing else.
CONTINUATION_ONLY_FIELDS: tuple[str, ...] = ("schema", "generated_at", "capsule_id")
CONTINUATION_KEYS: frozenset[str] = DRAFT_KEYS | frozenset(CONTINUATION_ONLY_FIELDS)

#: A draft that carries any of these is refused rather than silently stripped.
FORBIDDEN_DRAFT_FIELDS: frozenset[str] = frozenset(CONTINUATION_ONLY_FIELDS)

ACK_FIELDS: tuple[str, ...] = (
    "schema",
    "target_attempt_id",
    "capsule_id",
    "provider_session_id",
    "accepted",
)
ACK_KEYS: frozenset[str] = frozenset(ACK_FIELDS)

#: Provider account / native session / credential authority never enters a
#: continuation draft.  The bound current provider session is supplied
#: separately by the Executive PREPARE transaction and appears only on the ACK.
#: ``native_session_id`` is the forbidden synonym frozen by
#: ``control_plane.operator_harness_contract.FORBIDDEN_SESSION_SYNONYM``.
FORBIDDEN_KEY_MARKERS: tuple[str, ...] = (
    "access_token",
    "account_label",
    "api_key",
    "auth_token",
    "cookie",
    "credential",
    "native_handle",
    "native_session_id",
    "password",
    "private_key",
    "provider_account",
    "provider_session_id",
    "refresh_token",
    "secret",
    "session_token",
)

#: The existing secret-shaped-value family, verbatim from
#: ``control_plane.operator_harness_contract.AuthRealmFact.__post_init__``.
#: Matched case-insensitively as a substring.
#:
#: The word family applies to leaves of the OPEN nested grammar
#: (``github_state``, ``prior_attempt_receipt``, ``checkpoint``,
#: ``slack_dialogue_ref``) — the only place a credential can arrive as an
#: arbitrary labelled value.  Every top-level field is already format-pinned by
#: its own pattern, so those get the shape rules alone: naming a
#: credential-boundary ruling (``DEC:CRED0-CREDENTIAL-BOUNDARY``) is lawful
#: citation, and refusing it would make a draft unable to cite its own sources.
#: On nested leaves the family over-collects on purpose, which also enforces
#: the plan's own rule that ``prior_attempt_receipt`` carries a machine-derived
#: status receipt rather than copied provider error prose.
SECRET_VALUE_MARKERS: tuple[str, ...] = (
    "token",
    "refresh",
    "secret",
    "auth.json",
    "credential",
)

#: Credential formats recognisable by prefix.  Mirrors
#: ``common.redaction._SECRET_PREFIXES`` plus the Slack token shape.
_SECRET_PREFIX_RE = re.compile(
    r"(?i)(?:^|[^0-9A-Za-z])"
    r"(?:sb_secret_|sb_publishable_|sbp_|sk-ant-|sk-|github_pat_|ghp_|gho_|ghs_|xox[abprs]-)"
    r"[0-9A-Za-z+/=_-]{8,}"
)
#: High-entropy run detection, narrowed from ``common.redaction._TOKEN_SECRET_RE``.
#: ``-``, ``_``, ``/`` and ``.`` are treated as run BOUNDARIES rather than run
#: characters, because redaction over-collects harmlessly while this contract
#: *refuses the capsule*: with them included, ordinary material such as
#: ``docs/.../operator-continuation-idempotency-amendment.md`` and
#: ``research/MASTERMIND_EXECUTIVE_..._2026`` forms a 32+ run and every draft
#: citing its own sources would be rejected.
_LONG_RUN_RE = re.compile(r"(?<![0-9A-Za-z+=])[0-9A-Za-z+=]{32,}(?![0-9A-Za-z+=])")
#: Canonical identity/object hex is carved out of the run rule: 32 is the house
#: identity length (``ATT-<32hex>``, ``wake_events.IDENTITY_HEX_LEN``) and
#: 40/64 are full Git object ids, all of which this capsule carries lawfully and
#: validates by their own patterns.  A hex-encoded secret of exactly one of
#: those lengths is indistinguishable from them and is not detectable here.
_CANONICAL_HEX_RE = re.compile(r"^(?:[0-9a-f]{32}|[0-9a-f]{40}|[0-9a-f]{64})$")


class OperatorContinuationError(ValueError):
    """A continuation draft, capsule or ACK is not the closed wire."""


def canonical_bytes(value: Any) -> bytes:
    """Canonical JSON bytes: sorted keys, no spaces, UTF-8, no NaN/Infinity."""

    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise OperatorContinuationError(f"value is not canonical JSON data: {exc}") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


# ---------------------------------------------------------------------------
# leaf and scalar validation
# ---------------------------------------------------------------------------


def _assert_not_secret_shaped(text: str, *, name: str, word_family: bool = False) -> None:
    """Refuse a secret-shaped leaf.

    ``word_family`` selects whether :data:`SECRET_VALUE_MARKERS` applies; only
    the open nested grammar opts in.  The shape rules — credential prefixes and
    high-entropy runs — always apply.
    """

    if word_family:
        lowered = text.lower()
        for marker in SECRET_VALUE_MARKERS:
            if marker in lowered:
                raise OperatorContinuationError(
                    f"{name} carries secret-shaped material ({marker!r})"
                )
    if _SECRET_PREFIX_RE.search(text) is not None:
        raise OperatorContinuationError(f"{name} carries a credential-prefixed value")
    for run in _LONG_RUN_RE.findall(text):
        if _CANONICAL_HEX_RE.fullmatch(run) is None:
            raise OperatorContinuationError(
                f"{name} carries a high-entropy run that is not canonical identity hex"
            )


def _text(
    value: Any,
    *,
    name: str,
    pattern: re.Pattern[str],
    word_family: bool = False,
) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise OperatorContinuationError(f"{name} must be non-empty canonical text")
    if pattern.fullmatch(value) is None:
        raise OperatorContinuationError(f"{name} has an unsupported form")
    _assert_not_secret_shaped(value, name=name, word_family=word_family)
    return value


def _member(value: Any, *, name: str, allowed: frozenset[str]) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise OperatorContinuationError(f"{name} must be one of {sorted(allowed)}")
    return value


def _refs(value: Any, *, name: str, limit: int = MAX_REFS) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise OperatorContinuationError(f"{name} must be a sequence of refs")
    items = tuple(value)
    if len(items) > limit:
        raise OperatorContinuationError(f"{name} exceeds {limit} entries")
    refs: list[str] = []
    for index, item in enumerate(items):
        ref = _text(item, name=f"{name}[{index}]", pattern=_REF_RE)
        if ref in refs:
            raise OperatorContinuationError(f"{name} repeats {ref!r}")
        refs.append(ref)
    return tuple(refs)


def _texts(value: Any, *, name: str, limit: int) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise OperatorContinuationError(f"{name} must be a sequence of text entries")
    items = tuple(value)
    if len(items) > limit:
        raise OperatorContinuationError(f"{name} exceeds {limit} entries")
    texts: list[str] = []
    for index, item in enumerate(items):
        text = _text(item, name=f"{name}[{index}]", pattern=_TEXT_RE)
        if text in texts:
            raise OperatorContinuationError(f"{name} repeats {text!r}")
        texts.append(text)
    return tuple(texts)


def _assert_key_allowed(key: str, *, name: str) -> None:
    lowered = key.lower()
    for marker in FORBIDDEN_KEY_MARKERS:
        if marker in lowered:
            raise OperatorContinuationError(
                f"{name} carries provider/credential authority ({marker!r})"
            )


def _bounded_json(value: Any, *, name: str, depth: int = 0) -> Any:
    """One closed bounded JSON value: no floats, no control chars, no secrets."""

    if depth > MAX_MAPPING_DEPTH:
        raise OperatorContinuationError(f"{name} nests deeper than {MAX_MAPPING_DEPTH}")
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        if abs(value) > MAX_INT:
            raise OperatorContinuationError(f"{name} integer is outside the exact range")
        return value
    if isinstance(value, str):
        if len(value) > MAX_LEAF_CHARS:
            raise OperatorContinuationError(f"{name} exceeds {MAX_LEAF_CHARS} characters")
        if _TEXT_RE.fullmatch(value) is None and value != "":
            raise OperatorContinuationError(f"{name} contains control characters")
        _assert_not_secret_shaped(value, name=name, word_family=True)
        return value
    if isinstance(value, Mapping):
        if len(value) > MAX_MAPPING_KEYS:
            raise OperatorContinuationError(f"{name} exceeds {MAX_MAPPING_KEYS} keys")
        resolved: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str) or _MAPPING_KEY_RE.fullmatch(key) is None:
                raise OperatorContinuationError(f"{name} has an unsupported key {key!r}")
            _assert_key_allowed(key, name=f"{name}.{key}")
            resolved[key] = _bounded_json(item, name=f"{name}.{key}", depth=depth + 1)
        return resolved
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        items = tuple(value)
        if len(items) > MAX_SEQUENCE_ITEMS:
            raise OperatorContinuationError(f"{name} exceeds {MAX_SEQUENCE_ITEMS} items")
        return [
            _bounded_json(item, name=f"{name}[{index}]", depth=depth + 1)
            for index, item in enumerate(items)
        ]
    raise OperatorContinuationError(
        f"{name} holds an unsupported JSON type {type(value).__name__}"
    )


def _bounded_mapping(value: Any, *, name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise OperatorContinuationError(f"{name} must be an object")
    resolved = _bounded_json(value, name=name)
    assert isinstance(resolved, dict)  # _bounded_json returns dict for a Mapping
    return resolved


def _optional_bounded_mapping(value: Any, *, name: str) -> dict[str, Any] | None:
    if value is None:
        return None
    return _bounded_mapping(value, name=name)


def _source_revisions(value: Any) -> dict[str, str]:
    name = "source_revisions"
    if not isinstance(value, Mapping):
        raise OperatorContinuationError(f"{name} must be an object")
    if not value:
        raise OperatorContinuationError(f"{name} must name at least one Git object id")
    if len(value) > MAX_SOURCE_REVISIONS:
        raise OperatorContinuationError(f"{name} exceeds {MAX_SOURCE_REVISIONS} entries")
    resolved: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or _REVISION_KEY_RE.fullmatch(key) is None:
            raise OperatorContinuationError(f"{name} has an unsupported key {key!r}")
        _assert_key_allowed(key, name=f"{name}.{key}")
        if not isinstance(item, str) or GIT_OBJECT_ID_RE.fullmatch(item) is None:
            raise OperatorContinuationError(
                f"{name}.{key} must be a full lowercase Git object id"
            )
        resolved[key] = item
    return resolved


def _closed(value: Any, *, name: str, keys: frozenset[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise OperatorContinuationError(f"{name} must be an object")
    actual = set(value)
    if actual != keys:
        raise OperatorContinuationError(
            f"{name} fields drifted; missing={sorted(keys - actual)}, "
            f"unknown={sorted(actual - keys)}"
        )
    return value


# ---------------------------------------------------------------------------
# contracts
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class OperatorContinuationDraft:
    """Semantic continuation material only.

    No ``schema``, no ``generated_at``, no ``capsule_id``, no provider account
    label and no native/provider session id.  Rebuilt from current canonical
    sources immediately before PREPARE; never durable lifecycle state.
    """

    root_job_id: str
    job_id: str
    source_attempt_id: str
    target_attempt_id: str
    operation_key: str
    target_seat: str
    session_alias: str
    effective_grant_digest: str
    source_authority_refs: tuple[str, ...]
    agentos_refs: tuple[str, ...]
    github_state: dict[str, Any]
    prior_attempt_receipt: dict[str, Any]
    checkpoint: dict[str, Any] | None
    slack_dialogue_ref: dict[str, Any] | None
    accepted_ruling_refs: tuple[str, ...]
    next_action: str
    known_unknowns: tuple[str, ...]
    source_revisions: dict[str, str]

    def __post_init__(self) -> None:
        set_ = object.__setattr__
        set_(self, "root_job_id", _text(self.root_job_id, name="root_job_id", pattern=JOB_ID_RE))
        set_(self, "job_id", _text(self.job_id, name="job_id", pattern=JOB_ID_RE))
        set_(
            self,
            "source_attempt_id",
            _text(self.source_attempt_id, name="source_attempt_id", pattern=ATTEMPT_ID_RE),
        )
        set_(
            self,
            "target_attempt_id",
            _text(self.target_attempt_id, name="target_attempt_id", pattern=ATTEMPT_ID_RE),
        )
        if self.source_attempt_id == self.target_attempt_id:
            raise OperatorContinuationError(
                "source_attempt_id and target_attempt_id must differ"
            )
        set_(
            self,
            "operation_key",
            _text(self.operation_key, name="operation_key", pattern=OPERATION_KEY_RE),
        )
        set_(self, "target_seat", _member(self.target_seat, name="target_seat", allowed=SEATS))
        set_(
            self,
            "session_alias",
            _text(self.session_alias, name="session_alias", pattern=SESSION_ALIAS_RE),
        )
        if not isinstance(self.effective_grant_digest, str) or (
            DIGEST_RE.fullmatch(self.effective_grant_digest) is None
        ):
            raise OperatorContinuationError(
                "effective_grant_digest must be a lowercase SHA-256 digest"
            )
        set_(
            self,
            "source_authority_refs",
            _refs(self.source_authority_refs, name="source_authority_refs"),
        )
        set_(self, "agentos_refs", _refs(self.agentos_refs, name="agentos_refs"))
        set_(self, "github_state", _bounded_mapping(self.github_state, name="github_state"))
        set_(
            self,
            "prior_attempt_receipt",
            _bounded_mapping(self.prior_attempt_receipt, name="prior_attempt_receipt"),
        )
        set_(
            self,
            "checkpoint",
            _optional_bounded_mapping(self.checkpoint, name="checkpoint"),
        )
        set_(
            self,
            "slack_dialogue_ref",
            _optional_bounded_mapping(self.slack_dialogue_ref, name="slack_dialogue_ref"),
        )
        set_(
            self,
            "accepted_ruling_refs",
            _refs(self.accepted_ruling_refs, name="accepted_ruling_refs"),
        )
        set_(self, "next_action", _text(self.next_action, name="next_action", pattern=_TEXT_RE))
        set_(
            self,
            "known_unknowns",
            _texts(self.known_unknowns, name="known_unknowns", limit=MAX_KNOWN_UNKNOWNS),
        )
        set_(self, "source_revisions", _source_revisions(self.source_revisions))

    @classmethod
    def from_dict(cls, value: Any) -> "OperatorContinuationDraft":
        if isinstance(value, Mapping):
            present = set(value) & FORBIDDEN_DRAFT_FIELDS
            if present:
                raise OperatorContinuationError(
                    "continuation draft must not author "
                    f"{sorted(present)}; the Executive PREPARE transaction owns them"
                )
        raw = _closed(value, name="continuation draft", keys=DRAFT_KEYS)
        return cls(**{field: raw[field] for field in DRAFT_FIELDS})

    def to_dict(self) -> dict[str, Any]:
        return {
            "root_job_id": self.root_job_id,
            "job_id": self.job_id,
            "source_attempt_id": self.source_attempt_id,
            "target_attempt_id": self.target_attempt_id,
            "operation_key": self.operation_key,
            "target_seat": self.target_seat,
            "session_alias": self.session_alias,
            "effective_grant_digest": self.effective_grant_digest,
            "source_authority_refs": list(self.source_authority_refs),
            "agentos_refs": list(self.agentos_refs),
            "github_state": copy.deepcopy(self.github_state),
            "prior_attempt_receipt": copy.deepcopy(self.prior_attempt_receipt),
            "checkpoint": copy.deepcopy(self.checkpoint),
            "slack_dialogue_ref": copy.deepcopy(self.slack_dialogue_ref),
            "accepted_ruling_refs": list(self.accepted_ruling_refs),
            "next_action": self.next_action,
            "known_unknowns": list(self.known_unknowns),
            "source_revisions": dict(self.source_revisions),
        }


@dataclasses.dataclass(frozen=True)
class OperatorContinuation:
    """The finalized, content-addressed, immutable continuation capsule.

    Construct through :func:`finalize_continuation` (Executive PREPARE) or
    :func:`validate_continuation` (replay).  ``capsule_id`` is re-derived on
    construction, so a tampered capsule cannot be built.
    """

    schema: str
    generated_at: str
    capsule_id: str
    draft: OperatorContinuationDraft

    def __post_init__(self) -> None:
        if self.schema != OPERATOR_CONTINUATION_SCHEMA:
            raise OperatorContinuationError("unsupported continuation schema")
        _assert_generated_at(self.generated_at)
        if not isinstance(self.capsule_id, str) or DIGEST_RE.fullmatch(self.capsule_id) is None:
            raise OperatorContinuationError("capsule_id must be a lowercase SHA-256 digest")
        if not isinstance(self.draft, OperatorContinuationDraft):
            raise OperatorContinuationError("draft must be an OperatorContinuationDraft")
        expected = _digest(_capsule_without_id(self.draft, generated_at=self.generated_at))
        if self.capsule_id != expected:
            raise OperatorContinuationError(
                "capsule_id does not content-address this capsule"
            )
        payload = canonical_bytes(self.to_dict())
        if len(payload) > MAX_CAPSULE_BYTES:
            raise OperatorContinuationError(
                f"finalized capsule exceeds {MAX_CAPSULE_BYTES} canonical bytes"
            )

    @property
    def target_attempt_id(self) -> str:
        return self.draft.target_attempt_id

    @property
    def source_attempt_id(self) -> str:
        return self.draft.source_attempt_id

    @property
    def semantic_digest(self) -> str:
        """The semantic draft digest this capsule was prepared from."""

        return semantic_draft_digest(self.draft)

    @classmethod
    def from_dict(cls, value: Any) -> "OperatorContinuation":
        raw = _closed(value, name="continuation capsule", keys=CONTINUATION_KEYS)
        if raw["schema"] != OPERATOR_CONTINUATION_SCHEMA:
            raise OperatorContinuationError("unsupported continuation schema")
        draft = OperatorContinuationDraft(**{field: raw[field] for field in DRAFT_FIELDS})
        return cls(
            schema=OPERATOR_CONTINUATION_SCHEMA,
            generated_at=raw["generated_at"],
            capsule_id=raw["capsule_id"],
            draft=draft,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            **self.draft.to_dict(),
            "generated_at": self.generated_at,
            "capsule_id": self.capsule_id,
        }

    def canonical_bytes(self) -> bytes:
        """The exact immutable bytes every retry/reconciliation must reuse."""

        return canonical_bytes(self.to_dict())


@dataclasses.dataclass(frozen=True)
class ContinuationAck:
    """Evidence that the exact bound provider session consumed the exact capsule.

    Not model-authored authority, not Job completion, not Wake
    ``TARGET_ACKNOWLEDGED``.
    """

    schema: str
    target_attempt_id: str
    capsule_id: str
    provider_session_id: str
    accepted: bool

    def __post_init__(self) -> None:
        if self.schema != OPERATOR_CONTINUATION_ACK_SCHEMA:
            raise OperatorContinuationError("unsupported continuation ack schema")
        object.__setattr__(
            self,
            "target_attempt_id",
            _text(self.target_attempt_id, name="target_attempt_id", pattern=ATTEMPT_ID_RE),
        )
        if not isinstance(self.capsule_id, str) or DIGEST_RE.fullmatch(self.capsule_id) is None:
            raise OperatorContinuationError("capsule_id must be a lowercase SHA-256 digest")
        if (
            not isinstance(self.provider_session_id, str)
            or PROVIDER_SESSION_ID_RE.fullmatch(self.provider_session_id) is None
        ):
            raise OperatorContinuationError("provider_session_id has an unsupported form")
        if self.accepted is not True:
            raise OperatorContinuationError("continuation ack must set accepted=true")

    @classmethod
    def from_dict(cls, value: Any) -> "ContinuationAck":
        raw = _closed(value, name="continuation ack", keys=ACK_KEYS)
        return cls(
            schema=raw["schema"],
            target_attempt_id=raw["target_attempt_id"],
            capsule_id=raw["capsule_id"],
            provider_session_id=raw["provider_session_id"],
            accepted=raw["accepted"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "target_attempt_id": self.target_attempt_id,
            "capsule_id": self.capsule_id,
            "provider_session_id": self.provider_session_id,
            "accepted": self.accepted,
        }


# ---------------------------------------------------------------------------
# digest, finalization and validation
# ---------------------------------------------------------------------------


def _assert_generated_at(value: Any) -> str:
    if not isinstance(value, str) or GENERATED_AT_RE.fullmatch(value) is None:
        raise OperatorContinuationError(
            "generated_at must be canonical UTC 'YYYY-MM-DDTHH:MM:SS.mmmZ'"
        )
    month = int(value[5:7])
    day = int(value[8:10])
    hour = int(value[11:13])
    minute = int(value[14:16])
    second = int(value[17:19])
    if not (1 <= month <= 12 and 1 <= day <= 31 and hour <= 23 and minute <= 59 and second <= 59):
        raise OperatorContinuationError("generated_at is not a real UTC instant")
    return value


def _capsule_without_id(
    draft: OperatorContinuationDraft, *, generated_at: str
) -> dict[str, Any]:
    return {
        "schema": OPERATOR_CONTINUATION_SCHEMA,
        **draft.to_dict(),
        "generated_at": generated_at,
    }


def semantic_draft_digest(draft: OperatorContinuationDraft) -> str:
    """SHA-256 over the canonical JSON of the semantic draft.

    Any semantic field change changes this digest.  ``generated_at`` and
    ``capsule_id`` never participate, so the digest answers "is this the same
    continuation?" independently of when it was prepared.
    """

    if not isinstance(draft, OperatorContinuationDraft):
        raise OperatorContinuationError("draft must be an OperatorContinuationDraft")
    return _digest(draft.to_dict())


def finalize_continuation(
    draft: OperatorContinuationDraft,
    *,
    generated_at: str,
) -> OperatorContinuation:
    """Mint the one immutable capsule for a target Attempt.

    TRUSTED SEAM.  ``generated_at`` is accepted only from the fenced Executive
    PREPARE transaction, which mints it from the Runtime clock under the target
    Attempt's lease.  No model, adapter, Slack, OpenClaw or external caller may
    reach this function; it is deliberately absent from the current-source
    builder API.  Same draft + same Executive instant gives byte-identical
    capsule bytes and an identical ``capsule_id``.
    """

    if not isinstance(draft, OperatorContinuationDraft):
        raise OperatorContinuationError("draft must be an OperatorContinuationDraft")
    stamp = _assert_generated_at(generated_at)
    final_without_id = _capsule_without_id(draft, generated_at=stamp)
    capsule_id = _digest(final_without_id)
    return OperatorContinuation.from_dict({**final_without_id, "capsule_id": capsule_id})


def validate_continuation(
    value: Any,
    *,
    draft: OperatorContinuationDraft | None = None,
) -> OperatorContinuation:
    """Validate a finalized capsule wire and re-derive its content address.

    When ``draft`` is supplied the capsule must carry that exact semantic
    draft — the replay check that refuses a semantically different preparation
    under the same target Attempt.
    """

    capsule = (
        value
        if isinstance(value, OperatorContinuation)
        else OperatorContinuation.from_dict(value)
    )
    if draft is not None:
        expected = semantic_draft_digest(draft)
        if capsule.semantic_digest != expected:
            raise OperatorContinuationError(
                "capsule semantic digest does not match the supplied draft"
            )
    return capsule


def validate_continuation_ack(
    value: Any,
    *,
    capsule: OperatorContinuation | None = None,
    provider_session_id: str | None = None,
) -> ContinuationAck:
    """Validate an ACK against the exact prepared capsule and provider session.

    A wrong or blank target Attempt, capsule id, provider session, or
    ``accepted != True`` refuses.  Supplying ``capsule`` / ``provider_session_id``
    is how the Executive proves the ACK belongs to the one prepared capsule and
    the one currently bound session.
    """

    ack = value if isinstance(value, ContinuationAck) else ContinuationAck.from_dict(value)
    if capsule is not None:
        if not isinstance(capsule, OperatorContinuation):
            raise OperatorContinuationError("capsule must be an OperatorContinuation")
        if ack.capsule_id != capsule.capsule_id:
            raise OperatorContinuationError("ack does not name the prepared capsule")
        if ack.target_attempt_id != capsule.target_attempt_id:
            raise OperatorContinuationError("ack does not name the target Attempt")
    if provider_session_id is not None:
        if (
            not isinstance(provider_session_id, str)
            or PROVIDER_SESSION_ID_RE.fullmatch(provider_session_id) is None
        ):
            raise OperatorContinuationError("provider_session_id has an unsupported form")
        if ack.provider_session_id != provider_session_id:
            raise OperatorContinuationError("ack does not name the bound provider session")
    return ack


__all__ = [
    "ACK_FIELDS",
    "ACK_KEYS",
    "ATTEMPT_ID_RE",
    "CONTINUATION_KEYS",
    "CONTINUATION_ONLY_FIELDS",
    "ContinuationAck",
    "DIGEST_RE",
    "DRAFT_FIELDS",
    "DRAFT_KEYS",
    "FORBIDDEN_DRAFT_FIELDS",
    "FORBIDDEN_KEY_MARKERS",
    "GENERATED_AT_RE",
    "GIT_OBJECT_ID_RE",
    "JOB_ID_RE",
    "MAX_CAPSULE_BYTES",
    "MAX_KNOWN_UNKNOWNS",
    "MAX_MAPPING_DEPTH",
    "MAX_MAPPING_KEYS",
    "MAX_REFS",
    "MAX_SEQUENCE_ITEMS",
    "MAX_SOURCE_REVISIONS",
    "OPERATION_KEY_RE",
    "OPERATOR_CONTINUATION_ACK_SCHEMA",
    "OPERATOR_CONTINUATION_SCHEMA",
    "OperatorContinuation",
    "OperatorContinuationDraft",
    "OperatorContinuationError",
    "PROVIDER_SESSION_ID_RE",
    "SEATS",
    "SECRET_VALUE_MARKERS",
    "SESSION_ALIAS_RE",
    "canonical_bytes",
    "finalize_continuation",
    "semantic_draft_digest",
    "validate_continuation",
    "validate_continuation_ack",
]

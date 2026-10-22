"""control_plane.executive_cross_plane_view — read-only cockpit consumer of a Session Truth Receipt.

This module is a **consumer**, never a second truth plane.  It accepts one
already-normalized, already-validated ``mastermind.session_truth_receipt.v1``
document and renders bounded, deterministic per-workstream cards for an
Executive cockpit.  It deliberately owns **no**:

* truth store, queue, cursor, retry, polling loop, cache or lease;
* acquisition of GitHub/Linear/Slack/Agent OS state (it re-reads nothing — the
  receipt is the entire input, which is what stops this view from scraping the
  same two planes a second time);
* authentication, OAuth, credential resolution or any actor construction;
* identity inference, fuzzy matching, title/branch-similarity joins or
  first-match resolution — every join is an exact identifier compared against
  an exact identifier already present in the receipt;
* a drift engine, and **not a health engine either**.  Verdicts are copied
  verbatim out of ``receipt["findings"]``; health is the receipt's
  ``admission`` block, passed through untouched.  This module never classifies
  drift, never assigns a severity, never names a canonical or repair owner, and
  never invents an all-clear.  ``state`` below describes only whether *this
  consumer* could render the receipt faithfully.

Reused, never reimplemented: ``SessionTruthContractError``, ``RECEIPT_SCHEMA``,
``FINDING_SEVERITIES`` and ``semantic_hash`` from ``session_truth_contract``;
``semantic_projection`` from ``session_truth``; and the exact-identity closure
``select_session_truth_scope`` from ``session_truth_scope`` — the same function
the rules engine itself calls, so a card can never select a different identity
set than the findings it renders.

Four refusals this view exists to make structurally impossible
--------------------------------------------------------------------
1. **Merged/green is not proof.**  Delivery (``state``/``ci``/``draft``/SHAs)
   and proof (``completion``/``proof_state``) are rendered as two separate
   blocks that are never collapsed into one verdict.  A card cannot say
   "done"; only the receipt's own findings can say whether proof holds.
2. **No running Job is ever asserted.**  Linear status is a *projection*, not
   execution liveness, and Slack is *transport*, not consumption.  Every issue
   card carries ``execution.state = "NOT_PROJECTED"``, so no consumer of this
   document can render a running Job out of a Linear column or a Slack message.
3. **Unavailable is never empty.**  Every plane that is not readable is named
   with its own owner ``reason``.  It never renders as a source that reported
   "nothing", and a row this consumer could not type is counted and named too —
   ``session_truth_rules`` draws the same line, and an empty list here would
   silently invert a blocking finding.
4. **Nothing is silently dropped.**  A finding whose subject does not resolve
   to a workstream card is returned in document-level
   ``unattributed_findings``, not discarded.

Freshness is *relative to a caller-supplied* ``evaluated_at``.  This module
reads no clock: with no ``evaluated_at`` every source is ``UNKNOWN``, never
``CURRENT``.  Callers own the staleness threshold (``stale_after_seconds``);
this module invents no policy constant.

Determinism: the same receipt plus the same arguments always yields a
byte-identical document.  Cards, identities, PRs, issues, findings and
unattributed findings are each emitted in a total order, and no
``generated_at`` clock is stamped into the output.

Unbound carriers and issues are **never** assigned to the sole selected
workstream merely because the closure has cardinality one. Only a positive
owner-authored workstream key makes a workstream card. Selected-but-unbound
identities are returned as explicit typed degradation evidence instead of
being silently dropped or falsely linked.

Scope note: this is the first vertical.  It renders the exact-identity closure
the receipt's own scope selects and is exercised end-to-end against a single
MAS issue identity (``MAS-6``); it does not aggregate a portfolio.
"""
from __future__ import annotations

import copy
import json
from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from control_plane.session_truth import semantic_projection
from control_plane.session_truth_contract import (
    FINDING_SEVERITIES,
    RECEIPT_SCHEMA,
    SessionTruthContractError,
    semantic_hash,
)
from control_plane.session_truth_scope import select_session_truth_scope

SCHEMA = "mastermind.executive_cross_plane_view.v1"

#: Closed document key set, asserted by the compositor (fabric_job_view's idiom).
OUTPUT_KEYS = frozenset(
    {
        "schema",
        "state",
        "evaluated_at",
        "stale_after_seconds",
        "source_receipt",
        "execution",
        "admission",
        "finding_counts",
        "unavailable_sources",
        "digest_check",
        "cards",
        "unattributed_findings",
        "unknowns",
        "capability",
    }
)
CARD_KEYS = frozenset(
    {"workstream", "identities", "github", "linear", "findings", "finding_counts"}
)
IDENTITIES_KEYS = frozenset(
    {"linear_issue_ids", "repositories", "pull_requests", "operation_keys"}
)
PULL_REQUEST_CARD_KEYS = frozenset(
    {
        "repository",
        "number",
        "delivery",
        "pickup_head_sha",
        "proof",
        "linked_linear_issue_id",
        "operation_key",
        "wave",
        "portfolio_mode",
        "authority",
    }
)
ISSUE_CARD_KEYS = frozenset(
    {
        "issue_id",
        "status",
        "workstream",
        "parent_id",
        "projection_revision",
        "declared_completion",
        "updated_at",
        "github_relations",
        "execution",
    }
)
GITHUB_BLOCK_KEYS = frozenset(
    {"available", "observed_at", "freshness", "reason", "pull_requests"}
)
LINEAR_BLOCK_KEYS = frozenset(
    {"available", "observed_at", "freshness", "reason", "issues"}
)
SOURCE_KEYS = frozenset({"available", "observed_at", "freshness", "reason"})
UNAVAILABLE_SOURCE_KEYS = frozenset({"source", "reason", "omission_effect"})
DIGEST_CHECK_KEYS = frozenset({"state", "stored", "recomputed"})
IDENTITY_KEYS = frozenset({"repository", "number"})

#: Freshness is a *comparison against caller-supplied evidence*, never a verdict.
FRESHNESS_STATES = ("CURRENT", "STALE", "UNKNOWN", "UNAVAILABLE")
#: Read fidelity of this consumer only.  Not a health verdict: the receipt's
#: ``admission`` block is the sole health authority and is passed through intact.
DOCUMENT_STATES = ("CONSUMED", "DEGRADED", "REJECTED")

#: Reuses fabric_job_view's closed missingness vocabulary rather than inventing
#: one.  ``tests/test_executive_cross_plane_view.py`` asserts these stay equal to
#: ``fabric_job_view.MISSINGNESS_CLASSES`` so the two cannot drift silently.
MISSINGNESS_CLASSES = frozenset(
    {"MISSING_PRODUCER", "NULL_BY_DESIGN", "EXCLUDED", "OMITTED", "DEGRADED"}
)

#: Terminal ordering, matching ``session_truth_rules._SEVERITY_ORDER``.  Used only
#: to *order* and *count* already-classified findings; it never assigns severity.
_SEVERITY_ORDER = {"FATAL": 0, "BLOCKING": 1, "WARNING": 2, "INFO": 3}

# A new severity must fail loudly here rather than silently sort last and count
# as zero, which is what an un-guarded local copy of the ordering would do.
if set(_SEVERITY_ORDER) != set(FINDING_SEVERITIES):  # pragma: no cover - import guard
    raise RuntimeError(
        "severity ordering is out of step with FINDING_SEVERITIES; the cockpit "
        "consumer must never silently order or count an unclassified severity"
    )

#: Fields every rule finding must carry; the rest (``source_a``, ``source_b``,
#: ``details``) are preserved verbatim rather than dropped, because
#: ``COMPLETION_OWNER_EVIDENCE_UNKNOWN`` uses ``details.reason`` to separate two
#: distinct failure modes that would otherwise render as identical rows.
_FINDING_REQUIRED_KEYS = frozenset(
    {
        "code",
        "severity",
        "subject",
        "canonical_owner",
        "repair_owner",
        "modification_consequence",
    }
)

_EXECUTION_NOT_PROJECTED_REASON = (
    "Linear status is a projection and Slack is transport; this view renders no "
    "execution liveness and never asserts a running Job"
)

_PROJECTED_PLANES = ("github", "linear")
#: Present in every receipt, read by this consumer only for availability/absence.
_OBSERVED_PLANES = ("agentos", "slack", "executive", "identities")

_RECEIPT_KEYS = frozenset(
    {"schema", "scope", "skillpack", "observation", "observations", "findings", "admission",
     "semantic_hash"}
)
_OBSERVATION_KEYS = frozenset(
    {"agentos", "github", "linear", "slack", "executive", "identities"}
)


# ---------------------------------------------------------------------------
# small shared shapes
# ---------------------------------------------------------------------------

def _fact(
    missingness_class: str,
    target_field: str,
    producer_owner: str | None,
    reason: str,
) -> dict[str, Any]:
    if missingness_class not in MISSINGNESS_CLASSES:
        raise ValueError(f"unknown missingness_class {missingness_class!r}")
    return {
        "missingness_class": missingness_class,
        "target_field": target_field,
        "producer_owner": producer_owner,
        "reason": reason,
    }


def _timestamp(value: object) -> datetime | None:
    """Parse one offset-aware ISO-8601 stamp, or return ``None``.

    Mirrors ``session_truth_rules``: a naive stamp is not a timestamp.  This is
    date parsing, not a drift rule, so it is deliberately not imported from the
    rules module (whose helper is private).
    """

    if not isinstance(value, str) or not value:
        return None
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _available(source: object) -> bool:
    return isinstance(source, Mapping) and source.get("available") is True


def _rows(source: object, key: str) -> list[dict[str, Any]]:
    if not _available(source):
        return []
    value = source.get(key)
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, Mapping)]


def _text(value: object) -> str | None:
    """Exact-identity text, or ``None``.  Never normalized, trimmed or guessed."""

    return value if isinstance(value, str) and value else None


def _whole(value: object) -> int | None:
    """A strict integer, or ``None``.  Never coerces a float/bool/str/sequence."""

    return value if type(value) is int else None


def _sort_whole(value: object) -> int:
    """Total-order key for a value that may be absent or malformed."""

    return value if type(value) is int else 0


def _count_findings(findings: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts = {severity: 0 for severity in sorted(FINDING_SEVERITIES)}
    for finding in findings:
        severity = finding.get("severity")
        if severity in counts:
            counts[severity] += 1
    return counts


def _finding_sort_key(finding: Mapping[str, Any]) -> tuple[int, str, str]:
    return (
        _SEVERITY_ORDER[finding["severity"]],
        str(finding.get("code") or ""),
        str(finding.get("subject") or ""),
    )


def _finding_card(finding: Mapping[str, Any]) -> dict[str, Any]:
    """Verbatim projection of an existing rule finding — never reclassified.

    ``source_a``, ``source_b`` and ``details`` ride along untouched: they are the
    evidence the rules engine attached, and dropping them would collapse distinct
    findings onto identical card rows.
    """

    missing = sorted(_FINDING_REQUIRED_KEYS - set(finding))
    if missing:
        raise SessionTruthContractError(
            f"finding is missing required key(s): {', '.join(missing)}"
        )
    return copy.deepcopy(dict(finding))


# ---------------------------------------------------------------------------
# freshness
# ---------------------------------------------------------------------------

def _validate_stale_after(stale_after_seconds: object) -> float | None:
    if stale_after_seconds is None:
        return None
    if isinstance(stale_after_seconds, bool) or not isinstance(
        stale_after_seconds, (int, float)
    ):
        raise SessionTruthContractError(
            "stale_after_seconds must be null or a non-negative number"
        )
    if stale_after_seconds < 0:
        raise SessionTruthContractError(
            "stale_after_seconds must be null or a non-negative number"
        )
    return float(stale_after_seconds)


def _freshness(
    source: object,
    *,
    evaluated_at: datetime | None,
    stale_after_seconds: float | None,
) -> str:
    """Compare one source's own ``observed_at`` against caller-supplied evidence."""

    if not _available(source):
        return "UNAVAILABLE"
    observed = _timestamp(source.get("observed_at"))
    if evaluated_at is None or stale_after_seconds is None or observed is None:
        return "UNKNOWN"
    age = (evaluated_at - observed).total_seconds()
    if age < 0:
        # An observation stamped in the future relative to the caller's own
        # evidence is not "very fresh"; it is untrustworthy as a comparison.
        return "UNKNOWN"
    return "STALE" if age > stale_after_seconds else "CURRENT"


def _source_block(
    source: object,
    *,
    evaluated_at: datetime | None,
    stale_after_seconds: float | None,
) -> dict[str, Any]:
    block = {
        "available": _available(source),
        "observed_at": source.get("observed_at") if isinstance(source, Mapping) else None,
        "freshness": _freshness(
            source, evaluated_at=evaluated_at, stale_after_seconds=stale_after_seconds
        ),
        "reason": None,
    }
    if not block["available"]:
        # Refusal 3: an unreadable source carries its own owner reason, so it can
        # never be mistaken for a source that reported nothing.
        block["reason"] = (
            _text(source.get("reason"))
            if isinstance(source, Mapping)
            else "observation is not an object"
        )
    assert set(block) == SOURCE_KEYS
    return block


# ---------------------------------------------------------------------------
# identity validation (the receipt must be a receipt before it is believed)
# ---------------------------------------------------------------------------

def _validate_receipt(receipt: object) -> None:
    """Refuse anything that is not a complete, well-typed R1 receipt.

    This is a *shape* gate, not a re-validation of the receipt's content: the
    contract module already validated the inputs that produced it.  It exists so
    that a truncated, hand-edited or foreign document is degraded rather than
    rendered into a cockpit card.  Unknown top-level keys are refused for the
    same reason ``session_truth_contract._exact_keys`` refuses them.
    """

    if not isinstance(receipt, Mapping):
        raise SessionTruthContractError("receipt must be an object")
    keys = set(receipt)
    missing = sorted(_RECEIPT_KEYS - keys)
    if missing:
        raise SessionTruthContractError(
            f"receipt is missing key(s): {', '.join(missing)}"
        )
    unknown = sorted(keys - _RECEIPT_KEYS)
    if unknown:
        raise SessionTruthContractError(
            f"unknown top-level key(s) in receipt: {', '.join(unknown)}"
        )
    if receipt["schema"] != RECEIPT_SCHEMA:
        raise SessionTruthContractError(f"receipt.schema must be exactly {RECEIPT_SCHEMA!r}")
    observations = receipt["observations"]
    if not isinstance(observations, Mapping):
        raise SessionTruthContractError("receipt.observations must be an object")
    missing_planes = sorted(_OBSERVATION_KEYS - set(observations))
    if missing_planes:
        raise SessionTruthContractError(
            f"receipt.observations is missing plane(s): {', '.join(missing_planes)}"
        )
    if not isinstance(receipt["scope"], Mapping):
        raise SessionTruthContractError("receipt.scope must be an object")
    if not isinstance(receipt["admission"], Mapping):
        raise SessionTruthContractError("receipt.admission must be an object")
    semantic = receipt["semantic_hash"]
    if not isinstance(semantic, str) or not semantic.startswith("sha256:"):
        raise SessionTruthContractError("receipt.semantic_hash must be an owner digest")
    findings = receipt["findings"]
    if not isinstance(findings, list):
        raise SessionTruthContractError("receipt.findings must be a list")
    for index, finding in enumerate(findings):
        if not isinstance(finding, Mapping):
            raise SessionTruthContractError(f"receipt.findings[{index}] must be an object")
        if finding.get("severity") not in FINDING_SEVERITIES:
            raise SessionTruthContractError(
                f"receipt.findings[{index}].severity is invalid: {finding.get('severity')!r}"
            )
        missing_finding = sorted(_FINDING_REQUIRED_KEYS - set(finding))
        if missing_finding:
            raise SessionTruthContractError(
                f"receipt.findings[{index}] is missing key(s): {', '.join(missing_finding)}"
            )


def _digest_check(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Re-derive the receipt's own semantic hash with the owner's own function.

    A mismatch means the document no longer hashes to the digest it claims, so
    this consumer reports it instead of displaying the stored digest as if it
    were provenance.  It degrades rather than rejects: the content is still
    rendered verbatim and nothing is inferred from it.
    """

    stored = receipt.get("semantic_hash")
    try:
        recomputed = semantic_hash(semantic_projection(receipt))
    except (SessionTruthContractError, RecursionError, TypeError, ValueError):
        state = "UNVERIFIABLE"
        recomputed = None
    else:
        state = "VERIFIED" if recomputed == stored else "MISMATCH"
    block = {"state": state, "stored": stored, "recomputed": recomputed}
    assert set(block) == DIGEST_CHECK_KEYS
    return block


# ---------------------------------------------------------------------------
# cards
# ---------------------------------------------------------------------------

def _pull_request_card(pr: Mapping[str, Any]) -> dict[str, Any]:
    """Render one GitHub carrier.

    ``delivery`` and ``proof`` stay separate on purpose (refusal 1): a merged,
    green PR with a nonterminal ``proof_state`` must be readable as *not*
    proven without this module ever saying so on its own authority.
    """

    card = {
        "repository": pr.get("repository"),
        "number": pr.get("number"),
        "delivery": {
            "state": pr.get("state"),
            "ci": pr.get("ci"),
            "draft": pr.get("draft"),
            "base_sha": pr.get("base_sha"),
            "head_sha": pr.get("head_sha"),
            "merge_sha": pr.get("merge_sha"),
        },
        "pickup_head_sha": pr.get("pickup_head_sha"),
        "proof": {
            "declared_completion": pr.get("completion"),
            "proof_state": pr.get("proof_state"),
        },
        "linked_linear_issue_id": _text(pr.get("linear")),
        "operation_key": _text(pr.get("operation_key")),
        "wave": _text(pr.get("wave")),
        "portfolio_mode": _text(pr.get("portfolio_mode")),
        "authority": _text(pr.get("authority")),
    }
    assert set(card) == PULL_REQUEST_CARD_KEYS
    return card


def _issue_card(issue: Mapping[str, Any]) -> dict[str, Any]:
    relations = []
    for relation in (issue.get("github_relations") or []):
        if not isinstance(relation, Mapping):
            continue
        relations.append(
            {
                "repository": relation.get("repository"),
                "number": relation.get("number"),
                "relation": relation.get("relation"),
            }
        )
    relations.sort(
        key=lambda row: (
            str(row["repository"]),
            _sort_whole(row["number"]),
            str(row["relation"] or ""),
        )
    )
    card = {
        "issue_id": issue.get("id"),
        "status": issue.get("status"),
        "workstream": _text(issue.get("workstream")),
        "parent_id": _text(issue.get("parent_id")),
        "projection_revision": issue.get("projection_revision"),
        "declared_completion": issue.get("completion"),
        "updated_at": issue.get("updated_at"),
        "github_relations": relations,
        # Refusal 2: rendered, never absent, so a downstream consumer cannot
        # read a missing key as permission to infer execution state.
        "execution": {"state": "NOT_PROJECTED", "reason": _EXECUTION_NOT_PROJECTED_REASON},
    }
    assert set(card) == ISSUE_CARD_KEYS
    return card


def _subject_identities(text: str) -> tuple[tuple[str, int] | None, str | None]:
    """Split one finding subject into its exact carrier and issue identities."""

    if "->" in text:
        left, _, right = text.partition("->")
        return None, left if left else None
    if "#" in text and not text.startswith("WS:"):
        repository, _, number = text.rpartition("#")
        try:
            return (repository, int(number)), None
        except ValueError:
            return None, None
    if text.startswith("WS:"):
        # A workstream-scoped subject carries no carrier or issue identity.
        return None, None
    if text.startswith("MAS-"):
        return None, text
    return None, None


def _one(mapping: Mapping[Any, str], key: Any) -> set[str]:
    """A single-valued exact mapping lookup, always returned as a set."""

    value = mapping.get(key)
    return {value} if isinstance(value, str) and value else set()


def _resolve_subject(
    subject: object,
    *,
    pr_to_workstream: Mapping[tuple[str, int], str],
    issue_to_workstream: Mapping[str, str],
    operation_to_workstreams: Mapping[str, list[str]],
    workstreams: frozenset[str],
) -> set[str]:
    """Map one finding subject onto workstream keys by exact identifier only.

    Every branch compares an exact id to an exact id.  No title, branch,
    similarity or ordering fallback exists, and an unresolvable subject yields
    the empty set so the caller routes it to ``unattributed_findings``.
    """

    text = _text(subject)
    if not text:
        return set()

    # "A->B" parent/child divergence: attribute to every card holding either end.
    if "->" in text:
        left, _, right = text.partition("->")
        return _one(issue_to_workstream, left) | _one(issue_to_workstream, right)

    # "<owner>/<repo>#<number>" carrier identity.
    if "#" in text and not text.startswith("WS:"):
        repository, _, number = text.rpartition("#")
        try:
            identity = (repository, int(number))
        except ValueError:
            return set()
        return _one(pr_to_workstream, identity)

    # "WS:<KEY>#<wave>" workstream-scoped subject (MULTIPLE_ACTIVE_CARRIERS).
    if text.startswith("WS:"):
        workstream = text.split("#", 1)[0]
        return {workstream} if workstream in workstreams else set()

    # A known Linear issue id.
    if text in issue_to_workstream:
        return {issue_to_workstream[text]}

    # A known operation key.
    return set(operation_to_workstreams.get(text, ()))


# ---------------------------------------------------------------------------
# composition (pure)
# ---------------------------------------------------------------------------

def _source_receipt_block(receipt: Mapping[str, Any] | None) -> dict[str, Any]:
    """Traceability to the exact receipt this card was rendered from."""

    observation = receipt.get("observation") if isinstance(receipt, Mapping) else None
    schema = receipt.get("schema") if isinstance(receipt, Mapping) else None
    semantic = receipt.get("semantic_hash") if isinstance(receipt, Mapping) else None
    return {
        "schema": schema,
        "semantic_hash": semantic,
        "observation": {
            "started_at": observation.get("started_at") if isinstance(observation, Mapping) else None,
            "ended_at": observation.get("ended_at") if isinstance(observation, Mapping) else None,
        },
    }


def _document(
    *,
    state: str,
    evaluated_at: str | None,
    stale_after_seconds: float | None,
    source_receipt: dict,
    admission: Mapping[str, Any] | None,
    finding_counts: dict,
    unavailable_sources: list,
    digest_check: dict | None,
    cards: list,
    unattributed_findings: list,
    unknowns: list,
) -> dict:
    document = {
        "schema": SCHEMA,
        "state": state,
        "evaluated_at": evaluated_at,
        "stale_after_seconds": stale_after_seconds,
        "source_receipt": source_receipt,
        "execution": {"state": "NOT_PROJECTED", "reason": _EXECUTION_NOT_PROJECTED_REASON},
        "admission": None if admission is None else copy.deepcopy(dict(admission)),
        "finding_counts": finding_counts,
        "unavailable_sources": unavailable_sources,
        "digest_check": digest_check,
        "cards": cards,
        "unattributed_findings": unattributed_findings,
        "unknowns": sorted(
            unknowns,
            key=lambda fact: (
                fact["missingness_class"],
                fact["target_field"],
                fact["producer_owner"] or "",
                fact["reason"],
            ),
        ),
        # Read-only and effect-free by construction.  Deliberately carries no
        # health verdict: the receipt's ``admission`` is the health authority,
        # and a self-assessed "PROVEN" here would read as an all-clear that
        # nothing in this module is entitled to issue.
        "capability": {"read_only": True, "effect": "NONE"},
    }
    assert set(document) == OUTPUT_KEYS
    return document


def _rejected_document(reason: str, *, evaluated_at: str | None, stale_after_seconds) -> dict:
    """A closed, honest document for a receipt this view refused to believe."""

    return _document(
        state="REJECTED",
        evaluated_at=evaluated_at,
        stale_after_seconds=stale_after_seconds,
        source_receipt={"schema": None, "semantic_hash": None,
                        "observation": {"started_at": None, "ended_at": None}},
        admission=None,
        finding_counts=_count_findings(()),
        unavailable_sources=[],
        digest_check=None,
        cards=[],
        unattributed_findings=[],
        unknowns=[_fact("DEGRADED", "receipt", "session_truth", reason)],
    )


def build_cross_plane_view(
    receipt: Mapping[str, Any],
    *,
    evaluated_at: str | None = None,
    stale_after_seconds: float | None = None,
    strict: bool = False,
) -> dict[str, Any]:
    """Render one cockpit document from one already-built Session Truth receipt.

    ``evaluated_at`` is the caller's evidence clock and is the only time
    reference used; this function reads no clock of its own.  ``strict=True``
    raises :class:`SessionTruthContractError` instead of degrading to a
    ``REJECTED``/``DEGRADED`` document.  The input is never mutated and nothing
    is written.
    """

    stale_after = _validate_stale_after(stale_after_seconds)
    evaluated = _timestamp(evaluated_at) if evaluated_at is not None else None
    if evaluated_at is not None and evaluated is None:
        raise SessionTruthContractError("evaluated_at must be an offset-aware timestamp")

    try:
        _validate_receipt(receipt)
    except SessionTruthContractError as exc:
        if strict:
            raise
        return _rejected_document(
            f"receipt refused by the read-only consumer: {exc}",
            evaluated_at=evaluated_at,
            stale_after_seconds=stale_after,
        )

    observations = receipt["observations"]
    scope = receipt["scope"]
    digest_check = _digest_check(receipt)

    # Reuse the rules engine's own closure: a card can never select an identity
    # set that differs from the one its findings were computed against.
    inputs = {"scope": scope, **{name: observations.get(name) for name in sorted(_OBSERVATION_KEYS)}}
    try:
        selection = select_session_truth_scope(inputs)
    except (SessionTruthContractError, TypeError, ValueError, KeyError) as exc:
        # The shared selector assumes rows that the normalizer already typed. A
        # hand-edited or foreign receipt can violate that (an unhashable PR number
        # raises TypeError inside it), so this consumer degrades a typed refusal
        # rather than letting an unrelated module's assumption crash the cockpit.
        if strict:
            raise SessionTruthContractError(
                f"exact-identity closure could not be computed: {exc}"
            ) from exc
        return _document(
            state="DEGRADED",
            evaluated_at=evaluated_at,
            stale_after_seconds=stale_after,
            source_receipt=_source_receipt_block(receipt),
            admission=receipt["admission"],
            finding_counts=_count_findings(receipt["findings"]),
            unavailable_sources=[],
            digest_check=digest_check,
            cards=[],
            unattributed_findings=sorted(
                (_finding_card(row) for row in receipt["findings"] if isinstance(row, Mapping)),
                key=_finding_sort_key,
            ),
            unknowns=[_fact("DEGRADED", "receipt.scope", "session_truth",
                            f"exact-identity closure unavailable: {exc}")],
        )

    raw_prs = _rows(observations.get("github"), "pull_requests")
    raw_issues = _rows(observations.get("linear"), "issues")
    github_rows: dict[tuple[str, int], dict[str, Any]] = {}
    dropped_prs = 0
    for row in raw_prs:
        repository = _text(row.get("repository"))
        number = _whole(row.get("number"))
        if repository is None or number is None:
            dropped_prs += 1
            continue
        github_rows[(repository, number)] = dict(row)
    linear_rows: dict[str, dict[str, Any]] = {}
    dropped_issues = 0
    for row in raw_issues:
        issue_id = _text(row.get("id"))
        if issue_id is None:
            dropped_issues += 1
            continue
        linear_rows[issue_id] = dict(row)

    scope_repositories = {
        value
        for value in (scope.get("repositories") or [])
        if isinstance(value, str) and value
    }

    # Card membership is the closure UNION every identity this receipt's own
    # findings name, repository-fenced.  A receipt produced by an earlier rules
    # revision may carry a finding about a carrier the current closure no longer
    # selects; the finding is still testimony about that carrier, so the carrier
    # joins its card rather than being orphaned by closure drift.
    findings = [row for row in receipt["findings"] if isinstance(row, Mapping)]
    named_prs: set[tuple[str, int]] = set()
    named_issues: set[str] = set()
    for finding in findings:
        text = _text(finding.get("subject"))
        if not text:
            continue
        for endpoint in text.split("->"):
            identity, issue_id = _subject_identities(endpoint)
            if identity is not None and identity[0] in scope_repositories:
                named_prs.add(identity)
            if issue_id is not None:
                named_issues.add(issue_id)

    selected_prs = sorted(
        (selection.github_pull_requests | named_prs) & set(github_rows)
    )
    selected_issues = sorted(
        (selection.linear_issues | named_issues) & set(linear_rows)
    )

    # Exact identity -> workstream attribution, built from the receipt's own rows.
    pr_to_workstream: dict[tuple[str, int], str] = {}
    issue_to_workstream: dict[str, str] = {}
    operation_hits: dict[str, set[str]] = {}

    # Selection is not attribution. An operation-key or explicitly seeded ID
    # can bring a carrier/issue into scope without proving any WS ownership.
    # Keep those identities in typed omission evidence, never on a WS card.
    unattributed_pr_identities: list[tuple[str, int]] = []
    unattributed_issue_ids: list[str] = []

    pr_cards_by_workstream: dict[str, list[dict[str, Any]]] = {}
    for identity in selected_prs:
        pr = github_rows[identity]
        workstream = _text(pr.get("workstream"))
        if workstream not in selection.workstreams:
            unattributed_pr_identities.append(identity)
            continue
        pr_to_workstream[identity] = workstream
        pr_cards_by_workstream.setdefault(workstream, []).append(_pull_request_card(pr))
        operation_key = _text(pr.get("operation_key"))
        if operation_key and operation_key in selection.operation_keys:
            operation_hits.setdefault(operation_key, set()).add(workstream)

    issue_cards_by_workstream: dict[str, list[dict[str, Any]]] = {}
    for issue_id in selected_issues:
        issue = linear_rows[issue_id]
        workstream = _text(issue.get("workstream"))
        if workstream not in selection.workstreams:
            unattributed_issue_ids.append(issue_id)
            continue
        issue_to_workstream[issue_id] = workstream
        issue_cards_by_workstream.setdefault(workstream, []).append(_issue_card(issue))

    operation_to_workstreams = {key: sorted(value) for key, value in operation_hits.items()}

    # Route each existing finding to its card(s) by exact subject only.
    findings_by_workstream: dict[str, list[dict[str, Any]]] = {}
    unattributed: list[dict[str, Any]] = []
    for finding in findings:
        targets = _resolve_subject(
            finding.get("subject"),
            pr_to_workstream=pr_to_workstream,
            issue_to_workstream=issue_to_workstream,
            operation_to_workstreams=operation_to_workstreams,
            workstreams=selection.workstreams,
        )
        if not targets:
            unattributed.append(_finding_card(finding))
            continue
        for workstream in sorted(targets):
            findings_by_workstream.setdefault(workstream, []).append(_finding_card(finding))

    github_block = _source_block(
        observations.get("github"), evaluated_at=evaluated, stale_after_seconds=stale_after
    )
    linear_block = _source_block(
        observations.get("linear"), evaluated_at=evaluated, stale_after_seconds=stale_after
    )

    cards: list[dict[str, Any]] = []
    for workstream in sorted(selection.workstreams):
        pull_requests = sorted(
            pr_cards_by_workstream.get(workstream, []),
            key=lambda card: (str(card["repository"]), _sort_whole(card["number"])),
        )
        issues = sorted(
            issue_cards_by_workstream.get(workstream, []), key=lambda card: str(card["issue_id"])
        )
        card_findings = sorted(findings_by_workstream.get(workstream, []), key=_finding_sort_key)
        identities = {
            "linear_issue_ids": [card["issue_id"] for card in issues],
            "repositories": sorted({str(card["repository"]) for card in pull_requests}),
            "pull_requests": [
                {"repository": card["repository"], "number": card["number"]}
                for card in pull_requests
            ],
            "operation_keys": sorted(
                {str(card["operation_key"]) for card in pull_requests if card["operation_key"]}
            ),
        }
        assert set(identities) == IDENTITIES_KEYS
        for identity in identities["pull_requests"]:
            assert set(identity) == IDENTITY_KEYS
        github_plane = {**github_block, "pull_requests": pull_requests}
        linear_plane = {**linear_block, "issues": issues}
        assert set(github_plane) == GITHUB_BLOCK_KEYS
        assert set(linear_plane) == LINEAR_BLOCK_KEYS
        cards.append(
            {
                "workstream": workstream,
                "identities": identities,
                "github": github_plane,
                "linear": linear_plane,
                "findings": card_findings,
                "finding_counts": _count_findings(card_findings),
            }
        )

    # Refusal 3, applied to every plane: an unreadable source is named with its
    # own owner reason, and never rendered as one that reported nothing.
    plane_sources = {
        name: observations.get(name) for name in _OBSERVED_PLANES + _PROJECTED_PLANES
    }
    plane_sources["skillpack"] = receipt.get("skillpack")
    unavailable_sources = []
    for name in sorted(plane_sources):
        source = plane_sources[name]
        if _available(source):
            continue
        entry = {
            "source": name,
            "reason": (
                _text(source.get("reason"))
                if isinstance(source, Mapping)
                else "observation is not an object"
            ),
            "omission_effect": (
                "absent rows are not testimony; no plane may be rendered as empty"
            ),
        }
        assert set(entry) == UNAVAILABLE_SOURCE_KEYS
        unavailable_sources.append(entry)

    unknowns: list[dict[str, Any]] = []
    for name, block in (("github", github_block), ("linear", linear_block)):
        if block["freshness"] == "STALE":
            unknowns.append(
                _fact("DEGRADED", f"observations.{name}", name,
                      f"source observation is stale relative to evaluated_at: "
                      f"{block['observed_at']!r}")
            )
        elif block["freshness"] == "UNKNOWN":
            unknowns.append(
                _fact("MISSING_PRODUCER", f"observations.{name}.freshness", name,
                      "no caller-supplied evaluation window; freshness is undetermined")
            )
    # Exact identity is observable without turning scope cardinality into
    # an authored owner edge. Every unbound selected row remains accounted for.
    for repository, number in unattributed_pr_identities:
        unknowns.append(
            _fact("DEGRADED", "cards.github.pull_requests", "github",
                  f"{repository}#{number}: selected GitHub carrier has no exact "
                  "source-authored workstream binding; not attributed to a workstream")
        )
    for issue_id in unattributed_issue_ids:
        unknowns.append(
            _fact("DEGRADED", "cards.linear.issues", "linear",
                  f"{issue_id}: selected Linear issue has no exact source-authored "
                  "workstream binding; not attributed to a workstream")
        )
    if dropped_prs:
        unknowns.append(
            _fact("DEGRADED", "observations.github.pull_requests", "github",
                  f"{dropped_prs} carrier row(s) carried no exact repository/number identity "
                  "and were not rendered")
        )
    if dropped_issues:
        unknowns.append(
            _fact("DEGRADED", "observations.linear.issues", "linear",
                  f"{dropped_issues} issue row(s) carried no exact MAS id and were not rendered")
        )
    if digest_check["state"] != "VERIFIED":
        unknowns.append(
            _fact("DEGRADED", "semantic_hash", "session_truth",
                  f"receipt digest is {digest_check['state']}; stored provenance may not "
                  "describe this content")
        )
    if unattributed:
        unknowns.append(
            _fact("EXCLUDED", "cards.findings", "session_truth",
                  f"{len(unattributed)} finding(s) carry no workstream-scoped subject")
        )
    for name in _OBSERVED_PLANES:
        # Only ever announced for a plane that *was* read: an unreadable plane is
        # already named with its owner reason above, and conflating the two would
        # report an owner failure as a viewer choice.
        if _available(observations.get(name)):
            unknowns.append(
                _fact("EXCLUDED", f"observations.{name}", name,
                      "plane is observed in the receipt but not projected by this cockpit consumer")
            )

    degraded = (
        bool(unavailable_sources)
        or dropped_prs > 0
        or dropped_issues > 0
        or bool(unattributed_pr_identities)
        or bool(unattributed_issue_ids)
        or digest_check["state"] != "VERIFIED"
        or any(block["freshness"] == "STALE" for block in (github_block, linear_block))
        or not cards
    )
    state = "DEGRADED" if degraded else "CONSUMED"

    return _document(
        state=state,
        evaluated_at=evaluated_at,
        stale_after_seconds=stale_after,
        source_receipt=_source_receipt_block(receipt),
        admission=receipt["admission"],
        finding_counts=_count_findings(findings),
        unavailable_sources=unavailable_sources,
        digest_check=digest_check,
        cards=cards,
        unattributed_findings=sorted(unattributed, key=_finding_sort_key),
        unknowns=unknowns,
    )


# ---------------------------------------------------------------------------
# read-only adapter
# ---------------------------------------------------------------------------

def read_cross_plane_view(
    receipt_path: str | Path,
    *,
    evaluated_at: str | None = None,
    stale_after_seconds: float | None = None,
    strict: bool = False,
) -> dict[str, Any]:
    """Read one existing receipt artifact and render its view.  Reads nothing else.

    This opens one file, reads it once, and closes it.  It creates no cache,
    writes no receipt, polls nothing, and resolves no credential: a path whose
    contents are not a Session Truth receipt is degraded to a ``REJECTED``
    document rather than being searched for, repaired or re-acquired.
    """

    path = Path(receipt_path)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        if strict:
            raise SessionTruthContractError(
                f"receipt artifact is unreadable: {type(exc).__name__}"
            ) from exc
        return _rejected_document(
            f"receipt artifact unreadable: {type(exc).__name__}",
            evaluated_at=evaluated_at,
            stale_after_seconds=_validate_stale_after(stale_after_seconds),
        )
    try:
        receipt = json.loads(raw)
    except ValueError as exc:
        if strict:
            raise SessionTruthContractError(f"receipt artifact is not valid JSON: {exc}") from exc
        return _rejected_document(
            "receipt artifact is not valid JSON",
            evaluated_at=evaluated_at,
            stale_after_seconds=_validate_stale_after(stale_after_seconds),
        )
    return build_cross_plane_view(
        receipt,
        evaluated_at=evaluated_at,
        stale_after_seconds=stale_after_seconds,
        strict=strict,
    )


__all__ = [
    "SCHEMA",
    "OUTPUT_KEYS",
    "CARD_KEYS",
    "IDENTITIES_KEYS",
    "PULL_REQUEST_CARD_KEYS",
    "ISSUE_CARD_KEYS",
    "GITHUB_BLOCK_KEYS",
    "LINEAR_BLOCK_KEYS",
    "UNAVAILABLE_SOURCE_KEYS",
    "MISSINGNESS_CLASSES",
    "FRESHNESS_STATES",
    "DOCUMENT_STATES",
    "build_cross_plane_view",
    "read_cross_plane_view",
]
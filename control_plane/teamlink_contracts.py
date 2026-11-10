"""TeamLink contract shapes — TeamLinkMessage.v1 and ContextPacket.v1.

Adopted verbatim (field names, patterns and closed rules) from the v1 design
at ``~/.hermes/profiles/engineering/mmos/TEAMLINK_DESIGN.md`` (2026-11-09),
which is DESIGN ONLY.  This module encodes the two schemas and the pure rules
the design attaches to them; it owns NO transport, NO queue, NO broker, NO
store, NO retry loop and NO UI (design §6 non-goals).  Placement stays with
the ONE broker (``broker.claim_job``), decisions with the ONE Executive
decision ledger, and TeamLink is audited BY REFERENCE into that ledger with
the WO-17 correlation keys — never a second record owner.

Rules encoded here (design §1, §2, §4, §5):

* ``message_id`` is a deterministic mint — ``tlm-`` + sha256(sender principal,
  operation_key, body/context)[:32] — so a duplicate transport delivery of the
  same operation_key + content is recognised as the SAME message, never new
  work (mirrors ``decision_id_for_binding``);
* same ``operation_key`` + changed immutable envelope ⇒ REFUSED
  (``verify_duplicate``), even when an old message ID is copied;
  exactly like ``submit_ceo_intent``;
* ``delivery_state`` is monotonic over
  ``admitted → picked_up → executed → replied → consumed``; a regression is a
  protocol violation that raises, never applies.  ``unknown`` is OUTSIDE the
  chain: the honest terminal marker for "the transport could not tell".  It
  never auto-retries; reconciliation may later append a chain state observed
  on the ORIGINAL operation_key, and nothing backfills a guess;
* hop math: forwarding increments ``hop_count``; a forward whose hop_count
  would reach ``max_hops`` is refused (``hop_breach``).  Default 3, hard
  ceiling 8.  An expired actionable message is dead even below ``max_hops``;
* the wake gate: ``intent: informational`` NEVER requires a model turn on
  either side (``requires_model_turn`` is False only for informational);
* the echo guard: a received message whose ``(from, kind, intent, reply_to)``
  mirrors the one just sent to the same peer is a ping-pong echo — drop,
  record ``consumed``, never reply;
* answers settle: after ``question → answer`` the subject is closed; further
  turns require a NEW ``operation_key`` (``followup_requires_new_key``);
* ``ContextPacket.v1`` is a CACHE: references-only, must carry every
  ``EFFECT_UNKNOWN`` effect, and after ``expires_at`` must be re-fetched,
  never acted on.  Owners remain authoritative in all cases — a packet can
  only ever describe; it can never grant, place or fence.

Defensive bounds marked "beyond design" below are generous caps on fields the
design leaves unbounded; they exist so a hostile blob cannot pass validation,
never to constrain lawful producers.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

TEAMLINK_MESSAGE_SCHEMA = "TeamLinkMessage.v1"
CONTEXT_PACKET_SCHEMA = "ContextPacket.v1"

MESSAGE_ID_RE = re.compile(r"^tlm-[0-9a-f]{32}$")
PACKET_ID_RE = re.compile(r"^tlp-[0-9a-f]{32}$")
# Same grammar and 96-char ceiling as the Session Bridge operation_key.
OPERATION_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$")
REQUEST_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
ISO_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?([+-]\d{2}:?\d{2}|Z)")

# The WO-17 correlation keys, verbatim (executive_decision_ledger
# JSONL_CORRELATION_KEYS).  TeamLink copies these from an admitted
# binding/decision; it never mints or re-derives them.
CORRELATION_KEYS = (
    "root_run_ref", "immediate_parent_run_ref", "logical_child_key",
    "preview_id", "decision_id", "attempt_ref", "fence_counter", "request_digest",
)

PRINCIPAL_SIDES = frozenset({"hermes_profile", "t3_host_thread"})
MESSAGE_KINDS = frozenset({
    "instruction", "question", "answer", "decision_update", "evidence", "blocker", "status",
})
MESSAGE_INTENTS = frozenset({"informational", "actionable"})

# Monotonic delivery chain; "unknown" is deliberately OUTSIDE it.
DELIVERY_CHAIN = ("admitted", "picked_up", "executed", "replied", "consumed")
DELIVERY_UNKNOWN = "unknown"
DELIVERY_STATES = frozenset(DELIVERY_CHAIN) | {DELIVERY_UNKNOWN}
_DELIVERY_RANK = {state: index for index, state in enumerate(DELIVERY_CHAIN)}

DEFAULT_MAX_HOPS = 3
MAX_HOPS_CEILING = 8
BODY_MAX_CHARS = 4096
CONTEXT_REFS_MAX = 32
REF_MAX_CHARS = 1024        # beyond design (unbounded there): hostile-blob cap
PRINCIPAL_ID_MAX = 256      # beyond design
THREAD_REF_MAX = 256        # beyond design

OBJECTIVE_MAX_CHARS = 2048
SUMMARY_MAX_CHARS = 512
WHAT_MAX_CHARS = 512
RULE_MAX_CHARS = 1024
NEXT_ACTION_MAX_CHARS = 1024
ACCEPTED_DECISIONS_MAX = 64
OUTSTANDING_DEPENDENCIES_MAX = 64
ACTIVE_WORK_OWNERSHIP_MAX = 32
UNRESOLVED_EFFECTS_MAX = 64


class TeamLinkContractError(ValueError):
    """Closed-set validation failure; `code` names the violated rule."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


def _invalid(code: str, detail: str = "") -> None:
    raise TeamLinkContractError(code, detail)


def _exact_keys(value: Any, required: tuple, allowed: tuple, label: str) -> dict:
    if type(value) is not dict or not set(value) <= set(allowed):
        _invalid(f"INVALID_{label}_FIELDS")
    missing = [key for key in required if key not in value]
    if missing:
        _invalid(f"MISSING_{label}_FIELD", ",".join(missing))
    return value


def _text(value: Any, label: str, *, maximum: int, minimum: int = 0) -> str:
    if type(value) is not str:
        _invalid(f"INVALID_{label}")
    if len(value) < minimum or len(value) > maximum:
        _invalid(f"INVALID_{label}")
    return value


def _nullable_text(value: Any, label: str, *, maximum: int) -> str | None:
    if value is None:
        return None
    return _text(value, label, maximum=maximum)


def _integer(value: Any, label: str, *, minimum: int, maximum: int | None = None) -> int:
    if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
        _invalid(f"INVALID_{label}")
    return value


def _iso(value: Any, label: str) -> str:
    text = _text(value, label, maximum=64, minimum=1)
    if ISO_PATTERN.fullmatch(text) is None:
        _invalid(f"INVALID_{label}")
    offset = re.search(r"([+-])(\d{2}):?(\d{2})$", text)
    if offset and (int(offset[2]) > 23 or int(offset[3]) > 59):
        _invalid(f"INVALID_{label}")
    try:
        parsed = _parse_iso(text)
        if parsed.utcoffset() is None:
            _invalid(f"INVALID_{label}")
    except (ValueError, OverflowError):
        _invalid(f"INVALID_{label}")
    return text


def _principal(value: Any, label: str) -> dict:
    row = _exact_keys(value, ("side", "id"),
                      ("side", "id", "thread_ref"), f"{label}_PRINCIPAL")
    if type(row["side"]) is not str or row["side"] not in PRINCIPAL_SIDES:
        _invalid(f"INVALID_{label}_PRINCIPAL_SIDE")
    _text(row["id"], f"{label}_PRINCIPAL_ID", maximum=PRINCIPAL_ID_MAX, minimum=1)
    if "thread_ref" in row:
        ref = _nullable_text(row["thread_ref"], f"{label}_THREAD_REF", maximum=THREAD_REF_MAX)
        if ref is not None and not ref:
            _invalid(f"INVALID_{label}_THREAD_REF")
    return row


def _correlation(value: Any) -> dict:
    row = _exact_keys(value, (), CORRELATION_KEYS, "CORRELATION")
    if "fence_counter" in row and row["fence_counter"] is not None:
        _integer(row["fence_counter"], "FENCE_COUNTER", minimum=0)
    if "request_digest" in row:
        digest = _nullable_text(row["request_digest"], "REQUEST_DIGEST", maximum=64)
        if digest is not None and REQUEST_DIGEST_RE.fullmatch(digest) is None:
            _invalid("INVALID_REQUEST_DIGEST")
    for key in ("root_run_ref", "immediate_parent_run_ref", "logical_child_key",
                "preview_id", "decision_id", "attempt_ref"):
        if key in row:
            _nullable_text(row[key], key.upper(), maximum=REF_MAX_CHARS)
    return row


def mint_message_id(sender_id: str, operation_key: str, body: str,
                    context_refs: list[str] | tuple[str, ...] = ()) -> str:
    """Deterministic message id (design §1.2): same sender + operation_key +
    content ⇒ same id, so a duplicate delivery is the SAME message."""
    canonical = json.dumps(
        {"sender": sender_id, "operation_key": operation_key,
         "body": body, "context_refs": list(context_refs)},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "tlm-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


def validate_team_link_message(value: Any) -> dict:
    """Closed validation of TeamLinkMessage.v1 (design §1); raises
    TeamLinkContractError on any drift.  Returns the validated dict."""
    msg = _exact_keys(value, ("schema", "message_id", "operation_key", "correlation",
                              "from", "to", "kind", "intent", "body", "context_refs",
                              "hop_count", "max_hops", "delivery_state", "expires_at"),
                      ("schema", "message_id", "operation_key", "correlation",
                       "from", "to", "kind", "intent", "body", "context_refs",
                       "reply_to", "hop_count", "max_hops", "delivery_state", "expires_at"),
                      "MESSAGE")
    if msg["schema"] != TEAMLINK_MESSAGE_SCHEMA:
        _invalid("INVALID_MESSAGE_SCHEMA")
    if MESSAGE_ID_RE.fullmatch(_text(msg["message_id"], "MESSAGE_ID", maximum=36, minimum=1)) is None:
        _invalid("INVALID_MESSAGE_ID")
    if OPERATION_KEY_RE.fullmatch(
            _text(msg["operation_key"], "OPERATION_KEY", maximum=96, minimum=1)) is None:
        _invalid("INVALID_OPERATION_KEY")
    _correlation(msg["correlation"])
    _principal(msg["from"], "FROM")
    _principal(msg["to"], "TO")
    if type(msg["kind"]) is not str or msg["kind"] not in MESSAGE_KINDS:
        _invalid("INVALID_KIND")
    if type(msg["intent"]) is not str or msg["intent"] not in MESSAGE_INTENTS:
        _invalid("INVALID_INTENT")
    _text(msg["body"], "BODY", maximum=BODY_MAX_CHARS, minimum=1)
    refs = msg["context_refs"]
    if type(refs) is not list or len(refs) > CONTEXT_REFS_MAX:
        _invalid("INVALID_CONTEXT_REFS")
    for ref in refs:
        _text(ref, "CONTEXT_REF", maximum=REF_MAX_CHARS, minimum=1)
    if "reply_to" in msg:
        reply = _nullable_text(msg["reply_to"], "REPLY_TO", maximum=36)
        if reply is not None and MESSAGE_ID_RE.fullmatch(reply) is None:
            _invalid("INVALID_REPLY_TO")
    _integer(msg["hop_count"], "HOP_COUNT", minimum=0)
    _integer(msg["max_hops"], "MAX_HOPS", minimum=0, maximum=MAX_HOPS_CEILING)
    if type(msg["delivery_state"]) is not str or msg["delivery_state"] not in DELIVERY_STATES:
        _invalid("INVALID_DELIVERY_STATE")
    _iso(msg["expires_at"], "EXPIRES_AT")
    return msg


def verify_duplicate(original: dict, repeat: dict) -> str:
    """Compare validated immutable envelopes, never trust an ID-only match.

    The v1 mint remains compatible with existing operations and Unicode vectors;
    it is a content label, not sender authentication or destination authority.
    Delivery state and hop count are owner observations, not request identity.
    Equal identity does not authorize resetting either observation or replaying
    an effect. The existing original-operation owner retains that responsibility.
    """
    first = _immutable_envelope(original)
    second = _immutable_envelope(repeat)
    if second["operation_key"] != first["operation_key"]:
        return "different_operation_key"
    if first == second:
        return "same_message"
    return "refused_content_changed"


def _principal_identity(principal: dict) -> dict:
    return {"side": principal["side"], "id": principal["id"],
            "thread_ref": principal.get("thread_ref")}


def _immutable_envelope(value: dict) -> dict:
    msg = validate_team_link_message(value)
    return {
        **{key: msg[key] for key in (
            "schema", "message_id", "operation_key", "kind", "intent", "body",
            "context_refs", "max_hops", "expires_at")},
        "from": _principal_identity(msg["from"]),
        "to": _principal_identity(msg["to"]),
        "correlation": {key: msg["correlation"].get(key) for key in CORRELATION_KEYS},
        "reply_to": msg.get("reply_to"),
    }


def advance_delivery(current: str, target: str) -> str:
    """Monotonic delivery transition (design §1.12, §4.1).

    * same state ⇒ no-op (idempotent append appends nothing);
    * target ``unknown`` ⇒ allowed from any state: the honest terminal marker,
      never an auto-retry;
    * from ``unknown`` ⇒ only a chain state observed on the original
      operation during reconciliation may be appended (no guessed backfill;
      unknown→unknown is the same-state no-op);
    * chain → chain must move strictly forward; a regression raises
      (recorded, never applied).
    """
    if current not in DELIVERY_STATES or target not in DELIVERY_STATES:
        _invalid("INVALID_DELIVERY_STATE", f"{current}->{target}")
    if current == target:
        return current
    if target == DELIVERY_UNKNOWN:
        return target
    if current == DELIVERY_UNKNOWN:
        return target  # reconciliation observed the truth on the original key
    if _DELIVERY_RANK[target] <= _DELIVERY_RANK[current]:
        _invalid("DELIVERY_REGRESSION", f"{current}->{target}")
    return target


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def is_expired(record: dict, now: datetime | None = None) -> bool:
    """True when ``expires_at`` has passed (message dead / packet must be
    re-fetched, never acted on).  An unparseable timestamp is expired: an
    expiry a consumer cannot read provides no protection."""
    moment = datetime.now(timezone.utc) if now is None else now
    try:
        if not isinstance(moment, datetime) or moment.utcoffset() is None:
            return True
        expiry = record["expires_at"]
        return _parse_iso(_iso(expiry, "EXPIRES_AT")) <= moment
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
        return True


def may_forward(message: dict, now: datetime | None = None) -> tuple[bool, str]:
    """Hop math (design §5.2, §5.6).  Forwarding increments hop_count; a relay
    asked to forward a message whose hop_count would reach max_hops refuses
    (``hop_breach`` — ledger note + human ping, exchange stops).  An expired
    message is dead even below max_hops."""
    if is_expired(message, now):
        return False, "expired"
    validate_team_link_message(message)
    if message["hop_count"] + 1 >= message["max_hops"]:
        return False, "hop_breach"
    return True, ""


def requires_model_turn(message: dict) -> bool:
    """The wake gate (design §5.1): only ``intent: actionable`` may cause a
    model turn; informational delivery NEVER wakes either side."""
    return message["intent"] == "actionable"


def is_ping_pong_echo(sent: dict, received: dict) -> bool:
    """Recognize an exact semantic mirror between the same two principals.

    Another thread, side, operation, body or correlation is not an echo. The
    sender-dependent v1 message ID changes on reversal and is excluded, as are
    the two mutable transport observations. Hop limits still bound other loops.
    """
    first = _immutable_envelope(sent)
    second = _immutable_envelope(received)
    first.pop("message_id")
    second.pop("message_id")
    first["from"], first["to"] = first["to"], first["from"]
    return first == second


def followup_requires_new_key(settled_question: dict, follow_up: dict) -> bool:
    """Answers settle (design §5.4): after question → answer the subject is
    closed; the answerer must not re-question it.  A follow-up on the same
    subject is lawful only under a NEW operation_key (returns True when the
    follow-up reuses the settled key — the caller refuses it)."""
    return follow_up.get("operation_key") == settled_question.get("operation_key")


# ── ContextPacket.v1 ─────────────────────────────────────────────────────────


def validate_context_packet(value: Any) -> dict:
    """Closed validation of ContextPacket.v1 (design §2).  The packet is a
    CACHE: every effect with unknown outcome MUST appear in
    ``unresolved_effects`` (a packet that omits one is invalid at the
    producer); after ``expires_at`` it must be re-fetched, never acted on."""
    packet = _exact_keys(value, ("schema", "packet_id", "objective", "accepted_decisions",
                                 "outstanding_dependencies", "source_revision",
                                 "active_work_ownership", "unresolved_effects",
                                 "next_action", "expires_at"),
                         ("schema", "packet_id", "objective", "accepted_decisions",
                          "outstanding_dependencies", "source_revision",
                          "active_work_ownership", "unresolved_effects",
                          "next_action", "since_packet_id", "delta", "expires_at"),
                         "PACKET")
    if packet["schema"] != CONTEXT_PACKET_SCHEMA:
        _invalid("INVALID_PACKET_SCHEMA")
    if PACKET_ID_RE.fullmatch(_text(packet["packet_id"], "PACKET_ID", maximum=36, minimum=1)) is None:
        _invalid("INVALID_PACKET_ID")
    _text(packet["objective"], "OBJECTIVE", maximum=OBJECTIVE_MAX_CHARS)
    rows = packet["accepted_decisions"]
    _row_shapes(rows, ACCEPTED_DECISIONS_MAX, "ACCEPTED_DECISIONS",
                ("decision_id",), ("decision_id", "summary", "ledger_row"))
    for row in rows:
        _text(row["decision_id"], "DECISION_ID", maximum=REF_MAX_CHARS, minimum=1)
        if "summary" in row:
            _text(row["summary"], "DECISION_SUMMARY", maximum=SUMMARY_MAX_CHARS)
        if "ledger_row" in row:
            _nullable_text(row["ledger_row"], "LEDGER_ROW", maximum=REF_MAX_CHARS)
    rows = packet["outstanding_dependencies"]
    _row_shapes(rows, OUTSTANDING_DEPENDENCIES_MAX, "OUTSTANDING_DEPENDENCIES",
                ("what", "owner"), ("what", "owner", "ref"))
    for row in rows:
        _text(row["what"], "DEPENDENCY_WHAT", maximum=WHAT_MAX_CHARS, minimum=1)
        _text(row["owner"], "DEPENDENCY_OWNER", maximum=PRINCIPAL_ID_MAX, minimum=1)
        if "ref" in row:
            _nullable_text(row["ref"], "DEPENDENCY_REF", maximum=REF_MAX_CHARS)
    revision = _exact_keys(packet["source_revision"], ("branch", "head"),
                           ("branch", "head"), "SOURCE_REVISION")
    _text(revision["branch"], "SOURCE_BRANCH", maximum=REF_MAX_CHARS, minimum=1)
    _text(revision["head"], "SOURCE_HEAD", maximum=REF_MAX_CHARS, minimum=1)
    rows = packet["active_work_ownership"]
    _row_shapes(rows, ACTIVE_WORK_OWNERSHIP_MAX, "ACTIVE_WORK_OWNERSHIP",
                ("work_ref", "owner"), ("work_ref", "owner", "lease_expires_at"))
    for row in rows:
        _text(row["work_ref"], "WORK_REF", maximum=REF_MAX_CHARS, minimum=1)
        _text(row["owner"], "WORK_OWNER", maximum=PRINCIPAL_ID_MAX, minimum=1)
        if "lease_expires_at" in row:
            _iso_nullable(row["lease_expires_at"], "LEASE_EXPIRES_AT")
    rows = packet["unresolved_effects"]
    _row_shapes(rows, UNRESOLVED_EFFECTS_MAX, "UNRESOLVED_EFFECTS",
                ("effect_ref", "state", "rule"), ("effect_ref", "state", "rule"))
    for row in rows:
        _text(row["effect_ref"], "EFFECT_REF", maximum=REF_MAX_CHARS, minimum=1)
        if row["state"] != "EFFECT_UNKNOWN":
            _invalid("INVALID_EFFECT_STATE")
        _text(row["rule"], "EFFECT_RULE", maximum=RULE_MAX_CHARS, minimum=1)
    _text(packet["next_action"], "NEXT_ACTION", maximum=NEXT_ACTION_MAX_CHARS)
    if "since_packet_id" in packet:
        since = _nullable_text(packet["since_packet_id"], "SINCE_PACKET_ID", maximum=36)
        if since is not None and PACKET_ID_RE.fullmatch(since) is None:
            _invalid("INVALID_SINCE_PACKET_ID")
    if "delta" in packet:
        _exact_keys(packet["delta"], (), ("added", "changed", "removed"), "PACKET_DELTA")
        for key in ("added", "changed", "removed"):
            if key in packet["delta"]:
                items = packet["delta"][key]
                if type(items) is not list:
                    _invalid("INVALID_PACKET_DELTA")
                for item in items:
                    _text(item, "PACKET_DELTA_ITEM", maximum=REF_MAX_CHARS, minimum=1)
    _iso(packet["expires_at"], "PACKET_EXPIRES_AT")
    return packet


def _row_shapes(rows: Any, limit: int, label: str, required: tuple, allowed: tuple) -> None:
    if type(rows) is not list or len(rows) > limit:
        _invalid(f"INVALID_{label}")
    for row in rows:
        _exact_keys(row, required, allowed, label)


def _iso_nullable(value: Any, label: str) -> None:
    if value is not None:
        _iso(value, label)

"""Parent-local tracker for one Hermes child.

Executive OS still admits. Subagent Fabric (``fabric_task.py``) or a Cursor
cloud agent still executes. This ledger only stops a second submit, a carrier
change, an automatic retry of UNKNOWN, and a parent consume that has not been
independently reviewed. It is not a company queue.
"""
from __future__ import annotations

import hashlib
import json
import threading
from typing import Any, Mapping

from integrations.hermes_delegate.admission import InertExecutiveAdmission
from integrations.hermes_delegate.carriers import UnboundCarrier, carrier_spec
from integrations.hermes_delegate.handoff import HandoffError, render_child_handoff
from integrations.hermes_delegate.policy import load_policy, refusal_for_policy
from integrations.hermes_delegate.schema import ID_RE, SubmissionError, parse_submission


MAX_RESULT_BYTES = 1_048_576
_TERMINAL_STICKY = frozenset({
    "REFUSED",
    "UNKNOWN",
    "CANCELLED",
    "CONSUMED",
    "REVIEW_REJECTED",
    "RESULT_DIGEST_MISMATCH",
})


def _canonical(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _fingerprint(submission: Mapping[str, Any]) -> str:
    body = {
        "parent_id": submission["parent_id"],
        "root_id": submission["root_id"],
        "child_kind": submission["child_kind"],
        "objective": submission["objective"],
        "acceptance": submission["acceptance"],
        "constraints": list(submission["constraints"]),
    }
    return hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()


class _Record:
    def __init__(self, submission: Mapping[str, Any], fingerprint: str) -> None:
        self.submission = dict(submission)
        self.submission["constraints"] = tuple(submission["constraints"])
        self.fingerprint = fingerprint
        self.key = submission["idempotency_key"]
        self.run_id = submission["idempotency_key"]
        self.carrier = submission["carrier"]
        self.child_kind = submission["child_kind"]
        self.parent_id = submission["parent_id"]
        self.root_id = submission["root_id"]
        self.state = "PENDING_ADMISSION"
        self.reason: str | None = None
        self.detail: str | None = None
        self.review: dict[str, str] | None = None
        self.result_sha256: str | None = None
        self.result_text: str | None = None
        self.handoff: dict[str, Any] | None = None
        self.handoff_reason: str | None = None
        self.consumed = False
        self.result_fetched = False
        self.observed_terminal = False


class Bridge:
    def __init__(
        self,
        admission: Any | None = None,
        carriers: Mapping[str, Any] | None = None,
        policy: Mapping[str, Any] | None = None,
    ) -> None:
        self.admission = admission if admission is not None else InertExecutiveAdmission()
        self.carriers = dict(carriers or {})
        self.carriers.setdefault("fabric", UnboundCarrier())
        self.carriers.setdefault("cursor_cloud", UnboundCarrier())
        self.policy = dict(policy) if policy is not None else load_policy()
        self._by_key: dict[str, _Record] = {}
        self._by_fingerprint: dict[str, _Record] = {}
        self._lock = threading.Lock()

    def submit(self, raw: Mapping[str, Any]) -> dict[str, Any]:
        blocked = refusal_for_policy(self.policy)
        if blocked:
            return _bare(state="REFUSED", reason=blocked)
        try:
            submission = parse_submission(raw)
        except SubmissionError as exc:
            return _bare(state="REFUSED", reason=exc.reason)
        fingerprint = _fingerprint(submission)
        with self._lock:
            existing = self._by_key.get(submission["idempotency_key"])
            if existing is not None:
                return self._view(existing, deduped=True)
            replay_of = submission["replay_of"]
            if isinstance(replay_of, str):
                prior = self._by_key.get(replay_of)
                if prior is None:
                    return _bare(state="NOT_FOUND", reason="REPLAY_TARGET_ABSENT", idempotency_key=replay_of)
                return self._view(prior, deduped=True)
            prior = self._by_fingerprint.get(fingerprint)
            if prior is not None:
                return self._view(prior, deduped=True)
            record = _Record(submission, fingerprint)
            self._by_key[record.key] = record
            self._by_fingerprint[fingerprint] = record
            decision = self._admit(record)
            if decision is None:
                return self._view(record)
            if not self._accept_admission(record, decision):
                return self._view(record)
            self._submit_carrier(record)
            return self._view(record)

    def status(self, idempotency_key: str) -> dict[str, Any]:
        with self._lock:
            record = self._by_key.get(idempotency_key)
            if record is None:
                return _bare(state="NOT_FOUND", reason="UNKNOWN_CHILD", idempotency_key=idempotency_key)
            self._observe(record)
            return self._view(record)

    def cancel(self, idempotency_key: str) -> dict[str, Any]:
        with self._lock:
            record = self._by_key.get(idempotency_key)
            if record is None:
                return _bare(state="NOT_FOUND", reason="UNKNOWN_CHILD", idempotency_key=idempotency_key)
            if record.state in _TERMINAL_STICKY or record.state in {"REVIEWED", "TERMINAL"}:
                return self._view(record, deduped=record.state == "CANCELLED")
            if record.state not in {"SUBMITTED", "RUNNING", "PENDING_ADMISSION"}:
                return self._view(record)
            if record.state == "PENDING_ADMISSION":
                record.state = "UNKNOWN"
                record.detail = "CANCEL_DURING_ADMISSION"
                return self._view(record)
            try:
                result = self.carriers[record.carrier].cancel(record.run_id)
            except Exception as exc:
                self._latch_unknown(record, f"{type(exc).__name__}: {exc}")
                return self._view(record)
            if not isinstance(result, Mapping):
                self._latch_unknown(record, "CANCEL_RESULT_UNREADABLE")
                return self._view(record)
            observed = result.get("state")
            if observed in {"UNKNOWN", "EFFECT_UNKNOWN"}:
                detail = result.get("detail")
                self._latch_unknown(record, detail if isinstance(detail, str) and detail else str(observed))
                return self._view(record)
            if observed != "CANCELLED":
                self._latch_unknown(record, "CANCEL_RESULT_UNREADABLE")
                return self._view(record)
            record.state = "CANCELLED"
            return self._view(record)

    def review(
        self,
        idempotency_key: str,
        *,
        reviewer_id: str,
        verdict: str,
        result_sha256: str,
    ) -> dict[str, Any]:
        with self._lock:
            record = self._by_key.get(idempotency_key)
            if record is None:
                return _bare(state="NOT_FOUND", reason="UNKNOWN_CHILD", idempotency_key=idempotency_key)
            if record.review is not None or record.state in _TERMINAL_STICKY:
                return self._view(record, deduped=True)
            if not isinstance(reviewer_id, str) or ID_RE.fullmatch(reviewer_id) is None:
                return {**self._view(record), "state": "REFUSED", "reason": "REVIEW_INVALID"}
            if reviewer_id in {record.parent_id, record.root_id, record.run_id, record.key}:
                return {
                    **self._view(record),
                    "state": "SELF_APPROVAL_FORBIDDEN",
                    "reason": "SELF_APPROVAL_FORBIDDEN",
                }
            if verdict not in {"accept", "reject"} or not isinstance(result_sha256, str):
                return {**self._view(record), "state": "REFUSED", "reason": "REVIEW_INVALID"}
            if len(result_sha256) != 64 or any(ch not in "0123456789abcdef" for ch in result_sha256):
                return {**self._view(record), "state": "REFUSED", "reason": "REVIEW_INVALID"}
            self._observe(record)
            if record.state == "UNKNOWN":
                return self._view(record)
            if record.result_sha256 is None:
                return {**self._view(record), "state": "REFUSED", "reason": "RESULT_SHA_UNAVAILABLE"}
            if result_sha256 != record.result_sha256:
                return {**self._view(record), "state": "REFUSED", "reason": "REVIEW_DIGEST_MISMATCH"}
            record.review = {
                "reviewer_id": reviewer_id,
                "verdict": verdict,
                "result_sha256": result_sha256,
            }
            record.state = "REVIEWED" if verdict == "accept" else "REVIEW_REJECTED"
            return self._view(record)

    def consume(
        self,
        idempotency_key: str,
        *,
        parent_id: str,
        handoff_model: str | None = None,
        workstream: str | None = None,
        session: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            record = self._by_key.get(idempotency_key)
            if record is None:
                return _bare(state="NOT_FOUND", reason="UNKNOWN_CHILD", idempotency_key=idempotency_key)
            if record.consumed:
                return self._view(record, deduped=True, already_consumed=True)
            if record.state in _TERMINAL_STICKY and record.state != "REVIEW_REJECTED":
                return self._view(record)
            if record.state == "REVIEW_REJECTED":
                return {**self._view(record), "reason": "REVIEW_REJECTED"}
            if record.state != "REVIEWED":
                return {**self._view(record), "state": "REVIEW_REQUIRED", "reason": "REVIEW_REQUIRED"}
            if parent_id != record.parent_id:
                return {**self._view(record), "state": "REFUSED", "reason": "PARENT_MISMATCH"}
            if record.result_fetched:
                return self._view(record)
            record.result_fetched = True
            try:
                payload = self.carriers[record.carrier].result(record.run_id)
            except Exception as exc:
                self._latch_unknown(record, f"{type(exc).__name__}: {exc}")
                return self._view(record)
            body = _result_body(payload)
            if body is None:
                self._latch_unknown(record, "RESULT_UNREADABLE")
                return self._view(record)
            digest = hashlib.sha256(body).hexdigest()
            review = record.review or {}
            if digest != review.get("result_sha256"):
                record.state = "RESULT_DIGEST_MISMATCH"
                record.detail = "RESULT_DIGEST_MISMATCH"
                return self._view(record)
            try:
                text = body.decode("utf-8")
            except UnicodeError:
                self._latch_unknown(record, "RESULT_UNREADABLE")
                return self._view(record)
            record.result_sha256 = digest
            record.result_text = text
            record.consumed = True
            record.state = "CONSUMED"
            record.handoff, record.handoff_reason = _handoff(
                record,
                handoff_model=handoff_model,
                workstream=workstream,
                session=session,
            )
            return self._view(record)

    def _admit(self, record: _Record) -> Mapping[str, Any] | None:
        try:
            decision = self.admission.admit(record.submission)
        except Exception as exc:
            self._latch_unknown(record, f"{type(exc).__name__}: {exc}")
            return None
        if not isinstance(decision, Mapping):
            self._latch_unknown(record, "ADMISSION_RESULT_UNREADABLE")
            return None
        return decision

    def _accept_admission(self, record: _Record, decision: Mapping[str, Any]) -> bool:
        outcome = decision.get("outcome")
        reason = decision.get("reason")
        if outcome == "REFUSED":
            if not isinstance(reason, str):
                self._latch_unknown(record, "ADMISSION_REFUSAL_UNREADABLE")
                return False
            record.state = "REFUSED"
            record.reason = reason
            return False
        if outcome != "ADMITTED":
            self._latch_unknown(record, "ADMISSION_RESULT_UNREADABLE")
            return False
        if decision.get("carrier") != record.carrier or decision.get("idempotency_key") not in {None, record.key}:
            record.state = "REFUSED"
            record.reason = reason if isinstance(reason, str) and reason else "ADMISSION_CARRIER_MISMATCH"
            return False
        # Admitted suggestions such as fallback_carrier are ignored.
        record.state = "ADMITTED"
        return True

    def _submit_carrier(self, record: _Record) -> None:
        spec = carrier_spec(record.submission)
        try:
            result = self.carriers[record.carrier].submit(spec)
        except Exception as exc:
            self._latch_unknown(record, f"{type(exc).__name__}: {exc}")
            return
        if not isinstance(result, Mapping):
            self._latch_unknown(record, "CARRIER_RESULT_UNREADABLE")
            return
        observed = result.get("state")
        if observed in {"UNKNOWN", "EFFECT_UNKNOWN"}:
            detail = result.get("detail")
            self._latch_unknown(record, detail if isinstance(detail, str) and detail else str(observed))
            return
        if observed == "REFUSED":
            reason = result.get("reason")
            if not isinstance(reason, str):
                self._latch_unknown(record, "CARRIER_REFUSAL_UNREADABLE")
                return
            record.state = "REFUSED"
            record.reason = reason
            return
        if observed != "SUBMITTED" or result.get("run_id") != record.run_id:
            self._latch_unknown(record, "CARRIER_RUN_ID_MISMATCH" if observed == "SUBMITTED" else "CARRIER_RESULT_UNREADABLE")
            return
        record.state = "SUBMITTED"

    def _observe(self, record: _Record) -> None:
        if record.state in _TERMINAL_STICKY | {"REVIEWED", "CONSUMED"} or record.observed_terminal:
            return
        if record.state not in {"SUBMITTED", "RUNNING", "ADMITTED", "TERMINAL"}:
            return
        try:
            observed = self.carriers[record.carrier].status(record.run_id)
        except Exception as exc:
            self._latch_unknown(record, f"{type(exc).__name__}: {exc}")
            return
        if not isinstance(observed, Mapping):
            self._latch_unknown(record, "STATUS_UNREADABLE")
            return
        state = observed.get("state")
        if state in {"UNKNOWN", "EFFECT_UNKNOWN"}:
            detail = observed.get("detail")
            self._latch_unknown(record, detail if isinstance(detail, str) and detail else str(state))
            return
        if state == "TERMINAL" and observed.get("result_available") is True and isinstance(observed.get("result_sha256"), str):
            record.state = "TERMINAL"
            record.result_sha256 = observed["result_sha256"]
            record.observed_terminal = True
            return
        if state in {"RUNNING", "SUBMITTED"}:
            record.state = str(state)
            return
        self._latch_unknown(record, "STATUS_UNREADABLE")

    def _latch_unknown(self, record: _Record, detail: str) -> None:
        record.state = "UNKNOWN"
        record.detail = detail
        record.observed_terminal = True

    def _view(self, record: _Record, *, deduped: bool = False, already_consumed: bool = False) -> dict[str, Any]:
        body: dict[str, Any] = {
            "schema": "mastermind.hermes_delegate.child_view/v1",
            "idempotency_key": record.key,
            "run_id": record.run_id,
            "carrier": record.carrier,
            "child_kind": record.child_kind,
            "state": record.state,
            "deduped": deduped,
            "consumed": record.consumed,
            "already_consumed": already_consumed,
            "reason": record.reason,
            "detail": record.detail,
            "live_submit": False,
            "result_sha256": record.result_sha256 if record.consumed or record.observed_terminal else None,
        }
        if record.consumed:
            body["result_text"] = record.result_text
            body["handoff"] = record.handoff
            body["handoff_reason"] = record.handoff_reason
        return body


def _bare(*, state: str, reason: str, idempotency_key: str | None = None) -> dict[str, Any]:
    return {
        "schema": "mastermind.hermes_delegate.child_view/v1",
        "idempotency_key": idempotency_key,
        "state": state,
        "reason": reason,
        "deduped": False,
        "consumed": False,
        "already_consumed": False,
        "live_submit": False,
        "detail": None,
    }


def _result_body(payload: Any) -> bytes | None:
    if not isinstance(payload, Mapping):
        return None
    body = payload.get("body")
    if isinstance(body, str):
        body = body.encode("utf-8")
    if not isinstance(body, bytes) or len(body) > MAX_RESULT_BYTES:
        return None
    return body


def _handoff(
    record: _Record,
    *,
    handoff_model: str | None,
    workstream: str | None,
    session: str | None,
) -> tuple[dict[str, Any] | None, str | None]:
    if not handoff_model or not workstream or not session:
        return None, "HANDOFF_MODEL_REQUIRED"
    try:
        document = render_child_handoff(
            workstream=workstream,
            session=session,
            model=handoff_model,
            submission=record.submission,
            result_sha256=record.result_sha256 or "",
        )
    except HandoffError as exc:
        return None, exc.reason
    return document, None

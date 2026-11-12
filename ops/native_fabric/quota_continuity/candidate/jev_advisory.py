"""Batched typed Jev judgments for the incumbent Mastermind Subagent Fabric.

Advisory only: no worker/admission, policy, retry, lease or acceptance authority.
Exactly one native System One POST per evaluation. No auto-retries.

The transport is owner-selected. Two modes exist and only the second is new:

``direct`` (the default, unchanged)
    POST the vendor System One endpoint with the vendor key. This is the
    existing explicit standalone configuration and it stays available.

``shared_gateway`` (optional, default off, fail-closed)
    POST an owner-run loopback proxy that already holds the vendor key and owns
    the organization-scoped RPM/credit budget. It is selected only by
    ``JEV_TRANSPORT=shared_gateway`` and requires ``JEV_GATEWAY_ENDPOINT`` (an
    exact loopback ``.../v1/systemone`` URL) plus ``JEV_GATEWAY_TOKEN`` (the
    local scoped bearer that proxy admits). In this mode the advisory never
    falls back to the direct vendor key, never rotates a credential, never
    skips the shared budget, never retries and never rewrites the ``jev-latest``
    slug. A missing or invalid shared-gateway configuration fails closed with a
    bounded ``JevUnavailable`` code before any socket is opened.

The advisory itself stays default-off and typed-only: the native request
boundary keeps its own ``FABRIC_JEV_MODE=off`` default, so selecting the
shared gateway never by itself enables an advisory call.
"""
from __future__ import annotations
import http.client
import ipaddress
import json
import math
import os
import time
from typing import Any, Callable
from urllib import error, parse, request

ENDPOINT = "https://api.experientiallabs.ai/v1/systemone"
MODEL = "jev-latest"
MAX_STATE_BYTES = 30000
MAX_BODY_BYTES = 48000
MAX_REPLY_BYTES = 65536
COMPLEXITIES = ("C0_MECHANICAL", "C1_ROUTINE_BOUNDED", "C2_COMPLEX_BOUNDED", "C3_FRONTIER_JUDGMENT")

DIRECT_TRANSPORT = "direct"
SHARED_GATEWAY_TRANSPORT = "shared_gateway"
TRANSPORT_ENV = "JEV_TRANSPORT"
GATEWAY_ENDPOINT_ENV = "JEV_GATEWAY_ENDPOINT"
GATEWAY_TOKEN_ENV = "JEV_GATEWAY_TOKEN"
# The shared proxy serves the System One route at this exact path only.
GATEWAY_PATH = "/v1/systemone"
# The incumbent proxy admits a local bearer of at least 24 characters. The
# client holds the same admission rule so an unusable token is refused before a
# socket is opened rather than after a refused round trip.
MIN_GATEWAY_TOKEN_CHARS = 24
# An owner-approved encrypted tunnel terminates on loopback as well; only the
# transport scheme differs, never the host, port or path.
GATEWAY_SCHEMES = ("http", "https")


class JevUnavailable(RuntimeError):
    """Error code only: never place request text or credential in exceptions."""
    def __init__(self, code: str) -> None:
        super().__init__("JEV_" + code)
        self.code = code


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def native_post(body: bytes, key: str, timeout: float, endpoint: str = ENDPOINT,
               opener: Any = None) -> dict[str, Any]:
    """Send exactly one bounded System One POST and return the typed reply.

    ``endpoint`` is the direct vendor endpoint unless the owner selected the
    shared gateway, in which case it is an already validated loopback URL. Any
    other endpoint is re-validated here, so no caller can reach a non-loopback
    host through this function. ``opener`` replaces only the urllib opener for
    offline wire qualification; it never reaches a real socket in this module.
    """
    if endpoint != ENDPOINT:
        endpoint = gateway_endpoint(endpoint)
    http_request = request.Request(
        endpoint, data=body, method="POST",
        headers={"Authorization": "Bearer " + key,
                 "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with (opener or request.build_opener(NoRedirect)).open(http_request, timeout=timeout) as response:
            data = response.read(MAX_REPLY_BYTES + 1)
    except error.HTTPError as exc:
        raise JevUnavailable("HTTP_" + str(exc.code)) from None
    except (error.URLError, OSError, TimeoutError, http.client.HTTPException):
        raise JevUnavailable("TRANSPORT") from None
    if len(data) > MAX_REPLY_BYTES:
        raise JevUnavailable("REPLY_TOO_LARGE")
    try:
        value = json.loads(data)
    except (ValueError, UnicodeError):
        raise JevUnavailable("INVALID_JSON") from None
    if not isinstance(value, dict):
        raise JevUnavailable("INVALID_RESPONSE")
    return value


def _loopback_literal(host: str) -> str | None:
    """Return the loopback literal for ``host`` or None when it is not loopback.

    Names are never resolved. A rebound answer can therefore never redirect
    the advisory, and only an address literal or the reserved loopback name is
    accepted.
    """
    if host.lower() == "localhost":
        return "127.0.0.1"
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return None
    if not address.is_loopback:
        return None
    return "[" + str(address) + "]" if address.version == 6 else str(address)


def gateway_endpoint(raw: str) -> str:
    """Return the validated loopback gateway endpoint or fail closed.

    The accepted endpoint is exactly ``http://<loopback>:<port>/v1/systemone``
    (or the same shape over ``https`` for an owner-approved encrypted tunnel
    that terminates on loopback). Userinfo, a query, a fragment, any other
    path, a missing or privileged port and any address outside loopback are
    refused before a socket is opened.
    """
    if not isinstance(raw, str):
        raise JevUnavailable("GATEWAY_ENDPOINT_INVALID")
    value = raw.strip()
    if not value or any(ch.isspace() or ord(ch) < 0x21 or ord(ch) == 0x7F for ch in value):
        raise JevUnavailable("GATEWAY_ENDPOINT_INVALID")
    try:
        parts = parse.urlsplit(value)
        port = parts.port
    except ValueError:
        raise JevUnavailable("GATEWAY_ENDPOINT_INVALID") from None
    if parts.scheme.lower() not in GATEWAY_SCHEMES:
        raise JevUnavailable("GATEWAY_ENDPOINT_INVALID")
    if "@" in parts.netloc or parts.username is not None or parts.password is not None:
        raise JevUnavailable("GATEWAY_ENDPOINT_INVALID")
    if parts.query or parts.fragment:
        raise JevUnavailable("GATEWAY_ENDPOINT_INVALID")
    if parts.path != GATEWAY_PATH:
        raise JevUnavailable("GATEWAY_ENDPOINT_INVALID")
    if port is None or not 1024 <= port <= 65535:
        raise JevUnavailable("GATEWAY_ENDPOINT_INVALID")
    literal = _loopback_literal(parts.hostname or "")
    if literal is None:
        raise JevUnavailable("GATEWAY_ENDPOINT_INVALID")
    return "%s://%s:%d%s" % (parts.scheme.lower(), literal, port, GATEWAY_PATH)


def _shared_gateway_target() -> tuple[str, str]:
    """Resolve the owner-selected loopback endpoint and its scoped bearer."""
    endpoint = os.environ.get(GATEWAY_ENDPOINT_ENV)
    token = os.environ.get(GATEWAY_TOKEN_ENV)
    if not endpoint or not endpoint.strip() or not token or not token.strip():
        raise JevUnavailable("GATEWAY_NOT_CONFIGURED")
    token = token.strip()
    if len(token) < MIN_GATEWAY_TOKEN_CHARS:
        raise JevUnavailable("GATEWAY_TOKEN_INVALID")
    # The bearer is carried in a header. A control character would leave the
    # request before this module could refuse it, so it is refused here with a
    # bounded code instead of surfacing as an unwrapped transport error.
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in token):
        raise JevUnavailable("GATEWAY_TOKEN_INVALID")
    return gateway_endpoint(endpoint), token


def _transport_plan(api_key: str | None) -> tuple[str, str]:
    """Return the (endpoint, bearer) pair for the owner-selected transport.

    The shared gateway never borrows the direct vendor key: an unusable shared
    configuration fails closed instead of quietly reaching the vendor directly.
    """
    mode = (os.environ.get(TRANSPORT_ENV) or "").strip().lower() or DIRECT_TRANSPORT
    if mode == SHARED_GATEWAY_TRANSPORT:
        return _shared_gateway_target()
    if mode != DIRECT_TRANSPORT:
        raise JevUnavailable("TRANSPORT_INVALID")
    key = api_key if api_key is not None else (os.environ.get("EXPERIENTIAL_API_KEY")
        or os.environ.get("EXPLABS_API_KEY") or os.environ.get("EXPLABS_KEY_1"))
    if not key:
        raise JevUnavailable("NOT_CONFIGURED")
    return ENDPOINT, key


TASK_QUESTIONS: dict[str, dict[str, Any]] = {
    "complexity": {
        "type": "choice",
        "instructions": "Classify reasoning difficulty of this exact bounded child, not business importance. C3 only for unresolved architecture, contradictions, or frontier judgment.",
        "criteria": {
            "C0_MECHANICAL": "Mechanical deterministic transform or narrow extraction.",
            "C1_ROUTINE_BOUNDED": "Clear requirement, settled architecture, routine implementation or tests.",
            "C2_COMPLEX_BOUNDED": "Difficult multi-step engineering or research, architecture settled.",
            "C3_FRONTIER_JUDGMENT": "Unresolved architecture, source authority, or principal-level judgment.",
        },
    },
    "architecture_ambiguity": {
        "type": "noul",
        "instructions": "Does this bounded child require deciding an unresolved architecture or authority boundary?",
    },
    "independent_review": {
        "type": "noul",
        "instructions": "Would qualified independent review detect a material risk in this child?",
    },
    "execution_risk": {
        "type": "score",
        "instructions": "Severity of a wrong execution, independently of reasoning difficulty.",
        "criteria": ["Routine and readily reversible", "Material repair or user impact",
                     "Critical or irreversible external consequence"],
    },
}

RESULT_QUESTIONS: dict[str, dict[str, Any]] = {
    "completion": {
        "type": "choice",
        "instructions": "What completion state does this worker output actually claim? Never infer unseen evidence.",
        "criteria": {"complete_claimed": "Claims deliverables and verification are present",
                     "incomplete": "Reports unfinished, missing or failed deliverables",
                     "uncertain": "Insufficient basis to classify completion"},
    },
    "evidence_gap": {"type": "noul",
                     "instructions": "Does worker output lack a verification artifact required by the packet?"},
    "review_warranted": {"type": "noul",
                         "instructions": "Does this reported work merit qualified independent review?"},
    "output_risk": {"type": "score", "instructions": "Consequence of an unverified or wrong result.",
                    "criteria": ["Routine", "Material", "Critical"]},
}


def _probability(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise JevUnavailable("MALFORMED_ANSWER")
    result = float(value)
    if not math.isfinite(result) or not 0 <= result <= 1:
        raise JevUnavailable("MALFORMED_ANSWER")
    return result


def _score(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise JevUnavailable("MALFORMED_ANSWER")
    result = float(value)
    if not math.isfinite(result) or not 0 <= result <= 2:
        raise JevUnavailable("MALFORMED_ANSWER")
    return result


def _choice(answers: dict[str, Any], qid: str, options: set[str]) -> tuple[str, float]:
    raw = answers.get(qid)
    if not isinstance(raw, dict) or raw.get("type") != "choice":
        raise JevUnavailable("MALFORMED_ANSWER")
    chosen = raw.get("choice")
    if not isinstance(chosen, str) or chosen not in options:
        raise JevUnavailable("MALFORMED_ANSWER")
    return chosen, _probability(raw.get("confidence"))


def _noul(answers: dict[str, Any], qid: str) -> float:
    raw = answers.get(qid)
    if not isinstance(raw, dict) or raw.get("type") != "noul":
        raise JevUnavailable("MALFORMED_ANSWER")
    return _probability(raw.get("noul"))


def _rubric(answers: dict[str, Any], qid: str) -> float:
    raw = answers.get(qid)
    if not isinstance(raw, dict) or raw.get("type") != "score":
        raise JevUnavailable("MALFORMED_ANSWER")
    return _score(raw.get("score"))


def _usage(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {key: value[key] for key in ("input_tokens", "output_tokens")
            if type(value.get(key)) is int and 0 <= value[key] <= 10000000}


def evaluate(kind: str, state: dict[str, Any], *,
             candidates: list[str] | None = None,
             api_key: str | None = None,
             timeout_s: float = 3.0,
             transport: Callable[[bytes, str, float], dict[str, Any]] | None = None,
             opener: Any = None
             ) -> dict[str, Any]:
    """Return a validated typed advisory; transport injection is for offline tests.

    ``transport`` replaces the whole send and keeps the incumbent three
    argument call form. ``opener`` replaces only the urllib opener, so the real
    endpoint, headers, redirect refusal and error mapping stay qualified.
    """
    if kind not in ("task", "result", "skills") or not isinstance(state, dict):
        raise JevUnavailable("INVALID_INPUT")
    if not isinstance(timeout_s, (int, float)) or not math.isfinite(timeout_s) or not 0 < timeout_s <= 15:
        raise JevUnavailable("INVALID_TIMEOUT")
    try:
        encoded_state = json.dumps(state, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError, UnicodeError):
        raise JevUnavailable("INVALID_INPUT") from None
    if len(encoded_state) > MAX_STATE_BYTES:
        raise JevUnavailable("STATE_TOO_LARGE")
    if kind == "task":
        questions = TASK_QUESTIONS
    elif kind == "result":
        questions = RESULT_QUESTIONS
    else:
        if not isinstance(candidates, list) or not 1 <= len(candidates) <= 30:
            raise JevUnavailable("INVALID_CANDIDATES")
        if any(not isinstance(v, str) or not v.strip() or len(v) > 160 for v in candidates):
            raise JevUnavailable("INVALID_CANDIDATES")
        if len(set(candidates)) != len(candidates):
            raise JevUnavailable("DUPLICATE_CANDIDATES")
        options = {"none": "No listed skill is appropriate"}
        options.update({"skill_" + str(i): v for i, v in enumerate(candidates)})
        questions = {"skill": {"type": "choice",
            "instructions": "Which one listed skill most directly fits this task? This cannot waive mandatory skill triggers.",
            "criteria": options}}
    body = json.dumps({"model": MODEL, "state": state, "questions": questions},
                      ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(body) > MAX_BODY_BYTES:
        raise JevUnavailable("BODY_TOO_LARGE")
    endpoint, bearer = _transport_plan(api_key)
    start = time.monotonic()
    sender = transport or (lambda payload, secret, budget:
                           native_post(payload, secret, budget, endpoint, opener))
    try:
        response = sender(body, bearer, timeout_s)
    except (error.URLError, OSError, TimeoutError, http.client.HTTPException):
        # A provider transport failure is an advisory miss with a bounded
        # code. Never let a raw provider exception carry request text or
        # credential detail into the caller's stderr, and never retry.
        raise JevUnavailable("TRANSPORT") from None
    elapsed = round((time.monotonic() - start) * 1000)
    if not isinstance(response, dict) or not isinstance(response.get("answers"), dict):
        raise JevUnavailable("INVALID_RESPONSE")
    answers = response["answers"]
    if kind == "task":
        complexity, confidence = _choice(answers, "complexity", set(COMPLEXITIES))
        values = {"complexity": complexity, "confidence": confidence,
                  "architecture_ambiguity": _noul(answers, "architecture_ambiguity"),
                  "independent_review": _noul(answers, "independent_review"),
                  "execution_risk": _rubric(answers, "execution_risk")}
    elif kind == "result":
        completion, confidence = _choice(answers, "completion",
                                         {"complete_claimed", "incomplete", "uncertain"})
        values = {"completion": completion, "confidence": confidence,
                  "evidence_gap": _noul(answers, "evidence_gap"),
                  "review_warranted": _noul(answers, "review_warranted"),
                  "output_risk": _rubric(answers, "output_risk")}
    else:
        selected, confidence = _choice(answers, "skill",
            {"none"} | {"skill_" + str(i) for i in range(len(candidates or []))})
        values = {"skill": None if selected == "none" else candidates[int(selected[6:])],
                  "confidence": confidence}
    return {"schema": "mastermind.fabric_jev_advisory/v1",
            "kind": kind, "authority": "ADVISORY_ONLY",
            "model": response.get("model") if isinstance(response.get("model"), str) else MODEL,
            "values": values, "usage": _usage(response.get("usage")),
            "latency_ms": elapsed}


def select_complexity(advice: dict[str, Any], incumbent: str, *, threshold: float = .90) -> str:
    """Only fill missing complexity; never alter an explicit caller constraint."""
    if incumbent or advice.get("kind") != "task":
        return incumbent
    values = advice.get("values", {})
    complexity = values.get("complexity")
    confidence = values.get("confidence")
    if isinstance(confidence, (int, float)) and confidence >= threshold and complexity in COMPLEXITIES:
        if complexity == "C3_FRONTIER_JUDGMENT" or values.get("architecture_ambiguity", 0) >= .85:
            raise JevUnavailable("FRONTIER_NEEDS_EXPLICIT_REASON")
        return complexity
    return incumbent


def evaluate_task_packet(packet: str, task_class: str, **kwargs: Any) -> dict[str, Any]:
    return evaluate("task", {"task_class": task_class, "work_packet": packet}, **kwargs)


def evaluate_result_packet(packet: str, output: str, **kwargs: Any) -> dict[str, Any]:
    return evaluate("result", {"work_packet": packet, "worker_output": output}, **kwargs)

"""Batched typed Jev judgments for the incumbent Mastermind Subagent Fabric.

Advisory only: no worker/admission, policy, retry, lease or acceptance authority.
Exactly one native System One POST per evaluation. No auto-retries.
"""
from __future__ import annotations
import json
import math
import os
import time
from typing import Any, Callable
from urllib import error, request

ENDPOINT = "https://api.experientiallabs.ai/v1/systemone"
MODEL = "jev-latest"
MAX_STATE_BYTES = 30000
MAX_BODY_BYTES = 48000
MAX_REPLY_BYTES = 65536
COMPLEXITIES = ("C0_MECHANICAL", "C1_ROUTINE_BOUNDED", "C2_COMPLEX_BOUNDED", "C3_FRONTIER_JUDGMENT")


class JevUnavailable(RuntimeError):
    """Error code only: never place request text or credential in exceptions."""
    def __init__(self, code: str) -> None:
        super().__init__("JEV_" + code)
        self.code = code


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def native_post(body: bytes, key: str, timeout: float) -> dict[str, Any]:
    http_request = request.Request(
        ENDPOINT, data=body, method="POST",
        headers={"Authorization": "Bearer " + key,
                 "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with request.build_opener(NoRedirect).open(http_request, timeout=timeout) as response:
            data = response.read(MAX_REPLY_BYTES + 1)
    except error.HTTPError as exc:
        raise JevUnavailable("HTTP_" + str(exc.code)) from None
    except (error.URLError, OSError, TimeoutError):
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
    if not isinstance(raw, dict) or raw.get("type") != "choice" or raw.get("choice") not in options:
        raise JevUnavailable("MALFORMED_ANSWER")
    return raw["choice"], _probability(raw.get("confidence"))


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
             transport: Callable[[bytes, str, float], dict[str, Any]] | None = None
             ) -> dict[str, Any]:
    """Return a validated typed advisory; transport injection is for offline tests."""
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
    key = api_key if api_key is not None else (os.environ.get("EXPERIENTIAL_API_KEY")
        or os.environ.get("EXPLABS_API_KEY") or os.environ.get("EXPLABS_KEY_1"))
    if not key:
        raise JevUnavailable("NOT_CONFIGURED")
    start = time.monotonic()
    response = (transport or native_post)(body, key, timeout_s)
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

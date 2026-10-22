"""GitHub review Fabric admission via the EXISTING Executive CEO Unix socket.

The dedicated UID public/MCP app must NOT open the Runtime database. This
client uses the installed CEO socket and exact new review frame. The control
host alone authenticates its kernel peer and admits Jobs. Timeout after send
is EFFECT_UNKNOWN; do not retry the submit on another carrier.
"""
from __future__ import annotations

import json
import os
import re
import socket
from pathlib import Path

from control_plane.github_review_intent import COMMAND_ID_RE, ReviewIntentDecision
from control_plane.github_review_intent_ingress import FabricJobAdmissionPort
from control_plane.github_review_intent_ingress import ReviewIngressUnavailable
from control_plane.github_review_socket_contract import (
    FRAME_SCHEMA, RESPONSE_SCHEMA, MAX_FRAME_BYTES,
)

class ReviewAdmissionUnavailable(ReviewIngressUnavailable):
    """Opaque socket failure; unknown effects cannot be retried blindly."""

DEFAULT_SOCKET = "/var/run/mastermind-executive/ceo-ingress.sock"
MAX_RESPONSE = 8192


class ExecutiveReviewSocketClient:
    """Exact command status + one submit, no new Runtime or worker controller."""

    def __init__(
        self, *, socket_path: str = DEFAULT_SOCKET, timeout_seconds: float = 2.0
    ) -> None:
        path = Path(socket_path)
        if (not path.is_absolute()
                or os.path.normpath(socket_path) != socket_path
                or "\x00" in socket_path
                or len(os.fsencode(socket_path)) > 103
                or type(timeout_seconds) not in {int, float}
                or not 0 < timeout_seconds <= 4):
            raise ValueError("Executive CEO socket binding invalid")
        self._socket_path = socket_path
        self._timeout = float(timeout_seconds)

    def _call(self, frame: dict) -> dict:
        raw = json.dumps(
            frame, separators=(",", ":"), sort_keys=True,
            ensure_ascii=True, allow_nan=False,
        ).encode("ascii") + b"\n"
        if len(raw) > MAX_FRAME_BYTES:
            raise ReviewAdmissionUnavailable("REVIEW_SOCKET_FRAME_OVER_BOUND")
        sent = False
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
                conn.settimeout(self._timeout)
                conn.connect(self._socket_path)
                conn.sendall(raw)
                sent = True
                line = bytearray()
                while True:
                    block = conn.recv(min(1024, MAX_RESPONSE + 1 - len(line)))
                    if not block:
                        break
                    line.extend(block)
                    if len(line) > MAX_RESPONSE:
                        raise ValueError("response too large")
                    if b"\n" in block:
                        break
            if not line.endswith(b"\n") or line.count(b"\n") != 1:
                raise ValueError("incomplete response")
            message = json.loads(line)
            if not isinstance(message, dict) or message.get("ok") is not True:
                raise ReviewAdmissionUnavailable("REVIEW_SOCKET_ADMISSION_REFUSED")
            result = message.get("result")
            if not isinstance(result, dict) or result.get("schema") != RESPONSE_SCHEMA:
                raise ValueError("response identity invalid")
            return result
        except ReviewAdmissionUnavailable:
            raise
        except Exception:
            raise ReviewAdmissionUnavailable(
                "REVIEW_SOCKET_EFFECT_UNKNOWN" if sent else "REVIEW_SOCKET_UNAVAILABLE"
            ) from None

    def has_admitted_command(self, command_id: str) -> bool:
        if not isinstance(command_id, str) or COMMAND_ID_RE.fullmatch(command_id) is None:
            raise ReviewAdmissionUnavailable("REVIEW_COMMAND_ID_INVALID")
        result = self._call({
            "schema": FRAME_SCHEMA, "action": "status", "command_id": command_id,
        })
        if result.get("state") == "ABSENT" and set(result) == {"schema", "state"}:
            return False
        if (result.get("state") == "EXISTS"
                and isinstance(result.get("job_id"), str)
                and re.fullmatch(r"JOB-[0-9]+", result["job_id"]) is not None
                and set(result) == {"schema", "state", "job_id"}):
            return True
        raise ReviewAdmissionUnavailable("REVIEW_SOCKET_STATUS_INVALID")

    def admitted_command_ids(self) -> frozenset[str]:
        # No cross-repo/whole-ledger enumeration. The ingress has a closed
        # per-command fast path through has_admitted_command.
        raise ReviewAdmissionUnavailable("REVIEW_EXACT_STATUS_REQUIRED")

    def admit_review_intent(self, *, decision: ReviewIntentDecision, objective: str) -> str:
        if not isinstance(decision, ReviewIntentDecision) or not decision.admitted:
            raise ReviewAdmissionUnavailable("REVIEW_SOCKET_DECISION_INVALID")
        if not isinstance(objective, str) or not objective:
            raise ReviewAdmissionUnavailable("REVIEW_SOCKET_OBJECTIVE_INVALID")
        result = self._call({
            "schema": FRAME_SCHEMA, "action": "admit",
            "decision": decision.to_dict(), "objective": objective,
        })
        job_id = result.get("job_id")
        if (result.get("state") != "ADMITTED" or type(job_id) is not str
                or re.fullmatch(r"JOB-[0-9]+", job_id) is None
                or set(result) != {"schema", "state", "job_id"}):
            raise ReviewAdmissionUnavailable("REVIEW_SOCKET_ADMISSION_RESULT_INVALID")
        return job_id

"""Executive OS admission port for one Hermes child.

The live Executive owner is not called. The default port refuses verbatim and
does not choose a carrier. Tests supply a fake with the same mapping shape.
"""
from __future__ import annotations

from typing import Any, Mapping


ADMISSION_SCHEMA = "mastermind.hermes_delegate.admission/v1"
NOT_BOUND_REASON = "EXECUTIVE_ADMISSION_NOT_BOUND"


class InertExecutiveAdmission:
    """No Job, Attempt, ledger write, or carrier fallback."""

    def admit(self, submission: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "schema": ADMISSION_SCHEMA,
            "outcome": "REFUSED",
            "reason": NOT_BOUND_REASON,
            "carrier": submission.get("carrier"),
            "idempotency_key": submission.get("idempotency_key"),
        }

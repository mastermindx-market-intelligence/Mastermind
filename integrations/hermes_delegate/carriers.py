"""Pure carrier request shapes. Nothing here starts a process or opens a network connection.

``fabric_task.py request`` remains the Subagent Fabric entrypoint. A Cursor
cloud agent remains a separate carrier. This module only builds the bounded
request each injected port would receive after Executive admission.
"""
from __future__ import annotations

from typing import Any, Mapping


FABRIC_ADAPTER_ARGV0 = "python3"


class CarrierNotBound(RuntimeError):
    """Default ports refuse to stand in for a real carrier."""


def fabric_request_argv(submission: Mapping[str, Any], *, adapter: str = "fabric_task.py") -> list[str]:
    """Argv for ``fabric_task.py request`` without pool, model, or credential flags.

    The installed router still chooses provider, account, and host. ``--stdin``
    carries the packet. This list is data; it is not executed here.
    """
    return [
        FABRIC_ADAPTER_ARGV0,
        adapter,
        "request",
        "--id",
        submission["idempotency_key"],
        "--class",
        submission["task_class"],
        "--task-complexity",
        submission["task_complexity"],
        "--cwd",
        "~",
        "--root",
        submission["root_id"],
        "--parent",
        submission["parent_id"],
        "--stdin",
    ]


def fabric_packet(submission: Mapping[str, Any]) -> str:
    lines = [
        f"OBJECTIVE: {submission['objective']}",
        f"CHILD_KIND: {submission['child_kind']}",
        f"ACCEPTANCE: {submission['acceptance']}",
        f"IDEMPOTENCY_KEY: {submission['idempotency_key']}",
        "CARRIER: fabric",
        "CONSTRAINTS:",
    ]
    lines.extend(f"- {item}" for item in submission["constraints"])
    return "\n".join(lines) + "\n"


def cursor_cloud_request(submission: Mapping[str, Any]) -> dict[str, Any]:
    """Bounded cloud-agent request. ``live_submit`` stays false in this package."""
    return {
        "schema": "mastermind.hermes_delegate.cursor_cloud_request/v1",
        "live_submit": False,
        "idempotency_key": submission["idempotency_key"],
        "parent_id": submission["parent_id"],
        "root_id": submission["root_id"],
        "child_kind": submission["child_kind"],
        "task_class": submission["task_class"],
        "task_complexity": submission["task_complexity"],
        "objective": submission["objective"],
        "acceptance": submission["acceptance"],
        "constraints": list(submission["constraints"]),
    }


def carrier_spec(submission: Mapping[str, Any]) -> dict[str, Any]:
    if submission["carrier"] == "fabric":
        return {
            "carrier": "fabric",
            "run_id": submission["idempotency_key"],
            "argv": fabric_request_argv(submission),
            "stdin": fabric_packet(submission),
            "live_submit": False,
        }
    if submission["carrier"] == "cursor_cloud":
        return {
            "carrier": "cursor_cloud",
            "run_id": submission["idempotency_key"],
            "request": cursor_cloud_request(submission),
            "live_submit": False,
        }
    raise CarrierNotBound("CARRIER_INVALID")


class UnboundCarrier:
    """Fail closed. Tests inject a fake; production code must not grow a client here."""

    def submit(self, spec: Mapping[str, Any]) -> dict[str, Any]:
        raise CarrierNotBound("CARRIER_NOT_BOUND")

    def status(self, run_id: str) -> dict[str, Any]:
        raise CarrierNotBound("CARRIER_NOT_BOUND")

    def cancel(self, run_id: str) -> dict[str, Any]:
        raise CarrierNotBound("CARRIER_NOT_BOUND")

    def result(self, run_id: str) -> dict[str, Any]:
        raise CarrierNotBound("CARRIER_NOT_BOUND")

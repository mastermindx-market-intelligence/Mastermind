"""Bind Browser readiness to an already-qualified Capacity candidate.

This module creates no placement, ranking, admission, lease, browser, process,
retry, or effect state. It only proves that one sealed Capacity qualification
and one sealed Browser-host qualification describe the same physical host boot.
The existing Capacity owner retains ranking and commitment.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json

from control_plane.browser_host_observation import (
    BrowserHostObservationError,
    BrowserHostQualification,
    BrowserHostState,
)
from control_plane.executive_host_placement_preference import (
    HostPlacementPreferenceError,
    QualifiedHostCandidate,
)

SCHEMA = "mastermind.browser_capacity_binding.v1"
_BINDING_SEAL = object()


class BrowserCapacityBindingError(ValueError):
    """Closed refusal from the Browser/Capacity compatibility seam."""


def _canonical(value: dict[str, object]) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise BrowserCapacityBindingError("BINDING_INVALID") from exc


@dataclass(frozen=True, slots=True)
class BrowserCapacityBinding:
    worker_id: str
    capacity_qualification_receipt_id: str
    host_ref: str
    boot_ref: str
    profile_ref: str
    browser_instance_ref: str
    connector_generation: str
    backend_schema_digest: str
    binding_digest: str
    _seal: object = field(repr=False, compare=False, default=None)

    def __post_init__(self) -> None:
        if self._seal is not _BINDING_SEAL:
            raise BrowserCapacityBindingError("binding seal is invalid")

    @property
    def is_placement(self) -> bool:
        return False

    @property
    def is_admission(self) -> bool:
        return False

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": SCHEMA,
            "worker_id": self.worker_id,
            "capacity_qualification_receipt_id": self.capacity_qualification_receipt_id,
            "host_ref": self.host_ref,
            "boot_ref": self.boot_ref,
            "profile_ref": self.profile_ref,
            "browser_instance_ref": self.browser_instance_ref,
            "connector_generation": self.connector_generation,
            "backend_schema_digest": self.backend_schema_digest,
            "binding_digest": self.binding_digest,
            "is_placement": False,
            "is_admission": False,
        }


def bind_browser_capacity_candidate(
    capacity_candidate: QualifiedHostCandidate,
    browser: BrowserHostQualification,
) -> BrowserCapacityBinding:
    """Bind two existing qualifications without selecting or mutating either."""

    if type(capacity_candidate) is not QualifiedHostCandidate:
        raise BrowserCapacityBindingError("CAPACITY_QUALIFICATION_INVALID")
    if type(browser) is not BrowserHostQualification:
        raise BrowserCapacityBindingError("BROWSER_QUALIFICATION_INVALID")
    try:
        QualifiedHostCandidate.__post_init__(capacity_candidate)
    except (HostPlacementPreferenceError, TypeError, ValueError) as exc:
        raise BrowserCapacityBindingError("CAPACITY_QUALIFICATION_INVALID") from exc
    try:
        BrowserHostQualification.__post_init__(browser)
    except BrowserHostObservationError as exc:
        raise BrowserCapacityBindingError("BROWSER_QUALIFICATION_INVALID") from exc

    if browser.state is not BrowserHostState.READY or browser.reason != "ready":
        raise BrowserCapacityBindingError("BROWSER_NOT_READY")
    if browser.host_ref != capacity_candidate.host_ref:
        raise BrowserCapacityBindingError("HOST_MISMATCH")
    if browser.boot_ref != capacity_candidate.boot_ref:
        raise BrowserCapacityBindingError("BOOT_MISMATCH")

    payload = {
        "schema": SCHEMA,
        "worker_id": capacity_candidate.worker_id,
        "capacity_qualification_receipt_id": capacity_candidate.qualification_receipt_id,
        "host_ref": capacity_candidate.host_ref,
        "boot_ref": capacity_candidate.boot_ref,
        "profile_ref": browser.profile_ref,
        "browser_instance_ref": browser.browser_instance_ref,
        "connector_generation": browser.connector_generation,
        "backend_schema_digest": browser.backend_schema_digest,
    }
    digest = hashlib.sha256(_canonical(payload)).hexdigest()
    return BrowserCapacityBinding(
        worker_id=capacity_candidate.worker_id,
        capacity_qualification_receipt_id=capacity_candidate.qualification_receipt_id,
        host_ref=capacity_candidate.host_ref,
        boot_ref=capacity_candidate.boot_ref,
        profile_ref=browser.profile_ref,
        browser_instance_ref=browser.browser_instance_ref,
        connector_generation=browser.connector_generation,
        backend_schema_digest=browser.backend_schema_digest,
        binding_digest=digest,
        _seal=_BINDING_SEAL,
    )


__all__ = [
    "SCHEMA",
    "BrowserCapacityBinding",
    "BrowserCapacityBindingError",
    "bind_browser_capacity_candidate",
]

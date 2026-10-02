"""Pure reducer for deep, PID-bound Peekaboo accessibility observations.

This module performs no subprocess, UI, network, credential, persistence, or
lifecycle operation. A trusted native wrapper owns capture and supplies the
already-authoritative RuntimeBinding/seat/app metadata. The reducer validates
that metadata against the immutable DesktopTarget and projects only semantic
AX evidence into DesktopSnapshot.

Peekaboo element ids and geometry are observation evidence, never provider
session or turn identities. No title, OCR string, coordinate, or local hash is
promoted to a provider-native id.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Iterable, Mapping

from .turn import (
    DesktopSnapshot,
    DesktopTarget,
    EvidenceError,
    MessageEvidence,
    ModeSelection,
)

MAX_AX_ELEMENTS = 4000
_MAX_ELEMENT_TEXT = 262144
_DELIVERED_STATUS = frozenset({"read", "sent", "delivered"})
_TRANSIENT_STATUS = frozenset({"sending", "retrying"})
_BLOCK_TEXT = {
    "thinking failed": "unknown",
    "response failed": "transport",
    "network error": "transport",
    "something went wrong": "unknown",
}
def _map(value: object, code: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise EvidenceError(code)
    return value


def _string(value: object) -> str:
    return value if isinstance(value, str) else ""


def _clean(value: object) -> str:
    return re.sub(r"[ \t\r\f\v]+", " ", _string(value)).strip()


def _element_text(element: Mapping[str, Any]) -> str:
    for key in ("value", "label", "title", "description"):
        value = _string(element.get(key))
        if value:
            if len(value.encode("utf-8", errors="ignore")) > _MAX_ELEMENT_TEXT:
                raise EvidenceError("ax_element_text_too_large")
            return value
    return ""


def _bounds(element: Mapping[str, Any]) -> tuple[float, float, float, float]:
    raw = _map(element.get("bounds"), "ax_bounds_missing")
    try:
        x, y = float(raw["x"]), float(raw["y"])
        width, height = float(raw["width"]), float(raw["height"])
    except (KeyError, TypeError, ValueError, OverflowError):
        raise EvidenceError("ax_bounds_invalid") from None
    if min(x, y, width, height) < 0 or width <= 0 or height <= 0:
        raise EvidenceError("ax_bounds_invalid")
    return x, y, width, height
def _contains(
    outer: tuple[float, float, float, float],
    inner: tuple[float, float, float, float],
) -> bool:
    ox, oy, ow, oh = outer
    ix, iy, iw, ih = inner
    cx, cy = ix + iw / 2.0, iy + ih / 2.0
    return ox <= cx <= ox + ow and oy <= cy <= oy + oh


def _semantic_elements(data: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    raw = data.get("ui_elements")
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_AX_ELEMENTS:
        raise EvidenceError("ax_element_collection_invalid")
    result = []
    for item in raw:
        element = _map(item, "ax_element_invalid")
        element_id = _string(element.get("id"))
        if not element_id or element_id.startswith("ocr_"):
            continue
        result.append(element)
    if not result:
        raise EvidenceError("semantic_ax_elements_missing")
    return tuple(result)


def _match_exact_label(elements: Iterable[Mapping[str, Any]], value: str) -> bool:
    wanted = value.casefold()
    return any(
        _clean(_element_text(element)).casefold() == wanted
        for element in elements
    )
def _validate_target_receipt(
    payload: Mapping[str, Any], target: DesktopTarget
) -> None:
    receipt = _map(
        payload.get("target_receipt"),
        "peekaboo_target_receipt_missing",
    )
    if (
        receipt.get("pid") != target.pid
        or receipt.get("window_id") != target.window_id
    ):
        raise EvidenceError("peekaboo_target_receipt_mismatch")
    start = receipt.get("process_start_identity_decimal")
    if start is None:
        start = receipt.get("process_start_identity")
    if str(start) != target.process_start_ref:
        raise EvidenceError("peekaboo_process_identity_mismatch")


def _validate_capture_context(
    target: DesktopTarget,
    *,
    observed_host_ref: str,
    observed_seat_ref: str,
    observed_project_ref: str,
    observed_bundle_id: str,
    observed_app_version: str,
) -> None:
    expected = (
        target.host_ref,
        target.seat_ref,
        target.project_ref,
        target.app_bundle_id,
        target.app_version,
    )
    observed = (
        observed_host_ref,
        observed_seat_ref,
        observed_project_ref,
        observed_bundle_id,
        observed_app_version,
    )
    if observed != expected:
        raise EvidenceError("trusted_capture_context_mismatch")

"""Stable public seam for the closed Web-Sol protocol.

The reviewed protocol implementation is preserved byte-for-byte in the
internal implementation module. This public seam adds one narrow semantic
repair: a continuation cannot be classified STARTED while the exact target
probe reports a provider error. No schema, request, retry, lifecycle,
persistence, target-selection, or effect-ownership behavior changes here.
"""
from __future__ import annotations

import sys as _sys
from typing import Any as _Any

from . import _web_sol_protocol_impl as _impl

_validate_receipt_impl = _impl.validate_receipt


def _validate_receipt(value: dict[str, _Any]) -> dict[str, _Any]:
    receipt = _validate_receipt_impl(value)
    if (
        receipt["action"] == _impl.SurfaceAction.SUBMIT_CONTINUATION.value
        and receipt["status"] == _impl.ReceiptStatus.CONTINUATION_STARTED.value
        and receipt["observation"]["provider_error_present"] is True
    ):
        raise _impl.WebSolProtocolError(
            "$.observation.provider_error_present: "
            "must not be true for CONTINUATION_STARTED"
        )
    return receipt


# Imported callers receive the original implementation module so existing
# public and private seams, classes, function globals, and monkeypatches retain
# one identity. Only the public receipt validator is replaced.
_impl.validate_receipt = _validate_receipt
_sys.modules[__name__] = _impl

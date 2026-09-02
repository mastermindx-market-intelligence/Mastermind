"""Closed hosted-runner contract for the held Code Intelligence experiment.

No function here downloads, installs, launches, or discovers a tool.  The
hosted workflow must validate its frozen supply lock before it performs those
separate operations.  Keeping this layer pure gives reviewers an executable
proof that no caller can select a URL, command, credential, cache, runner, or
image.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import re
import sys
from typing import Mapping, Sequence


OPERATION_KEY = "mastermind-codeintel-b0-hosted-tool-bundle-forge-20260902-sol-001"
RECEIPT_SCHEMA = "mastermind.codeintel_experiment_bundle.v1"
_INPUT_KEYS = frozenset({"mode", "consumer_sha", "consumer_tree_sha", "operation_key"})
_MODES = frozenset({"C0", "Z0"})
_EFFECTS = frozenset({"NOT_APPLIED", "APPLIED", "EFFECT_UNKNOWN"})
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_REASON = re.compile(r"^[A-Z][A-Z0-9_]{2,95}$")


class DispatchInputError(ValueError):
    """Raised for any deviation from the four-field dispatch surface."""


class ReceiptError(ValueError):
    """Raised when a result receipt cannot be safely represented."""


@dataclass(frozen=True)
class DispatchRequest:
    mode: str
    consumer_sha: str
    consumer_tree_sha: str
    operation_key: str


def _require_hex(value: object, code: str, expression: re.Pattern[str]) -> str:
    if not isinstance(value, str) or not expression.fullmatch(value):
        raise DispatchInputError(code)
    return value


def validate_dispatch_inputs(inputs: Mapping[str, object]) -> DispatchRequest:
    """Validate only the immutable Mode, consumer commit/tree, and operation key."""

    keys = set(inputs)
    if keys - _INPUT_KEYS:
        raise DispatchInputError("UNEXPECTED_DISPATCH_INPUT")
    if keys != _INPUT_KEYS:
        raise DispatchInputError("DISPATCH_INPUT_MISSING")
    mode = inputs["mode"]
    if not isinstance(mode, str) or mode not in _MODES:
        raise DispatchInputError("MODE_INVALID")
    consumer_sha = _require_hex(inputs["consumer_sha"], "CONSUMER_SHA_INVALID", _HEX40)
    consumer_tree_sha = _require_hex(
        inputs["consumer_tree_sha"], "CONSUMER_TREE_SHA_INVALID", _HEX40
    )
    if inputs["operation_key"] != OPERATION_KEY:
        raise DispatchInputError("OPERATION_KEY_INVALID")
    return DispatchRequest(
        mode=mode,
        consumer_sha=consumer_sha,
        consumer_tree_sha=consumer_tree_sha,
        operation_key=OPERATION_KEY,
    )


def fixed_phase_e_command(mode: str) -> str:
    """Return the sole sealed command for a consumer mode; no argv is accepted."""

    if mode not in _MODES:
        raise DispatchInputError("MODE_INVALID")
    return (
        "unshare -n -- /usr/bin/env -i PATH=/usr/bin:/bin "
        "python3 -m experiments.codeintel_supply.hosted_runner "
        f"execute --sealed --mode {mode}"
    )


def _receipt_hex(value: object, code: str) -> str:
    if not isinstance(value, str) or not _HEX64.fullmatch(value):
        raise ReceiptError(code)
    return value


def build_receipt(
    *,
    mode: str,
    consumer_sha: str,
    consumer_tree_sha: str,
    lock_digest: str,
    bundle_sha256: str,
    effect: str,
    reason_codes: Sequence[str],
) -> dict[str, object]:
    """Create the public, closed receipt; arbitrary metadata is intentionally absent."""

    try:
        request = validate_dispatch_inputs(
            {
                "mode": mode,
                "consumer_sha": consumer_sha,
                "consumer_tree_sha": consumer_tree_sha,
                "operation_key": OPERATION_KEY,
            }
        )
    except DispatchInputError as error:
        raise ReceiptError(str(error)) from error
    if effect not in _EFFECTS:
        raise ReceiptError("EFFECT_INVALID")
    if not isinstance(reason_codes, Sequence) or isinstance(reason_codes, (str, bytes)):
        raise ReceiptError("REASON_CODES_INVALID")
    normalized_reasons = sorted(set(reason_codes))
    if not all(isinstance(code, str) and _REASON.fullmatch(code) for code in normalized_reasons):
        raise ReceiptError("REASON_CODES_INVALID")
    return validate_receipt(
        {
        "schema": RECEIPT_SCHEMA,
        "operation_key": request.operation_key,
        "mode": request.mode,
        "consumer_sha": request.consumer_sha,
        "consumer_tree_sha": request.consumer_tree_sha,
        "lock_digest": _receipt_hex(lock_digest, "LOCK_DIGEST_INVALID"),
        "bundle_sha256": _receipt_hex(bundle_sha256, "BUNDLE_SHA256_INVALID"),
        "effect": effect,
        "reason_codes": normalized_reasons,
        }
    )


def validate_receipt(receipt: Mapping[str, object]) -> dict[str, object]:
    """Validate the complete closed receipt before it can govern any replay."""

    if not isinstance(receipt, Mapping):
        raise ReceiptError("RECEIPT_INVALID")
    expected_keys = {
        "schema",
        "operation_key",
        "mode",
        "consumer_sha",
        "consumer_tree_sha",
        "lock_digest",
        "bundle_sha256",
        "effect",
        "reason_codes",
    }
    if set(receipt) != expected_keys:
        raise ReceiptError("RECEIPT_KEYS_INVALID")
    if receipt["schema"] != RECEIPT_SCHEMA:
        raise ReceiptError("RECEIPT_SCHEMA_INVALID")
    try:
        request = validate_dispatch_inputs(
            {
                "mode": receipt["mode"],
                "consumer_sha": receipt["consumer_sha"],
                "consumer_tree_sha": receipt["consumer_tree_sha"],
                "operation_key": receipt["operation_key"],
            }
        )
    except DispatchInputError as error:
        raise ReceiptError(str(error)) from error
    if not isinstance(receipt["effect"], str) or receipt["effect"] not in _EFFECTS:
        raise ReceiptError("EFFECT_INVALID")
    reason_codes = receipt["reason_codes"]
    if not isinstance(reason_codes, list) or not all(
        isinstance(code, str) and _REASON.fullmatch(code) for code in reason_codes
    ):
        raise ReceiptError("REASON_CODES_INVALID")
    if reason_codes != sorted(set(reason_codes)):
        raise ReceiptError("REASON_CODES_INVALID")
    return {
        "schema": RECEIPT_SCHEMA,
        "operation_key": request.operation_key,
        "mode": request.mode,
        "consumer_sha": request.consumer_sha,
        "consumer_tree_sha": request.consumer_tree_sha,
        "lock_digest": _receipt_hex(receipt["lock_digest"], "LOCK_DIGEST_INVALID"),
        "bundle_sha256": _receipt_hex(receipt["bundle_sha256"], "BUNDLE_SHA256_INVALID"),
        "effect": receipt["effect"],
        "reason_codes": reason_codes,
    }


def retry_allowed(receipt: Mapping[str, object]) -> bool:
    """Only a proven non-application can be retried; unknown effect is terminal."""

    try:
        return validate_receipt(receipt)["effect"] == "NOT_APPLIED"
    except ReceiptError:
        return False


def main(argv: Sequence[str] | None = None) -> int:
    """Fail closed for an invoked held experiment before any external effect."""

    parser = argparse.ArgumentParser(prog="codeintel-hosted-runner")
    subcommands = parser.add_subparsers(dest="command", required=True)
    execute = subcommands.add_parser("execute")
    execute.add_argument("--sealed", action="store_true", required=True)
    execute.add_argument("--mode", choices=sorted(_MODES), required=True)
    arguments = parser.parse_args(argv)
    if arguments.command != "execute" or not arguments.sealed:
        return 64
    sys.stderr.write("HELD_SOURCE_CONTRACT_ONLY\n")
    return 78


if __name__ == "__main__":
    raise SystemExit(main())

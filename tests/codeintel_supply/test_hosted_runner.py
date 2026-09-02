from __future__ import annotations

import json
import subprocess
import sys

import pytest

from experiments.codeintel_supply.hosted_runner import (
    DispatchInputError,
    ReceiptError,
    build_receipt,
    fixed_phase_e_command,
    retry_allowed,
    validate_dispatch_inputs,
    validate_receipt,
)


OPERATION_KEY = "mastermind-codeintel-b0-hosted-tool-bundle-forge-20260902-sol-001"
CONSUMER_SHA = "a" * 40
CONSUMER_TREE_SHA = "b" * 40


def _inputs(**overrides: str) -> dict[str, str]:
    value = {
        "mode": "C0",
        "consumer_sha": CONSUMER_SHA,
        "consumer_tree_sha": CONSUMER_TREE_SHA,
        "operation_key": OPERATION_KEY,
    }
    value.update(overrides)
    return value


def test_closed_dispatch_input_contract_accepts_only_the_named_four_inputs():
    request = validate_dispatch_inputs(_inputs())

    assert request.mode == "C0"
    assert request.consumer_sha == CONSUMER_SHA
    assert request.consumer_tree_sha == CONSUMER_TREE_SHA
    assert request.operation_key == OPERATION_KEY

    with pytest.raises(DispatchInputError, match="UNEXPECTED_DISPATCH_INPUT"):
        validate_dispatch_inputs(_inputs(caller_url="https://example.invalid"))


@pytest.mark.parametrize(
    "overrides, code",
    [
        ({"mode": "P0"}, "MODE_INVALID"),
        ({"consumer_sha": "A" * 40}, "CONSUMER_SHA_INVALID"),
        ({"consumer_tree_sha": "b" * 39}, "CONSUMER_TREE_SHA_INVALID"),
        ({"operation_key": "mastermind-codeintel-c0-anything"}, "OPERATION_KEY_INVALID"),
    ],
)
def test_dispatch_input_contract_fails_closed(overrides, code):
    with pytest.raises(DispatchInputError, match=code):
        validate_dispatch_inputs(_inputs(**overrides))


def test_phase_e_command_is_mode_fixed_and_never_accepts_caller_argv_or_network():
    c0 = fixed_phase_e_command("C0")
    z0 = fixed_phase_e_command("Z0")

    assert c0 != z0
    assert "unshare -n" in c0
    assert "--mode C0" in c0
    assert "--mode Z0" in z0
    assert "{consumer" not in c0
    assert "{argv" not in c0


def test_receipt_is_closed_secret_free_and_effect_unknown_blocks_retry():
    receipt = build_receipt(
        mode="Z0",
        consumer_sha=CONSUMER_SHA,
        consumer_tree_sha=CONSUMER_TREE_SHA,
        lock_digest="c" * 64,
        bundle_sha256="d" * 64,
        effect="EFFECT_UNKNOWN",
        reason_codes=["POST_PHASE_E_RECEIPT_UNAVAILABLE"],
    )

    assert set(receipt) == {
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
    assert receipt["schema"] == "mastermind.codeintel_experiment_bundle.v1"
    assert receipt["effect"] == "EFFECT_UNKNOWN"
    assert retry_allowed(receipt) is False
    rendered = json.dumps(receipt, sort_keys=True)
    assert "/Users/" not in rendered
    assert "token" not in rendered.lower()


def test_receipt_rejects_any_open_ended_or_nonterminal_effect():
    with pytest.raises(ReceiptError, match="EFFECT_INVALID"):
        build_receipt(
            mode="C0",
            consumer_sha=CONSUMER_SHA,
            consumer_tree_sha=CONSUMER_TREE_SHA,
            lock_digest="c" * 64,
            bundle_sha256="d" * 64,
            effect="RETRYING",
            reason_codes=[],
        )


def test_retry_requires_a_complete_validated_not_applied_receipt():
    valid_receipt = build_receipt(
        mode="C0",
        consumer_sha=CONSUMER_SHA,
        consumer_tree_sha=CONSUMER_TREE_SHA,
        lock_digest="c" * 64,
        bundle_sha256="d" * 64,
        effect="NOT_APPLIED",
        reason_codes=["SEALED_PHASE_NOT_ENTERED"],
    )

    assert validate_receipt(valid_receipt) == valid_receipt
    assert retry_allowed(valid_receipt) is True
    assert retry_allowed({"effect": "NOT_APPLIED"}) is False
    assert retry_allowed({**valid_receipt, "untrusted": True}) is False
    assert retry_allowed({**valid_receipt, "mode": ["C0"]}) is False
    assert retry_allowed({**valid_receipt, "effect": ["NOT_APPLIED"]}) is False


def test_sealed_module_entrypoint_fails_closed_while_the_experiment_is_held():
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "experiments.codeintel_supply.hosted_runner",
            "execute",
            "--sealed",
            "--mode",
            "C0",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 78
    assert result.stdout == ""
    assert result.stderr == "HELD_SOURCE_CONTRACT_ONLY\n"

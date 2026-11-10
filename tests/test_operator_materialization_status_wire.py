"""Canonical typed status encoding preserves each original receipt schema."""
import pytest

from control_plane.operator_harness_wire import to_wire
from control_plane.operator_materialization_receipt import (
    MATERIALIZATION_RECEIPT_SCHEMA_V3,
    MATERIALIZATION_STATUS_SCHEMA,
    OperatorMaterializationReceiptError,
    build_operator_materialization_receipt,
    canonical_json_bytes,
    operator_materialization_status,
)
from tests.test_operator_materialization_receipt import _inputs, _receipt
from tests.test_remote_planner_producer_custody import selection, versioned_receipt


def _versioned_receipt(version):
    if version == 1:
        return _receipt()
    if version == 2:
        return versioned_receipt()
    values = _inputs()
    values.pop("expected_provider_session_id")
    return build_operator_materialization_receipt(**values,
        schema=MATERIALIZATION_RECEIPT_SCHEMA_V3,
        planner_producer=selection(attempt=values["attempt_id"]))


@pytest.mark.parametrize("version", [1, 2, 3])
@pytest.mark.parametrize("state", ["RECEIPT_CURRENT_IN_LIVE_BROKER", "RECEIPT_ONLY_AFTER_RESTART"])
def test_status_round_trip_preserves_exact_original_receipt_bytes(version, state):
    receipt = _versioned_receipt(version)
    original = {"schema_version": MATERIALIZATION_STATUS_SCHEMA,
                "status": state, "receipt": receipt.to_dict()}
    status = operator_materialization_status(original)
    encoded = status.to_dict()
    assert canonical_json_bytes(encoded) == canonical_json_bytes(original)
    assert operator_materialization_status(encoded) == status
    assert encoded["receipt"]["receipt_digest"] == receipt.receipt_digest
    if version == 1:
        assert "planner_producer" not in encoded["receipt"]
    if version in (1, 3):
        assert "observed_planner_contract" not in encoded["receipt"]
        # Generic dataclass expansion is deliberately NOT the versioned codec.
        with pytest.raises(OperatorMaterializationReceiptError, match="closed schema"):
            operator_materialization_status(to_wire(status))
        omitted = ("planner_producer", "observed_planner_contract") if version == 1 else ("observed_planner_contract",)
        for field in omitted:
            explicit_none = {**encoded, "receipt": {**encoded["receipt"], field: None}}
            with pytest.raises(OperatorMaterializationReceiptError, match="closed schema"):
                operator_materialization_status(explicit_none)


@pytest.mark.parametrize("state", ["ABSENT", "CONFLICT"])
def test_negative_status_keeps_explicit_absence_and_closed_schema(state):
    original = {"schema_version": MATERIALIZATION_STATUS_SCHEMA,
                "status": state, "receipt": None}
    status = operator_materialization_status(original)
    assert status.to_dict() == original
    with pytest.raises(OperatorMaterializationReceiptError):
        operator_materialization_status({**status.to_dict(), "receipt": _receipt().to_dict()})

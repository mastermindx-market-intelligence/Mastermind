"""Final receipt consumption through the existing read-only Runtime boundary.

Runtime and terminal proofs are real local objects. Namespace custody, Context
source acquisition and Relay observations remain explicit test fixtures.
"""
import sqlite3

import pytest

from control_plane.executive_runtime import Runtime, RuntimeReadBinding, RuntimeReadUnavailable
from integrations.product_acceptance_request_owner import (
    ProductAcceptanceRequestOwner, ProductAcceptanceRequestUnavailable,
)
from integrations.product_acceptance_ruling_owner import ProductAcceptanceRulingReceiptReader
from tests.test_executive_runtime_bounded_read import ObservationNamespace
from tests.test_product_acceptance_ruling_owner import ready, qualify, complete_parent


@pytest.mark.parametrize("parent_complete", [False, True])
def test_receipt_reader_uses_bound_read_only_runtime_without_principal_owner(
    tmp_path, monkeypatch, parent_complete,
):
    values = ready(tmp_path, monkeypatch)
    runtime, requester, _binding, _target, _basis, prepared, *_ = values
    qualified = qualify(values)
    if parent_complete:
        complete_parent(runtime, requester, [qualified["evidence_digest"]])
    before = runtime.events.list_events()
    keeper = sqlite3.connect(runtime.store.path, isolation_level=None)
    keeper.execute("SELECT 1 FROM jobs").fetchone()
    namespace = ObservationNamespace(runtime.store.path)
    binding = RuntimeReadBinding(namespace)

    def read(bound_runtime):
        owner = ProductAcceptanceRequestOwner(bound_runtime, requester.reader)
        assert owner.ruling_owner is None
        return ProductAcceptanceRulingReceiptReader(owner).observe_acceptance(
            prepared.message["message_key"]
        )

    try:
        if parent_complete:
            result = Runtime.read_bound(tmp_path, binding=binding, reader=read)
            assert result["state"] == "PRODUCT_ACCEPTED"
            assert result["qualified_ruling_digest"] == qualified["evidence_digest"]
            assert result["parent_job_id"] == requester._test_root.job_id
        else:
            with pytest.raises(ProductAcceptanceRequestUnavailable,
                               match="PRODUCT_PARENT_RETURN_UNVERIFIED"):
                Runtime.read_bound(tmp_path, binding=binding, reader=read)
        assert runtime.events.list_events() == before
        assert namespace.entries == namespace.exits and not namespace.active
    finally:
        keeper.close()


def test_bound_receipt_is_withheld_if_namespace_invalidates_before_return(tmp_path, monkeypatch):
    values = ready(tmp_path, monkeypatch)
    runtime, requester, _binding, _target, _basis, prepared, *_ = values
    qualified = qualify(values)
    complete_parent(runtime, requester, [qualified["evidence_digest"]])
    keeper = sqlite3.connect(runtime.store.path, isolation_level=None)
    keeper.execute("SELECT 1 FROM jobs").fetchone()
    namespace = ObservationNamespace(runtime.store.path)
    binding = RuntimeReadBinding(namespace)

    def read(bound_runtime):
        receipt = ProductAcceptanceRulingReceiptReader(
            ProductAcceptanceRequestOwner(bound_runtime, requester.reader)
        ).observe_acceptance(prepared.message["message_key"])
        namespace.invalid = True
        return receipt

    try:
        with pytest.raises(RuntimeReadUnavailable):
            Runtime.read_bound(tmp_path, binding=binding, reader=read)
    finally:
        keeper.close()

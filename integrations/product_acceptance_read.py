"""Existing final receipt owner to a bounded selected read, with no write authority."""
from __future__ import annotations

from common import product_acceptance_read_contract as contract
from control_plane.agentos_product_acceptance_basis import (
    AgentOsProductAcceptanceBasisReader, ProductAcceptanceBasisUnavailable,
)
from control_plane.executive_runtime import Runtime
from integrations.product_acceptance_request_owner import (
    ProductAcceptanceRequestOwner, ProductAcceptanceRequestUnavailable,
)
from integrations.product_acceptance_ruling_owner import ProductAcceptanceRulingReceiptReader


def read_acceptance(runtime, basis_reader, selected):
    """Materialize one exact original receipt inside the existing bound read path.

    This is not an authentication entry point. Workspace's permission, source
    and abort brackets and Runtime's namespace custody remain required owners.
    No principal COMMIT owner is acquired and no request or ruling is created.
    """
    selected = contract.selection(selected)
    if (type(runtime) is not Runtime or runtime.store.read_binding is None
            or type(basis_reader) is not AgentOsProductAcceptanceBasisReader):
        return contract.unavailable(selected, "ACCEPTANCE_NOT_COMPOSED")
    owner = ProductAcceptanceRulingReceiptReader(ProductAcceptanceRequestOwner(runtime, basis_reader))
    try:
        request = owner._request(selected["request_message_key"])
        if (request["context"]["work_ref"] != selected["work_ref"]
                or request["subject"]["root_job_id"] != selected["root_job_id"]):
            return contract.unavailable(selected, "SELECTION_MISMATCH")
        root = runtime.jobs.get_job(selected["root_job_id"])
        # A pending root can be refused without invoking terminal-proof readers
        # that correctly invalidate their bound capability on a proof failure.
        # COMPLETED only permits the existing verifier to run; it is not acceptance.
        if root is None or getattr(root.status, "value", root.status) != "COMPLETED":
            return contract.unavailable(selected, "PARENT_RETURN_UNVERIFIED")
        receipt = owner.observe_acceptance(selected["request_message_key"])
        if owner._request(selected["request_message_key"]) != request:
            return contract.unavailable(selected, "RUNTIME_CHANGED")
        runtime.store.read_binding.validate_before_core_return()
        return contract.validate_view({"schema": contract.VIEW_SCHEMA, "selection": selected,
            "state": "ACCEPTED", "reason_codes": [], "receipt": receipt}, selected=selected)
    except ProductAcceptanceRequestUnavailable as exc:
        runtime.store.read_binding.validate_before_core_return()
        reason = {"PRODUCT_PARENT_RETURN_UNVERIFIED": "PARENT_RETURN_UNVERIFIED",
                  "PRODUCT_PARENT_CONSUMPTION_UNPROVEN": "PARENT_CONSUMPTION_UNPROVEN"}.get(
                      exc.code, "ACCEPTANCE_UNAVAILABLE")
        return contract.unavailable(selected, reason)
    except ProductAcceptanceBasisUnavailable as exc:
        return contract.unavailable(selected, "SOURCE_CHANGED" if
            exc.code == "SOURCE_REVISION_RECONCILIATION_REQUIRED" else "SOURCE_UNAVAILABLE")

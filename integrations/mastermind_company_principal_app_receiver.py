"""Optional receiving-host composition for one authenticated App RULING.

The service selects the real peer and injects its current admission guard.
This provider never starts Runtime, selects an account, or registers a route.
Original uncertain effects retain the existing read-only recovery owner.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from control_plane.coo_principal_host import CooHostProvider
from control_plane.agentos_product_acceptance_basis import (
    AgentOsProductAcceptanceBasisReader, ProductAcceptanceBasisUnavailable,
)
from control_plane.executive_runtime import Runtime
from integrations.company_dialogue_principal_app_contract import decode_app_request
from integrations.company_dialogue_principal_host_contract import (
    MAX_RESPONSE_BYTES, encode_json_frame, validate_response,
)
from integrations.mastermind_company_principal_decision_host import build_acquired_principal_decision_host
from integrations.product_acceptance_request_owner import ProductAcceptanceRequestUnavailable
from integrations.slack_agent_dialogue.executive_observation_client import ExecutiveDialogueObservationClient
from integrations.slack_agent_dialogue.host_local_observation import HostLocalDialogueObservationReader


@dataclass(frozen=True)
class PrincipalDialogueAppReceiver:
    runtime: Runtime
    authority: CooHostProvider
    socket_path: Path
    observation_client: ExecutiveDialogueObservationClient | HostLocalDialogueObservationReader
    product_acceptance_reader: AgentOsProductAcceptanceBasisReader | None = None

    async def ruling(self, raw: bytes, *, receiving_request_guard: Callable[[], None]) -> dict:
        # Preserve the original bytes: parsing and re-encoding here would hide
        # duplicate keys from the closed contract's validator.
        request = decode_app_request(raw)
        host = await build_acquired_principal_decision_host(
            runtime=self.runtime, authority=self.authority, caller=request.caller,
            obligation_id=request.obligation_id, socket_path=self.socket_path,
            observation_client=self.observation_client,
            receiving_request_guard=receiving_request_guard,
            product_acceptance_reader=self.product_acceptance_reader,
        )
        result = await host.gateway.call(request.tool, request.arguments)
        if (self.product_acceptance_reader is not None and result.get("ok") is True
                and request.arguments.get("selected_option") == "opt-product-accept"):
            # Preserve the original send result even if later qualification is
            # unavailable. A closed qualification is never a reason to resend.
            try:
                qualified = await host.request_owner.ruling_owner.qualify_committed_request()
            except (ProductAcceptanceRequestUnavailable, ProductAcceptanceBasisUnavailable) as exc:
                qualified = {"state": "QUALIFICATION_PENDING", "detail_code": exc.code}
            except Exception:
                qualified = {"state": "QUALIFICATION_PENDING",
                             "detail_code": "PRODUCT_RULING_UNAVAILABLE"}
            result = {**result, "data": {**result["data"],
                                        "product_acceptance": qualified}}
        return validate_response(encode_json_frame(result, limit=MAX_RESPONSE_BYTES),
                                 tool=request.tool)

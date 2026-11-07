"""Default-closed request facet on the incumbent authenticated Company socket.

The receiving service must select this host explicitly and the actual worker
must hold its distinct observed MCP grant. Consultation and native return grants
are insufficient. This module creates no listener, admission or scheduler.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

from common.company_consultation_host_contract import MAX_RESPONSE_BYTES, encode_json_frame
from control_plane.agentos_product_acceptance_basis import AgentOsProductAcceptanceBasisReader
from control_plane.coo_principal_host import CooHostProvider
from control_plane.executive_runtime import ActiveMcpCapabilityBindingFacts, Runtime, StateConflict
from integrations.company_consultation_host import CompanyConsultationHost, _dialogue_binding
from integrations.company_consultation_host_authorization import CompanyCallerAuthority
from integrations.mastermind_company_mcp import product_acceptance as contract
from integrations.mastermind_company_mcp.adapter import CompanyDialogueGateway
from integrations.product_acceptance_request_owner import ProductAcceptanceRequestOwner
from integrations.session_bridge.runtime_owner import RuntimeFabricTargetProjector
from integrations.slack_agent_dialogue.service import call_service


class ProductAcceptanceCallerAuthority(CompanyCallerAuthority):
    def _project(self, parent_pid, *, connection=None):
        result = self._runtime.current_harness_mcp_binding_for_parent_pid(
            parent_pid, config_name=contract.CONFIG_NAME,
            server_identity=contract.SERVER_IDENTITY, server_version=contract.SERVER_VERSION,
            tool_schema_digest=contract.TOOL_SCHEMA_DIGEST, auth_status='unsupported',
            **({'connection': connection} if connection is not None else {}))
        if type(result) is not ActiveMcpCapabilityBindingFacts:
            raise StateConflict('product acceptance capability unavailable')
        for cap in (result.requested_capability, result.observed_capability):
            if (cap.name != contract.CONFIG_NAME or cap.kind != 'mcp_server'
                    or cap.mcp_server_identity != contract.SERVER_IDENTITY
                    or cap.mcp_server_version != contract.SERVER_VERSION
                    or cap.tool_schema_digest != contract.TOOL_SCHEMA_DIGEST
                    or cap.mcp_auth_status != 'unsupported'):
                raise StateConflict('product acceptance capability differs')
        return result


class _RequestBinding:
    def __init__(self, host, authority):
        self.host, self.authority = host, authority
        self.facts = authority.revalidate()
        self.target = self._target(self.facts)

    def _target(self, facts):
        def jobs():
            with self.host.runtime.bounded_acquisition() as acquired:
                page = acquired.list_jobs(job_ids=[facts.binding.job_id], limit=2)
            if page.next_cursor is not None:
                raise StateConflict('product requester projection is ambiguous')
            return list(page.items)
        projector = RuntimeFabricTargetProjector(self.host.runtime, job_reader=jobs)
        targets = projector.list_targets()
        if len(targets) != 1:
            raise StateConflict('product requester has no current source')
        target = targets[0]
        physical = target.physical.identity
        if (physical.workspace_id != self.host.workspace_id
                or physical.channel_id != self.host.channel_id
                or target.epoch.harness_provider != 'openai-codex'):
            raise StateConflict('product requester is outside installed scope')
        CompanyConsultationHost._matches(target, facts)  # Pure identity equality, no consultation grant.
        if projector.resolve(target.target_ref) != target:
            raise StateConflict('product requester changed during projection')
        return target

    def guard(self):
        facts = self.authority.revalidate()
        if facts != self.facts or self._target(facts) != self.target:
            raise StateConflict('product requester changed')
        if self.authority.revalidate() != facts:
            raise StateConflict('product requester changed during source observation')

    def resolve(self):
        self.guard()
        # Only this separately authenticated facet supplies DECISION_REQUEST.
        return dataclasses.replace(_dialogue_binding(self.target),
                                   allowed_message_types=('DECISION_REQUEST',))


class ProductAcceptanceRequestHost:
    def __init__(self, *, runtime: Runtime, reader: AgentOsProductAcceptanceBasisReader,
                 worker_uid: int, relay_socket_path: Path, workspace_id: str,
                 channel_id: str, armed: bool = False, inspector=None,
                 principal_authority: CooHostProvider | None = None):
        if (type(runtime) is not Runtime or type(reader) is not AgentOsProductAcceptanceBasisReader
                or type(worker_uid) is not int or worker_uid <= 0 or type(armed) is not bool
                or not Path(relay_socket_path).is_absolute()
                or type(workspace_id) is not str or not workspace_id
                or type(channel_id) is not str or not channel_id
                or (principal_authority is not None and type(principal_authority) is not CooHostProvider)):
            raise TypeError('product acceptance requires exact installed owners')
        self.runtime, self.reader = runtime, reader
        self.worker_uid, self.relay_socket_path = worker_uid, Path(relay_socket_path)
        self.workspace_id, self.channel_id = workspace_id, channel_id
        self.armed, self.inspector = armed, inspector
        self.principal_authority = principal_authority

    async def call(self, peer, frame):
        authority, send_started = None, False
        try:
            tool, arguments = contract.decode_request(frame)
        except Exception:
            return encode_json_frame(contract.envelope(error='INVALID_REQUEST'), limit=MAX_RESPONSE_BYTES)
        if not self.armed:
            return encode_json_frame(contract.envelope(error='ACCESS_REFUSED'), limit=MAX_RESPONSE_BYTES)
        try:
            authority = ProductAcceptanceCallerAuthority(runtime=self.runtime, peer=peer,
                worker_uid=self.worker_uid, inspector=self.inspector)
            context = _RequestBinding(self, authority)

            def before_write():
                nonlocal send_started
                context.guard()
                send_started = True

            async def service(path, request):
                context.guard()
                return await call_service(path, request, before_write=before_write)

            requester = ProductAcceptanceRequestOwner(self.runtime, self.reader)
            gateway = CompanyDialogueGateway(context, socket_path=self.relay_socket_path,
                service_call=service, product_acceptance_owner=requester)
            result = await gateway.call(tool, arguments)
            if (self.principal_authority is not None and result.get('ok') is False
                    and result.get('error', {}).get('detail_code') == 'PRODUCT_REQUEST_RECONCILIATION_REQUIRED'):
                from integrations.product_acceptance_qualification_recovery import ProductAcceptanceQualificationRecovery
                from integrations.product_acceptance_request_owner import ProductAcceptanceRequestUnavailable
                from control_plane.agentos_product_acceptance_basis import ProductAcceptanceBasisUnavailable
                try:
                    qualified = await ProductAcceptanceQualificationRecovery(requester=requester,
                        authority=self.principal_authority, socket_path=self.relay_socket_path).recover(
                            binding=context.resolve(), message_key=result['data']['message_key'],
                            receiving_request_guard=context.guard, service_call=call_service)
                    result = {**result, 'ok': True, 'error': None, 'data': qualified}
                except (ProductAcceptanceRequestUnavailable, ProductAcceptanceBasisUnavailable) as exc:
                    result = {**result, 'error': {**result['error'], 'detail_code': exc.code}}
            context.guard()  # No disclosure after caller or source rotation.
            return encode_json_frame(contract.from_dialogue(result), limit=MAX_RESPONSE_BYTES)
        except Exception:
            return encode_json_frame(contract.envelope(
                error='EFFECT_UNKNOWN' if send_started else 'ACCESS_REFUSED'), limit=MAX_RESPONSE_BYTES)
        finally:
            if authority is not None:
                authority.close()

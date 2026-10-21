"""Native-return composition on the existing authenticated Company socket.

No listener, registry, credential or provider lifecycle is created. Registration
is per request, after the exact native Wake acknowledgement, and the canonical
Runtime event log owns durable admission. Deployment must explicitly arm this
facet and admit its separate sealed MCP capability.
"""
from __future__ import annotations

from common.company_consultation_host_contract import MAX_RESPONSE_BYTES, encode_json_frame
from control_plane.executive_runtime import ActiveMcpCapabilityBindingFacts, StateConflict
from control_plane.operator_harness_contract import runtime_binding_id_for
from integrations.company_consultation_host_authorization import CompanyCallerAuthority
from integrations.mastermind_company_mcp import native_return as contract
from integrations.session_bridge.installed import build_runtime_native_reply_writer
from integrations.session_bridge.runtime_owner import RuntimeFabricTargetProjector, RuntimeCodexTargetProjector
from integrations.session_bridge.runtime_return import RuntimeSessionReturn
from integrations.session_bridge.schemas import BridgeError
from integrations.slack_agent_dialogue.service import call_service, DialogueServiceError


class NativeReturnCallerAuthority(CompanyCallerAuthority):
    def _project(self, parent_pid, *, connection=None):
        result = self._runtime.current_harness_mcp_binding_for_parent_pid(
            parent_pid, config_name=contract.CONFIG_NAME,
            server_identity=contract.SERVER_IDENTITY, server_version=contract.SERVER_VERSION,
            tool_schema_digest=contract.TOOL_SCHEMA_DIGEST, auth_status='unsupported',
            **({'connection': connection} if connection is not None else {}))
        if type(result) is not ActiveMcpCapabilityBindingFacts:
            raise StateConflict('native capability unavailable')
        for cap in (result.requested_capability, result.observed_capability):
            if (cap.name != contract.CONFIG_NAME or cap.kind != 'mcp_server'
                    or cap.mcp_server_identity != contract.SERVER_IDENTITY
                    or cap.mcp_server_version != contract.SERVER_VERSION
                    or cap.tool_schema_digest != contract.TOOL_SCHEMA_DIGEST
                    or cap.mcp_auth_status != 'unsupported'):
                raise StateConflict('native capability differs')
        return result


async def call_native_reply(host, peer, frame):
    authority, entered = None, False
    try:
        _, arguments = contract.decode_request(frame)
    except Exception:
        return encode_json_frame(contract.envelope(error='INVALID_REQUEST'), limit=MAX_RESPONSE_BYTES)
    if not host.native_return_armed:
        return encode_json_frame(contract.envelope(error='ACCESS_REFUSED'), limit=MAX_RESPONSE_BYTES)
    try:
        authority = NativeReturnCallerAuthority(runtime=host.runtime, peer=peer,
            worker_uid=host.worker_uid, inspector=host.inspector)
        facts = authority.revalidate().binding
        fabric = RuntimeFabricTargetProjector(host.runtime)
        codex = RuntimeCodexTargetProjector(fabric, owner_configured=lambda: host.native_return_armed)
        returns = RuntimeSessionReturn(host.runtime, fabric=fabric, codex=codex,
                                      socket_path=host.relay_socket_path)
        binding = returns.resolve(native_session_id=facts.provider_session_id,
            operation_key=arguments['operation_key'], in_reply_to=arguments['in_reply_to'])

        def guard(current, *, connection=None):
            latest = authority.revalidate(connection=connection).binding
            if (current != binding or current.native_session_id != latest.provider_session_id
                    or current.binding_id != runtime_binding_id_for(latest.attempt_id, latest.session_epoch_id)
                    or current.binding_generation != latest.generation_number
                    or current.process_generation_id != latest.process_generation_id):
                raise StateConflict('native writer changed')
            returns.require_native_ack(current, workspace_id=host.workspace_id,
                                       channel_id=host.channel_id, connection=connection)
            return True

        guard(binding)  # No factory callback until authenticated consumption.

        async def service(path, request, *, before_write=None):
            if request['operation'] != 'send_message':
                return await call_service(path, request)
            refusal = None
            from contextlib import contextmanager
            @contextmanager
            def fence():
                nonlocal refusal
                try:
                    with returns.native_reply_commit_fence(binding, request['args']['message'],
                            guard=lambda conn: guard(binding, connection=conn)):
                        yield
                except BridgeError as error:
                    refusal = error
                    raise
            try:
                return await call_service(path, request, before_write=before_write, commit_fence=fence)
            except DialogueServiceError:
                if refusal is not None and refusal.code == 'carrier_effect_unknown':
                    raise DialogueServiceError('SEND_EFFECT_UNKNOWN') from None
                raise

        writer = build_runtime_native_reply_writer(host.runtime,
            dialogue_socket_path=host.relay_socket_path, native_session_id=facts.provider_session_id,
            current_writer_guard=guard, codex_owner_configured=lambda: host.native_return_armed,
            service_call=service)
        entered = True
        result = await writer(arguments)
        return encode_json_frame(contract.envelope(data=result), limit=MAX_RESPONSE_BYTES)
    except BridgeError as error:
        code = ('EFFECT_UNKNOWN' if error.code == 'carrier_effect_unknown'
                else 'CONFLICT' if error.code in {'operation_conflict', 'operation_carrier_conflict'}
                else 'UNAVAILABLE' if entered else 'ACCESS_REFUSED')
        return encode_json_frame(contract.envelope(error=code), limit=MAX_RESPONSE_BYTES)
    except Exception:
        return encode_json_frame(contract.envelope(error='EFFECT_UNKNOWN' if entered else 'ACCESS_REFUSED'),
                                 limit=MAX_RESPONSE_BYTES)
    finally:
        if authority is not None:
            authority.close()

"""Concrete request-local consultation composition inside the Executive host.

Executive/Runtime, Agent Dialogue and Wake remain the only lifecycle, carrier
and effect owners. This adapter owns no listener, registry, retry or credential.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import socket
from types import MappingProxyType
from typing import Any
import uuid

from common.agent_dialogue_consultation_contract import canonical_consultation_json
from common.company_consultation_host_contract import (
    HostFrameError, MAX_REQUEST_BYTES, MAX_RESPONSE_BYTES, decode_request, encode_json_frame,
)
from control_plane.consultation_runtime import (
    consultation_recipient_binding, consultation_requester_binding,
)
from control_plane.executive_peer_identity import PeerIdentity, capture_peer_identity
from control_plane.executive_runtime import ActiveMcpCapabilityBindingFacts, Runtime, StateConflict
from control_plane.wake_events import utc_now_iso
from integrations.company_consultation_dispatch import (
    CallerIdentity, InvocationContext, NoSuchRecipient, RecipientBinding,
    RuntimeConsultationDispatcher,
)
from integrations.company_consultation_target_resolution import ExecutiveConsultationPacketTargetResolver
from integrations.company_consultation_targets import TargetedAgentDialogueConsultationPacketCarrier
from integrations.mastermind_company_mcp.adapter import DialogueBinding
from integrations.mastermind_company_mcp.consultation import (
    COMPANY_CONSULTATION_SERVER_IDENTITY, COMPANY_CONSULTATION_SERVER_VERSION,
    COMPANY_CONSULTATION_TOOL_SCHEMA_DIGEST, CompanyConsultationGateway,
    CompanyConsultationToolError, _error, validate_company_consultation_tool_arguments,
)
from integrations.company_consultation_host_authorization import (
    COMPANY_MCP_CONFIG_NAME, CompanyCallerAuthority,
)
from integrations.session_bridge.runtime_owner import RuntimeFabricTarget, RuntimeFabricTargetProjector
from integrations.slack_agent_dialogue.company_consultation_peer_resolver import (
    CompanyConsultationPeerResolver, ConsultationPeer,
)


def _binding_fields(binding) -> dict[str, Any]:
    return {key: getattr(binding, key) for key in
            ("binding_id", "binding_generation", "reasoning_surface")}


def _peer_ref(target: RuntimeFabricTarget) -> str:
    value = {"root_job_id": target.epoch.root_job_id, "operation_key": target.operation_key}
    return "peer-" + hashlib.sha256(canonical_consultation_json(value).encode()).hexdigest()[:32]


def _dialogue_binding(target: RuntimeFabricTarget) -> DialogueBinding:
    # Reuse the existing exact source reconstruction without borrowing its
    # RESULT grant or the separate Company Dialogue MCP send grant.
    binding = target.reply_binding()
    return DialogueBinding(
        actor_ref=MappingProxyType(dict(binding.current_writer)),
        work_ref=binding.work_ref, commission_ref=MappingProxyType(dict(binding.commission_ref)),
        session_ref=binding.session_ref, operation_key=binding.dialogue_operation_key,
        watch_mode=binding.watch_mode, applies_to=MappingProxyType(dict(binding.applies_to)),
        thread_ts=binding.thread_ts, allowed_message_types=(), reply_to_message_key=None,
    )


@dataclass(frozen=True)
class _Party:
    target: RuntimeFabricTarget
    capability: ActiveMcpCapabilityBindingFacts
    binding: Any


class _RequestContext:
    def __init__(self, host: "CompanyConsultationHost", authority: CompanyCallerAuthority) -> None:
        self.host, self.authority = host, authority
        self.caller = host._caller(authority.revalidate())
        self.selected: _Party | None = None
        self.invocation = InvocationContext(
            invocation_id=str(uuid.uuid4()), issued_at=utc_now_iso(),
            parent_fingerprint=self.caller.target.physical.identity.parent_fingerprint,
            deadline_ms=60_000, valid_for_seconds=300,
            response_budget=MappingProxyType({
                "max_answers": 1, "max_evidence_reads": 1,
                "max_forward_hops": 0, "max_payload_bytes": 32768,
            }),
        )

    def guard(self, phase: str | None = None) -> None:
        try:
            if self.host._caller(self.authority.revalidate()) != self.caller:
                raise StateConflict("Company caller context changed")
            if self.selected is not None:
                current = self.host._recipient(self.selected.target)
                if current != self.selected:
                    raise StateConflict("Company recipient changed before effect")
            # Recipient/source reads can outlive the first caller observation.
            # Finish with caller-context and then kernel/grant checks adjacent
            # to the effect, rather than treating the first check as a lease.
            if self.host._caller(self.authority.revalidate()) != self.caller:
                raise StateConflict("Company caller changed during recipient projection")
            if self.authority.revalidate() != self.caller.capability:
                raise StateConflict("Company caller changed during final source projection")
        except Exception:
            raise StateConflict("Company request authority is unavailable") from None

    def current(self) -> InvocationContext:
        self.guard()
        return self.invocation

    def resolve(self) -> DialogueBinding:
        self.guard()
        return _dialogue_binding(self.caller.target)


class CompanyConsultationHost:
    """Four semantic tools composed only from installed host and Runtime facts."""

    def __init__(
        self, *, runtime: Runtime, repository_root: Path, worker_uid: int,
        relay_socket_path: Path, workspace_id: str, channel_id: str,
        inspector=None,
    ) -> None:
        if not isinstance(runtime, Runtime):
            raise TypeError("Company host requires canonical Runtime")
        if type(worker_uid) is not int or worker_uid <= 0:
            raise ValueError("Company host requires installed worker UID")
        path = Path(relay_socket_path)
        if not path.is_absolute() or os.path.normpath(str(path)) != str(path):
            raise ValueError("Company host requires an absolute Relay socket")
        self.runtime = runtime
        self.repository_root = Path(repository_root).resolve(strict=True)
        self.worker_uid, self.relay_socket_path = worker_uid, path
        self.workspace_id, self.channel_id = workspace_id, channel_id
        self.inspector = inspector
        # This existing resolver owns and validates the exact Relay scope.
        ExecutiveConsultationPacketTargetResolver(
            runtime, workspace_id=workspace_id, channel_id=channel_id,
        )

    def _projector(self, *, root_job_id=None, job_id=None) -> RuntimeFabricTargetProjector:
        def jobs():
            with self.runtime.bounded_acquisition() as acquired:
                page = acquired.list_jobs(
                    limit=128, **({"root_job_id": root_job_id} if root_job_id is not None
                                  else {"job_ids": [job_id]}),
                )
            if page.next_cursor is not None:
                raise StateConflict("Company program exceeds bounded discovery")
            return list(page.items)
        return RuntimeFabricTargetProjector(self.runtime, job_reader=jobs)

    def _scope(self, target: RuntimeFabricTarget) -> None:
        physical = target.physical.identity
        if (physical.workspace_id != self.workspace_id or physical.channel_id != self.channel_id
                or target.epoch.harness_provider != "openai-codex"):
            raise StateConflict("Company target is outside installed scope")

    def _capability(self, attempt_id, *, connection=None):
        return self.runtime.current_harness_mcp_binding_for_attempt(
            attempt_id, config_name=COMPANY_MCP_CONFIG_NAME,
            server_identity=COMPANY_CONSULTATION_SERVER_IDENTITY,
            server_version=COMPANY_CONSULTATION_SERVER_VERSION,
            tool_schema_digest=COMPANY_CONSULTATION_TOOL_SCHEMA_DIGEST,
            auth_status="unsupported", connection=connection,
        )

    @staticmethod
    def _matches(target, facts) -> None:
        epoch, writer = target.epoch, facts.binding
        fields = {
            "job_id": "job_id", "attempt_id": "attempt_id", "worker_id": "worker_id",
            "harness_session_epoch_id": "session_epoch_id",
            "harness_generation_number": "generation_number",
            "harness_provider_session_id": "provider_session_id",
            "harness_provider": "provider", "harness_account_label": "account_label",
            "harness_owner_seat": "owner_seat",
        }
        if any(getattr(epoch, left) != getattr(writer, right) for left, right in fields.items()):
            raise StateConflict("Company target and admitted writer disagree")

    def _caller(self, facts: ActiveMcpCapabilityBindingFacts) -> _Party:
        projector = self._projector(job_id=facts.binding.job_id)
        values = projector.list_targets()
        if len(values) != 1:
            raise StateConflict("Company caller has no unique current dialogue source")
        target = values[0]
        self._scope(target)
        self._matches(target, facts)
        with self.runtime.store.read() as connection:
            current = self._capability(facts.binding.attempt_id, connection=connection)
            _, binding = consultation_requester_binding(
                self.runtime, facts.binding.attempt_id, connection=connection,
            )
        if current != facts or projector.resolve(target.target_ref) != target:
            raise StateConflict("Company caller changed during projection")
        return _Party(target, current, binding)

    def _recipient(self, target: RuntimeFabricTarget) -> _Party:
        self._scope(target)
        with self.runtime.store.read() as connection:
            facts = self._capability(target.epoch.attempt_id, connection=connection)
            binding = consultation_recipient_binding(
                self.runtime, target.epoch.attempt_id, connection=connection,
            )
        self._matches(target, facts)
        if self._projector(job_id=target.epoch.job_id).resolve(target.target_ref) != target:
            raise StateConflict("Company recipient changed during projection")
        return _Party(target, facts, binding)

    def _peers(self, context: _RequestContext) -> tuple[CompanyConsultationPeerResolver, dict[str, _Party]]:
        root = context.caller.target.epoch.root_job_id
        peers, parties = [], {}
        for target in self._projector(root_job_id=root).list_targets():
            if (target.epoch.root_job_id != root
                    or target.epoch.worker_id == context.caller.target.epoch.worker_id):
                continue
            try:
                party = self._recipient(target)
            except StateConflict:
                continue
            ref = _peer_ref(target)
            if ref in parties:
                raise StateConflict("Company peer projection is ambiguous")
            parties[ref] = party
            peers.append(ConsultationPeer(
                peer_ref=ref, display_name="Peer " + ref[5:13], program_ref=root,
                actor_ref=_dialogue_binding(target).actor_ref,
                binding=MappingProxyType(_binding_fields(party.binding)),
            ))
        return CompanyConsultationPeerResolver(tuple(peers)), parties

    async def call(self, peer: PeerIdentity, frame: bytes) -> bytes:
        tool, authority, dispatch_started = "unknown", None, False
        try:
            tool, arguments = decode_request(frame)
            arguments = validate_company_consultation_tool_arguments(tool, arguments)
        except (HostFrameError, CompanyConsultationToolError, TypeError, ValueError):
            return encode_json_frame(_error(tool, "INVALID_REQUEST"), limit=MAX_RESPONSE_BYTES)
        try:
            authority = CompanyCallerAuthority(
                runtime=self.runtime, peer=peer, worker_uid=self.worker_uid, inspector=self.inspector,
            )
            context = _RequestContext(self, authority)
            resolver, parties = (self._peers(context) if tool in ("company.peers", "company.consult")
                                 else (CompanyConsultationPeerResolver(()), {}))
            def recipient(ref):
                context.guard()
                party = parties.get(ref)
                if party is None:
                    raise NoSuchRecipient(ref)
                context.selected = party
                context.guard()
                return RecipientBinding(
                    actor_ref=_dialogue_binding(party.target).actor_ref,
                    recipient_binding=_binding_fields(party.binding),
                )
            packets = TargetedAgentDialogueConsultationPacketCarrier(
                binding_resolver=context,
                targets=ExecutiveConsultationPacketTargetResolver(
                    self.runtime, workspace_id=self.workspace_id, channel_id=self.channel_id,
                ),
                socket_path=self.relay_socket_path,
            )
            caller = _dialogue_binding(context.caller.target)
            dispatcher = RuntimeConsultationDispatcher(
                runtime=self.runtime, repository_root=self.repository_root,
                caller=CallerIdentity(
                    job_id=caller.actor_ref["job_id"], attempt_id=caller.actor_ref["attempt_id"],
                    worker_id=caller.actor_ref["worker_id"], reasoning_surface="codex",
                    binding=_binding_fields(context.caller.binding), dialogue_binding=caller,
                ), recipients=recipient, packets=packets, invocations=context, before_effect=context.guard,
            )
            async def dispatch(name, request):
                nonlocal dispatch_started
                context.guard()
                dispatch_started = True
                return await dispatcher(name, request)
            gateway = CompanyConsultationGateway(
                peer_resolver=resolver, dispatcher=dispatch,
                observed_tool_schema_digest=COMPANY_CONSULTATION_TOOL_SCHEMA_DIGEST,
                utc_now=lambda: context.invocation.issued_at,
                program_ref=context.caller.target.epoch.root_job_id,
            )
            context.guard()
            result = await gateway.call(tool, arguments)
            if tool in ("company.peers", "company.consultation"):
                context.guard()
            return encode_json_frame(result, limit=MAX_RESPONSE_BYTES)
        except asyncio.CancelledError:
            if not dispatch_started or tool not in ("company.consult", "company.reply"):
                raise
            return encode_json_frame(_error(tool, "EFFECT_UNKNOWN"), limit=MAX_RESPONSE_BYTES)
        except Exception:
            code = ("EFFECT_UNKNOWN" if dispatch_started and tool in ("company.consult", "company.reply")
                    else "ACCESS_REFUSED")
            return encode_json_frame(_error(tool, code), limit=MAX_RESPONSE_BYTES)
        finally:
            if authority is not None:
                authority.close()

    async def handle_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Serve one frame on this accepted connection; the service owns lifetime."""
        connected = None
        try:
            async with asyncio.timeout(60):
                transport = writer.get_extra_info("socket")
                if transport is None:
                    return
                connected = socket.socket(fileno=os.dup(transport.fileno()))
                peer = capture_peer_identity(connected)
                if peer.euid != self.worker_uid:
                    return
                frame = await reader.readuntil(b"\n")
                if len(frame) > MAX_REQUEST_BYTES:
                    return
                writer.write(await self.call(peer, frame))
                await writer.drain()
        except (OSError, ValueError, asyncio.IncompleteReadError, asyncio.LimitOverrunError, TimeoutError):
            pass
        finally:
            if connected is not None:
                connected.close()
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), timeout=1)
            except (OSError, TimeoutError):
                pass

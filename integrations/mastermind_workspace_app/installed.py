"""Fixed bounded workspace client of the existing App-peer CeoIngress socket.

This is transport composition only: no owner, enrollment, token acquisition,
Runtime path, cache lifecycle, retry, or installation state is created here.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from .contract import (
    MAX_RESPONSE_BYTES,
    FRAME_SCHEMA_V3, MAX_PLAN_RESPONSE_BYTES, validate_v3_frame,
    MAX_RESULT_RESPONSE_BYTES,
    canonical,
    response_ceiling_for,
    validate_frame,
    validate_v2_frame,
)


class CeoIngressWorkspaceClient:
    def __init__(self, socket_path, *, timeout_seconds=10, acceptance_timeout_seconds=30,
                 action_timeout_seconds=480):
        self.socket_path = Path(socket_path)
        if (not self.socket_path.is_absolute() or type(timeout_seconds) not in (int, float)
                or not 0.1 <= timeout_seconds <= 30
                or type(acceptance_timeout_seconds) not in (int, float)
                or not 0.1 <= acceptance_timeout_seconds <= 30
                or type(action_timeout_seconds) not in (int, float)
                or not 0.1 <= action_timeout_seconds <= 480):
            raise ValueError("invalid_input")
        self.timeout_seconds = timeout_seconds
        self.acceptance_timeout_seconds = acceptance_timeout_seconds
        # Refresh retains its existing 180s compiler + 240s composition bounds.
        # This separate finite transport budget never changes any READ budget.
        self.action_timeout_seconds = action_timeout_seconds

    async def request(self, frame):
        from common import workspace_host_observation_contract as host_wire
        if type(frame) is dict and frame.get("schema") == host_wire.FRAME_SCHEMA:
            from integrations.mastermind_workspace_app.host_observation_client import request_host_observation
            return await request_host_observation(self, frame)
        from common import workspace_instruction_admission_contract as instruction_wire
        if instruction_wire.is_frame(frame):
            from integrations.mastermind_workspace_app.instruction_admission_client import request_instruction_admission
            return await request_instruction_admission(self,frame)
        from common import workspace_project_admission_wire as project_admission_wire
        if project_admission_wire.is_project_admission_frame(frame):
            from integrations.mastermind_workspace_app.project_admission_client import request_project_admission
            return await request_project_admission(self, frame)
        from common import workspace_control_room_action_contract as action_wire
        if type(frame) is dict and frame.get("schema") == action_wire.FRAME_SCHEMA:
            return await self._request_action(frame)
        # Frozen v2 frames use the exact same wire envelope as v1; only the
        # schema name and selection grammar differ.  Operation-driven response
        # ceiling selection happens BEFORE the socket is opened so a misrouted
        # result frame can never widen into the larger Mission ceiling.
        from control_plane.coo_principal_host import FACT_SCHEMA, validate_facts_frame
        from common import coo_agentos_context_contract as context_wire
        from common.product_acceptance_read_contract import FRAME_SCHEMA as ACCEPTANCE_FRAME_SCHEMA, validate_frame as validate_acceptance_frame
        from common.workspace_control_room_read_contract import (
            FRAME_SCHEMA as CCR_READ_FRAME_SCHEMA, validate_frame as validate_ccr_read_frame,
        )
        from common import executive_workspace_fabric_contract as fabric_wire
        timeout = self.timeout_seconds
        from common import workspace_project_instructions_contract as instructions_wire
        from common import workspace_project_plan_contract as plan_wire
        from common import workspace_project_journal_contract as journal_wire
        from common import workspace_project_knowledge_read_contract as knowledge_wire
        from common import workspace_project_session_contract as session_wire
        from common import workspace_project_direction_contract as direction_wire
        from common import workspace_project_archive_contract as archive_wire
        from common import workspace_autonomy_read_contract as autonomy_wire
        from common import workspace_resource_capacity_contract as capacity_wire
        from common import workspace_byok_read_contract as byok_wire
        from common import workspace_source_operation_wire as source_wire
        current_context = type(frame) is dict and frame.get("schema") == context_wire.CURRENT_FRAME_SCHEMA
        context_read = type(frame) is dict and frame.get("schema") in {context_wire.FRAME_SCHEMA, context_wire.CURRENT_FRAME_SCHEMA}
        if context_read:
            (context_wire.validate_current_frame if current_context else context_wire.validate_frame)(frame)
            ceiling = context_wire.MAX_RESPONSE_BYTES
            timeout = self.acceptance_timeout_seconds
        elif isinstance(frame, dict) and frame.get("schema") == byok_wire.FRAME_SCHEMA:
            byok_wire.validate_frame(frame)
            ceiling = byok_wire.MAX_RESPONSE_BYTES
        elif isinstance(frame, dict) and frame.get("schema") in {archive_wire.FRAME_SCHEMA, archive_wire.PAGE_FRAME_SCHEMA}:
            archive_wire.validate_read_frame(frame)
            ceiling = archive_wire.MAX_RESPONSE_BYTES
            timeout = self.acceptance_timeout_seconds
        elif isinstance(frame, dict) and frame.get("schema") == direction_wire.FRAME_SCHEMA:
            direction_wire.validate_frame(frame)
            ceiling = direction_wire.MAX_RESPONSE_BYTES
        elif type(frame) is dict and frame.get("schema") == source_wire.FRAME_SCHEMA:
            frame = source_wire.validate_frame(frame)
            ceiling = source_wire.MAX_RESPONSE_BYTES
            timeout = self.timeout_seconds if frame["operation"] == "read" else self.action_timeout_seconds
        elif isinstance(frame, dict) and frame.get("schema") == instructions_wire.FRAME_SCHEMA:
            instructions_wire.validate_frame(frame)
            ceiling = instructions_wire.MAX_RESPONSE_BYTES
            timeout = self.acceptance_timeout_seconds
        elif isinstance(frame, dict) and frame.get("schema") == capacity_wire.FRAME_SCHEMA:
            capacity_wire.validate_frame(frame)
            ceiling = capacity_wire.MAX_RESPONSE_BYTES
        elif isinstance(frame, dict) and frame.get("schema") == autonomy_wire.FRAME_SCHEMA:
            autonomy_wire.validate_frame(frame)
            ceiling = autonomy_wire.MAX_RESPONSE_BYTES
        elif isinstance(frame, dict) and frame.get("schema") == session_wire.FRAME_SCHEMA:
            session_wire.validate_frame(frame)
            ceiling = session_wire.MAX_RESPONSE_BYTES
            timeout = self.acceptance_timeout_seconds
        elif isinstance(frame, dict) and frame.get("schema") == knowledge_wire.FRAME_SCHEMA:
            knowledge_wire.validate_frame(frame)
            ceiling = knowledge_wire.MAX_RESPONSE_BYTES
            timeout = self.acceptance_timeout_seconds
        elif isinstance(frame, dict) and frame.get("schema") == journal_wire.FRAME_SCHEMA:
            journal_wire.validate_frame(frame)
            ceiling = journal_wire.MAX_RESPONSE_BYTES
            timeout = self.acceptance_timeout_seconds
        elif isinstance(frame, dict) and frame.get("schema") == plan_wire.FRAME_SCHEMA:
            plan_wire.validate_frame(frame)
            ceiling = plan_wire.MAX_RESPONSE_BYTES
            timeout = self.acceptance_timeout_seconds
        elif isinstance(frame, dict) and frame.get("schema") == fabric_wire.FRAME_SCHEMA:
            fabric_wire.validate_frame(frame)
            ceiling = fabric_wire.ceiling(frame["operation"])
        elif isinstance(frame, dict) and frame.get("schema") == CCR_READ_FRAME_SCHEMA:
            validate_ccr_read_frame(frame)
            ceiling = MAX_RESPONSE_BYTES
        elif isinstance(frame, dict) and frame.get("schema") == ACCEPTANCE_FRAME_SCHEMA:
            from common.product_acceptance_acquisition_contract import (
                OPERATION as ORIGINAL_OPERATION, validate_frame as validate_original_frame,
            )
            if frame.get("operation") == ORIGINAL_OPERATION:
                validate_original_frame(frame)
            else:
                validate_acceptance_frame(frame)
            ceiling = MAX_RESPONSE_BYTES
            # This read includes the sealed source owner's existing 15-second
            # observation, in addition to bounded Runtime proof reads. Keep it
            # inside the existing 30-second client ceiling without changing
            # any old operation or renewing the source owner's own deadline.
            timeout = self.acceptance_timeout_seconds
        elif isinstance(frame, dict) and frame.get("schema") == FACT_SCHEMA:
            validate_facts_frame(frame)
            ceiling = MAX_RESPONSE_BYTES
        elif isinstance(frame, dict) and frame.get("schema") == "mastermind.executive_workspace_read.v5":
            from common import executive_workspace_activity_contract as activity
            activity.validate_frame(frame)
            ceiling = activity.MAX_RESPONSE_BYTES
        elif isinstance(frame, dict) and frame.get("schema") == FRAME_SCHEMA_V3:
            validate_v3_frame(frame)
            ceiling = MAX_PLAN_RESPONSE_BYTES
        elif isinstance(frame, dict) and frame.get("schema") == "mastermind.executive_workspace_mission_result_read.v1":
            from common.executive_workspace_mission_result_contract import (
                MAX_COMPOUND_RESPONSE_BYTES,
                validate_frame as validate_mission_result_frame,
            )
            validate_mission_result_frame(frame)
            ceiling = MAX_COMPOUND_RESPONSE_BYTES
        elif isinstance(frame, dict) and frame.get("schema") == "mastermind.executive_workspace_read.v2":
            validate_v2_frame(frame)
            ceiling = response_ceiling_for(frame.get("operation"))
        else:
            validate_frame(frame)
            ceiling = MAX_RESPONSE_BYTES
        encoded = canonical(frame) + b"\n"

        async def exchange():
            # The receive limit mirrors the operation's closed ceiling so an
            # oversized socket envelope never materializes in this client.
            reader, writer = await asyncio.open_unix_connection(str(self.socket_path), limit=ceiling)
            try:
                writer.write(encoded)
                await writer.drain()
                raw = await reader.readuntil(b"\n")
                if len(raw) > ceiling:
                    raise ValueError("source_unavailable")
                value = context_wire.decode(raw, limit=ceiling) if context_read else json.loads(raw)
                if type(value) is not dict:
                    raise ValueError("source_unavailable")
                if value.get("ok") is True:
                    if set(value) != {"ok", "result"} or type(value["result"]) is not dict:
                        raise ValueError("source_unavailable")
                    if context_read:
                        validator = context_wire.validate_current_result if current_context else context_wire.validate_result
                        validator(value["result"], expected_context=frame["principal_context"],
                            capability_profile_digest=frame["capability_profile_digest"],
                            **({"expected_workspace_principal": frame["workspace_principal"]} if current_context else {}))
                elif (value.get("ok") is not False or set(value) != {"ok", "status", "error"}
                      or type(value["status"]) is not int or value["status"] not in (400, 403, 404, 503)
                      or type(value["error"]) is not dict or set(value["error"]) != {"code", "message"}):
                    raise ValueError("source_unavailable")
                return value
            finally:
                if context_read:
                    # Keep cleanup finite even after the read budget expires;
                    # no retry, new connection, or compiler deadline renewal.
                    try:
                        writer.close()
                        await asyncio.wait_for(writer.wait_closed(), timeout=min(1.0, timeout))
                    except Exception:
                        pass
                else:
                    writer.close()
                    await writer.wait_closed()
        try:
            return await asyncio.wait_for(exchange(), timeout)
        except Exception:
            raise ValueError("source_unavailable") from None


    async def _request_action(self, frame):
        from common import workspace_control_room_action_contract as wire
        from control_plane.workspace_owned_task import await_owned
        try:
            request = wire.validate_frame(frame)
        except (TypeError, ValueError):
            operation = frame.get("operation") if type(frame) is dict else None
            if type(operation) is not str or operation not in wire.OPERATIONS:
                raise ValueError("invalid_input") from None
            return {"ok": True, "result": wire.refused_result(
                operation, code="invalid_input", status=400,
            )}
        operation = request["operation"]
        encoded = canonical(request) + b"\n"
        write_attempted = False
        received = None

        async def exchange():
            nonlocal write_attempted, received
            reader, writer = await asyncio.open_unix_connection(
                str(self.socket_path), limit=wire.MAX_RESPONSE_BYTES,
            )
            try:
                # Set before write: even a raised write may have sent a prefix.
                write_attempted = True
                writer.write(encoded)
                await writer.drain()
                raw = await reader.readuntil(b"\n")
                received = wire.decode_result_envelope(raw, operation=operation)
                return received
            finally:
                # Cleanup cannot erase a complete qualified response or replace
                # the primary failure. Its own wait is bounded even when the
                # main exchange has already been cancelled by its deadline.
                try:
                    writer.close()
                    await asyncio.wait_for(
                        writer.wait_closed(), timeout=min(1.0, self.action_timeout_seconds),
                    )
                except (Exception, asyncio.CancelledError):
                    pass

        async def bounded_exchange():
            try:
                await asyncio.wait_for(exchange(), timeout=self.action_timeout_seconds)
            except Exception:
                pass
            if received is not None:
                return received
            result = (wire.unknown_result(operation) if write_attempted
                      else wire.refused_result(operation, code="source_unavailable", status=503))
            return {"ok": True, "result": result}

        # One connection, one frame write, no retry. Caller cancellation is
        # deferred until this bounded exchange has actually settled.
        return await await_owned(asyncio.create_task(bounded_exchange()))


# Re-exported for tests and the App to import the operation-specific ceiling.
__all__ = ["CeoIngressWorkspaceClient", "MAX_RESULT_RESPONSE_BYTES"]

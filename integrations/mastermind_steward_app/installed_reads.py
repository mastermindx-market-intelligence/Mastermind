"""Concrete installed Steward projection over the incumbent sealed read owners."""
from control_plane import chairman_control_room, surface_bindings
from common.executive_content_contract import STEWARD_SCHEMA, MAX_RESPONSE_BYTES, canonical
from integrations.mastermind_steward_app.projection import ControlRoomStewardReadPort
from integrations.mastermind_secretary_mcp.adapter import SecretaryGroundingGateway
from integrations.mastermind_secretary_mcp.schemas import validate_tool_arguments


class InstalledStewardReadProvider:
    def __init__(self, *, readers, runtime, bindings_path, now):
        self.readers=readers
        self.runtime=runtime
        self.bindings_path=bindings_path
        self.now=now

    def _snapshot(self):
        # Reuse the sealed boot collector and explicit installed Runtime. The
        # repository-default Runtime path is never opened as a fallback.
        before=self.readers.observe()
        packet,inbox=self.readers._collect()
        active,_=chairman_control_room._read_active_builds(str(self.readers._macro_root))
        agent,_=chairman_control_room._read_agent_os_state(str(self.readers._macro_root))
        _,jobs,_=chairman_control_room._read_runtime_jobs_from_runtime(self.runtime)
        bindings,problems=surface_bindings.load_bindings(self.bindings_path)
        snapshot=chairman_control_room.compose_control_room(inbox=inbox,boot_packet=packet,
            active_builds=active,agent_os_state=agent,runtime_jobs=jobs,bindings=bindings,
            binding_problems=problems,generated_at=self.now().strftime('%Y-%m-%dT%H:%M:%SZ'))
        if self.readers.observe()!=before:
            raise ValueError('CONTENT_UNAVAILABLE')
        return snapshot

    async def handle_frame(self, frame):
        try:
            if type(frame) is not dict or set(frame)!={'schema','tool','arguments'} or frame['schema']!=STEWARD_SCHEMA:
                raise ValueError('INVALID_REQUEST')
            args=validate_tool_arguments(frame['tool'],frame['arguments'])
        except Exception:
            return {'ok':False,'error':{'code':'INVALID_REQUEST'}}
        try:
            # Existing physical executor keeps capacity held if an awaiting
            # caller times out; no orphan thread opens another read slot.
            snapshot=await self.readers._read_executor.run(self._snapshot,timeout=15)
            port=ControlRoomStewardReadPort(lambda:snapshot,clock=self.now)
            result=await SecretaryGroundingGateway(port).call(frame['tool'],args)
            reply={'ok':True,'result':result}
            if len(canonical(reply))+1>MAX_RESPONSE_BYTES:
                return {'ok':False,'error':{'code':'OVER_BUDGET'}}
            return reply
        except Exception:
            return {'ok':False,'error':{'code':'CONTENT_UNAVAILABLE'}}

import asyncio
import pytest
from integrations.mastermind_steward_app.installed_grounding import CeoIngressStewardReadPort
from control_plane.executive_steward_reads import InstalledStewardReadProvider
from integrations.mastermind_steward_app.projection import ControlRoomStewardReadPort
from integrations.mastermind_secretary_mcp.adapter import SecretaryGroundingGateway, GroundingRefusedError
from test_mastermind_steward_app_projection import _snapshot, NOW


def test_concrete_wire_rehydrates_canonical_grounding_and_refuses_unrelated_reply():
    class Client:
        corrupt=False
        async def request(self, frame):
            gateway=SecretaryGroundingGateway(ControlRoomStewardReadPort(_snapshot,clock=lambda:NOW))
            result=await gateway.call(frame['tool'],frame['arguments'])
            if self.corrupt:
                result['tool']='get_attention'
            return {'ok':True,'result':result}
    async def run():
        client=Client();port=CeoIngressStewardReadPort(client)
        result=await port.list_responsibilities()
        assert result.facts
        assert all(fact.subject_ref.startswith('responsibility:') for fact in result.facts)
        client.corrupt=True
        with pytest.raises(GroundingRefusedError):
            await port.list_responsibilities()
    asyncio.run(run())


def test_control_provider_refuses_unknown_frame_before_any_source_read():
    provider=InstalledStewardReadProvider(readers=None,runtime=None,bindings_path=None,now=lambda:NOW)
    assert asyncio.run(provider.handle_frame({'schema':'mastermind.executive_steward_read.v1','tool':'submit_ceo_intent','arguments':{}}))['ok'] is False

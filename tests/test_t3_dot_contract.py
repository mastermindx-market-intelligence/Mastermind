"""Release coherence checks for the existing typed T3 gateway and port."""
import asyncio
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from integrations.session_bridge.t3_dot_tools import TOOLS
from integrations.session_bridge.t3_dot_port import execute, execute_with_shutdown
from tests.test_t3_dot_native_owner import profile

ROOT = Path(__file__).resolve().parents[1]


class ContractTests(unittest.TestCase):
    def test_published_gateway_catalog_is_exact_python_contract(self):
        declared=json.loads((ROOT/'integrations/studio_direct_mcp/t3-dot-tools.json').read_text())
        self.assertEqual(declared, {'tools':list(TOOLS)})

    def test_port_cancellation_retains_original_native_effect(self):
        frame={'schema':'mastermind.t3_dot_call.v1','principal_key':'p:tunnel:account-a',
               'tool':'t3_thread_launch','arguments':{'operation_id':'original','environment_id':'native-env-1',
                                                   'project_id':'project-1'}}
        class Owner:
            def __init__(self,*args,**kwargs):
                self.runner=type('Runner',(),{'last_effect':{'pid':1234,'helper_state':'RETURN_UNQUALIFIED'}})()
        class Tools:
            def __init__(self,owner): pass
            async def call(self,*args): raise asyncio.CancelledError()
            from integrations.session_bridge.t3_dot_tools import T3DotTools
            _failure=staticmethod(T3DotTools._failure)
        with patch('integrations.session_bridge.t3_dot_port.read_profile',return_value=profile()), \
             patch('integrations.session_bridge.t3_dot_port.NativeDotFleetOwner',Owner), \
             patch('integrations.session_bridge.t3_dot_port.T3DotTools',Tools):
            result=asyncio.run(execute('/fixture/profile','0'*64,frame))
        self.assertEqual(result['status'],'EFFECT_UNKNOWN')
        self.assertEqual(result['original']['operation_id'],'original')
        self.assertEqual(result['native_helper']['pid'],1234)
        self.assertFalse(result['retry_allowed'])

    def test_shutdown_handler_is_installed_and_removed_for_only_this_invocation(self):
        async def scenario():
            loop=asyncio.get_running_loop()
            async def operation(*args): return {'status':'fixture'}
            with patch.object(loop,'add_signal_handler') as add, patch.object(loop,'remove_signal_handler') as remove, \
                 patch('integrations.session_bridge.t3_dot_port.execute',operation):
                result=await execute_with_shutdown('/fixture/profile','0'*64,{})
                self.assertEqual(result,{'status':'fixture'})
                self.assertEqual(add.call_count,1); self.assertEqual(remove.call_count,1)
        asyncio.run(scenario())


if __name__=='__main__': unittest.main()

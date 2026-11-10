"""Real SDK stdio validation of the isolated prototype, with synthetic backends only.

No SSH, network, Paper application, tunnel or real credential is contacted.
This is not the blocked production-service integration.
"""
import asyncio
import json
from pathlib import Path
import sys
import tempfile
import unittest

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent
LOCAL = "host-" + "a" * 64
REMOTE = "host-" + "b" * 64
TARGET = "01" + "B" * 24

LAUNCHER = r"""
import asyncio, json, sys
from contextlib import asynccontextmanager
from types import SimpleNamespace
sys.path.insert(0, ROOT)
import host_routes as h
import validation_basic as f
from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent, ImageContent

class Catalog:
    tools = [SimpleNamespace(name=n) for n in sorted(h.TOOL_NAMES)]
    def model_dump(self, mode='json'):
        return {'tools': [{'name': t.name} for t in self.tools]}

calls = []
def payload_result(value, image=False):
    content=[TextContent(type='text', text=json.dumps(value))]
    if image:
        content.append(ImageContent(type='image', mimeType='image/png', data='aGVsbG8='))
    return CallToolResult(content=content)

async def invoke(name, args, host):
    calls.append((host, name))
    if name == 'paper_edit' and MODE == 'lost':
        raise TimeoutError('synthetic')
    value={'execution_binding': f.binding(host), 'state': 'OBSERVED',
           'synthetic_call_count': len(calls), 'retry_allowed': False}
    if name == 'paper_inspect':
        value.update(state='CONNECTED', document={'write_binding_ready': True})
    if name == 'paper_edit':
        value.update(state='APPLIED_RESPONSE_OBSERVED', operation_id=args['operation_id'])
        if MODE == 'wrong_operation': value['operation_id']='not-the-request'
        if MODE == 'wrong_host': value['execution_binding']=f.binding('host-'+'9'*64)
    if name == 'paper_prepare':
        value.update(state='PAPER_READY', operation_id=args['operation_id'], file_id=args['file_id'])
        if MODE == 'wrong_file': value['file_id']='01'+'C'*24
    return payload_result(value, name == 'paper_read')

class Backend:
    async def initialize(self):
        return SimpleNamespace(serverInfo=SimpleNamespace(name='mastermind-paper'))
    async def list_tools(self): return Catalog()
    async def call_tool(self, name, args): return await invoke(name, args, f.REMOTE)

@asynccontextmanager
async def connect(route):
    yield Backend()
    if MODE == 'cleanup': raise RuntimeError('synthetic cleanup')

async def local(name, args): return await invoke(name, args, f.LOCAL)
policy=f.policy()
policy['routes'][0]['tool_schema_sha256']=h.schema_digest(Catalog())
router=h.HostRouter(policy, f.binding(f.LOCAL), local, allow_write=WRITE,
                    allow_prepare=WRITE, connect=connect)
server=FastMCP('prototype-wire-fixture')
h.register_tools(server, router)
server.run(transport='stdio')
"""


class WireTests(unittest.IsolatedAsyncioTestCase):
    async def wire(self, name=None, arguments=None, *, mode='normal', write=True):
        code = ('ROOT=' + repr(str(ROOT)) + '\nMODE=' + repr(mode)
                + '\nWRITE=' + repr(write) + '\n' + LAUNCHER)
        with tempfile.TemporaryDirectory(prefix='paper-router-wire-fixture-') as directory:
            script=Path(directory)/'fixture.py'
            script.write_text(code)
            params=StdioServerParameters(command=sys.executable, args=['-I',str(script)],
                                        env={'PATH':'/usr/bin:/bin'})
            async with stdio_client(params) as (reader, writer):
                async with ClientSession(reader,writer) as client:
                    await client.initialize()
                    if name is None:
                        return await client.list_tools()
                    return await client.call_tool(name, arguments or {})

    def body(self, result): return json.loads(result.content[0].text)

    def edit_args(self, host=REMOTE):
        args={'tool':'set_text_content', 'arguments':{'fileId':TARGET},
              'expected_snapshot':'1'*64, 'operation_id':'wire-once'}
        if host is not None: args['host_ref']=host
        return args

    async def test_actual_sdk_surface_and_annotations(self):
        tools=(await self.wire()).tools
        rows={t.name:t for t in tools}
        self.assertEqual(len(rows),6)
        self.assertIn('paper_hosts',rows)
        for name,row in rows.items():
            self.assertNotIn('command',row.inputSchema.get('properties',{}))
            self.assertNotIn('endpoint',row.inputSchema.get('properties',{}))
            self.assertNotIn('execution_binding',row.inputSchema.get('properties',{}))
            self.assertNotIn('host_ref',row.inputSchema.get('required',[]))
        self.assertFalse(rows['paper_edit'].annotations.readOnlyHint)
        self.assertTrue(rows['paper_edit'].annotations.destructiveHint)
        self.assertFalse(rows['paper_edit'].annotations.idempotentHint)

    async def test_readonly_surface_has_no_mutating_tools(self):
        self.assertEqual({t.name for t in (await self.wire(write=False)).tools},
                         {'paper_hosts','paper_inspect','paper_catalog','paper_read'})

    async def test_host_listing_has_no_credentials_or_readiness_claim(self):
        result=self.body(await self.wire('paper_hosts'))
        self.assertEqual(result['state'],'CONFIGURED_NOT_PROBED')
        self.assertEqual(len(result['hosts']),2)
        self.assertFalse(result['automatic_failover'])
        self.assertNotIn('identity_file',json.dumps(result))
        self.assertNotIn('runtime_root',json.dumps(result))

    async def test_remote_inspect_preserves_expected_host(self):
        result=self.body(await self.wire('paper_inspect',{'host_ref':REMOTE}))
        self.assertEqual(result['execution_binding']['host_ref'],REMOTE)
        self.assertEqual(result['state'],'CONNECTED')

    async def test_local_default_is_fixed(self):
        result=self.body(await self.wire('paper_inspect'))
        self.assertEqual(result['execution_binding']['host_ref'],LOCAL)
        self.assertEqual(result['synthetic_call_count'],1)

    async def test_unknown_host_does_not_fall_back(self):
        result=self.body(await self.wire('paper_edit',self.edit_args('host-'+'9'*64)))
        self.assertEqual(result['state'],'HOST_NOT_CONFIGURED')
        self.assertEqual(result['effect_state'],'EFFECT_NONE')
        self.assertFalse(result['automatic_failover'])

    async def test_remote_edit_preserves_operation(self):
        result=self.body(await self.wire('paper_edit',self.edit_args()))
        self.assertEqual(result['state'],'APPLIED_RESPONSE_OBSERVED')
        self.assertEqual(result['operation_id'],'wire-once')
        self.assertEqual(result['synthetic_call_count'],2)

    async def test_missing_remote_reply_is_unknown_on_original_host(self):
        result=self.body(await self.wire('paper_edit',self.edit_args(),mode='lost'))
        self.assertEqual(result['state'],'EFFECT_UNKNOWN')
        self.assertEqual(result['requested_host_ref'],REMOTE)
        self.assertEqual(result['operation_id'],'wire-once')
        self.assertFalse(result['retry_allowed'])

    async def test_missing_local_reply_is_unknown_on_original_host(self):
        result=self.body(await self.wire('paper_edit',self.edit_args(None),mode='lost'))
        self.assertEqual(result['state'],'EFFECT_UNKNOWN')
        self.assertEqual(result['requested_host_ref'],LOCAL)
        self.assertEqual(result['operation_id'],'wire-once')

    async def test_wrong_operation_reply_is_not_accepted(self):
        result=self.body(await self.wire('paper_edit',self.edit_args(),mode='wrong_operation'))
        self.assertEqual(result['state'],'EFFECT_UNKNOWN')
        self.assertEqual(result['operation_id'],'wire-once')

    async def test_wrong_host_reply_is_not_accepted(self):
        result=self.body(await self.wire('paper_edit',self.edit_args(),mode='wrong_host'))
        self.assertEqual(result['state'],'EFFECT_UNKNOWN')
        self.assertEqual(result['requested_host_ref'],REMOTE)

    async def test_wrong_prepare_file_reply_is_not_accepted(self):
        result=self.body(await self.wire('paper_prepare',{'file_id':TARGET,
            'expected_snapshot':'1'*64,'operation_id':'wire-once','host_ref':REMOTE},mode='wrong_file'))
        self.assertEqual(result['state'],'EFFECT_UNKNOWN')

    async def test_valid_receipt_survives_cleanup_failure(self):
        result=self.body(await self.wire('paper_edit',self.edit_args(),mode='cleanup'))
        self.assertEqual(result['state'],'APPLIED_RESPONSE_OBSERVED')
        self.assertEqual(result['operation_id'],'wire-once')

    async def test_native_image_block_survives_forwarding(self):
        reply=await self.wire('paper_read',{'tool':'get_screenshot','arguments':{},'host_ref':REMOTE})
        self.assertFalse(reply.isError)
        self.assertEqual(reply.content[1].type,'image')
        self.assertEqual(reply.content[1].data,'aGVsbG8=')
        self.assertEqual(self.body(reply)['execution_binding']['host_ref'],REMOTE)


if __name__=='__main__': unittest.main()

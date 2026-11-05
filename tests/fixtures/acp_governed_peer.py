"""Synthetic SDK peer for the native private admission seam; not DSH proof."""
import asyncio
import json
import os
import socket
import sys

import acp
from acp.schema import (AgentMessageChunk, Implementation, InitializeResponse, NewSessionResponse,
    PromptResponse, SessionConfigOptionSelect, SessionConfigSelectOption, TextContentBlock,
    ToolCallStart, ToolCallProgress)

MODE = sys.argv[1]


class Peer:
    def on_connect(self, client):
        self.client = client

    async def initialize(self, **kwargs):
        return InitializeResponse(protocol_version=acp.PROTOCOL_VERSION,
                                  agent_info=Implementation(name='gate-peer', version='1'))

    async def new_session(self, **kwargs):
        descriptor = int(os.environ.pop('MMX_ACP_ATTEST_FD'))
        os.set_inheritable(descriptor, False)
        sock = socket.socket(fileno=descriptor)
        sock.setblocking(False)
        reader, writer = await asyncio.open_connection(sock=sock)
        try:
            seed = json.loads(await reader.readline())
            message = dict(seed, ready=True)
            if MODE == 'bad-ready': message['projection_sha256'] = '0' * 64
            writer.write(json.dumps(message).encode() + b'\n')
            await writer.drain()
            if json.loads(await reader.readline()) != {'accepted': True}:
                raise ValueError('owner did not accept readiness')
        finally:
            writer.close()
            await writer.wait_closed()
        return NewSessionResponse(session_id='governed-session', config_options=[
            SessionConfigOptionSelect(id='model', name='Model', category='model', type='select',
                current_value='model-a', options=[SessionConfigSelectOption(value='model-a', name='A')])])

    async def prompt(self, session_id, prompt, **kwargs):
        print('PROMPT', file=sys.stderr, flush=True)
        start = ToolCallStart(session_update='tool_call', tool_call_id='read-1',
            title='mcp__granted__read_file' if MODE != 'denied' else 'mcp__granted__write_file',
            kind='other', status='in_progress', raw_input={'file': 'memo.txt'})
        finish = ToolCallProgress(session_update='tool_call_update', tool_call_id='read-1',
            status='failed' if MODE == 'failed' else 'completed',
            content=[{'type': 'content', 'content': {'type': 'text', 'text': 'synthetic result'}}])
        if MODE != 'orphan':
            await self.client.session_update(session_id=session_id, update=start)
        if MODE == 'duplicate-start':
            await self.client.session_update(session_id=session_id, update=start)
        if MODE != 'pending':
            await self.client.session_update(session_id=session_id, update=finish)
        if MODE == 'duplicate-result':
            await self.client.session_update(session_id=session_id, update=finish)
        await self.client.session_update(session_id=session_id, update=AgentMessageChunk(
            session_update='agent_message_chunk', content=TextContentBlock(type='text', text='{"answer":42}')))
        if MODE == 'late':
            # Deliberately send terminal + trailing tool callback in one write.
            # This fixed peer uses initialize/new/prompt IDs 0/1/2.
            sys.stdout.write(json.dumps({'jsonrpc':'2.0','id':2,'result':{'stopReason':'end_turn'}})
                + '\n' + json.dumps({'jsonrpc':'2.0','method':'session/update','params':{
                    'sessionId':session_id,'update':{'sessionUpdate':'tool_call_update',
                    'toolCallId':'late-orphan','status':'completed','content':[]}}}) + '\n')
            sys.stdout.flush()
        return PromptResponse(stop_reason='end_turn')

    async def cancel(self, **kwargs):
        return None


asyncio.run(acp.run_agent(Peer()))

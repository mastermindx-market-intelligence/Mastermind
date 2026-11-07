from __future__ import annotations

import asyncio
import json

import acp
from acp.schema import (
    AgentMessageChunk,
    Implementation,
    InitializeResponse,
    NewSessionResponse,
    PromptResponse,
    SessionConfigOptionSelect,
    SessionConfigSelectOption,
    TextContentBlock,
)


class Peer:
    def on_connect(self, client):
        self.client = client

    async def initialize(self, **kwargs):
        return InitializeResponse(
            protocol_version=acp.PROTOCOL_VERSION,
            agent_info=Implementation(name="fixture-native", version="1"),
        )

    async def new_session(self, **kwargs):
        return NewSessionResponse(
            session_id="native-session",
            config_options=[
                SessionConfigOptionSelect(
                    id="model",
                    name="Model",
                    category="model",
                    type="select",
                    current_value="model-a",
                    options=[SessionConfigSelectOption(value="model-a", name="Model A")],
                )
            ],
        )

    async def prompt(self, session_id, prompt, **kwargs):
        await self.client.session_update(
            session_id=session_id,
            update=AgentMessageChunk(
                session_update="agent_message_chunk",
                content=TextContentBlock(type="text", text=json.dumps({"answer": 42})),
            ),
        )
        return PromptResponse(stop_reason="end_turn")

    async def cancel(self, **kwargs):
        return None


if __name__ == "__main__":
    asyncio.run(acp.run_agent(Peer()))

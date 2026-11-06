"""Shared fixtures for offline Hermes model tests. No network."""

from __future__ import annotations

import json
from pathlib import Path

from integrations.hermes_models.client import CompletionRequest, HermesModelClient, HttpResponse
from integrations.hermes_models.contract import PROVIDERS


CANARY = "mmx-canary-secret-DO-NOT-LOG-9f3a"
TOOL = (
    {
        "type": "function",
        "function": {
            "name": "clarify",
            "description": "ask one question",
            "parameters": {"type": "object", "properties": {}},
        },
    },
)


class ScriptedTransport:
    def __init__(self, responses) -> None:
        self.responses = list(responses)
        self.calls = []

    def post_json(self, url, headers, body, timeout):
        self.calls.append(
            {"url": url, "headers": dict(headers), "body": json.loads(json.dumps(body)), "timeout": timeout}
        )
        item = self.responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        self.now += 0.025
        return self.now


def env_for(*provider_ids: str, secret: str = "offline-test-credential") -> dict[str, str]:
    values: dict[str, str] = {}
    for provider_id in provider_ids:
        values[PROVIDERS[provider_id].credential_env] = secret
    return values


def client(tmp: Path, transport, environ: dict[str, str]) -> HermesModelClient:
    return HermesModelClient(
        transport=transport,
        meter_path=tmp / "usage.jsonl",
        environ=environ,
        monotonic=Clock(),
        now=lambda: "2026-10-25T00:00:00Z",
    )


def ok_body(model: str, *, content: str = "noted", tool_call: bool = False) -> HttpResponse:
    message: dict = {"role": "assistant", "content": content}
    if tool_call:
        message = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "clarify", "arguments": "{}"},
                }
            ],
        }
    return HttpResponse(
        status=200,
        headers={},
        body={
            "model": model,
            "choices": [{"message": message, "finish_reason": "tool_calls" if tool_call else "stop"}],
            "usage": {
                "prompt_tokens": 11,
                "completion_tokens": 4,
                "prompt_tokens_details": {"cached_tokens": 2},
                "quota_debit": 0.01,
                "account": "pool-a",
                "weekly_reset": "2026-11-01T00:00:00Z",
            },
        },
    )


def request(role: str, provider_id: str | None, *, effect: str, turn: str, messages=None, tools=()) -> CompletionRequest:
    return CompletionRequest(
        role=role,
        turn_id=turn,
        messages=messages or ({"role": "user", "content": "status"},),
        tools=tuple(tools),
        effect=effect,
        provider_id=provider_id,
        profile=None,
    )


def read_meter(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line]

"""Release pin for claude-agent-sdk: an API-failure terminal must name its cause.

PBR RUNTIME (#1693, seat ruling CR-RT-3). Production ran claude-agent-sdk 0.2.110,
whose reader builds the terminal text as ``"; ".join(errors) or str(subtype)``. The
CLI reports an API failure as ``subtype: "success"`` with ``is_error: true``, an empty
``errors[]`` and the "API Error: ..." prose in ``result``, so every CN/HK failure from
10-10 to 10-21 surfaced as the self-contradictory "Claude Code returned an error
result: success". 0.2.151 prefers ``errors[]``, then ``result``, then a non-success
subtype, then the HTTP status, and raises a typed ``ResultError``.

``pyproject.toml`` only declared ``claude-agent-sdk>=0.2``, and
``scripts/deploy_code_to_vps.sh`` ships source without installing dependencies, so
nothing kept the installed SDK at the fixed release. These tests pin the floor, the
installed version, and the public message shape through the real ``query()`` path
with a closed synthetic transport (no subprocess, no network, no credential).
"""
from __future__ import annotations

import asyncio
import importlib.metadata
import re
import tomllib
from pathlib import Path

import pytest

import claude_agent_sdk as sdk
from claude_agent_sdk import _errors

from test_sdk_generation_compatibility import ClosedTransport, terminal

FLOOR = (0, 2, 151)
PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def _version_tuple(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", text)[:3])


def _declared_sdk_requirement() -> str:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    matches = [
        dep for dep in data["project"]["dependencies"]
        if re.match(r"^claude-agent-sdk\b", dep.strip())
    ]
    assert len(matches) == 1, matches
    return matches[0].strip()


def test_pyproject_floor_excludes_the_contradictory_message_release():
    requirement = _declared_sdk_requirement()
    floor = re.search(r">=\s*([0-9][0-9.]*)", requirement)
    assert floor is not None, requirement
    assert _version_tuple(floor.group(1)) >= FLOOR, requirement


def test_installed_sdk_meets_the_declared_floor():
    installed = importlib.metadata.version("claude-agent-sdk")
    assert _version_tuple(installed) >= FLOOR, installed


async def _run_api_failure(frame):
    transport = ClosedTransport([frame], trailing_exit=True)
    messages = []
    async with asyncio.timeout(3):
        async for message in sdk.query(
            prompt="fixture prompt", options=sdk.ClaudeAgentOptions(), transport=transport,
        ):
            messages.append(message)
    return messages


@pytest.mark.parametrize("status,prose", [
    (401, "API Error: 401 fixture authentication failed"),
    (429, "API Error: 429 fixture rate limit"),
])
def test_api_failure_terminal_names_the_api_error_not_success(status, prose):
    frame = terminal(
        subtype="success", is_error=True, errors=[], result=prose,
        api_error_status=status, terminal_reason="api_error", stop_reason="error",
    )
    with pytest.raises(_errors.ProcessError) as caught:
        asyncio.run(_run_api_failure(frame))
    text = str(caught.value)
    assert "error result: success" not in text
    assert prose in text
    result_error = getattr(_errors, "ResultError", None)
    assert result_error is not None and isinstance(caught.value, result_error)
    assert caught.value.data["api_error_status"] == status


def test_api_failure_without_prose_falls_back_to_http_status_not_success():
    frame = terminal(
        subtype="success", is_error=True, errors=[], result="",
        api_error_status=401, terminal_reason="api_error", stop_reason="error",
    )
    with pytest.raises(_errors.ProcessError) as caught:
        asyncio.run(_run_api_failure(frame))
    text = str(caught.value)
    assert "error result: success" not in text
    assert "HTTP 401" in text

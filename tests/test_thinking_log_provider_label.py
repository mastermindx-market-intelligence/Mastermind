"""The response-ledger provider label must not read Claude Code aliases as OpenAI.

Bug: ``str(model).startswith(("gpt-", "o"))`` labelled the Claude Code alias
"opus" as "openai" whenever backend is not sdk/cli/codex (e.g. backend "none"
on the armed SDK failure path).
"""
from __future__ import annotations

import pytest

from brain import thinking_log


@pytest.mark.parametrize("model,backend,expected", [
    ("opus", "none", "claude_code"),
    ("opus[1m]", "none", "claude_code"),
    ("sonnet", "api", "claude_code"),
    ("haiku", "none", "claude_code"),
    ("haiku-fast", "none", "claude_code"),
    ("o3", "none", "openai"),
    ("o4-mini", "api", "openai"),
    ("gpt-5", "none", "openai"),
    ("claude-opus-4-1", "api", "claude_api"),
    ("deepseek-v4", "none", "deepseek"),
    ("orca", "none", None),
    ("opus", "codex", "openai_codex"),
    ("gpt-5", "sdk", "claude_code"),
])
def test_provider_label_by_model_and_backend(model, backend, expected):
    row = thinking_log.build_row(question="q", answer="a", model=model, backend=backend)
    assert row["provider"] == expected

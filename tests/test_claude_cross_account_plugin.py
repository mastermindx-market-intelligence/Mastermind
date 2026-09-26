"""Contract checks for the existing Claude plugin's communication extension.

These checks validate shipped prompts/examples, not native model behavior or
live account enrollment. The existing Company gateway remains the authority.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

import pytest
import yaml

from integrations.mastermind_company_mcp.consultation import (
    CompanyConsultationToolError,
    validate_company_consultation_tool_arguments,
)

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "integrations/claude_executive_plugin"
SKILL = PLUGIN / "skills/cross-account-communication/SKILL.md"
COMMANDS = {
    "company-peers": "company.peers",
    "company-ask": "company.consult",
    "company-read": "company.consultation",
    "company-reply": "company.reply",
}


def command_source(name: str) -> tuple[dict, str, dict]:
    path = PLUGIN / "commands" / f"{name}.md"
    assert path.is_file(), f"missing communication command: {name}"
    text = path.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    assert len(parts) == 3 and parts[0] == ""
    frontmatter = yaml.safe_load(parts[1])
    examples = re.findall(r"```json\n(.*?)\n```", parts[2], re.S)
    assert len(examples) == 1, "one canonical wire example per command"
    return frontmatter, parts[2], json.loads(examples[0])


@pytest.mark.parametrize("name,tool", COMMANDS.items())
def test_command_examples_match_real_company_gateway(name, tool):
    frontmatter, body, example = command_source(name)
    assert frontmatter["name"] == name
    assert frontmatter["description"]
    assert set(example) == {"tool", "arguments"}
    assert example["tool"] == tool
    assert validate_company_consultation_tool_arguments(
        tool, example["arguments"]
    ) == example["arguments"]
    assert "cross-account-communication/SKILL.md" in body
    assert "mastermind-executive" in body
    assert "$ARGUMENTS" in body
    assert "allowed-tools" not in frontmatter
    assert "!`" not in body, "commands must not execute shell substitutions"


@pytest.mark.parametrize("name", COMMANDS)
@pytest.mark.parametrize("field", ["account", "session_id", "thread_ts", "token"])
def test_examples_cannot_gain_model_selected_identity_or_transport(name, field):
    _, _, example = command_source(name)
    arguments = {**example["arguments"], field: "untrusted"}
    with pytest.raises(CompanyConsultationToolError) as error:
        validate_company_consultation_tool_arguments(example["tool"], arguments)
    assert error.value.code == "INVALID_REQUEST"


@pytest.mark.parametrize("name", ["company-ask", "company-reply"])
def test_send_commands_do_not_turn_ambiguous_results_into_resends(name):
    frontmatter, body, _ = command_source(name)
    assert frontmatter["disable-model-invocation"] is True
    assert "EFFECT_UNKNOWN" in body
    assert "Do not resend" in body
    assert "synthetic" in body


def test_communication_skill_preserves_owner_and_effect_boundaries():
    assert SKILL.is_file(), "missing communication consumer skill"
    text = SKILL.read_text(encoding="utf-8")
    frontmatter = yaml.safe_load(text.split("---", 2)[1])
    assert frontmatter["name"] == "cross-account-communication"
    assert frontmatter["description"].startswith("Use when")
    for required in (
        "mastermind-executive", "company.peers", "company.consult",
        "company.reply", "company.consultation", "EFFECT_UNKNOWN",
        "same-program", "Wake", "consumption", "No broadcast",
        "No login", "not a worker commission", "no automatic retry",
        "do not bypass", "no idle-session wake guarantee",
    ):
        assert required in text, f"missing communication boundary: {required}"


def test_runbook_requires_all_directed_account_pairs_and_truthful_receipts():
    path = PLUGIN / "references/cross-account-qualification.md"
    assert path.is_file(), "missing native release qualification contract"
    text = path.read_text(encoding="utf-8")
    for sender in range(1, 5):
        for recipient in range(1, 5):
            if sender != recipient:
                assert f"A{sender} -> A{recipient}" in text
    for required in (
        "NOT_RUN", "BUILT_NOT_PROVEN", "#955", "#962", "#1001",
        "not account identifiers", "actual native", "EFFECT_UNKNOWN",
        "disabled", "cross-project", "cross-program", "restart",
        "consumption", "no new", "CI", "independent review",
    ):
        assert required in text, f"missing qualification boundary: {required}"


def test_example_refs_are_explicitly_nonproduction():
    for name in ("company-ask", "company-read", "company-reply"):
        _, body, example = command_source(name)
        assert "synthetic" in body
        assert "Never send the example" in body
        refs = [v for v in example["arguments"].values() if isinstance(v, str)]
        assert any(re.fullmatch(r"(?:peer|consult)-0{31}1", v) for v in refs)

"""Opt-in disabled Hermes bindings to the EXISTING Executive and Paper MCP servers.

The incumbent Hermes role installer remains the sole config writer. This
renderer augments its already-qualified native BYOK YAML; it never discovers a
new endpoint, obtains tokens, connects a server, or enables a tool. Native
selected-child and Fabric execution retain their original authority.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

# Executive writes (session_send, session_summon, submit_ceo_intent) need their
# original principal-bound release, never an inferred Hermes role grant.
EXECUTIVE_READ_TOOLS = (
    "executive_state", "executive_inbox", "executive_job",
    "executive_fabric", "ceo_intent_status", "session_targets",
    "executive_mdm",
)
PAPER_READ_TOOLS = ("paper_inspect", "paper_catalog", "paper_read")
SERVER_NAMES = ("mastermind_executive_v3", "mastermind_paper")


def disarmed_server_entries() -> dict[str, dict[str, Any]]:
    """Fixed transport declarations; secret references, not credentials."""
    return {
        "mastermind_executive_v3": {
            "url": "${MASTERMIND_EXECUTIVE_V3_MCP_URL}",
            "headers": {"Authorization": "Bearer ${MASTERMIND_EXECUTIVE_MCP_ACCESS_TOKEN}"},
            "enabled": False,
            "timeout": 30,
            "tools": {
                "include": list(EXECUTIVE_READ_TOOLS),
                "resources": False, "prompts": False,
            },
        },
        "mastermind_paper": {
            "command": "${MASTERMIND_PAPER_MCP_PYTHON}",
            "args": ["${MASTERMIND_PAPER_MCP_SERVER}"],
            "enabled": False,
            "timeout": 30,
            "tools": {
                "include": list(PAPER_READ_TOOLS),
                "resources": False, "prompts": False,
            },
        },
    }


def augment_disarmed_document(document: dict[str, Any]) -> dict[str, Any]:
    """Augment the incumbent unique-key-parsed config; no side effects.

    Refuses previously enabled Steward, unrecognized MCP, native-toolset
    enlargement, and missing host restrictions rather than masking them.
    """
    if not isinstance(document, dict):
        raise ValueError("EXEC_PAPER_BASE_INVALID")
    servers = document.get("mcp_servers")
    if not isinstance(servers, dict) or set(servers) != {"mastermind_steward"}:
        raise ValueError("EXEC_PAPER_BASE_MCP_DRIFT")
    steward = servers["mastermind_steward"]
    if not isinstance(steward, dict) or steward.get("enabled") is not False:
        raise ValueError("EXEC_PAPER_STEWARD_NOT_DISARMED")
    if document.get("toolsets") != ["clarify"]:
        raise ValueError("EXEC_PAPER_NATIVE_TOOLSET_DRIFT")
    agent = document.get("agent")
    if not isinstance(agent, dict) or not isinstance(agent.get("disabled_toolsets"), list):
        raise ValueError("EXEC_PAPER_NATIVE_TOOLSET_DRIFT")
    if not {"terminal", "file", "browser", "delegation", "computer_use"}.issubset(
        set(agent["disabled_toolsets"])
    ):
        raise ValueError("EXEC_PAPER_NATIVE_TOOLSET_DRIFT")
    result = deepcopy(document)
    result["mcp_servers"].update(disarmed_server_entries())
    return result


def render_disarmed_native_exec_paper(profile: object) -> str:
    """Installer-compatible render hook. NOT a live enrollment or grant."""
    from integrations.hermes_harness.native_byok import render_disarmed_native_byok
    from integrations.hermes_runtime.errors import RuntimeRefusal
    from integrations.hermes_steward.config_guard import _load_unique_yaml
    import yaml

    source = render_disarmed_native_byok(profile)
    try:
        data = augment_disarmed_document(_load_unique_yaml(source.encode("utf-8")))
        rendered = (
            "# Existing Hermes BYOK config with two DISABLED read-only MCP clients.\n"
            "# No Executive/Paper connectivity, write permission or dispatch granted.\n"
            + yaml.safe_dump(data, sort_keys=False, allow_unicode=False)
        )
        if len(rendered.encode("utf-8")) > 64 * 1024:
            raise ValueError("EXEC_PAPER_CONFIG_TOO_LARGE")
        if _load_unique_yaml(rendered.encode("utf-8")) != data:
            raise ValueError("EXEC_PAPER_CONFIG_ROUNDTRIP_DRIFT")
    except (ValueError, TypeError, UnicodeError, yaml.YAMLError):
        raise RuntimeRefusal("EXEC_PAPER_CONFIG_UNQUALIFIED") from None
    return rendered


def exact_disarmed_catalog(profile: object, observed: bytes) -> dict[str, tuple[str, ...]] | None:
    """Pure proposed input for the EXISTING supervisor's registry guard.

    A caller must first apply the incumbent private-file, custody and runtime
    checks. This function never reads an installed file or enables a server;
    it provides no native admission, only exact-byte recognition and the
    expected *disabled* MCP census for the already-authoritative supervisor.
    """
    if type(observed) is not bytes or len(observed) > 64 * 1024:
        return None
    if observed != render_disarmed_native_exec_paper(profile).encode("utf-8"):
        return None
    from integrations.hermes_steward.client import ALLOWED_TOOLS
    return {
        "mastermind_steward": tuple(ALLOWED_TOOLS),
        "mastermind_executive_v3": tuple(EXECUTIVE_READ_TOOLS),
        "mastermind_paper": tuple(PAPER_READ_TOOLS),
    }

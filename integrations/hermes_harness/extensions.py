"""Register Steward reads, mmx_delegate, and Secretary skills on the runtime.

Hermes built-in toolsets ``delegation`` and ``skills`` stay disabled. These
names are extension tools. The composed profile allowlist must list them or
the runtime registry check refuses to start.
"""

from __future__ import annotations

from integrations.hermes_delegate.policy import TOOL_NAME
from integrations.hermes_models.contract import PROVIDERS
from integrations.hermes_runtime.contract import (
    clear_child_secret_env,
    clear_extension_tools,
    register_child_secret_env,
    register_extension_tools,
)
from integrations.hermes_steward.client import ALLOWED_TOOLS

STEWARD_TOOLS = frozenset(ALLOWED_TOOLS)
DELEGATE_TOOLS = frozenset({TOOL_NAME})
SKILL_TOOLS = frozenset({
    "skill_chatgpt_browser_session_operator",
    "skill_mastermind_context",
    "skill_mastermind_fabric_secretary_local",
})
HARNESS_ROLES = frozenset({"mmsecretary", "mmmeta"})


def extension_names_for(role: str) -> frozenset[str]:
    if role not in HARNESS_ROLES:
        return frozenset()
    names = set(STEWARD_TOOLS)
    names.update(DELEGATE_TOOLS)
    if role == "mmsecretary":
        names.update(SKILL_TOOLS)
    return frozenset(names)


def _role_of(profile: object) -> str:
    role = getattr(profile, "role", "")
    return role if isinstance(role, str) else ""


def steward_tools(profile: object) -> frozenset[str]:
    if _role_of(profile) not in HARNESS_ROLES:
        return frozenset()
    return STEWARD_TOOLS


def delegate_tools(profile: object) -> frozenset[str]:
    if _role_of(profile) not in HARNESS_ROLES:
        return frozenset()
    return DELEGATE_TOOLS


def secretary_skills(profile: object) -> frozenset[str]:
    if _role_of(profile) != "mmsecretary":
        return frozenset()
    return SKILL_TOOLS


def boot_harness() -> None:
    """Register the three extension sources and the provider env names.

    Registration stores names only. It does not read credentials or admit work.
    A second call replaces the previous registration in this process.
    """

    clear_extension_tools()
    clear_child_secret_env()
    register_extension_tools("steward", steward_tools)
    register_extension_tools("delegate", delegate_tools)
    register_extension_tools("secretary", secretary_skills)
    register_child_secret_env(sorted({spec.credential_env for spec in PROVIDERS.values()}))

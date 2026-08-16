"""P1A capability classification.  Policy only; not a production grant.

Presence is not authority.  A discovered native tool is not an Executive permit.
"""
from __future__ import annotations

from typing import Iterable, Mapping, Sequence

CLASS_REQUIRED = "REQUIRED"
CLASS_ALLOWED_AMBIENT = "ALLOWED_AMBIENT"
CLASS_FORBIDDEN = "FORBIDDEN"
CLASS_UNCLASSIFIED = "UNCLASSIFIED"

LAUNCH_OK = "LAUNCH_OK"
LAUNCH_REFUSED_MISSING_REQUIRED = "LAUNCH_REFUSED_MISSING_REQUIRED"
LAUNCH_REFUSED_FORBIDDEN_PRESENT = "LAUNCH_REFUSED_FORBIDDEN_PRESENT"
LAUNCH_REFUSED_UNCLASSIFIED = "LAUNCH_REFUSED_UNCLASSIFIED"


def classify_name(
    name: str,
    *,
    required: Iterable[str],
    allowed_ambient: Iterable[str],
    forbidden: Iterable[str],
) -> str:
    value = str(name or "").strip()
    required_set = set(required)
    allowed_set = set(allowed_ambient)
    forbidden_set = set(forbidden)
    if value in forbidden_set:
        return CLASS_FORBIDDEN
    if value in required_set:
        return CLASS_REQUIRED
    if value in allowed_set:
        return CLASS_ALLOWED_AMBIENT
    return CLASS_UNCLASSIFIED


def classify_observed(
    observed: Sequence[str],
    *,
    required: Sequence[str],
    allowed_ambient: Sequence[str],
    forbidden: Sequence[str],
) -> dict[str, list[str]]:
    buckets = {
        CLASS_REQUIRED: [],
        CLASS_ALLOWED_AMBIENT: [],
        CLASS_FORBIDDEN: [],
        CLASS_UNCLASSIFIED: [],
    }
    for name in observed:
        buckets[classify_name(
            name,
            required=required,
            allowed_ambient=allowed_ambient,
            forbidden=forbidden,
        )].append(name)
    missing_required = [name for name in required if name not in set(observed)]
    return {
        **{key: sorted(values) for key, values in buckets.items()},
        "missing_required": sorted(missing_required),
    }


def launch_decision(
    classification: Mapping[str, Sequence[str]],
    *,
    fail_closed_unclassified: bool,
) -> str:
    if classification.get("missing_required"):
        return LAUNCH_REFUSED_MISSING_REQUIRED
    if classification.get(CLASS_FORBIDDEN):
        return LAUNCH_REFUSED_FORBIDDEN_PRESENT
    if fail_closed_unclassified and classification.get(CLASS_UNCLASSIFIED):
        return LAUNCH_REFUSED_UNCLASSIFIED
    return LAUNCH_OK


def write_profile_fail_closed(classification: Mapping[str, Sequence[str]]) -> str:
    """Production write-capable profiles fail closed on unclassified capabilities."""
    return launch_decision(classification, fail_closed_unclassified=True)


MINIMAL_SURFACE_TOML = """\
model = "{model}"
approval_policy = "never"
sandbox_mode = "read-only"

[features]
apps = false

[skills.bundled]
enabled = false
{mcp_block}
"""


def render_minimal_surface_config(
    *,
    model: str,
    mcp_command: str,
    mcp_args: Sequence[str],
    mcp_cwd: str,
) -> str:
    quoted_args = ", ".join(f'"{item}"' for item in mcp_args)
    mcp_block = "\n".join(
        [
            "",
            "[mcp_servers.ohf_probe]",
            f'command = "{mcp_command}"',
            f"args = [{quoted_args}]",
            f'cwd = "{mcp_cwd}"',
            "startup_timeout_sec = 10",
        ]
    )
    return MINIMAL_SURFACE_TOML.format(model=model, mcp_block=mcp_block)


# Version-specific 0.147.0 keys, verified by config parse:
#   [features] apps = false            accepted
#   [skills.bundled] enabled = false   accepted
#   [skills] bundled = false           rejected (expected BundledSkillsConfig)
CODEX_0_147_APPS_DISABLE = ("features.apps", False)
CODEX_0_147_BUNDLED_SKILLS_DISABLE = ("skills.bundled.enabled", False)

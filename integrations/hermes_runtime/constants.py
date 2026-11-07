"""Pinned Hermes runtime constants.

Sibling packages (model routing, Steward, delegation, secretary skills) may
import this module. It does not admit jobs, start Hermes, or read secrets.
"""
from __future__ import annotations

# NousResearch/hermes-agent MIT pin inspected by the qualification lane.
# A profile, checkout, or installer that names any other revision is refused.
PINNED_UPSTREAM_SHA = "1c0cd667746d3395fe9e1b6c74f8f85952486f18"
UPSTREAM_REPOSITORY = "https://github.com/NousResearch/hermes-agent.git"

PROFILE_SCHEMA = "mastermind.hermes_runtime_profile.v1"
REGISTRY_SCHEMA = "mastermind.hermes_runtime_registry.v1"
HEALTH_SCHEMA = "mastermind.hermes_runtime_health.v1"
MANIFEST_SCHEMA = "mastermind.hermes_runtime_manifest.v1"
INSTALL_SCHEMA = "mastermind.hermes_runtime_install.v1"

HEALTH_PATH = "/api/health"
DASHBOARD_PATH = "/"
LOOPBACK_HOST = "127.0.0.1"

# Exact non-clarify CLI/plugin toolsets observed at the pin. Enabling any of
# these in a WP1 profile is a refusal. WP4/WP5 add bridge tools under new
# names; they do not flip these Hermes toolsets on.
REFUSED_HERMES_TOOLSETS = frozenset({
    "web", "browser", "terminal", "file", "code_execution", "vision",
    "video", "image_gen", "video_gen", "x_search", "tts", "stt",
    "skills", "todo", "kanban", "memory", "context_engine", "session_search",
    "connections", "delegation", "cronjob", "yuanbao", "computer_use",
    "a2a",
})
ADMITTED_HERMES_TOOLSETS = frozenset({"clarify"})
KNOWN_HERMES_TOOLSETS = REFUSED_HERMES_TOOLSETS | ADMITTED_HERMES_TOOLSETS
DEFAULT_TOOL_ALLOWLIST = frozenset({"clarify"})

# Candidate routes copied from the qualified disarmed profiles. WP2 is the
# place that may widen this table; WP1 does not call a provider.
QUALIFIED_MODEL_ROUTES = {
    "mmsecretary": {"provider": "zai", "default": "glm-5.3-flash"},
    "mmmeta": {"provider": "zai", "default": "glm-5.3"},
}
QUALIFIED_VISION_ROUTE = {"provider": "zai", "model": "glm-5.3-flash"}

GATEWAY_TOKEN_ENV = "HERMES_GATEWAY_TOKEN"
DASHBOARD_USERNAME_ENV = "HERMES_DASHBOARD_BASIC_AUTH_USERNAME"
DASHBOARD_PASSWORD_ENV = "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD"
# Always passed to the Hermes child when present. WP2 registers provider
# names through register_child_secret_env; unregistered keys stay on disk.
DEFAULT_CHILD_SECRET_ENV = frozenset({
    DASHBOARD_USERNAME_ENV,
    DASHBOARD_PASSWORD_ENV,
})

CONFIG_EXIT = 78
POLICY_EXIT = 2
IO_EXIT = 3

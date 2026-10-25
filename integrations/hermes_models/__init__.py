"""Hermes OpenAI-compatible model providers for the Secretary and Meta-CEO profiles.

This package is a subordinate transport and profile renderer. It does not admit
Executive work, claim Capacity, or arm a live provider. Model identity is the
existing Model Router catalog plus the unmerged BytePlus ModelArk contract from
PR #1824. Hermes native ``fallback_model`` is intentionally not emitted: 429
and outage handling live here and never replay a side-effecting turn.
"""

from __future__ import annotations

from integrations.hermes_models.client import HermesModelClient
from integrations.hermes_models.contract import (
    CREDENTIAL_ENV_NAMES,
    CREDENTIAL_FILE_ENV_NAMES,
    MODELARK_CONTRACT,
    UPSTREAM_HERMES_SHA,
)
from integrations.hermes_models.profile_config import render_profile

__all__ = [
    "CREDENTIAL_ENV_NAMES",
    "CREDENTIAL_FILE_ENV_NAMES",
    "HermesModelClient",
    "MODELARK_CONTRACT",
    "UPSTREAM_HERMES_SHA",
    "render_profile",
]

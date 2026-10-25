"""Shadow stays on until this unit's Slack bot user id is set.

The id is HERMES_SLACK_BOT_USER_ID from that unit's 0600 secrets file.
A missing or malformed id is not an identity, so live posting stays refused.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping

from integrations.hermes_runtime.errors import RuntimeRefusal

_USER = re.compile(r"^U[A-Z0-9]{6,32}$")


def assert_may_leave_shadow(environ: Mapping[str, str] | None = None) -> str:
    """Return this agent's bot user id, or refuse to leave shadow mode."""

    env = os.environ if environ is None else environ
    value = env.get("HERMES_SLACK_BOT_USER_ID")
    if not isinstance(value, str) or _USER.fullmatch(value) is None:
        raise RuntimeRefusal("SHADOW_ID_REQUIRED")
    return value

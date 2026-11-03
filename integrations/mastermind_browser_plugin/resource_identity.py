"""Preserve the authenticated Browser resource without creating auth policy.

Legacy internal resource tokens remain supported. HTTPS audiences use the
existing Business MCP URI validator; identity is never normalized.
"""
from __future__ import annotations

import re
from integrations.business_mcp_auth.contracts import AuthError, _split_https_url

_LEGACY_RESOURCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def validate_browser_resource(value: object) -> str:
    if type(value) is str and _LEGACY_RESOURCE.fullmatch(value) is not None:
        return value
    try:
        resource, _ = _split_https_url(value)
    except (AuthError, TypeError, ValueError) as exc:
        raise ValueError("browser resource is invalid") from exc
    return resource

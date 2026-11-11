"""Fail-closed native BYOK egress through an operator-owned loopback CONNECT proxy.

No proxy is created or launched here. The existing role-private 0600 secrets
file supplies only its own per-role proxy address. RestrictAddressFamilies,
IPAddressDeny=any remains. The root-managed unit permits only the role's
one loopback alias for its authenticated gateway, native backend and
approved vendor CONNECT proxy. Shared 127.0.0.1 is not permitted by
the actual root unit. Kernel and parent-slice enforcement need host proof.
Source qualification is not evidence of an installed policy, real CONNECT,
TLS verification or an authenticated provider response.
"""

from __future__ import annotations

from collections.abc import Mapping
from urllib.parse import urlsplit

from .errors import RuntimeRefusal

PROXY_ENV_NAME = "HERMES_NATIVE_HTTPS_PROXY"
ROLE_ENV_NAME = "HERMES_NATIVE_EGRESS_ROLE"
ROLE_PROXY_HOST = {
    "mmsecretary": "127.0.0.2",
    "mmmeta": "127.0.0.3",
}
ROLE_PROXY_PORT = {"mmsecretary": 18651, "mmmeta": 18652}
ROLES = frozenset(ROLE_PROXY_HOST)


def native_egress_child_env(role: str, private_values: Mapping[str, str]) -> dict[str, str]:
    """Only a role-pinned, canonical IPv4 loopback HTTP CONNECT URL is forwarded.

    A URL in an interactive shell is NEVER consulted. The proxy's mandatory
    remote hostname/port allowlist and TLS transport need a separate receiving
    owner and real host verification before a provider can be called.
    """
    if role not in ROLES:
        raise RuntimeRefusal("NATIVE_EGRESS_ROLE_REFUSED")
    if private_values.get(ROLE_ENV_NAME) != role:
        raise RuntimeRefusal("NATIVE_EGRESS_ROLE_BINDING_MISSING")
    raw = private_values.get(PROXY_ENV_NAME)
    if not isinstance(raw, str) or not raw:
        raise RuntimeRefusal("NATIVE_EGRESS_PROXY_NOT_ENROLLED")
    try:
        url = urlsplit(raw)
        port = url.port
    except (ValueError, TypeError):
        raise RuntimeRefusal("NATIVE_EGRESS_PROXY_INVALID") from None
    host = ROLE_PROXY_HOST[role]
    if (url.scheme != "http" or url.hostname != host
            or not isinstance(port, int) or port != ROLE_PROXY_PORT[role]
            or raw != f"http://{host}:{port}"):
        raise RuntimeRefusal("NATIVE_EGRESS_PROXY_INVALID")
    # A CONNECT proxy must be locally controlled and allowlisted OUTSIDE this
    # native unit. HTTP_PROXY/ALL_PROXY, shell proxy values and other role
    # tokens never reach the child.
    return {
        "HTTPS_PROXY": raw,
        "NO_PROXY": f"127.0.0.1,localhost,{host}",
    }

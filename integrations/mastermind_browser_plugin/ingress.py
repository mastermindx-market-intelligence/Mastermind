"""Pure ingress projection for the separate Mastermind Browser MCP plugin.

This module creates no listener, tunnel, OAuth resource, browser, provider
session, host placement or authority. It binds one exact public Browser MCP
resource to one exact internal tailnet Browser route while preserving native
supervisor-private stdio as the separate internal lane.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit


PUBLIC_PATH = "/mcp"
INTERNAL_PATH = "/browser-fabric"
TAILNET_SUFFIX = ".ts.net"
SCHEMA = "mastermind.browser_ingress_plan.v1"


class BrowserIngressError(ValueError):
    """One Browser ingress endpoint cannot be represented safely."""


def _https_endpoint(
    value: object,
    *,
    expected_path: str,
    require_tailnet: bool,
) -> str:
    if type(value) is not str or not value or len(value) > 2048:
        raise BrowserIngressError("Browser ingress URL is invalid")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except (TypeError, ValueError) as exc:
        raise BrowserIngressError("Browser ingress URL is invalid") from exc
    host = parsed.hostname
    if (
        parsed.scheme != "https"
        or type(host) is not str
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or parsed.path != expected_path
        or parsed.query
        or parsed.fragment
    ):
        raise BrowserIngressError("Browser ingress URL is invalid")
    if require_tailnet and (
        not host.endswith(TAILNET_SUFFIX) or len(host) <= len(TAILNET_SUFFIX)
    ):
        raise BrowserIngressError("Internal Browser route must be a tailnet host")
    canonical = f"https://{host}"
    if port == 443 and parsed.netloc.endswith(":443"):
        canonical += ":443"
    return canonical + expected_path


@dataclass(frozen=True, slots=True)
class BrowserIngressPlan:
    public_resource_url: str
    internal_upstream_url: str
    public_path: str = PUBLIC_PATH
    internal_path: str = INTERNAL_PATH
    web_lane: str = "oauth_https"
    native_lane: str = "supervisor_private_stdio"
    same_browser_owner_required: bool = True
    requires_dedicated_public_binding: bool = True

    @property
    def is_admission(self) -> bool:
        return False

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": SCHEMA,
            "public_resource_url": self.public_resource_url,
            "internal_upstream_url": self.internal_upstream_url,
            "public_path": self.public_path,
            "internal_path": self.internal_path,
            "web_lane": self.web_lane,
            "native_lane": self.native_lane,
            "same_browser_owner_required": self.same_browser_owner_required,
            "requires_dedicated_public_binding": self.requires_dedicated_public_binding,
            "is_admission": False,
        }


def build_browser_ingress_plan(
    *,
    public_resource_url: object,
    internal_upstream_url: object,
) -> BrowserIngressPlan:
    """Validate two exact transport endpoints; grant neither transport authority."""
    public = _https_endpoint(
        public_resource_url,
        expected_path=PUBLIC_PATH,
        require_tailnet=False,
    )
    internal = _https_endpoint(
        internal_upstream_url,
        expected_path=INTERNAL_PATH,
        require_tailnet=True,
    )
    return BrowserIngressPlan(
        public_resource_url=public,
        internal_upstream_url=internal,
    )

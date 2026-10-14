"""Pure binding plan for a dedicated Mastermind Browser Secure MCP Tunnel.

The Browser tunnel deliberately has a different tunnel identity from Studio
Direct so Browser catalog/release failure is not coupled to the Studio/Paper
app. This module creates no tunnel, process, credential, OAuth link, browser,
grant, placement or lifecycle state.
"""
from __future__ import annotations

from dataclasses import dataclass
from http.client import HTTPS_PORT
import re
from urllib.parse import urlsplit

PROFILE_NAME = "mastermind-browser"
INTERNAL_PATH = "/browser-fabric"
SCHEMA = "mastermind.browser_tunnel_binding.v1"
_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$")


class BrowserTunnelBindingError(ValueError):
    """The dedicated Browser tunnel binding cannot be represented safely."""


def _ref(value: object, field: str) -> str:
    if type(value) is not str or _REF.fullmatch(value) is None:
        raise BrowserTunnelBindingError(f"{field} is invalid")
    return value


def _upstream(value: object) -> str:
    if type(value) is not str or not value or len(value) > 2048:
        raise BrowserTunnelBindingError("internal Browser upstream is invalid")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except (TypeError, ValueError) as exc:
        raise BrowserTunnelBindingError("internal Browser upstream is invalid") from exc
    host = parsed.hostname
    if (
        parsed.scheme != "https"
        or type(host) is not str
        or not host.endswith(".ts.net")
        or len(host) <= len(".ts.net")
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, HTTPS_PORT)
        or parsed.path != INTERNAL_PATH
        or parsed.query
        or parsed.fragment
    ):
        raise BrowserTunnelBindingError(
            f"internal Browser upstream must be exact HTTPS tailnet path {INTERNAL_PATH}"
        )
    canonical = f"https://{host}"
    if port == HTTPS_PORT and parsed.netloc.endswith(f":{HTTPS_PORT}"):
        canonical += f":{HTTPS_PORT}"
    return canonical + INTERNAL_PATH


@dataclass(frozen=True, slots=True)
class BrowserTunnelBinding:
    browser_tunnel_ref: str
    studio_tunnel_ref: str
    internal_upstream_url: str
    profile_name: str = PROFILE_NAME
    requires_separate_tunnel: bool = True
    reuses_tunnel_client_runtime: bool = True

    @property
    def is_registration(self) -> bool:
        return False

    @property
    def is_auth_linking(self) -> bool:
        return False

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": SCHEMA,
            "browser_tunnel_ref": self.browser_tunnel_ref,
            "studio_tunnel_ref": self.studio_tunnel_ref,
            "internal_upstream_url": self.internal_upstream_url,
            "profile_name": self.profile_name,
            "requires_separate_tunnel": True,
            "reuses_tunnel_client_runtime": True,
            "is_registration": False,
            "is_auth_linking": False,
            "authority": {
                "tunnel_binding_is_authority": False,
                "may_create_tunnel": False,
                "may_link_auth0": False,
                "may_select_browser": False,
                "may_mint_browser_grant": False,
            },
        }


def build_browser_tunnel_binding(
    *,
    browser_tunnel_ref: object,
    studio_tunnel_ref: object,
    internal_upstream_url: object,
) -> BrowserTunnelBinding:
    browser = _ref(browser_tunnel_ref, "browser_tunnel_ref")
    studio = _ref(studio_tunnel_ref, "studio_tunnel_ref")
    if browser == studio:
        raise BrowserTunnelBindingError(
            "Browser and Studio must use distinct tunnel identities"
        )
    return BrowserTunnelBinding(
        browser_tunnel_ref=browser,
        studio_tunnel_ref=studio,
        internal_upstream_url=_upstream(internal_upstream_url),
    )

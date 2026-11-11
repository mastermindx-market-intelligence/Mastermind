"""Read-only, default-disabled Chris-Dot canary selection from the sealed Executive MCP document.

No OAuth issuer, identity or Slack permission is created here. An installed
Executive Runtime must use the *same* current sealed MCP policy document and
release identity that authenticates the original request. No mutable sidecar
config, environment grant or caller-provided Slack user ID.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from control_plane.principal_projection import NeutralPrincipalProjection
from integrations.slack_agent_dialogue.dot_canary_event import (
    TrustedCanaryPolicy, canary_event_definition,
)
from .web_reply_subscription_owner import owner_key


_SHA = re.compile(r"^[0-9a-f]{64}$")
_SLACK_TS = re.compile(r"^[0-9]{10,16}\.[0-9]{6}$")


def validate_dot_canary_settings(raw):
    """Closed, opt-in one-account config; absent is OFF and has no side effects."""
    if not isinstance(raw, dict):
        raise ValueError("Executive document unavailable")
    value=raw.get("dot_canary")
    if value is None:
        return None
    if type(value) is not dict or type(value.get("armed")) is not bool:
        raise ValueError("invalid Chris-Dot canary selection")
    if value["armed"] is False:
        if set(value)!={"armed"}:
            raise ValueError("disabled canary carries hidden owner fields")
        return None
    keys={"armed","subject_digest","workspace_id","channel_id",
          "relay_bot_user_id","owner_slack_user_id","not_before_ts"}
    if (set(value)!=keys or raw.get("reply_events_armed") is not True
            or raw.get("executive_mcp_profile")!="web_ceo_v3"
            or type(value["subject_digest"]) is not str
            or _SHA.fullmatch(value["subject_digest"]) is None
            or type(value["not_before_ts"]) is not str
            or _SLACK_TS.fullmatch(value["not_before_ts"]) is None):
        raise ValueError("canary requires valid enrolled Executive event host")
    # Reuse the projection's full Slack-ID and policy validation, but the
    # computed owner_key belongs to the actual verified principal at call time.
    candidate=TrustedCanaryPolicy(
        workspace_id=value["workspace_id"],channel_id=value["channel_id"],
        relay_bot_user_id=value["relay_bot_user_id"],
        owner_slack_user_id=value["owner_slack_user_id"],
        principal_digest="a"*64,not_before_ts=value["not_before_ts"],current=True,
    )
    canary_event_definition(candidate)
    return dict(value)


class InstalledDotCanaryPolicyProvider:
    """Current sealed config is read on *every* discovery or modifying request."""

    def __init__(self, config_path, *, release_sha, peer_uid):
        self.path=Path(config_path)
        self.release_sha=release_sha
        self.peer_uid=peer_uid
        if (not self.path.is_absolute() or type(release_sha) is not str
                or re.fullmatch(r"[0-9a-f]{40}",release_sha) is None
                or type(peer_uid) is not int or peer_uid<=0):
            raise TypeError("exact installed Executive owner required")

    def __call__(self, principal: NeutralPrincipalProjection):
        if type(principal) is not NeutralPrincipalProjection:
            raise ValueError("authenticated Executive principal required")
        from ops.executive_os.executive_mcp_entry import (
            require_sealed_path,validate_document,
        )
        try:
            require_sealed_path(self.path)
            raw=validate_document(json.loads(self.path.read_text(encoding="utf-8")))
            if (raw["release_sha"]!=self.release_sha
                    or raw["service_uid"]!=self.peer_uid):
                raise ValueError("installed release changed")
            cfg=validate_dot_canary_settings(raw)
            if cfg is None or principal.subject_digest!=cfg["subject_digest"]:
                return None
            policy=TrustedCanaryPolicy(
                workspace_id=cfg["workspace_id"],
                channel_id=cfg["channel_id"],
                relay_bot_user_id=cfg["relay_bot_user_id"],
                owner_slack_user_id=cfg["owner_slack_user_id"],
                principal_digest=owner_key(principal),
                not_before_ts=cfg["not_before_ts"],
                current=True,
            )
            canary_event_definition(policy)
            return policy
        except Exception:
            # A broken/seal-changed document is a refusal, not an implicit
            # "no canary" default after any grant was issued.
            raise ValueError("current Chris-Dot enrollment policy unavailable") from None

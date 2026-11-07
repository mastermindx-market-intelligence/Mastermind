"""Reuse the installed MCP receiver's exact policy selection and sealed document.

No permissive callback, new resource policy, token lookup or credential is added.
"""
from pathlib import Path
import json

from integrations.business_mcp_auth.contracts import validate_resource_policy
from integrations.mastermind_executive_app.gateway import AppPolicies, load_app_policies


class ReplyPolicyUnavailable(ValueError):
    pass


class ReplyPolicyDenied(ValueError):
    """An actual current validated policy no longer admits this account."""


class ReplyPolicySelection:
    """Trusted in-process receiver composition; construction authenticates nobody."""
    def __init__(self, policies: tuple[AppPolicies, ...]):
        if type(policies) is not tuple or not policies or any(type(p) is not AppPolicies for p in policies):
            raise TypeError("existing receiver policy variants required")
        self._variants = policies

    def policies(self):
        return tuple(validate_resource_policy(policy) for pair in self._variants
            for policy in (pair.read, pair.submit))

    def select(self, principal):
        values = self.policies()
        matches = [p for p in values if (p.policy_id, p.issuer, p.resource) ==
            (principal.policy_id, principal.issuer, principal.resource)]
        if len(matches) != 1 or principal.subject_digest not in matches[0].allowed_subject_digests:
            raise ReplyPolicyDenied("original subscriber policy denied")
        return matches[0]


class InstalledReplyPolicySelection(ReplyPolicySelection):
    """Re-read the SAME sealed MCP document used by executive_mcp_entry.main."""
    def __init__(self, config_path, *, release_sha, peer_uid):
        self._path = Path(config_path)
        self._release_sha, self._peer_uid = release_sha, peer_uid
        # Admission is checked on use as well; no loaded policy cache can survive
        # a current installed document change or inaccessible/seal-broken file.
        self.policies()

    def policies(self):
        from ops.executive_os.executive_mcp_entry import (
            require_sealed_path, validate_document, build_additional_policies,
        )
        try:
            require_sealed_path(self._path)
            raw = validate_document(json.loads(self._path.read_text(encoding="utf-8")))
            if (raw["release_sha"] != self._release_sha or raw["service_uid"] != self._peer_uid
                    or raw.get("executive_mcp_profile") != "web_ceo_v3"):
                raise ValueError
            if raw.get("reply_events_armed",False) is not True:
                raise ReplyPolicyDenied("installed event receiver disarmed")
            primary = load_app_policies(raw["policies"])
            pairs = (primary, *build_additional_policies(raw, primary))
            return tuple(validate_resource_policy(p) for pair in pairs for p in (pair.read, pair.submit))
        except ReplyPolicyDenied:
            raise
        except Exception:
            raise ReplyPolicyUnavailable("current installed receiver policy unavailable") from None

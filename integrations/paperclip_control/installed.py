"""Opt-in composition inside the existing sealed Workspace installation.

The configuration contains references and explicit principal grants, not copied
credentials, replicated agent state or a new authority registry. Its loader is
supplied by the incumbent installed-configuration owner.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Callable

from integrations.business_mcp_auth.contracts import VerifiedPrincipal
from .client import PaperclipHttpClient, checked_origin
from .contract import CONFIG_SCHEMA, DIGEST, DONOR_REVISION, PaperclipError, digest, identifier


@dataclass(frozen=True)
class Access:
    subject_digest: str
    client_ref: str
    credential_env: str | None = None
    local_operator: bool = False
    create_backlog: bool = False


@dataclass(frozen=True)
class HermesBinding:
    agent_id: str
    profile_ref: str
    supervisor_session_ref: str | None
    gateway_ref: str

    def public(self) -> dict:
        return {"agentId": self.agent_id, "runtime": "hermes", "profileRef": self.profile_ref,
                "supervisorSessionRef": self.supervisor_session_ref, "gatewayRef": self.gateway_ref,
                "qualification": "CONFIGURED_NOT_LIVE_VERIFIED"}


def _ref(value: object) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,191}", value) is None:
        raise ValueError("invalid configured reference")
    return value


def validate_configuration(raw: object) -> dict:
    keys = {"schema", "origin", "company_id", "source_revision", "access", "work_owner", "wake_owner", "create_backlog_enabled", "hermes_bindings", "project_bindings"}
    if type(raw) is not dict or set(raw) != keys or raw["schema"] != CONFIG_SCHEMA:
        raise ValueError("Paperclip binding fields differ")
    origin = checked_origin(raw["origin"])
    identifier(raw["company_id"])
    if raw["source_revision"] != DONOR_REVISION:
        raise ValueError("Paperclip API revision requires explicit source qualification")
    if raw["work_owner"] not in {"legacy", "paperclip"} or raw["wake_owner"] not in {"legacy", "paperclip"}:
        raise ValueError("one management owner per domain is required")
    if type(raw["create_backlog_enabled"]) is not bool or raw["create_backlog_enabled"] and raw["work_owner"] != "paperclip":
        raise ValueError("work cutover required before Paperclip authoring")
    if type(raw["access"]) is not list or len(raw["access"]) > 64:
        raise ValueError("bounded explicit principal bindings required")
    identities = set()
    for entry in raw["access"]:
        if type(entry) is not dict or set(entry) != {"subject_digest", "client_ref", "credential_env", "local_operator", "create_backlog"}:
            raise ValueError("Paperclip principal binding differs")
        if not isinstance(entry["subject_digest"], str) or DIGEST.fullmatch(entry["subject_digest"]) is None:
            raise ValueError("qualified subject digest required")
        _ref(entry["client_ref"])
        if type(entry["local_operator"]) is not bool or type(entry["create_backlog"]) is not bool:
            raise ValueError("explicit source grants required")
        env = entry["credential_env"]
        if env is not None and (not isinstance(env, str) or re.fullmatch(r"[A-Z][A-Z0-9_]{2,95}", env) is None):
            raise ValueError("source credential must be an environment reference")
        if (env is None) != entry["local_operator"]:
            raise ValueError("select one existing credential mode")
        if entry["local_operator"] and not (origin.startswith("http://127.0.0.1:") or origin.startswith("http://[::1]:")):
            raise ValueError("local trusted access requires an explicit loopback operator")
        identity = (entry["subject_digest"], entry["client_ref"])
        if identity in identities:
            raise ValueError("ambiguous source principal")
        identities.add(identity)
    if type(raw["hermes_bindings"]) is not list or len(raw["hermes_bindings"]) > 128:
        raise ValueError("bounded Hermes references required")
    agents, profiles = set(), set()
    for entry in raw["hermes_bindings"]:
        if type(entry) is not dict or set(entry) != {"agent_id", "profile_ref", "supervisor_session_ref", "gateway_ref"}:
            raise ValueError("Hermes reference fields differ")
        agent = identifier(entry["agent_id"])
        profile = _ref(entry["profile_ref"])
        _ref(entry["gateway_ref"])
        if entry["supervisor_session_ref"] is not None:
            _ref(entry["supervisor_session_ref"])
        if agent in agents or profile in profiles:
            raise ValueError("adopt the existing bot once; duplicate agent/profile bindings refused")
        agents.add(agent)
        profiles.add(profile)
    if type(raw["project_bindings"]) is not list or len(raw["project_bindings"]) > 256:
        raise ValueError("bounded existing project references required")
    project_ids, work_refs = set(), set()
    for entry in raw["project_bindings"]:
        if type(entry) is not dict or set(entry) != {"project_id", "work_ref"}:
            raise ValueError("project reference fields differ")
        project_id = identifier(entry["project_id"])
        work_ref = entry["work_ref"]
        if not isinstance(work_ref, str) or re.fullmatch(r"WS:[A-Za-z0-9][A-Za-z0-9._-]{0,127}", work_ref) is None:
            raise ValueError("existing work reference required")
        if project_id in project_ids or work_ref in work_refs:
            raise ValueError("ambiguous project join")
        project_ids.add(project_id)
        work_refs.add(work_ref)
    return raw


@dataclass(frozen=True)
class PaperclipWorkspaceBinding:
    client: PaperclipHttpClient
    company_id: str
    source_revision: str
    revision: str
    work_owner: str
    wake_owner: str
    create_backlog_enabled: bool
    access: tuple[Access, ...]
    hermes_bindings: tuple[HermesBinding, ...]
    project_bindings: tuple[tuple[str, str], ...]
    policy_id: str
    current: Callable[[], bool] = field(repr=False, compare=False)

    def permission(self, principal: VerifiedPrincipal, *, mutate: bool = False) -> Access:
        if type(principal) is not VerifiedPrincipal or principal.policy_id != self.policy_id:
            raise PaperclipError("COMPANY_ACCESS_DENIED", status=403)
        try:
            current = self.current() is True
        except Exception:
            current = False
        if not current:
            raise PaperclipError("COMPANY_BINDING_CHANGED", status=403)
        matches = [entry for entry in self.access if entry.subject_digest == principal.subject_digest and entry.client_ref == principal.client_ref]
        if len(matches) != 1:
            raise PaperclipError("COMPANY_ACCESS_DENIED", status=403)
        selected = matches[0]
        if mutate and not (selected.create_backlog and self.create_backlog_enabled and self.work_owner == "paperclip"):
            raise PaperclipError("COMPANY_COMMAND_NOT_ENABLED", status=403)
        return selected

    def credential(self, access: Access) -> str | None:
        if access.local_operator:
            return None
        value = os.environ.get(access.credential_env or "")
        if not value:
            raise PaperclipError("SOURCE_CREDENTIAL_UNAVAILABLE")
        return value

    def scope(self, principal: VerifiedPrincipal) -> str:
        return digest({"namespace": "mastermind-paperclip-source.v1", "policy": principal.policy_id,
                       "issuer": principal.issuer_digest, "subject": principal.subject_digest,
                       "client": principal.client_ref, "company": self.company_id})


def build_installed_binding(raw: object, *, policy, load_current: Callable[[], object]) -> PaperclipWorkspaceBinding:
    selected = validate_configuration(raw)
    revision = digest(selected)
    allowed = set(policy.allowed_subject_digests)
    if any(entry["subject_digest"] not in allowed for entry in selected["access"]):
        raise ValueError("Paperclip grant exceeds the existing Workspace principal policy")
    return PaperclipWorkspaceBinding(
        client=PaperclipHttpClient(selected["origin"]), company_id=identifier(selected["company_id"]),
        source_revision=selected["source_revision"], revision=revision,
        work_owner=selected["work_owner"], wake_owner=selected["wake_owner"],
        create_backlog_enabled=selected["create_backlog_enabled"],
        access=tuple(Access(**entry) for entry in selected["access"]),
        hermes_bindings=tuple(HermesBinding(**entry) for entry in selected["hermes_bindings"]),
        project_bindings=tuple((identifier(entry["project_id"]), entry["work_ref"]) for entry in selected["project_bindings"]),
        policy_id=policy.policy_id,
        current=lambda: digest(validate_configuration(load_current())) == revision,
    )

"""Immutable profile-owner grants for the installed Browser Link backend.

These are closed owner configuration, not discovery-issued authority. The
content-addressed profile_ref pins all bindings in existing signed start refs.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

from .native_channel import LinkEnrollment, LinkProtocolError, integer, record, reference, native_host_name
from .tool_contract import LINK_TOOL_SCHEMA_DIGEST

GRANT_SCHEMA = "mastermind.browser_link.profile_grant.v2"
PROFILES_SCHEMA = "mastermind.browser_link.profiles.v2"


@dataclass(frozen=True)
class LinkProfileGrant:
    profile_ref: str
    owner_ref: str
    operation_ref: str
    generation: str
    host_id: str
    boot_session_id: str
    expires_at_ms: int
    store_device: int
    store_inode: int
    exclusive: bool
    enrollment: LinkEnrollment
    chrome_pid: int
    chrome_start_identity: str

    def _material(self):
        return {"schema": GRANT_SCHEMA, "backend_schema_digest": LINK_TOOL_SCHEMA_DIGEST,
                "owner_ref": self.owner_ref, "operation_ref": self.operation_ref,
                "generation": self.generation, "host_id": self.host_id,
                "boot_session_id": self.boot_session_id, "expires_at_ms": self.expires_at_ms,
                "store_device": self.store_device, "store_inode": self.store_inode,
                "exclusive": self.exclusive, "enrollment": self.enrollment.document(),
                "chrome_pid": self.chrome_pid, "chrome_start_identity": self.chrome_start_identity}

    @staticmethod
    def _address(material):
        raw = json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                         allow_nan=False).encode("utf-8")
        return "link-" + hashlib.sha256(raw).hexdigest()

    def __post_init__(self):
        for value in (self.owner_ref, self.operation_ref, self.generation, self.host_id, self.boot_session_id):
            reference(value)
        integer(self.expires_at_ms)
        if any(type(value) is not int or not 0 <= value < 2**63 for value in (self.store_device, self.store_inode)):
            raise LinkProtocolError("LINK_PROFILE_STORE_INVALID")
        if (self.exclusive is not True or type(self.enrollment) is not LinkEnrollment
                or type(self.chrome_pid) is not int or self.chrome_pid <= 1
                or type(self.chrome_start_identity) is not str or not self.chrome_start_identity
                or len(self.chrome_start_identity) > 128):
            raise LinkProtocolError("LINK_PROFILE_GRANT_INVALID")
        self.enrollment.__post_init__()
        if self.profile_ref != self._address(self._material()):
            raise LinkProtocolError("LINK_PROFILE_GRANT_CHANGED")

    def document(self):
        return {**self._material(), "profile_ref": self.profile_ref}

    @classmethod
    def create(cls, **fields):
        material = {"schema": GRANT_SCHEMA, "backend_schema_digest": LINK_TOOL_SCHEMA_DIGEST,
                    **fields, "enrollment": fields["enrollment"].document()}
        return cls(profile_ref=cls._address(material), **fields)

    @classmethod
    def from_document(cls, value: Any):
        fields = {"profile_ref", "owner_ref", "operation_ref", "generation", "host_id",
                  "boot_session_id", "expires_at_ms", "store_device", "store_inode", "exclusive", "enrollment",
                  "chrome_pid", "chrome_start_identity"}
        record(value, fields | {"schema", "backend_schema_digest"})
        if value["schema"] != GRANT_SCHEMA or value["backend_schema_digest"] != LINK_TOOL_SCHEMA_DIGEST:
            raise LinkProtocolError("LINK_PROFILE_GRANT_INVALID")
        args = {key: value[key] for key in fields}
        args["enrollment"] = LinkEnrollment.from_document(args["enrollment"])
        return cls(**args)


def parse_profile_grants(value, *, lease, host_binding, artifact_store):
    record(value, {"schema", "profiles"})
    rows = value["profiles"]
    if value["schema"] != PROFILES_SCHEMA or type(rows) is not list or not 1 <= len(rows) <= 64:
        raise LinkProtocolError("LINK_PROFILE_CONFIGURATION_INVALID")
    grants = tuple(LinkProfileGrant.from_document(row) for row in rows)
    seen = {key: set() for key in ("profile", "instance", "host", "socket")}
    for grant in grants:
        if (grant.owner_ref != lease.owner_ref or grant.operation_ref != lease.operation_ref
                or grant.generation != lease.generation or grant.host_id != host_binding.host_id
                or grant.boot_session_id != host_binding.boot_session_id
                or grant.expires_at_ms != lease.lease_expires_at_ms
                or grant.store_device != artifact_store.device or grant.store_inode != artifact_store.inode):
            raise LinkProtocolError("LINK_PROFILE_OWNER_MISMATCH")
        keys = {"profile": grant.profile_ref, "instance": grant.enrollment.instance_id,
                "host": native_host_name(grant.enrollment.instance_id),
                "socket": str(grant.enrollment.socket_path)}
        for kind, key in keys.items():
            if key in seen[kind]:
                raise LinkProtocolError("LINK_PROFILE_ROUTE_CONFLICT")
            seen[kind].add(key)
    # Frozen grants, captured once. Offline Chrome is refused at resource use,
    # not allowed to take down other configured profiles at service startup.
    return {grant.profile_ref: grant for grant in grants}


def historical_profile_document(value):
    """Validate an immutable historical grant without making it current authority.

    A backend upgrade changes the content address. Recovery still needs to
    identify the old physical endpoint, but may never activate an old grant.
    """
    if type(value) is not dict:
        raise LinkProtocolError("LINK_PROFILE_HISTORY_INVALID")
    digest = value.get("backend_schema_digest")
    if (type(digest) is not str or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)):
        raise LinkProtocolError("LINK_PROFILE_HISTORY_INVALID")
    material = {key: item for key, item in value.items() if key != "profile_ref"}
    if value.get("profile_ref") != LinkProfileGrant._address(material):
        raise LinkProtocolError("LINK_PROFILE_HISTORY_CHANGED")
    # Reuse the current closed grammar and value validation with a derived
    # current address, then return only a detached history document.
    current = {**material, "backend_schema_digest": LINK_TOOL_SCHEMA_DIGEST}
    current["profile_ref"] = LinkProfileGrant._address(current)
    LinkProfileGrant.from_document(current)
    return json.loads(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                 ensure_ascii=False, allow_nan=False))

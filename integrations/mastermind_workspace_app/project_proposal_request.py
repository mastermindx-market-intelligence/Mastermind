"""Goal-to-proposal composition over an explicitly authored server profile.

This does not publish, create a programme, grant a writer or admit Runtime work.
The candidate key is draft identity until a real canonical source receipt exists.
The actual Macro compiler retains schema and programme validation authority.
"""
from __future__ import annotations
import copy
import hashlib
import re

from common.executive_workspace_contract import canonical
from integrations.mastermind_workspace_app.source_operation_principal import source_principal_frame

REQUEST_SCHEMA = "mastermind.project_proposal_request.v1"
_PROFILE_KEYS = {"title", "program", "repos", "owner", "class", "blast_radius", "ambiguity", "waves", "next_action"}
_REQUEST_KEYS = {"schema", "request_id", "goal", "expected_macro_sha", "profile_sha256"}


def profile_digest(profile):
    """A source revision for explicit authored metadata, never a permission."""
    if type(profile) is not dict or set(profile) != _PROFILE_KEYS:
        raise ValueError("invalid_profile")
    try:
        raw = canonical(profile)
        if len(raw) > 12288:
            raise ValueError("invalid_profile")
        return hashlib.sha256(raw).hexdigest()
    except (TypeError, OverflowError, RecursionError):
        raise ValueError("invalid_profile") from None


def creation_work_ref(request_id, *, principal):
    """Same original CREATE address, derived only from the verified owner.

    A lost prepare response need not invent or persist the not-yet-returned
    workstream key. This is an address calculation, not source existence,
    publication, membership or a permission. The calling read owner must still
    qualify its current action grant and return only actual original Events.
    """
    if (type(request_id) is not str
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", request_id) is None):
        raise ValueError("invalid_input")
    identity = source_principal_frame(principal)
    candidate = hashlib.sha256(canonical({"principal": identity, "request_id": request_id})).hexdigest()
    return "WS:PROJECT-" + candidate[:32].upper()


def build_proposal_request(request, *, principal, authored_profile):
    """Build the actual canonical compiler's input without inferring ownership.

    The HTTP owner supplies a VerifiedPrincipal and its selected private profile.
    Expected source/profile revisions are retained in the original command before
    any effect. Changed source or goal must not replace an unknown operation.
    """
    if (type(request) is not dict or set(request) != _REQUEST_KEYS or request["schema"] != REQUEST_SCHEMA
            or type(request["request_id"]) is not str
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", request["request_id"]) is None
            or type(request["goal"]) is not str or not request["goal"].strip()
            or len(request["goal"].encode("utf-8")) > 4000
            or type(request["expected_macro_sha"]) is not str
            or re.fullmatch(r"[0-9a-f]{40}", request["expected_macro_sha"]) is None):
        raise ValueError("invalid_input")
    profile = copy.deepcopy(authored_profile)
    if request["profile_sha256"] != profile_digest(profile):
        raise ValueError("source_changed")
    # The existing auth owner extracts actual stable identity, not an email,
    # display label, token, client assertion or permission receipt generation.
    work_ref = creation_work_ref(request["request_id"], principal=principal)
    record = {"key": work_ref[3:], "objective": request["goal"], "status": "proposed", **profile}
    value = {"schema": "agentos.project_proposal_request.v1", "request_id": request["request_id"],
             "expected_commit": request["expected_macro_sha"], "record": record}
    if len(canonical(value)) > 16384:
        raise ValueError("invalid_input")
    return value

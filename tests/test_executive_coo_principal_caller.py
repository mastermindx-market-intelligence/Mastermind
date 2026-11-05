"""Current COO facts from real signed JWTs; no installed or send authority."""
from __future__ import annotations

import asyncio
import copy
import dataclasses
import sys
from pathlib import Path

import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse

sys.path.insert(0, str(Path(__file__).parent))
try:
    import test_executive_coo_app as fixture
finally:
    sys.path.pop(0)

from integrations.executive_mcp.coo import COO_TOOL_NAMES
from integrations.mastermind_executive_app.coo import create_coo_app
from integrations.mastermind_executive_app.coo_binding import COO_SCOPES
from integrations.slack_agent_dialogue.company_dialogue_runtime_binding import CooPrincipalDialogueCaller

rsa_key = fixture.rsa_key


def setup(rsa_key, tmp_path):
    app, token, current, settings = fixture.setup(rsa_key, tmp_path)
    current["authority"] = dataclasses.replace(current["authority"],
        principal_actions=("bounded_intent", "governed_orchestration"))
    current["mission"] = copy.deepcopy(current["mission"])
    return app, token, current, settings


def request(token):
    return Request({"type": "http", "method": "POST", "path": "/v1/tools/executive_mandate",
        "raw_path": b"/v1/tools/executive_mandate", "query_string": b"",
        "headers": [(b"authorization", ("Bearer " + token).encode())]})


def call(app, token, **kwargs):
    return asyncio.run(app.resolve_principal_dialogue_caller(request(token),
        work_ref=kwargs.get("work_ref", "WS:ONE"),
        reasoning_surface=kwargs.get("reasoning_surface", "coo-qualified-host")))


def refused(result):
    assert isinstance(result, JSONResponse)
    assert result.status_code in (401, 403)
    assert b"PRIVATE_CANARY" not in result.body
    assert b"/private/" not in result.body


def test_real_signed_principal_produces_exact_current_mission_facts(rsa_key, tmp_path):
    app, token, current, _ = setup(rsa_key, tmp_path)
    result = call(app, token)
    assert type(result) is CooPrincipalDialogueCaller
    assert result.admission_context.work_ref == "WS:ONE"
    assert result.root_job_id == current["mission"]["mission"]["root_job_id"]
    assert result.capability_profile_digest == current["authority"].capability_profile_digest
    assert result.accountable_seat == result.owed_seat == "coo"
    assert result.admission_context.authority_generation_digest == current["authority"].authority_generation_digest


@pytest.mark.parametrize("fault", ["scope", "subject", "client", "expired", "signature"])
def test_other_or_invalid_principal_cannot_borrow_an_enabled_mission(rsa_key, tmp_path, fault):
    app, token, _, _ = setup(rsa_key, tmp_path)
    changes = {"scope": {"scope": "mastermind.executive.read"},
        "subject": {"sub": "another-subject"}, "client": {"client_id": "another-client"},
        "expired": {"iat": fixture.fixture.NOW - 600, "nbf": fixture.fixture.NOW - 600,
                    "exp": fixture.fixture.NOW - 60}}
    if fault == "signature":
        parts = token.split("."); parts[2] = ("A" if parts[2][0] != "A" else "B") + parts[2][1:]
        token = ".".join(parts)
    else:
        token = fixture.fixture._token(rsa_key, **{"scope": " ".join(COO_SCOPES), **changes[fault]})
    refused(call(app, token))


@pytest.mark.parametrize("fault", ["grant", "mission", "owed", "accountable", "noncurrent", "surface"])
def test_source_or_scope_cannot_create_a_principal_caller(rsa_key, tmp_path, fault):
    app, token, current, _ = setup(rsa_key, tmp_path)
    kwargs = {}
    if fault == "grant":
        current["authority"] = dataclasses.replace(current["authority"], principal_actions=("bounded_intent",))
    elif fault == "mission": kwargs["work_ref"] = "WS:OTHER"
    elif fault == "owed": current["mission"]["principal"]["owed_turn"]["seat"] = "worker"
    elif fault == "accountable": current["mission"]["principal"]["accountable_seat"] = "ceo"
    elif fault == "noncurrent": current["mission"]["read_state"]["state"] = "HISTORICAL"
    else: kwargs["reasoning_surface"] = "../caller-supplied"
    refused(call(app, token, **kwargs))


@pytest.mark.parametrize("fault", ["revoke", "generation", "capability", "root", "seat", "exception"])
def test_change_during_owner_read_is_closed(rsa_key, tmp_path, fault):
    _, token, current, settings = setup(rsa_key, tmp_path)
    reads = []
    def mission(principal, work_ref):
        before = copy.deepcopy(current["mission"])
        reads.append(work_ref)
        if len(reads) == 1:
            if fault == "revoke": current["binding"]["enabled"] = False
            elif fault == "generation": current["authority"] = dataclasses.replace(current["authority"], authority_generation_digest="e" * 64)
            elif fault == "capability": current["authority"] = dataclasses.replace(current["authority"], capability_profile_digest="e" * 64)
            elif fault == "root": current["mission"]["mission"]["root_job_id"] = "JOB-999"
            elif fault == "seat": current["mission"]["principal"]["owed_turn"]["seat"] = "chairman"
            else: raise RuntimeError("PRIVATE_CANARY /private/credentials")
        return before
    app = create_coo_app(dataclasses.replace(settings, mission_provider=mission), audit_sink=fixture.Sink())
    refused(call(app, token))


def test_new_helper_does_not_expand_the_six_tool_surface():
    assert COO_TOOL_NAMES == ("executive_mandate", "executive_state", "executive_inbox",
        "executive_fabric", "submit_principal_intent", "principal_intent_status")


def test_token_expiring_during_owner_read_cannot_return_caller_facts(rsa_key, tmp_path):
    _, token, current, settings = setup(rsa_key, tmp_path)
    now = [fixture.fixture.NOW]
    def mission(principal, work_ref):
        now[0] += 3600
        return current["mission"]
    settings = dataclasses.replace(settings,
        executive=dataclasses.replace(settings.executive, clock=lambda: now[0]),
        mission_provider=mission)
    app = create_coo_app(settings, audit_sink=fixture.Sink())
    refused(call(app, token))


def test_internal_helper_is_not_an_http_tool_even_for_a_valid_principal(rsa_key, tmp_path):
    app, token, _, _ = setup(rsa_key, tmp_path)
    result = asyncio.run(fixture.request(app, token, "resolve_principal_dialogue_caller",
                                        {"work_ref": "WS:ONE"}))
    assert result.status_code == 404

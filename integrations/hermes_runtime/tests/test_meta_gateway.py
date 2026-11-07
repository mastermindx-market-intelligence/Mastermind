"""Role startup and secret isolation; no installed service/provider claim."""
import pytest

from integrations.hermes_runtime import secrets as secret_owner
from integrations.hermes_runtime import supervisor
from integrations.hermes_runtime.constants import conversation_contract
from integrations.hermes_runtime.errors import RuntimeRefusal
from integrations.hermes_runtime.secrets import (
    Secrets, child_env, register_child_secret_env, role_conversation_token,
)
from integrations.hermes_runtime.tests.test_secretary_gateway import (
    CONVERSATION, HEALTH, selected_runtime, wrapper,
)

ROLES = ("mmsecretary", "mmmeta")


@pytest.mark.parametrize("role", ROLES)
def test_both_conversation_credentials_are_reserved_and_never_forwarded(monkeypatch, tmp_path, role):
    selected = conversation_contract(role)
    sibling = conversation_contract("mmmeta" if role == "mmsecretary" else "mmsecretary")
    secrets = Secrets(HEALTH, "hermes", "dashboard-fixture-value", {
        selected.token_env: CONVERSATION, "PROVIDER_KEY": "provider-fixture-value",
    })
    assert role_conversation_token(secrets, role=role) == CONVERSATION
    for token_env in (selected.token_env, sibling.token_env):
        with pytest.raises(RuntimeRefusal, match="STAYS_ON_THE_FRONT_DOOR"):
            register_child_secret_env([token_env])
    # Even a late erroneous registration cannot make these credentials child input.
    monkeypatch.setattr(secret_owner, "_CHILD_SECRET_ENV", {selected.token_env, sibling.token_env})
    both = Secrets(HEALTH, "hermes", "dashboard-fixture-value", {
        selected.token_env: CONVERSATION, sibling.token_env: "sibling-role-fixture-token",
    })
    forwarded = child_env(both, home=tmp_path)
    assert not {selected.token_env, sibling.token_env}.intersection(forwarded)
    assert CONVERSATION not in forwarded.values()
    assert "sibling-role-fixture-token" not in forwarded.values()


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("source", ["health", "dashboard", "provider", "overlong"])
def test_selected_role_credential_cannot_alias_other_authority(role, source):
    selected = conversation_contract(role)
    values = {"PROVIDER_KEY": "provider-fixture-value"}
    token = {"health": HEALTH, "dashboard": "dashboard-fixture-value",
             "provider": values["PROVIDER_KEY"], "overlong": "x" * 257}[source]
    values[selected.token_env] = token
    with pytest.raises(RuntimeRefusal, match="CREDENTIAL_ALIAS_REFUSED"):
        role_conversation_token(Secrets(HEALTH, "hermes", "dashboard-fixture-value", values),
                                role=role)


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("also_selected", [False, True])
def test_foreign_role_credential_refuses_before_registry_or_child(monkeypatch, tmp_path, role, also_selected):
    runtime = selected_runtime(tmp_path, role=role)
    selected = conversation_contract(role)
    sibling = conversation_contract("mmmeta" if role == "mmsecretary" else "mmsecretary")
    values = {sibling.token_env: "sibling-role-fixture-token"}
    if also_selected:
        values[selected.token_env] = CONVERSATION
    runtime.secrets = Secrets(HEALTH, "hermes", "dashboard-fixture-value", values)
    monkeypatch.setattr(runtime, "_check_registry", lambda: pytest.fail("registry entered after credential refusal"))
    with pytest.raises(RuntimeRefusal, match="CONVERSATION_ROLE_UNQUALIFIED"):
        runtime.start()
    assert runtime.gateway is None and runtime.child_starts == 0


@pytest.mark.parametrize("role", ROLES)
def test_supervisor_start_selects_explicit_role_capability(monkeypatch, tmp_path, role):
    runtime = selected_runtime(tmp_path, role=role)
    observed = []
    class Gateway:
        def __init__(self, host, port, token, snapshot, **options):
            observed.append((host, port, token, options))
    monkeypatch.setattr(supervisor, "Gateway", Gateway)
    # Isolate startup wiring from the separately covered native preflight/loop.
    monkeypatch.setattr(runtime, "_model_child_env", lambda: {})
    monkeypatch.setattr(runtime, "_check_registry", lambda: None)
    monkeypatch.setattr(runtime, "_loop_guarded", lambda: None)
    runtime.start()
    runtime._thread.join(timeout=2)
    assert not runtime._thread.is_alive()
    assert len(observed) == 1
    host, port, token, options = observed[0]
    assert (host, port, token) == (runtime.profile.gateway_host, runtime.profile.gateway_port, HEALTH)
    assert options == {"role": role, "conversation_token": CONVERSATION,
                       "conversation_handler": runtime._native_conversation}


@pytest.mark.parametrize("role", ROLES)
def test_early_unavailable_reply_retains_selected_role_schema(tmp_path, role):
    runtime = selected_runtime(tmp_path, role=role)
    runtime._backend_ready = False
    contract = conversation_contract(role)
    reply = runtime._native_conversation(wrapper({"operation": "submit"}, role=role))
    assert reply["schema"] == contract.response_schema
    assert reply["result"] == {"schema": contract.native_schema, "status": "UNAVAILABLE"}

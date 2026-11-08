"""Plan selection/account/one-send proof through the actual native bridge."""
from __future__ import annotations

import copy
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from types import SimpleNamespace
import threading
import time

import pytest

from control_plane.experiential_plan_policy import (
    FREE_CHAT_MODELS, FREE_NATIVE_MODELS, PAID_UNCENSORED_MODELS, PLAN_ACCOUNT_PREFIX,
    PLAN_ACCOUNT_SCHEMA, PLAN_OBSERVATION_SCHEMA, PlanRequestRefused,
    admit_plan_account, plan_policy_digest, select_plan_model,
)
from ops.native_fabric.experiential53 import experiential_host_context as owner
from ops.native_fabric.experiential53 import experiential_transport as transport
from ops.native_fabric.experiential_native_bridge import experiential_bridge as bridge


def facts(port=8311, mode="free_and_uncensored", balance=37.0):
    organization = "fixture-organization"
    digest = hashlib.sha256(organization.encode()).hexdigest()
    account = PLAN_ACCOUNT_PREFIX + digest
    registration = {
        "schema": PLAN_ACCOUNT_SCHEMA, "account": account,
        "organization_sha256": digest, "plan_policy": mode,
        "policy_digest": plan_policy_digest(mode),
        "free_credits_per_day": 7000, "paid_allowance_usd_per_month": 200,
        "entitlement_source": "chairman_declared_plan", "funding": "provider_prepaid_wallet",
    }
    provider = {"enabled": True, "accounts": [
        {"name": account, "enabled": True, "per_account_cap": 1, "plan": registration}
    ], "plan_gateway": {"account": account, "host": "127.0.0.1", "port": port,
                         "route_host": "fixture-host", "route_id": "fixture-plan"}}
    replies = {
        "/statusz": {"plan_policy": mode, "plan_policy_digest": plan_policy_digest(mode),
                     "account_metadata_enabled": True},
        "/api/whoami": {"org_id": organization},
        "/api/v1/credits": {"data": {"total_credits": 46, "total_usage": 46 - balance}},
        "/v1/models": {"data": [{"id": model} for model in FREE_CHAT_MODELS + tuple(FREE_NATIVE_MODELS) + PAID_UNCENSORED_MODELS]},
    }
    context = owner._observed_context(provider, read=replies.__getitem__, token="fixture-proxy-token-32-characters",
                                      base=f"http://127.0.0.1:{port}")
    # Fixture-only positive account evidence exercises admission/transport.
    # The real metadata owner returns None, covered separately below.
    context["quota_readback"]["included_funding"] = {
        "schema": "mastermind.experiential_included_funding/v1",
        "source": "authenticated_provider_account",
        "organization_sha256": digest, "plan_tier": "max",
        "plan_active": True, "daily_credits": 7000,
        "continue_on_credits": False, "provider_enforces_included_stop": True,
        "paid_uncensored_remains_available": True,
        "observed_at_unix": time.time(),
        "included_models": list(FREE_CHAT_MODELS) + list(FREE_NATIVE_MODELS),
    }
    return provider, replies, context


def admit(context, model=PAID_UNCENSORED_MODELS[0]):
    return admit_plan_account(model=model, account=context["account"],
                              registration=context["registry_entry"]["plan"],
                              observation=context["quota_readback"])


def test_fresh_paid_selection_prefers_deepseek_and_preserves_explicit_glm():
    assert select_plan_model("paid_uncensored", PAID_UNCENSORED_MODELS) == PAID_UNCENSORED_MODELS[0]
    assert select_plan_model("paid_uncensored", [PAID_UNCENSORED_MODELS[1]]) == PAID_UNCENSORED_MODELS[1]
    assert select_plan_model("paid_uncensored", PAID_UNCENSORED_MODELS, PAID_UNCENSORED_MODELS[1]) == PAID_UNCENSORED_MODELS[1]
    with pytest.raises(PlanRequestRefused, match="SELECTED_MODEL_UNAVAILABLE"):
        select_plan_model("paid_uncensored", [PAID_UNCENSORED_MODELS[1]], PAID_UNCENSORED_MODELS[0])


def test_configured_allowance_is_not_fabricated_remaining_capacity():
    _, _, context = facts()
    result = admit(context)
    assert result["wallet_balance_usd_observed"] == 37
    assert result["monthly_allowance_remaining_usd"] is None
    assert result["free_credits_remaining"] is None
    assert result["quota_owner"] == "provider"


@pytest.mark.parametrize("field,value,reason", [
    ("account", "account-a", "OBSERVATION_MISMATCH"),
    ("organization_sha256", "0" * 64, "OBSERVATION_MISMATCH"),
    ("policy_digest", "0" * 64, "OBSERVATION_MISMATCH"),
    ("observed_at_unix", 1, "OBSERVATION_STALE"),
    ("observed_at_unix", True, "OBSERVATION_STALE"),
    ("wallet_balance_usd", True, "OBSERVATION_INVALID"),
    ("wallet_balance_usd", float("nan"), "OBSERVATION_INVALID"),
])
def test_untrusted_or_stale_account_observation_cannot_admit(field, value, reason):
    _, _, context = facts()
    context["quota_readback"][field] = value
    with pytest.raises(PlanRequestRefused, match=reason):
        admit(context)


def test_free_lane_can_use_zero_wallet_and_cannot_spill_to_paid():
    _, _, context = facts(mode="free_only", balance=0)
    assert admit(context, FREE_CHAT_MODELS[0])["plan_lane"] == "free"
    with pytest.raises(PlanRequestRefused, match="PAID_LANE_DISABLED"):
        admit(context)
    _, _, context = facts(balance=0)
    with pytest.raises(PlanRequestRefused, match="WALLET_EXHAUSTED"):
        admit(context)


def test_account_owner_refuses_other_org_or_policy_before_admission():
    provider, replies, _ = facts()
    replies["/api/whoami"]["org_id"] = "other-organization"
    with pytest.raises(owner.HostContextRefused, match="ORGANIZATION_MISMATCH"):
        owner._observed_context(provider, read=replies.__getitem__, token="fixture-proxy-token-32-characters", base="http://127.0.0.1:8311")
    replies["/statusz"]["plan_policy"] = "legacy"
    with pytest.raises(owner.HostContextRefused, match="POLICY_MISMATCH"):
        owner._observed_context(provider, read=replies.__getitem__, token="fixture-proxy-token-32-characters", base="http://127.0.0.1:8311")


def native_packet(model):
    if model == "jev-latest":
        return {"state": "The list contains apple and pear.", "questions": {
            "present": {"type": "noul", "instructions": "The list contains apple."},
            "fruit": {"type": "choice", "instructions": "Which named fruit is present?",
                      "criteria": {"apple": "apple", "orange": "orange"}},
            "count": {"type": "score", "instructions": "Rate fruit variety.",
                      "criteria": ["one fruit", "two fruits", "three fruits"]}}}
    return {"input": "The list contains apple and pear.", "questions": [
        {"name": "present", "type": "predicate", "instructions": "The list contains apple."},
        {"name": "fruit", "type": "choice", "instructions": "Which named fruit is present?",
         "choices": [{"value": "apple", "description": "apple"}, {"value": "orange", "description": "orange"}]},
        {"name": "count", "type": "score", "instructions": "Rate fruit variety.",
         "levels": [{"label": "one", "description": "one fruit"}, {"label": "two", "description": "two fruits"},
                    {"label": "three", "description": "three fruits"}]}]}


def native_answer(model):
    if model == "jev-latest":
        return {"present": {"type": "noul", "noul": 0.99},
                "fruit": {"type": "choice", "choice": "apple", "confidence": 0.98},
                "count": {"type": "score", "score": 1, "confidence": 0.98}}
    return [{"name": "present", "type": "predicate", "probability": 0.99},
            {"name": "fruit", "type": "choice", "choice": "apple", "confidence": 0.98},
            {"name": "count", "type": "score", "score": 1, "confidence": 0.98}]


@pytest.fixture
def local_gateway():
    requests = []
    response_status = [200]

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append((body, {**dict(self.headers), "_request_path": self.path}))
            if body["model"] in FREE_NATIVE_MODELS:
                assert self.path == "/v1/" + FREE_NATIVE_MODELS[body["model"]]
                answer = native_answer(body["model"])
                payload = json.dumps({"model": body["model"],
                    "answers": answer, "usage": {"input_tokens": 12, "cost": 0}}).encode()
            else:
                assert self.path == "/v1/chat/completions"
                payload = json.dumps({"model": body["model"], "choices": [
                    {"message": {"role": "assistant", "content": "native plan proof"}, "finish_reason": "stop"}
                ], "usage": {"prompt_tokens": 8, "completion_tokens": 4}}).encode()
            self.send_response(response_status[0])
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("X-Request-Id", "fixture-provider-request")
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=.01), daemon=True)
    thread.start()
    yield server.server_port, requests, response_status
    server.shutdown()
    server.server_close()
    thread.join(2)


def run_bridge(tmp_path, monkeypatch, port, model):
    _, _, context = facts(port=port)
    adapter = bridge.HostAdapter(transport.pin, transport,
        SimpleNamespace(host_owned_context=lambda: copy.deepcopy(context)), tmp_path)
    monkeypatch.setattr(bridge, "resolve_host_adapter", lambda *_: adapter)
    prompt = tmp_path / "prompt.txt"
    prompt.write_text(json.dumps(native_packet(model)) if model in FREE_NATIVE_MODELS
                      else "Return the fixed proof phrase.")
    args = dict(run_id="native-plan-" + str(time.time_ns()), task_class="mechanical", model=model,
                packet_root=str(tmp_path), prompt_file=str(prompt), root="fixture-root",
                strict_manual_pin=True, retention_acknowledged=True, sensitive_data_opt_in=True,
                proprietary_code=False, code_exposure_opt_in=False)
    # Execute against the real incumbent read-only lease validator and original
    # exclusive request reservation, while replacing only the remote provider.
    import sqlite3
    import sys
    candidate = Path(__file__).resolve().parents[1] / "ops/native_fabric/quota_continuity/candidate"
    monkeypatch.syspath_prepend(str(candidate))
    import native_plan_worker
    runtime = tmp_path / "ext"
    state = runtime / "state" / "remote_sub"
    state.mkdir(parents=True)
    monkeypatch.setattr(native_plan_worker, "HERE", runtime)
    db = tmp_path / "leases.sqlite"
    now = time.time()
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE leases (id TEXT, account TEXT, pool TEXT, model TEXT, orchestrator_id TEXT, state TEXT, last_heartbeat REAL, ttl INT, granted_at REAL, renewable INT, purpose TEXT)")
        conn.execute("INSERT INTO leases VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     ("fixture-lease", context["account"], "experiential", model,
                      "fixture-root", "held", now, 300, now, 1, "WORKER"))
    monkeypatch.setitem(sys.modules, "lease_broker", SimpleNamespace(DEFAULT_DB=str(db)))
    for name, value in {"POOL_LEASE_ID": "fixture-lease", "POOL_ACCOUNT": context["account"],
                        "POOL_RUN_ID": args["run_id"], "POOL_ORCHESTRATOR_ID": "fixture-root",
                        "POOL_TASK_CLASS": "mechanical"}.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("LANE_LEASED", raising=False)
    packet = prompt.read_bytes()
    request = {"schema": "mastermind.fabric_request_artifact.v1", "run_id": args["run_id"],
               "root_id": "fixture-root", "task_class": "mechanical", "cwd": str(tmp_path),
               "parent_run_id": None, "packet_sha256": hashlib.sha256(packet).hexdigest()}
    raw = json.dumps(request).encode()
    (state / (args["run_id"] + ".request.json")).write_bytes(raw)
    (state / (args["run_id"] + ".request.packet")).write_bytes(packet)
    (state / (args["run_id"] + ".request-launch.json")).write_text(json.dumps({
        "schema": "mastermind.fabric_request_launch.v1", "run_id": args["run_id"],
        "root_id": "fixture-root", "parent_run_id": None, "state": "LAUNCH_ATTEMPT_RESERVED",
        "request_sha256": hashlib.sha256(raw).hexdigest(), "packet_sha256": hashlib.sha256(packet).hexdigest(),
        "route": {"POOL": "experiential", "MODEL": model}}))
    return args, context


@pytest.mark.parametrize("model", FREE_CHAT_MODELS + PAID_UNCENSORED_MODELS)
def test_actual_bridge_to_transport_preserves_selected_model_and_policy(tmp_path, monkeypatch, local_gateway, model):
    port, requests, _ = local_gateway
    args, context = run_bridge(tmp_path, monkeypatch, port, model)
    outcome = bridge.exec_command(**args)
    assert outcome["state"] == "EXECUTED"
    assert outcome["model"] == model
    assert outcome["outcome"]["model_echo"] == model
    assert outcome["outcome"]["plan_lane"] == ("free" if model in FREE_CHAT_MODELS else "paid_uncensored")
    assert len(requests) == 1
    frame, headers = requests[0]
    assert frame["model"] == model
    assert frame["max_tokens"] == 512
    assert frame["gateway"]["retry"]["max_total_attempts"] == 1
    assert {k.lower(): v for k, v in headers.items()}["x-fabric-plan-policy"] == context["quota_readback"]["policy_digest"]
    with pytest.raises(bridge.ExperientialBridgeRefused, match="DUPLICATE_LAUNCH"):
        bridge.exec_command(**args)
    assert len(requests) == 1


def test_429_keeps_original_binding_and_never_selects_second_paid_model(tmp_path, monkeypatch, local_gateway):
    port, requests, status = local_gateway
    status[0] = 429
    args, _ = run_bridge(tmp_path, monkeypatch, port, PAID_UNCENSORED_MODELS[0])
    with pytest.raises(bridge.ExperientialBridgeRefused):
        bridge.exec_command(**args)
    with pytest.raises(bridge.ExperientialBridgeRefused, match="DUPLICATE_LAUNCH"):
        bridge.exec_command(**args)
    assert len(requests) == 1
    assert requests[0][0]["model"] == PAID_UNCENSORED_MODELS[0]


def test_new_process_cannot_repeat_original_send(tmp_path, monkeypatch, local_gateway):
    port, requests, _ = local_gateway
    args, _ = run_bridge(tmp_path, monkeypatch, port, FREE_CHAT_MODELS[0])
    bridge.exec_command(**args)
    bridge._LAUNCH_BOUND.clear()
    with pytest.raises(bridge.ExperientialBridgeRefused, match="SEND_RESERVATION_REFUSED"):
        bridge.exec_command(**args)
    assert len(requests) == 1


def test_selected_lease_account_and_local_custody_required_before_send(tmp_path, monkeypatch, local_gateway):
    port, requests, _ = local_gateway
    args, _ = run_bridge(tmp_path, monkeypatch, port, FREE_CHAT_MODELS[0])
    monkeypatch.setenv("POOL_ACCOUNT", "other-account")
    with pytest.raises(bridge.ExperientialBridgeRefused, match="LEASE_OR_SEND_RESERVATION_REFUSED"):
        bridge.exec_command(**args)
    monkeypatch.setenv("LANE_LEASED", "1")
    with pytest.raises(bridge.ExperientialBridgeRefused, match="ORIGINAL_IDENTITY_MISMATCH"):
        bridge.exec_command(**args)
    assert requests == []


def test_plain_catalog_ids_do_not_authorize_max_funding():
    provider, replies, _ = facts()
    replies["/v1/models"]["data"] = [
        {"id": model} for model in FREE_CHAT_MODELS + PAID_UNCENSORED_MODELS]
    context = owner._observed_context(provider, read=replies.__getitem__,
        token="fixture-proxy-token-32-characters", base="http://127.0.0.1:8311")
    assert context["quota_readback"]["available_models"] == sorted(FREE_CHAT_MODELS + PAID_UNCENSORED_MODELS)
    assert context["quota_readback"]["included_funding"] is None
    with pytest.raises(PlanRequestRefused, match="INCLUDED_FUNDING_UNVERIFIED"):
        admit(context, FREE_CHAT_MODELS[0])
    assert admit(context)["plan_lane"] == "paid_uncensored"
    frame = {"model": "deepseek-v4.1-flash", "choices": [
        {"message": {"content": "proof"}}], "usage": {}}
    assert transport._parse_completion(json.dumps(frame).encode(), "application/json",
                                       FREE_CHAT_MODELS[0])[1] == "deepseek-v4.1-flash"
    frame["model"] = PAID_UNCENSORED_MODELS[0]
    with pytest.raises(transport.ExperientialTransportRefused, match="MODEL_MISMATCH"):
        transport._parse_completion(json.dumps(frame).encode(), "application/json", FREE_CHAT_MODELS[0])


@pytest.mark.parametrize("model", tuple(FREE_NATIVE_MODELS))
def test_native_free_protocol_uses_original_bridge_lease_and_result(tmp_path, monkeypatch, local_gateway, model):
    port, requests, _ = local_gateway
    args, context = run_bridge(tmp_path, monkeypatch, port, model)
    outcome = bridge.exec_command(**args)
    assert outcome["state"] == "EXECUTED" and outcome["model"] == model
    detail = outcome["outcome"]
    assert detail["request_endpoint"] == FREE_NATIVE_MODELS[model]
    assert detail["plan_lane"] == "free" and detail["max_output_tokens"] is None
    assert detail["idempotency_key"] == ""
    assert json.loads(detail["content"])["answers"] == native_answer(model)
    assert detail["cost_usd_observed"] == 0 and detail["cost_settled"] is False
    assert len(requests) == 1
    body, headers = requests[0]
    assert body["model"] == model and body["questions"] == native_packet(model)["questions"]
    assert headers["_request_path"] == "/v1/" + FREE_NATIVE_MODELS[model]
    assert not {"messages", "stream", "max_tokens", "max_output_tokens"}.intersection(body)
    assert "idempotency-key" not in {key.lower() for key in headers}
    assert body["gateway"]["retry"]["max_total_attempts"] == 1
    bridge._LAUNCH_BOUND.clear()
    with pytest.raises(bridge.ExperientialBridgeRefused, match="SEND_RESERVATION_REFUSED"):
        bridge.exec_command(**args)
    assert len(requests) == 1


@pytest.mark.parametrize("model", tuple(FREE_NATIVE_MODELS))
def test_native_free_refusal_has_one_send_and_no_paid_fallback(tmp_path, monkeypatch, local_gateway, model):
    port, requests, status = local_gateway
    status[0] = 429
    args, _ = run_bridge(tmp_path, monkeypatch, port, model)
    with pytest.raises(bridge.ExperientialBridgeRefused, match="RATE_LIMITED"):
        bridge.exec_command(**args)
    with pytest.raises(bridge.ExperientialBridgeRefused, match="DUPLICATE_LAUNCH"):
        bridge.exec_command(**args)
    assert len(requests) == 1 and requests[0][0]["model"] == model


@pytest.mark.parametrize("model", tuple(FREE_NATIVE_MODELS))
@pytest.mark.parametrize("bad", ["not json", '{"state":"a","state":"b","questions":{}}',
                               '{"input":"x","questions":[],"model":"paid"}'])
def test_native_invalid_packet_refuses_before_send(tmp_path, monkeypatch, local_gateway, model, bad):
    port, requests, _ = local_gateway
    args, _ = run_bridge(tmp_path, monkeypatch, port, model)
    Path(args["prompt_file"]).write_text(bad)
    with pytest.raises(bridge.ExperientialBridgeRefused, match="PLAN_NATIVE"):
        bridge.exec_command(**args)
    assert requests == []
    marker = tmp_path / "ext/state/remote_sub" / (args["run_id"] + ".task-cli-started.json")
    assert not marker.exists()


@pytest.mark.parametrize("model", tuple(FREE_NATIVE_MODELS))
def test_native_protocol_binding_cannot_be_changed_to_chat(model):
    _, _, context = facts()
    with pytest.raises(transport.ExperientialTransportRefused, match="PROTOCOL_MISMATCH"):
        transport.require_plan_route_qualified(transport.GatewayRoute(**context["route"]), model)
    assert admit(context, model)["endpoint"] == FREE_NATIVE_MODELS[model]


@pytest.mark.parametrize("model", tuple(FREE_NATIVE_MODELS))
@pytest.mark.parametrize("fault", ["answers", "value", "model", "refusal"])
def test_native_answer_validation_preserves_question_and_model_identity(model, fault):
    frame = {"model": model, "answers": native_answer(model), "usage": {}}
    first = frame["answers"]["present"] if type(frame["answers"]) is dict else frame["answers"][0]
    if fault == "answers":
        frame["answers"] = {}
    elif fault == "value":
        first["noul" if model == "jev-latest" else "probability"] = 1.1
    elif fault == "model":
        frame["model"] = "other-model"
    else:
        first["type"] = "refusal"
    with pytest.raises(transport.ExperientialTransportRefused):
        transport._parse_native_completion(json.dumps(frame).encode(), "application/json", model, native_packet(model))


def test_native_latest_alias_preserves_documented_release_and_rejects_conflicting_identity():
    model = "jev-latest"
    frame = json.dumps({"model": "jev-1.13.0", "answers": native_answer(model)}).encode()
    assert transport._parse_native_completion(frame, "application/json", model,
        native_packet(model))[1] == "jev-1.13.0"
    assert transport._parse_native_completion(frame, "application/json", model,
        native_packet(model), canonical_model="jev-latest")[1] == "jev-1.13.0"
    with pytest.raises(transport.ExperientialTransportRefused, match="MODEL_MISMATCH"):
        transport._parse_native_completion(frame, "application/json", model,
            native_packet(model), canonical_model="other-model")


def test_invalid_native_response_keeps_original_reconciliation_handle(tmp_path, monkeypatch, local_gateway):
    port, requests, _ = local_gateway
    args, _ = run_bridge(tmp_path, monkeypatch, port, "jev-latest")
    def invalid(*_args, **_kwargs):
        raise transport.ExperientialTransportRefused("GATEWAY_RESPONSE_MALFORMED")
    monkeypatch.setattr(transport, "_parse_native_completion", invalid)
    with pytest.raises(bridge.ExperientialBridgeRefused, match="provider_request_id=fixture-provider-request"):
        bridge.exec_command(**args)
    assert len(requests) == 1
    with pytest.raises(bridge.ExperientialBridgeRefused, match="DUPLICATE_LAUNCH"):
        bridge.exec_command(**args)
    assert len(requests) == 1

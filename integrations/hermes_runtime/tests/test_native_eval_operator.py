"""Actual CLI/held qualification with explicit host and native RPC fixture edges.

No listener, system service, credential or provider is used. The existing
enrollment qualifier, configuration, request/response validators and CLI run.
"""
from copy import deepcopy
import io
import json
from types import SimpleNamespace

import pytest

from integrations.hermes_harness.native_byok import expected_native_config
from integrations.hermes_runtime import cli, native_eval_operator as operator
from integrations.hermes_runtime import native_eval_inputs as inputs, native_session_control as control
from integrations.hermes_runtime import tcp_sandbox
from integrations.hermes_runtime.profile import dump_profile, profile_sha256
from integrations.hermes_runtime.tests.test_operator_native_enrollment import enrollment_command, SHA
from integrations.hermes_runtime.tests.test_native_eval_inputs import documents
from integrations.hermes_harness.tests.test_native_current_agentos_context import current_document
from ops.executive_os.native_gateway_sources import DERIVATION_BASE, EVAL_INPUTS_DERIVATION_PATCH
from scripts.agent_eval.store import run_path
from tests.agent_eval_factories import fresh_run_id


@pytest.fixture
def command(enrollment_command, monkeypatch, capsys):
    world = enrollment_command(role="mmmeta")
    world.state.inspect_status = "ENROLLED"
    recipe = world.launch.recipe
    publication = current_document()
    publication["session"].update(role="mmmeta", principal_id=world.target["principal_id"])
    recipe["executive_consumer"] = publication
    recipe["vendor_derivation"] = {"kind": "native_eval_inputs", "base_sha": DERIVATION_BASE,
        "patch_sha256": EVAL_INPUTS_DERIVATION_PATCH, "source_root": "/fixture/pristine"}
    recipe["evaluation_inputs"] = {"schema": inputs.RECIPE_SCHEMA,
        "artifact_root": str(world.path.parent / "existing-eval")}
    world.config.write_text(expected_native_config(world.profile, recipe["executive_consumer"],
                                                   evaluation_inputs=recipe["evaluation_inputs"]))
    scenario, configuration, text, files, context = documents(world.target["profile_id"])
    spec = {"run_id": fresh_run_id(), "scenario_id": scenario["scenario_id"],
        "scenario_version": scenario["scenario_version"], "scenario_digest": scenario["scenario_digest"],
        "configuration_id": configuration["configuration_id"],
        "configuration_digest": configuration["configuration_digest"],
        "experiment_id": None, "experiment_digest": None, "arm_id": None,
        "pair_key": None, "replicate_index": None, "candidate_files": files, "context_text": context}
    request = {"schema": operator.SUBMIT_SCHEMA, "session_id": world.target["session_id"],
               "text": text, "evaluation": spec}
    recovery = operator.recovery_for("submit", request, world.target["profile_id"])
    binding = {"run_id": spec["run_id"], "binding_sha256": "d" * 64}
    receipt = {"admission_id": "original-admission", "ref": {
        "profile_id": recovery["profile_id"], "session_id": recovery["session_id"]},
        "sequence": 1, "status": "terminal", "outcome": "completed",
        "authority_epoch": world.target["authority_epoch"], "execution_generation": 1}
    state = SimpleNamespace(calls=[], loss=None, change=None, capability=None, mutate=None,
                            publication_count=0, reads=[], admitted=False, policy=0)
    original_client = control.NativeSecretaryClient

    def called(name):
        state.calls.append(name)
        if state.change == name:
            world.state.changed = True
        if state.loss == name:
            raise TimeoutError("private response is unavailable")

    class Client(original_client):
        def enroll_session(self, *args):
            pytest.fail("an evaluation command cannot create an enrollment")

        def evaluation_capabilities(self):
            called("capabilities")
            value = {"producer": inputs.producer_descriptor(SHA, DERIVATION_BASE, EVAL_INPUTS_DERIVATION_PATCH),
                "profile_id": world.target["profile_id"],
                "profile_digest": "sha256:" + profile_sha256(dump_profile(world.profile)),
                "run_schema": "mastermind.agent_evaluation_run.v3", "complete_evaluation": False}
            if state.capability == "withdrawn":
                return control._result("UNAVAILABLE", role="mmmeta")
            if state.capability == "producer":
                value["producer"]["runner_code_ref"] = "git:mastermindx-market-intelligence/Mastermind@" + "b" * 40
            if state.capability == "profile":
                value["profile_id"] += "-foreign"
            if state.capability == "complete":
                value["complete_evaluation"] = True
            return control._result("OBSERVED", role="mmmeta", evaluation=value)

        def observe(self, session):
            called("observe")
            assert session == recovery["session_id"]
            return control._result("TARGET", role="mmmeta", target=deepcopy(world.target))

        def submit(self, target, submission_id, body, *, evaluation):
            assert target == world.target and submission_id == recovery["submission_id"]
            assert body == text and evaluation == spec
            state.admitted = True
            called("submit")
            value = control._result("ADMITTED", role="mmmeta",
                admission={**deepcopy(receipt), "status": "queued", "outcome": None, "execution_generation": None},
                evaluation_binding=deepcopy(binding))
            if state.mutate == "submit-extra":
                value["alternate_receipt"] = {}
            return value

        def read_original(self, **identity):
            state.reads.append(deepcopy(identity))
            assert identity["session_id"] == recovery["session_id"]
            assert identity["submission_id"] == recovery["submission_id"]
            assert identity["input_sha256"] == recovery["input_sha256"]
            called("read")
            value = control._result("OBSERVED", role="mmmeta", admission=deepcopy(receipt),
                evaluation_binding=deepcopy(binding), answer="never copy this original private answer",
                terminal_metadata={"reported": {"reasoning": "not an output field"}})
            if state.mutate == "read-binding":
                value["evaluation_binding"]["run_id"] = fresh_run_id()
            if state.mutate == "read-outcome":
                value["admission"]["outcome"] = "unbounded private label " * 100
            return value

        def publish_evaluation(self, **identity):
            assert identity == {"session_id": recovery["session_id"], "submission_id": recovery["submission_id"],
                "input_sha256": recovery["input_sha256"], "admission_id": receipt["admission_id"],
                "evaluation_binding": binding}
            state.publication_count += 1
            called("publish")
            if state.mutate == "published-not-submitted":
                return control._result("NOT_SUBMITTED", role="mmmeta")
            item = {"schema": "mastermind.hermes_native_eval_publication/v1",
                "disposition": "CREATED" if state.publication_count == 1 else "IDEMPOTENT",
                "relative_path": str(run_path(recovery["run_id"])), "run_digest": "sha256:" + "f" * 64,
                "validity": "INVALID_EFFECT_UNKNOWN", "reason_codes": ["REQUIRED_OBSERVATION_UNAVAILABLE"],
                "complete_evaluation": False, "provider_delivery_proven": False, "model_identity_verified": False}
            if state.mutate == "published-valid":
                item["validity"] = "VALID"
            if state.mutate == "published-path":
                item["relative_path"] = "foreign/receipt.json"
            return control._result("PUBLISHED", role="mmmeta", admission_id=receipt["admission_id"],
                                   evaluation_binding=deepcopy(binding), publication=item)

    def policy(profile):
        assert dump_profile(profile) == dump_profile(world.profile)
        state.policy += 1
        # It must run before any asynchronous owner/native read, and exactly
        # once per invocation. A repeated attachment would fail on live Linux.
        assert not state.calls

    monkeypatch.setattr(control, "NativeSecretaryClient", Client)
    monkeypatch.setattr(tcp_sandbox, "enforce_role_tcp_ports", policy)

    def run(operation, value=None, raw=None):
        state.calls.clear()
        world.state.changed = False
        prior_policy = state.policy
        if raw is None:
            raw = json.dumps(value or (request if operation == "submit" else recovery)).encode()
        monkeypatch.setattr(cli.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(raw)))
        code = cli.main(["eval-" + operation, "--profile", str(world.path),
                         "--hermes-bin", str(world.binary)], native_launch=world.launch)
        out = capsys.readouterr()
        assert not out.err
        decoded = json.loads(out.out)
        assert "never copy this original private answer" not in out.out
        assert "not an output field" not in out.out
        if state.calls:
            assert state.policy == prior_policy + 1
        return code, decoded

    return SimpleNamespace(world=world, state=state, request=request, recovery=recovery,
                           binding=binding, receipt=receipt, run=run)


def test_actual_submit_admits_once_and_returns_original_recovery_without_answer(command):
    w = command
    code, value = w.run("submit")
    assert code == 0 and value["status"] == "ADMITTED"
    assert value["recovery"] == {**w.recovery, "admission_id": w.receipt["admission_id"],
                                "evaluation_binding": w.binding}
    assert w.state.calls == ["capabilities", "observe", "submit"]
    assert w.world.state.inspections == 1 and w.world.state.creations == 0
    assert value["complete_evaluation"] is False


@pytest.mark.parametrize("loss", ["submit", "publish"])
def test_lost_reply_keeps_known_recovery_without_retry(command, loss):
    w = command
    w.state.loss = loss
    code, value = w.run(loss)
    assert code == 3 and value["status"] == "EFFECT_UNKNOWN"
    assert value["recovery"]["run_id"] == w.recovery["run_id"]
    assert value["recovery"]["submission_id"] == w.recovery["submission_id"]
    assert w.state.calls.count(loss) == 1
    assert w.world.state.creations == 0
    if loss == "publish":
        assert value["recovery"]["admission_id"] == w.receipt["admission_id"]
        assert "submit" not in w.state.calls


def test_historical_read_and_repeated_publication_ignore_new_enrollment_tip(command):
    w = command
    w.world.state.inspect_status = "ABSENT"
    code, observed = w.run("read")
    assert code == 0 and observed["status"] == "OBSERVED"
    assert w.state.calls == ["read"] and w.world.state.inspections == 0
    code, first = w.run("publish", observed["recovery"])
    assert code == 0 and first["publication"]["disposition"] == "CREATED"
    code, second = w.run("publish", first["recovery"])
    assert code == 0 and second["publication"]["disposition"] == "IDEMPOTENT"
    assert first["publication"]["run_digest"] == second["publication"]["run_digest"]
    assert w.state.calls == ["read", "capabilities", "publish"]
    assert w.world.state.inspections == w.world.state.creations == 0


@pytest.mark.parametrize("status,outcome", [("queued", None), ("started", None), ("unknown", None),
                                           ("terminal", "steering"), ("terminal", "steered")])
def test_nonterminal_or_transfer_publication_returns_once_without_effect(command, status, outcome):
    w = command
    w.receipt.update(status=status, outcome=outcome)
    code, value = w.run("publish")
    assert code == 0 and value["status"] == "OBSERVED"
    assert value["reason"] == "ORIGINAL_NOT_PUBLISHABLE"
    assert w.state.calls == ["read"] and w.state.publication_count == 0


@pytest.mark.parametrize("operation", ["submit", "publish"])
@pytest.mark.parametrize("bad", ["withdrawn", "producer", "profile", "complete"])
def test_capability_refusal_prevents_mutation_but_not_historical_read(command, operation, bad):
    w = command
    w.state.capability = bad
    code, value = w.run(operation)
    assert code == 2 and value["status"] == "UNAVAILABLE"
    assert "submit" not in w.state.calls and "publish" not in w.state.calls
    if operation == "publish":
        assert value["recovery"]["admission_id"] == w.receipt["admission_id"]
    code, value = w.run("read")
    assert code == 0 and value["status"] == "OBSERVED"
    assert w.state.calls == ["read"]


@pytest.mark.parametrize("point,operation,code", [
    ("capabilities", "submit", 2), ("observe", "submit", 2),
    ("submit", "submit", 3), ("read", "publish", 2),
    ("capabilities", "publish", 2), ("publish", "publish", 3)])
def test_owner_change_preserves_effect_boundary_and_original_identity(command, point, operation, code):
    w = command
    w.state.change = point
    actual, value = w.run(operation)
    assert actual == code
    assert value["status"] == ("EFFECT_UNKNOWN" if code == 3 else "UNAVAILABLE")
    assert w.state.calls.count("submit") == (1 if operation == "submit" and code == 3 else 0)
    assert w.state.calls.count("publish") == (1 if operation == "publish" and code == 3 else 0)
    if point == "submit" or operation == "publish":
        assert value["recovery"]["admission_id"] == w.receipt["admission_id"]
        assert value["recovery"]["evaluation_binding"] == w.binding
    assert w.world.state.creations == 0


@pytest.mark.parametrize("mutate,operation,code", [
    ("submit-extra", "submit", 3), ("read-binding", "read", 2),
    ("read-outcome", "read", 2), ("published-valid", "publish", 3),
    ("published-path", "publish", 3), ("published-not-submitted", "publish", 3)])
def test_unqualified_responses_never_become_success_or_learning_acceptance(command, mutate, operation, code):
    w = command
    w.state.mutate = mutate
    actual, value = w.run(operation)
    assert actual == code
    assert value["status"] == ("EFFECT_UNKNOWN" if code == 3 else "UNAVAILABLE")
    assert value["publication"] is None
    if operation == "publish":
        assert w.state.calls.count("publish") == 1
        assert value["recovery"]["admission_id"] == w.receipt["admission_id"]


@pytest.mark.parametrize("raw", [b'{"schema":', b'{"schema":"one","schema":"two"}', b"[]", b"x" * (operator.MAX_REQUEST_BYTES + 1)])
def test_bad_request_never_enters_native_or_prints_untrusted_input(command, raw):
    w = command
    code, value = w.run("submit", raw=raw)
    assert code == 2 and value["status"] == "REFUSED"
    assert w.state.calls == [] and w.world.state.inspections == 0


@pytest.mark.parametrize("field", ["artifact_root", "observations", "producer", "run"])
def test_caller_cannot_supply_publication_authority_or_observation_fields(command, field):
    w = command
    request = {**w.recovery, field: {}}
    code, value = w.run("publish", request)
    assert code == 2 and value["status"] == "REFUSED"
    assert w.state.calls == []


def test_wrong_original_profile_or_enrolled_session_never_submits(command):
    w = command
    request = {**w.request, "session_id": "other-native-session"}
    code, value = w.run("submit", request)
    assert code == 2 and value["reason"] == "ORIGINAL_ENROLLMENT_REQUIRED"
    assert "submit" not in w.state.calls
    code, value = w.run("publish", {**w.recovery, "profile_id": w.recovery["profile_id"] + "-foreign"})
    assert code == 2 and value["status"] == "REFUSED"
    assert w.state.calls == []


@pytest.mark.parametrize("operation", ["submit", "read", "publish"])
def test_outer_runner_loss_after_connected_result_preserves_uncertainty(command, monkeypatch, operation):
    import asyncio
    w = command
    original = asyncio.run
    def lose_after_result(coroutine):
        original(coroutine)
        raise RuntimeError("runner shutdown lost its return")
    monkeypatch.setattr(asyncio, "run", lose_after_result)
    code, value = w.run(operation)
    assert code == (2 if operation == "read" else 3)
    assert value["status"] == ("UNAVAILABLE" if operation == "read" else "EFFECT_UNKNOWN")
    assert value["recovery"] == w.recovery
    assert value["reason"] == "EVALUATION_OPERATOR_RUNNER_RECONCILIATION_REQUIRED"
    assert w.state.calls.count("submit") <= 1 and w.state.calls.count("publish") <= 1


def test_shared_enrollment_attaches_tcp_policy_once_before_asyncio(enrollment_command, monkeypatch, capsys):
    import asyncio
    world = enrollment_command(role="mmmeta")
    calls = []
    def policy(profile):
        assert dump_profile(profile) == dump_profile(world.profile)
        with pytest.raises(RuntimeError, match="no running event loop"):
            asyncio.get_running_loop()
        calls.append(profile.role)
    monkeypatch.setattr(tcp_sandbox, "enforce_role_tcp_ports", policy)
    assert cli._enroll_meta_session(world.path, world.binary, native_launch=world.launch) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ENROLLED"
    assert calls == ["mmmeta"]
    assert world.state.creations == 1 and world.state.qualifications >= 4

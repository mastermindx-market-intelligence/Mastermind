"""Prospective diagnostic-only patch; no installed code or provider invocation."""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import sys
import types

import pytest

ROOT = Path(__file__).resolve().parents[1]
PROPOSAL = ROOT / "research/proposals/fabric_refusal_diagnostics_20261102"
MANIFEST = json.loads((PROPOSAL / "manifest.json").read_text())
UNKNOWN = "UNCLASSIFIED_PRELAUNCH_REFUSAL"


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture(scope="module")
def material(tmp_path_factory):
    # This is a historical prospective patch, not an embargo on unrelated
    # active-reader improvements. Keep its exact reviewed input reproducible
    # in source archives without depending on Git history or live host files.
    original = (PROPOSAL / "fabric_task.py.base").read_bytes()
    patch = (PROPOSAL / "native-refusal-diagnostics.patch").read_bytes()
    assert digest(original) == MANIFEST["preimage_sha256"]
    assert digest(patch) == MANIFEST["patch_sha256"]
    destination = tmp_path_factory.mktemp("refusal-source")
    target = destination / MANIFEST["target_path"]
    target.parent.mkdir(parents=True)
    target.write_bytes(original)
    applied = subprocess.run(
        ["git", "apply", str(PROPOSAL / "native-refusal-diagnostics.patch")],
        cwd=destination, capture_output=True, text=True, timeout=10, check=False,
    )
    assert applied.returncode == 0, applied.stderr
    postimage = target.read_bytes()
    assert digest(postimage) == MANIFEST["postimage_sha256"]
    compile(postimage, str(target), "exec")
    # The RED invocation chooses the unmodified source, not a fake broken patch.
    selected = original if os.environ.get("MMX_REFUSAL_DIAGNOSTICS_BASELINE") == "1" else postimage
    return original.decode(), postimage.decode(), selected.decode()


def component_namespace(source: str, here: Path) -> dict:
    """Execute exact materialized functions; omit import-time native side effects."""
    names = {
        "FabricTaskError", "validate_run_id", "_bounded_regular",
        "_acceptance_unknown", "inspect_run", "_inspect_run", "_parse_route",
        "_safe_request_refusal_code",
    }
    nodes = []
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names:
            nodes.append(node)
        elif isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_REQUEST_REFUSAL_CODES" for t in node.targets
        ):
            nodes.append(node)
    module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), *nodes], type_ignores=[])
    ast.fix_missing_locations(module)
    ns = {
        "Path": Path, "os": os, "stat": stat, "json": json, "shlex": shlex,
        "HERE": here, "RUN_ID_RE": re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}"),
        "_paths": lambda rid: (here / (rid + ".log"), here / (rid + ".result")),
    }
    exec(compile(module, "materialized-native-components", "exec"), ns)
    return ns


@pytest.fixture
def ns(material, tmp_path, monkeypatch):
    provider = types.ModuleType("provider_outcome")
    provider.digest = digest
    monkeypatch.setitem(sys.modules, "provider_outcome", provider)
    return component_namespace(material[2], tmp_path)


def retained_receipts(ns, *, code="NO_ROUTE", legacy=False, mutation=None, launch=False):
    rid = "source-refusal-fixture"
    state = ns["HERE"] / "state/remote_sub"
    state.mkdir(parents=True)
    request = {"schema": "mastermind.fabric_request_artifact.v1", "run_id": rid,
               "root_id": "source-root", "parent_run_id": "source-parent"}
    raw = json.dumps(request).encode()
    (state / (rid + ".request.json")).write_bytes(raw)
    refusal = {"schema": "mastermind.fabric_request_refusal.v1", "run_id": rid,
               "root_id": request["root_id"], "parent_run_id": request["parent_run_id"],
               "request_sha256": digest(raw), "launch_attempted": False,
               "reason": "prelaunch_FabricTaskError"}
    if not legacy:
        refusal["refusal_code"] = code
    refusal.update(mutation or {})
    (state / (rid + ".request-refused.json")).write_text(json.dumps(refusal))
    if launch:
        (state / (rid + ".request-launch.json")).write_text("{}")
    return rid, state


def test_known_refusal_code_is_visible_without_authority(ns):
    rid, _ = retained_receipts(ns)
    out = ns["inspect_run"](rid)
    assert out["state"] == "REQUEST_REFUSED_BEFORE_LAUNCH"
    assert out["request_refusal_code"] == "NO_ROUTE"
    assert out["execution_absence_proven"] is True
    assert out["root_id"] is None and out["parent_run_id"] is None
    assert out["accepted"] is None and out["result_available"] is False
    assert out["background_execution"] is False
    assert out["same_run_replay_allowed"] is False


@pytest.mark.parametrize("message,expected", [
    ("NO_ROUTE", "NO_ROUTE"),
    ("ROUTE_INCOMPLETE", "ROUTE_INCOMPLETE"),
    ("REQUEST_ROUTING_RETURN_UNQUALIFIED", "REQUEST_ROUTING_RETURN_UNQUALIFIED"),
    ("REQUEST_MAX_TURNS_INVALID", "REQUEST_MAX_TURNS_INVALID"),
    ("REQUEST_MAX_TURNS_ROUTE_UNSUPPORTED", "REQUEST_MAX_TURNS_ROUTE_UNSUPPORTED"),
    ("ECONOMIC_POLICY_REFUSED: secret-private-detail", "ECONOMIC_POLICY_REFUSED"),
    ("not-a-closed-code private=secret", UNKNOWN),
    ("NO_ROUTE_SECRET", UNKNOWN),
    ("NO_ROUTE " , UNKNOWN),
    ("NO_ROUTE\nsecret", UNKNOWN),
    ("x" * 2000, UNKNOWN),
])
def test_only_closed_error_codes_survive(ns, message, expected):
    out = ns["_safe_request_refusal_code"](ns["FabricTaskError"](message))
    assert out == expected
    assert "secret" not in out


def test_route_refusal_keeps_original_exception_but_not_its_private_text(ns):
    raw = "no eligible route; provider-private=secret"
    with pytest.raises(ns["FabricTaskError"]) as info:
        ns["_parse_route"](raw)
    assert str(info.value) == raw
    assert ns["_safe_request_refusal_code"](info.value) == "NO_ROUTE"


def test_valid_route_is_unchanged(ns):
    assert ns["_parse_route"]("POOL=fixture MODEL=fixture HOST=fixture MODE=fixture") == {
        "POOL": "fixture", "MODEL": "fixture", "HOST": "fixture", "MODE": "fixture"}


def test_unknown_exception_and_argument_do_not_invoke_stringification(ns):
    class Dangerous:
        def __str__(self):
            raise AssertionError("must not stringify")
    class Derived(ns["FabricTaskError"]):
        def __getattribute__(self, key):
            raise AssertionError("must not inspect a subclass")
    classify = ns["_safe_request_refusal_code"]
    assert classify(ValueError("NO_ROUTE")) == UNKNOWN
    assert classify(ns["FabricTaskError"](Dangerous())) == UNKNOWN
    assert classify(Derived("NO_ROUTE")) == UNKNOWN


@pytest.mark.parametrize("code", [None, "SECRET-PRIVATE-DETAIL", 1, [], {}, True])
def test_unrecognized_receipt_code_is_unclassified(ns, code):
    rid, _ = retained_receipts(ns, code=code)
    out = ns["inspect_run"](rid)
    assert out["request_refusal_code"] == UNKNOWN
    assert "SECRET-PRIVATE-DETAIL" not in json.dumps(out)
    assert out["same_run_replay_allowed"] is False


def test_legacy_refusal_does_not_get_a_fabricated_reason(ns):
    rid, _ = retained_receipts(ns, legacy=True)
    assert ns["inspect_run"](rid)["request_refusal_code"] == UNKNOWN


@pytest.mark.parametrize("mutation", [
    {"schema": "wrong"}, {"run_id": "other"}, {"root_id": "other"},
    {"parent_run_id": "other"}, {"request_sha256": "0" * 64},
    {"launch_attempted": True},
])
def test_invalid_original_proof_cannot_expose_a_refusal_code(ns, mutation):
    rid, _ = retained_receipts(ns, mutation=mutation)
    out = ns["inspect_run"](rid)
    assert out["state"] != "REQUEST_REFUSED_BEFORE_LAUNCH"
    assert "request_refusal_code" not in out
    assert out.get("root_id") is None


def test_launch_marker_prevents_no_launch_classification(ns):
    rid, _ = retained_receipts(ns, launch=True)
    out = ns["inspect_run"](rid)
    assert out["state"] == "REQUEST_RETAINED_NO_START_EVIDENCE"
    assert "request_refusal_code" not in out
    assert out["execution_absence_proven"] is False


def test_symlinked_refusal_cannot_supply_diagnostics(ns):
    rid, state = retained_receipts(ns)
    path = state / (rid + ".request-refused.json")
    retained = path.read_text()
    path.unlink()
    foreign = ns["HERE"] / "foreign.json"
    foreign.write_text(retained)
    path.symlink_to(foreign)
    out = ns["inspect_run"](rid)
    assert out["state"] != "REQUEST_REFUSED_BEFORE_LAUNCH"
    assert "request_refusal_code" not in out


def test_proposal_remains_inert_and_preserves_its_original_admission_ast(material):
    assert digest((PROPOSAL / "fabric_task.py.base").read_bytes()) == MANIFEST["preimage_sha256"]
    assert MANIFEST["active_candidate_unchanged"] is True
    # This immutable proposal records its historical preimage. The current
    # native candidate may separately implement the diagnosed live defect;
    # the tests below verify that current behavior without rewriting archives.
    old, new = map(ast.parse, material[:2])
    ignored = {"inspect_run", "_parse_route", "_safe_request_refusal_code"}
    def clean(module):
        module = copy.deepcopy(module)
        kept = []
        for node in module.body:
            if isinstance(node, ast.FunctionDef) and node.name in ignored:
                continue
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_REQUEST_REFUSAL_CODES" for t in node.targets):
                continue
            # The only change to the actual request/writer body is one diagnostic
            # entry on the existing prelaunch-refusal object, not admission logic.
            for child in ast.walk(node):
                if isinstance(child, ast.Dict):
                    pairs = [(k, v) for k, v in zip(child.keys, child.values)
                             if not (isinstance(k, ast.Constant) and k.value == "refusal_code")]
                    child.keys = [k for k, _ in pairs]
                    child.values = [v for _, v in pairs]
            kept.append(node)
        return ast.dump(ast.Module(body=kept, type_ignores=[]), include_attributes=False)
    assert clean(old) == clean(new)


@pytest.fixture
def current_native_ns(tmp_path, monkeypatch):
    # Operates on the real current candidate, never on an installed generation.
    provider = types.ModuleType("provider_outcome")
    provider.digest = digest
    monkeypatch.setitem(sys.modules, "provider_outcome", provider)
    return component_namespace((ROOT / MANIFEST["target_path"]).read_text(), tmp_path)


@pytest.mark.parametrize("message,expected", [
    ("NONE reason=no_operator_available", "NO_OPERATOR_AVAILABLE"),
    ("NONE reason=no_pool_available", "NO_POOL_AVAILABLE"),
    ("ROUTE_INCOMPLETE", "ROUTE_INCOMPLETE"),
    ("ECONOMIC_POLICY_REFUSED: redacted private detail", "ECONOMIC_POLICY_REFUSED"),
    ("NONE reason=private-host-token", UNKNOWN),
    ("NONE reason=no_operator_available private=secret", UNKNOWN),
    ("NO_OPERATOR_AVAILABLE private=secret", UNKNOWN),
])
def test_current_candidate_classifies_only_exact_closed_refusals(current_native_ns, message, expected):
    classify = current_native_ns["_safe_request_refusal_code"]
    assert classify(current_native_ns["FabricTaskError"](message)) == expected
    assert "secret" not in classify(current_native_ns["FabricTaskError"](message))
    assert classify(ValueError(message)) == UNKNOWN


def test_deadline_picker_no_operator_refusal_can_be_diagnosed_without_retry(current_native_ns):
    with pytest.raises(current_native_ns["FabricTaskError"]) as exc:
        current_native_ns["_parse_route"]("NONE reason=no_operator_available")
    code = current_native_ns["_safe_request_refusal_code"](exc.value)
    assert code == "NO_OPERATOR_AVAILABLE"

    rid, _ = retained_receipts(current_native_ns, code=code)
    status = current_native_ns["inspect_run"](rid)
    assert status["state"] == "REQUEST_REFUSED_BEFORE_LAUNCH"
    assert status["request_refusal_code"] == code
    assert status["execution_absence_proven"] is True
    assert status["accepted"] is None and status["result_available"] is False
    assert status["same_run_replay_allowed"] is False
    assert status.get("root_id") is None


@pytest.mark.parametrize("legacy,code,launch", [
    (True, "NO_OPERATOR_AVAILABLE", False),
    (False, "private-provider-text", False),
    (False, "NO_OPERATOR_AVAILABLE", True),
])
def test_current_candidate_never_invents_legacy_or_launch_reason(current_native_ns, legacy, code, launch):
    rid, _ = retained_receipts(current_native_ns, code=code, legacy=legacy, launch=launch)
    status = current_native_ns["inspect_run"](rid)
    if launch:
        assert status["state"] == "REQUEST_RETAINED_NO_START_EVIDENCE"
        assert "request_refusal_code" not in status
    else:
        assert status["state"] == "REQUEST_REFUSED_BEFORE_LAUNCH"
        assert status["request_refusal_code"] == UNKNOWN
        assert status["same_run_replay_allowed"] is False

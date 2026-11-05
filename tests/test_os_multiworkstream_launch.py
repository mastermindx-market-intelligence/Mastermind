"""Finite v2 launch enrollment through the incumbent compiler and publisher.

Custody fixtures are disposable TESTDATA; this does not publish live grants.
"""
from __future__ import annotations

import copy
import json

import pytest

from ops.executive_os import autonomy_control as owner
from ops.executive_os import os_gateway_publication as compiler
from ops.executive_os import os_release_assets as assets
from tests import test_h2_gateway_profiles as h2
from tests import test_os_gateway_publication as pure
from tests import test_os_gateway_publication_owner as harness
from tests.test_os_gateway_publication_owner import gateway, gateway_tmp_path


def manifest():
    ecosystem = {key: value for key, value in h2.manifest().items() if key != "v"}
    ecosystem.update(label="Executive Ecosystem", workstream="WS:EXECUTIVE-ECOSYSTEM-COMPLETION")
    office = copy.deepcopy(ecosystem)
    office.update(label="Meta-CEO Office", workstream="WS:CHAIRMAN-CONTROL-ROOM")
    office["profiles"] = office["profiles"][:1]
    return {"v": 2, "defaultWorkstream": ecosystem["workstream"],
            "bindings": [ecosystem, office]}


def test_v2_roundtrips_original_bytes_without_mutating_or_flattening_enrollment():
    value = manifest()
    before = copy.deepcopy(value)
    raw = assets._canonical(value)
    assert assets.decode_launch_manifest(raw) == raw
    bindings = assets._decode_launch_bindings(value)
    assert len(bindings) == 2
    assert [binding["workstream"] for binding in bindings] == [
        "WS:EXECUTIVE-ECOSYSTEM-COMPLETION", "WS:CHAIRMAN-CONTROL-ROOM"]
    assert all(binding["v"] == 1 and "label" not in binding for binding in bindings)
    assert value == before
    rows = h2.templates(value)
    assert [row["execution_profile"] for row in rows] == [
        "research_only", "native_research_only", "research_only"]
    assert rows[0]["workstream"] == rows[1]["workstream"]
    assert rows[2]["workstream"] == value["bindings"][1]["workstream"]


@pytest.mark.parametrize("fault", [
    "extra-root", "missing-default", "unknown-default", "empty", "seventeen",
    "extra-entry", "entry-version", "missing-label", "blank-label", "long-label",
    "control-label", "duplicate-workstream", "missing-workstream", "missing-priority",
    "multiple-projects", "native-only", "reverse-pair", "bounded-code",
    "native-attempt", "bool-attempt", "write", "validation", "frontier-extra",
    "template-cap", "version-bool",
])
def test_v2_rejects_ambiguous_or_broader_enrollment(fault):
    value = manifest()
    first = value["bindings"][0]
    if fault == "extra-root": value["token"] = "unaccepted"
    elif fault == "missing-default": del value["defaultWorkstream"]
    elif fault == "unknown-default": value["defaultWorkstream"] = "WS:Missing"
    elif fault == "empty": value["bindings"] = []
    elif fault == "seventeen": value["bindings"] *= 9
    elif fault == "extra-entry": first["provider"] = "unaccepted"
    elif fault == "entry-version": first["v"] = 1
    elif fault == "missing-label": del first["label"]
    elif fault == "blank-label": first["label"] = ""
    elif fault == "long-label": first["label"] = "x" * 121
    elif fault == "control-label": first["label"] = "Office\n"
    elif fault == "duplicate-workstream": value["bindings"][1]["workstream"] = first["workstream"]
    elif fault == "missing-workstream": del first["workstream"]
    elif fault == "missing-priority": del first["priority"]
    elif fault == "multiple-projects": first["projects"].append({"ref": "another", "label": "Other"})
    elif fault == "native-only": first["profiles"] = first["profiles"][1:]
    elif fault == "reverse-pair": first["profiles"].reverse()
    elif fault == "bounded-code":
        first.update(profiles=[{"ref": "bounded_code_change", "label": "Code"}],
                     allowedWritePaths=["src/file.py"], validation={"git_diff_check": True})
    elif fault == "native-attempt": first["attemptLimit"] = 2
    elif fault == "bool-attempt": first["attemptLimit"] = True
    elif fault == "write": first["allowedWritePaths"] = ["src/file.py"]
    elif fault == "validation": first["validation"] = {"git_diff_check": True}
    elif fault == "frontier-extra": first["frontierModels"] = [{"ref": "one", "label": "One", "provider": "new"}]
    elif fault == "template-cap":
        value["bindings"] = [dict(copy.deepcopy(first), workstream=f"WS:Entry{i}") for i in range(9)]
        value["defaultWorkstream"] = "WS:Entry0"
    elif fault == "version-bool": value["v"] = True
    assert assets._decode_launch_bindings(value) is None
    with pytest.raises(ValueError):
        assets.decode_launch_manifest(assets._canonical(value))


@pytest.mark.parametrize("validation", [
    {"pytest_targets": []}, {"compileall_paths": []}, {"git_diff_check": False},
])
def test_v2_native_pair_refuses_inert_nonempty_validation_without_changing_v1(validation):
    value = manifest()
    value["bindings"][0]["validation"] = validation
    assert assets._decode_launch_bindings(value) is None
    with pytest.raises(ValueError):
        assets.decode_launch_manifest(assets._canonical(value))
    legacy = {"v": 1, **{key: item for key, item in value["bindings"][0].items() if key != "label"}}
    assert assets._decode_launch_bindings(legacy) == (legacy,)


def test_v2_template_and_byte_limits_are_independent_and_unchanged():
    entry = {"label": "A", "workstream": "WS:W0", "priority": 0,
             "projects": [{"ref": "aa", "label": "A"}],
             "profiles": [{"ref": "research_only", "label": "R"}]}
    value = {"v": 2, "defaultWorkstream": "WS:W0",
             "bindings": [dict(copy.deepcopy(entry), workstream=f"WS:W{i}") for i in range(16)]}
    raw = assets._canonical(value)
    assert len(raw) <= 4096
    assert assets.decode_launch_manifest(raw) == raw
    assert len(h2.templates(value)) == 16
    for binding in value["bindings"]:
        binding["label"] = "x" * 120
    assert assets._decode_launch_bindings(value) is not None
    assert len(assets._canonical(value)) > 4096
    with pytest.raises(ValueError, match="4096"):
        assets.decode_launch_manifest(assets._canonical(value))


def test_v2_label_uses_existing_utf16_limit_and_pair_optional_presence():
    value = manifest()
    value["bindings"][0]["label"] = "🚀" * 60
    value["bindings"][0].update(allowedWritePaths=[], validation={})
    rows = h2.templates(value)
    assert rows[0]["validation"] == rows[1]["validation"] == {}
    assert "validation" not in rows[2]
    assert assets.decode_launch_manifest(assets._canonical(value))
    value["bindings"][0]["label"] += "🚀"
    assert assets._decode_launch_bindings(value) is None


def test_v1_bounded_code_and_optional_presence_remain_unchanged():
    value = json.loads(harness._launch_manifest_bytes())
    value.update(profiles=[{"ref": "bounded_code_change", "label": "Code"}],
                 allowedWritePaths=["src/file.py"], validation={"git_diff_check": True})
    raw = assets._canonical(value)
    assert assets.decode_launch_manifest(raw) == raw
    assert assets._decode_launch_bindings(value) == (value,)
    legacy = json.loads(harness._launch_manifest_bytes())
    del legacy["attemptLimit"]
    assert "attempt_limit" not in h2.templates(legacy)[0]


def grants_for(value=None):
    return [{"principal_scope": "1" * 64, "template": template}
            for template in h2.templates(manifest() if value is None else value)]


def test_compiler_preserves_three_exact_ordered_grants_for_one_principal():
    grants = grants_for()
    candidate = h2.compile_grants(grants)
    assert candidate.publication_document()["grants"] == grants
    assert compiler._grants({"grants": grants}) == tuple(grants)


@pytest.mark.parametrize("fault", [
    "interleaved", "native-other-workstream", "native-other-principal", "optional",
    "duplicate", "bounded-extra-workstream",
])
def test_compiler_cannot_broaden_the_pair_or_multi_workstream_read_authority(fault):
    grants = grants_for()
    if fault == "interleaved": grants.insert(1, grants.pop())
    elif fault == "native-other-workstream": grants[1]["template"]["workstream"] = "WS:Unknown"
    elif fault == "native-other-principal": grants[1]["principal_scope"] = "2" * 64
    elif fault == "optional": grants[1]["template"]["validation"] = {}
    elif fault == "duplicate": grants.append(copy.deepcopy(grants[2]))
    elif fault == "bounded-extra-workstream":
        grants[2]["template"].update(execution_profile="bounded_code_change",
                                     allowed_write_paths=["src/file.py"],
                                     validation={"git_diff_check": True})
    with pytest.raises(ValueError):
        h2.compile_grants(grants)


def test_legacy_bounded_singleton_and_distinct_principals_still_compile():
    bounded = pure.grant(execution_profile="bounded_code_change",
                         allowed_write_paths=["src/file.py"], validation={"git_diff_check": True})
    assert h2.compile_grants([bounded])
    assert h2.compile_grants([bounded, pure.grant(scope="2" * 64, workstream="WS:Other")])


def install_v2_receipt(gateway):
    path = gateway.release / assets.INSTALLED_RECEIPT
    receipt = json.loads(path.read_bytes())
    raw = assets._canonical(manifest()).decode()
    receipt["launch_config"] = raw
    receipt["launch_config_sha256"] = assets._hash(raw.encode())
    path.chmod(0o600)
    path.write_bytes(assets._canonical(receipt))
    path.chmod(0o444)
    _, document, bundle = gateway.host.qualify_launch_publication(harness.SHA, harness.TREE_SHA)
    gateway.bundle = bundle
    assert document["commission_templates"] == h2.templates(manifest())


def test_actual_owner_publishes_all_three_grants_through_one_identity_and_transaction(gateway):
    install_v2_receipt(gateway)
    before = (owner.CONTROL_CONFIG.read_bytes(), owner.WORKER_CONFIG.read_bytes())
    result = gateway.publish()
    assert result.replayed is False
    document = json.loads(owner.OS_GATEWAY_COMMISSION_GRANT.read_bytes())
    rows = document["grants"]
    assert len(rows) == 3
    assert len({row["principal_scope"] for row in rows}) == 1
    assert [row["template"] for row in rows] == list(h2.templates(manifest()))
    assert before == (owner.CONTROL_CONFIG.read_bytes(), owner.WORKER_CONFIG.read_bytes())
    assert not owner.AUTONOMY_TRANSACTION.exists()


@pytest.mark.parametrize("fault", [
    "omit-office", "omit-native", "interleaved", "workstream", "department", "scope",
])
def test_actual_owner_refuses_incomplete_or_forged_enrollment_before_effect(gateway, monkeypatch, fault):
    install_v2_receipt(gateway)
    original = gateway.host._compile_gateway_candidates

    def corrupt(*args, **kwargs):
        candidate = dict(original(*args, **kwargs))
        document = json.loads(candidate["commission_grant_bytes"])
        rows = document["grants"]
        if fault == "omit-office": rows.pop()
        elif fault == "omit-native": rows.pop(1)
        elif fault == "interleaved": rows.insert(1, rows.pop())
        elif fault == "workstream": rows[2]["template"]["workstream"] = "WS:Another"
        elif fault == "department": rows[2]["template"]["department"] = "another"
        elif fault == "scope": rows[2]["principal_scope"] = "2" * 64
        candidate["commission_grant_bytes"] = compiler.canonical(document) + b"\n"
        return candidate

    monkeypatch.setattr(gateway.host, "_compile_gateway_candidates", corrupt)
    before = tuple(path.read_bytes() if path.exists() else None for path in gateway.target_paths())
    with pytest.raises(owner.GatewayPublicationError, match="gateway_grant_invalid"):
        gateway.publish()
    assert before == tuple(path.read_bytes() if path.exists() else None for path in gateway.target_paths())
    assert not owner.AUTONOMY_TRANSACTION.exists()

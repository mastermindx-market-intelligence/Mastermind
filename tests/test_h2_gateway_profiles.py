"""H2 finite manifest -> exact grant pair, using the real joined validators.

Host publication cases reuse the incumbent disposable Root-owner fixture. That
fixture's custody/OS stubs are TESTDATA, never a live grant or identity proof.
The profile catalogs, receipt decoder, template derivation, pure compiler and
postimage verifier in these tests are the actual production implementations.
"""
from __future__ import annotations

import copy
import json

import pytest

from ops.executive_os import autonomy_control as owner
from ops.executive_os import os_gateway_publication as compiler
from ops.executive_os import os_release_assets as assets
from tests import test_os_gateway_publication as pure
from tests import test_os_gateway_publication_owner as harness
from tests.test_os_gateway_publication_owner import gateway, gateway_tmp_path


def manifest(**overrides):
    value = json.loads(harness._launch_manifest_bytes())
    value.update(attemptLimit=1, profiles=[
        {"ref": "research_only", "label": "Research only"},
        {"ref": "native_research_only", "label": "Native research only"},
    ])
    value.update(overrides)
    return value


def templates(value=None):
    return owner.ProductionGatewayPublicationHost()._gateway_templates(
        json.dumps(manifest() if value is None else value))


def pair(**common):
    return [pure.grant(attempt_limit=1, **common), pure.grant(
        execution_profile="native_research_only", attempt_limit=1, **common)]


def compile_grants(grants):
    return pure.compile_candidate(inputs=pure.qualified_inputs(
        pure.publication_document(grants=grants)))


def test_joined_catalog_and_manifest_are_real_read_only_attempt_one():
    from control_plane import ceo_request
    from integrations.executive_mcp import schemas

    assert schemas.EXECUTION_PROFILES == {
        name: ceo_request.EXECUTION_PROFILES[name]
        for name in ("research_only", "bounded_code_change")}
    assert "native_research_only" not in schemas.EXECUTION_PROFILES
    assert set(ceo_request.derive_authorities("native_research_only")) == {"READ", "RESEARCH"}
    value = manifest()
    assert assets.decode_launch_manifest(assets._canonical(value)) == assets._canonical(value)
    assert [row["execution_profile"] for row in templates(value)] == [
        "research_only", "native_research_only"]


@pytest.mark.parametrize("optional", [{}, {"allowedWritePaths": [], "validation": {}}])
def test_templates_preserve_optional_presence_and_exact_nonprofile_fields(optional):
    rows = templates(manifest(**optional))
    assert len(rows) == 2
    assert {k: v for k, v in rows[0].items() if k != "execution_profile"} == {
        k: v for k, v in rows[1].items() if k != "execution_profile"}
    assert rows[1]["attempt_limit"] == 1
    assert ("validation" in rows[1]) == ("validation" in optional)
    assert ("allowed_write_paths" in rows[1]) == ("allowedWritePaths" in optional)
    rows[0]["department"] = "different"
    assert rows[1]["department"] == "os-gateway"


def test_single_choice_legacy_output_and_compatibility_entry_unchanged():
    host = owner.ProductionGatewayPublicationHost()
    raw = harness._launch_manifest_bytes().decode()
    assert host._gateway_templates(raw) == (host._gateway_template(raw),)
    assert host._gateway_template(raw)["attempt_limit"] == 3
    with pytest.raises(owner.GatewayPublicationError):
        host._gateway_template(json.dumps(manifest()))


@pytest.mark.parametrize("change", [
    {"profiles": [{"ref": "native_research_only", "label": "Native"}]},
    {"profiles": list(reversed(manifest()["profiles"]))},
    {"profiles": [manifest()["profiles"][0]] * 2},
    {"profiles": manifest()["profiles"] + [manifest()["profiles"][0]]},
    {"projects": manifest()["projects"] * 2},
    {"attemptLimit": 2}, {"attemptLimit": True},
    {"allowedWritePaths": ["src/a.py"]},
    {"validation": {"git_diff_check": True}},
    {"validation": []}, {"unknown": "field"},
])
def test_manifest_pair_refuses_omission_order_extra_paths_tests_and_bounds(change):
    with pytest.raises(owner.GatewayPublicationError):
        templates(manifest(**change))


def test_manifest_pair_requires_explicit_attempt_one():
    value = manifest()
    del value["attemptLimit"]
    with pytest.raises(owner.GatewayPublicationError):
        templates(value)


@pytest.mark.parametrize("optional", [{}, {"allowed_write_paths": [], "validation": {}}])
def test_real_compiler_emits_exact_pair_and_preserves_legacy_distinct_scopes(optional):
    grants = pair(**optional)
    candidate = compile_grants(grants)
    published = json.loads(candidate.artifact(compiler.COMMISSION_CONFIG_PATH).content)
    assert published["grants"] == grants
    legacy = [pure.grant(), pure.grant(scope="2" * 64)]
    assert compiler._grants({"grants": legacy}) == tuple(legacy)


def test_compiler_uses_real_canonical_native_law_and_frozen_legacy_adapter(monkeypatch):
    from control_plane import ceo_request
    from integrations.executive_mcp import schemas

    canonical_profiles, legacy_profiles = [], []
    actual_normalize = ceo_request.normalize_high_level_request
    actual_validate = schemas.validate_tool_arguments

    def observed_normalize(arguments):
        canonical_profiles.append(arguments["execution_profile"])
        return actual_normalize(arguments)

    def observed_legacy(name, arguments):
        legacy_profiles.append(arguments["execution_profile"])
        return actual_validate(name, arguments)

    monkeypatch.setattr(ceo_request, "normalize_high_level_request", observed_normalize)
    monkeypatch.setattr(schemas, "validate_tool_arguments", observed_legacy)
    grants = pair()
    assert compiler._grants({"grants": grants}) == tuple(grants)
    assert legacy_profiles == ["research_only"]
    assert canonical_profiles == ["research_only", "native_research_only"]
    # Publishing a qualified template cannot open the frozen callable surface.
    with pytest.raises(schemas.GatewayError, match="authenticated App"):
        actual_validate("submit_ceo_intent", {
            **compiler.TEMPLATE_VALIDATION_ARGUMENTS, **grants[1]["template"]})


@pytest.mark.parametrize("fault", [
    "native_only", "reverse", "duplicate", "third", "separate_scope", "interleaved",
    "department", "priority", "workstream", "optional_presence", "attempt",
    "write", "validation", "extra_profile",
])
def test_compiler_refuses_every_broader_same_scope_or_native_grant(fault):
    grants = pair()
    if fault == "native_only": grants = grants[1:]
    elif fault == "reverse": grants.reverse()
    elif fault == "duplicate": grants[1] = copy.deepcopy(grants[0])
    elif fault == "third": grants.append(copy.deepcopy(grants[0]))
    elif fault == "separate_scope": grants[1]["principal_scope"] = "2" * 64
    elif fault == "interleaved": grants.insert(1, pure.grant(scope="2" * 64))
    elif fault in ("department", "workstream"):
        grants[1]["template"][fault] = "other" if fault == "department" else "WS:Other"
    elif fault == "priority": grants[1]["template"]["priority"] += 1
    elif fault == "optional_presence": grants[1]["template"]["validation"] = {}
    elif fault == "attempt":
        for grant in grants: grant["template"]["attempt_limit"] = 2
    elif fault == "write":
        for grant in grants: grant["template"]["allowed_write_paths"] = ["src/a.py"]
    elif fault == "validation":
        for grant in grants: grant["template"]["validation"] = {"git_diff_check": True}
    elif fault == "extra_profile": grants[1]["template"]["execution_profile"] = "bounded_code_change"
    with pytest.raises(ValueError):
        compile_grants(grants)


def _install_pair_receipt(gateway):
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
    assert len(document["commission_templates"]) == 2


def test_real_owner_publishes_both_exact_grants_without_control_worker_edits(gateway):
    _install_pair_receipt(gateway)
    before = (owner.CONTROL_CONFIG.read_bytes(), owner.WORKER_CONFIG.read_bytes())
    result = gateway.publish()
    assert result.replayed is False
    grant = json.loads(owner.OS_GATEWAY_COMMISSION_GRANT.read_bytes())
    rows = grant["grants"]
    assert len(rows) == 2
    assert rows[0]["principal_scope"] == rows[1]["principal_scope"]
    assert [row["template"] for row in rows] == list(templates())
    assert before == (owner.CONTROL_CONFIG.read_bytes(), owner.WORKER_CONFIG.read_bytes())
    assert not owner.AUTONOMY_TRANSACTION.exists()


@pytest.mark.parametrize("mutation", ["omit", "reverse", "duplicate", "drift", "type_drift"])
def test_actual_owner_rejects_forged_grant_postimage_before_any_effect(gateway, monkeypatch, mutation):
    _install_pair_receipt(gateway)
    original = gateway.host._compile_gateway_candidates

    def corrupt(*args, **kwargs):
        candidate = dict(original(*args, **kwargs))
        document = json.loads(candidate["commission_grant_bytes"])
        if mutation == "omit": document["grants"].pop()
        elif mutation == "reverse": document["grants"].reverse()
        elif mutation == "duplicate": document["grants"][1] = copy.deepcopy(document["grants"][0])
        elif mutation == "type_drift": document["grants"][1]["template"]["attempt_limit"] = True
        else: document["grants"][1]["template"]["priority"] += 1
        candidate["commission_grant_bytes"] = compiler.canonical(document) + b"\n"
        return candidate

    monkeypatch.setattr(gateway.host, "_compile_gateway_candidates", corrupt)
    before = tuple(path.read_bytes() if path.exists() else None for path in gateway.target_paths())
    with pytest.raises(owner.GatewayPublicationError, match="gateway_grant_invalid"):
        gateway.publish()
    assert before == tuple(path.read_bytes() if path.exists() else None for path in gateway.target_paths())
    assert not owner.AUTONOMY_TRANSACTION.exists()

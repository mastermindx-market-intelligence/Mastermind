"""Native policy preflight uses the incumbent fingerprint, never live admission."""
import hashlib
import json

import pytest

from ops.native_fabric.quota_continuity import policy_change as change
from ops.native_fabric.quota_continuity.source import fabric_policy_snapshot as owner


def policy():
    return {"version": 1, "routing": {"execute_order": ["glm", "grok"],
            "grok_expiring_priority": {"enabled": False}},
            "pools": {"glm": {"model": "glm-5.3", "enabled": False},
                      "grok": {"model": "grok-4.7", "windows": {
                          "weekly": {"limit": 100, "remaining_pct": 50,
                                     "source": "fixture", "reset_at": "2026-11-07T00:00:00Z"}}}}}


def raw(value):
    return json.dumps(value, sort_keys=True).encode()


def preview(before, after):
    source = raw(before)
    return change.preview_change(source, raw(after), expected_source_sha256=hashlib.sha256(source).hexdigest())


def test_unchanged_is_read_only_and_never_capacity_or_admission():
    value = policy()
    result = preview(value, value)
    assert result["status"] == "UNCHANGED" and result["requirements"] == []
    assert result["existing_snapshot_compatible"] is True
    assert result["current_critical_sha256"] == owner.critical_fingerprint(raw(value))
    assert result["active_bindings"] == "NOT_OBSERVED"
    assert result["account_configuration"] == "NOT_READ"
    assert result["credential_rotation"] == "EXISTING_ACCOUNT_OWNER_ONLY"
    for flag in ("credential_resolution_performed", "original_operations_rebound", "writes_applied", "activation_authorized"):
        assert result[flag] is False


def test_model_change_requires_new_generation_and_original_binding_retention():
    before, after = policy(), policy()
    after["pools"]["glm"]["model"] = "glm-5.3-flash"
    result = preview(before, after)
    assert result["status"] == "CRITICAL_POLICY_CHANGE"
    assert result["changes"]["pools"] == {"added": [], "removed": [], "changed": ["glm"]}
    assert result["existing_snapshot_compatible"] is False
    assert {"REVIEWED_NATIVE_GENERATION_REQUIRED", "DRAIN_OR_RETAIN_ACTIVE_BINDINGS",
            "RETAIN_ORIGINAL_OPERATION_GENERATIONS", "REVALIDATE_NEW_ADMISSIONS"} <= set(result["requirements"])
    with pytest.raises(ValueError, match="ROUTING_CRITICAL_POLICY_MISMATCH"):
        owner.compatible(raw(before), raw(after))


def test_added_and_removed_pools_do_not_become_qualified_or_erase_originals():
    before, after = policy(), policy()
    del after["pools"]["glm"]
    after["pools"]["new-pool"] = {"model": "candidate-only", "enabled": False}
    after["routing"]["execute_order"] = ["grok"]
    result = preview(before, after)
    assert result["changes"]["pools"] == {"added": ["new-pool"], "removed": ["glm"], "changed": []}
    assert result["changes"]["routing_changed"] is True
    assert "QUALIFY_ADDED_POOLS_AND_MODELS" in result["requirements"]
    assert "DRAIN_OR_RETAIN_ACTIVE_BINDINGS" in result["requirements"]
    assert result["activation_authorized"] is False


def test_native_owner_approved_noncritical_fields_keep_exact_semantics():
    before, after = policy(), policy()
    after["routing"]["grok_expiring_priority"]["enabled"] = True
    after["pools"]["grok"]["windows"]["weekly"].update(remaining_pct=25, source="new-observation")
    result = preview(before, after)
    assert result["status"] == "NONCRITICAL_POLICY_CHANGE"
    assert result["existing_snapshot_compatible"] is True
    assert owner.compatible(raw(before), raw(after))["critical_sha256"] == result["current_critical_sha256"]
    assert result["requirements"] == ["INCUMBENT_PUBLISHER_SOURCE_RECHECK"]
    after["pools"]["grok"]["windows"]["weekly"]["limit"] = 200
    assert preview(before, after)["existing_snapshot_compatible"] is False


def test_other_policy_changes_are_not_silently_ignored():
    before, after = policy(), policy()
    after["new_policy_section"] = {"mode": "candidate"}
    result = preview(before, after)
    assert result["changes"]["other_policy_changed"] is True
    assert result["status"] == "CRITICAL_POLICY_CHANGE"


def test_formatting_only_changes_are_not_new_capacity():
    source = raw(policy())
    result = change.preview_change(source, json.dumps(policy(), indent=2).encode(),
                                   expected_source_sha256=hashlib.sha256(source).hexdigest())
    assert result["status"] == "SOURCE_ONLY_CHANGE"
    assert result["expected_source_sha256"] != result["candidate_source_sha256"]
    assert result["existing_snapshot_compatible"] is True


@pytest.mark.parametrize("expected,code", [("f" * 64, "EXPECTED_SOURCE_REVISION_CHANGED"),
    ("not-a-digest", "EXPECTED_SOURCE_DIGEST_INVALID"), (None, "EXPECTED_SOURCE_DIGEST_INVALID")])
def test_stale_or_malformed_revision_refuses(expected, code):
    with pytest.raises(change.PolicyChangeError, match=code):
        change.preview_change(raw(policy()), raw(policy()), expected_source_sha256=expected)


@pytest.mark.parametrize("value", [b'{"pools":{},"pools":{}}', b"[]", b"x: .nan", b"x: 2026-11-06",
    b"!!python/object/apply:os.system [echo not-executed]", b"not: [valid", b"\xff", b""])
def test_invalid_documents_are_fixed_non_disclosing_refusals(value):
    with pytest.raises(change.PolicyChangeError) as raised:
        change.observe_policy(value)
    assert str(raised.value) in {"POLICY_OWNER_VALIDATION_REFUSED", "POLICY_POOL_SHAPE_INVALID",
                                 "POLICY_INPUT_OVER_BUDGET_OR_INVALID"}


@pytest.mark.parametrize("value", [b"x: &x [*x]", b"x: &x {}\ny: {<<: *x}", b"x: " + b"[" * 33 + b"0" + b"]" * 33])
def test_graph_is_bounded_before_owner_construction(value, monkeypatch):
    monkeypatch.setattr(owner, "parse_policy", lambda _: pytest.fail("unsafe graph reached constructor"))
    with pytest.raises(change.PolicyChangeError, match="POLICY_GRAPH_REFUSED"):
        change.observe_policy(value)


@pytest.mark.parametrize("location", ["api_key", "password", "authorization", "description"])
def test_known_credential_material_is_not_fingerprinted_or_returned(location, monkeypatch):
    value = policy()
    value["pools"]["glm"][location] = "Bearer synthetic-private-material"
    monkeypatch.setattr(change.hashlib, "sha256", lambda *_: pytest.fail("credential material hashed"))
    with pytest.raises(change.PolicyChangeError, match="CREDENTIAL_MATERIAL_REFUSED"):
        change.observe_policy(raw(value))


def test_escaped_invalid_unicode_is_a_fixed_refusal():
    value = policy()
    value["description"] = "\ud800"
    with pytest.raises(change.PolicyChangeError, match="POLICY_OWNER_VALIDATION_REFUSED"):
        change.observe_policy(raw(value))


def test_identifier_and_pool_count_bounds():
    value = policy()
    value["pools"]["/not/a/pool"] = {}
    with pytest.raises(change.PolicyChangeError, match="POLICY_POOL_SHAPE_INVALID"):
        change.observe_policy(raw(value))
    value = policy()
    value["pools"].update({f"pool-{i}": {} for i in range(change.MAX_POOLS)})
    with pytest.raises(change.PolicyChangeError, match="POLICY_POOL_SHAPE_INVALID"):
        change.observe_policy(raw(value))


def test_paths_never_write_inputs_or_create_state_and_refuse_symlink(tmp_path):
    # Isolate operator-owned inputs from pytest/plugin bookkeeping in tmp_path.
    policy_dir = tmp_path / "policy_inputs"
    policy_dir.mkdir()
    current, candidate = policy_dir / "current.yaml", policy_dir / "candidate.yaml"
    current.write_bytes(raw(policy()))
    candidate.write_bytes(raw(policy()))
    before = {p.name: p.read_bytes() for p in policy_dir.iterdir()}
    result = change.preview_paths(current, candidate, expected_source_sha256=hashlib.sha256(current.read_bytes()).hexdigest())
    assert result["status"] == "UNCHANGED"
    assert {p.name: p.read_bytes() for p in policy_dir.iterdir()} == before
    link = policy_dir / "link.yaml"
    link.symlink_to(current)
    with pytest.raises(change.PolicyChangeError, match="POLICY_SOURCE_UNAVAILABLE"):
        change.observe_path(link)


@pytest.mark.parametrize("selected", ["current", "candidate"])
def test_source_change_during_validation_is_not_a_valid_preview(tmp_path, monkeypatch, selected):
    paths = {name: tmp_path / (name + ".yaml") for name in ("current", "candidate")}
    for path in paths.values():
        path.write_bytes(raw(policy()))
    original = change.preview_change
    def moving(*args, **kwargs):
        result = original(*args, **kwargs)
        paths[selected].write_bytes(raw(policy()) + b"\n")
        return result
    monkeypatch.setattr(change, "preview_change", moving)
    with pytest.raises(change.PolicyChangeError, match="POLICY_SOURCE_CHANGED"):
        change.preview_paths(paths["current"], paths["candidate"], expected_source_sha256=hashlib.sha256(raw(policy())).hexdigest())


def test_cli_uses_native_owner_and_sanitizes_failure(tmp_path, capsys):
    path = tmp_path / "public-policy.yaml"
    path.write_bytes(raw(policy()))
    assert change.main(["inspect", "--policy", str(path)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["configured_pool_ids"] == ["glm", "grok"]
    assert result["critical_sha256"] == owner.critical_fingerprint(path.read_bytes())
    assert change.main(["preview", "--current-policy", str(path), "--candidate-policy", str(path),
                        "--expected-source-sha256", result["source_sha256"]]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "UNCHANGED"
    assert change.main(["inspect", "--policy", str(tmp_path / "missing-private-path")]) == 2
    failure = capsys.readouterr().out
    assert "missing-private-path" not in failure
    assert json.loads(failure)["writes_applied"] is False

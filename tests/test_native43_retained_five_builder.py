"""Exact native43 retained-five, opt-in source-only cohort.

Only disposable source stages are constructed. No native CURRENT, publisher,
provider credential, live policy, or installed service is accessed.
"""
from contextlib import redirect_stdout, redirect_stderr
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
from unittest import mock

import pytest


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "ops/native_fabric/quota_continuity/rollout/build_review_stage.py"
DONORS = BUILDER.parent / "provider_application/native43_retained"


@pytest.fixture(scope="module")
def retained_stage(tmp_path_factory):
    spec = importlib.util.spec_from_file_location("_native43_retained_five_builder_test", BUILDER)
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    output = tmp_path_factory.mktemp("native43-retained-five")
    args = [
        "build_review_stage", "--output", str(output),
        "--include-provider-plan-application",
        "--include-provider-plan-remote-placement",
        "--include-provider-plan-maintenance-guard",
        "--include-provider-plan-terminal-diagnostics",
        "--include-provider-plan-memory-support",
        "--include-provider-plan-fleet-launch-repair",
        "--include-go-application", "--include-application-http",
        "--include-application-glm", "--include-native43-retained-five",
    ]
    with mock.patch.object(sys, "argv", args), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        builder.main()
    return builder, output


def test_selected43_donors_are_explicit_and_source_pinned(retained_stage):
    builder, output = retained_stage
    assert len(builder.NATIVE43_RETAINED_MEMBERS) == 5
    manifest = json.loads((output / "native-manifest.json").read_bytes())
    inventory = json.loads((output / "native-source-inventory.json").read_bytes())
    assert len(manifest) == len(inventory["files"]) == 126
    assert builder._manifest_digest(manifest) == builder.NATIVE43_RETAINED_COMPOSED_SHA256
    for relative, (replaced, retained) in builder.NATIVE43_RETAINED_MEMBERS.items():
        donor = DONORS / Path(relative).name
        raw = donor.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == retained != replaced
        staged = (output / "native-code-stage" / relative).read_bytes()
        assert staged == raw
        assert inventory["files"][relative]["sha256"] == retained
        assert inventory["files"][relative]["bytes"] == len(raw)
        assert inventory["files"][relative]["composition"]["preimage_sha256"] == replaced
    support = (output / "native-code-stage/ext/support_bundle.py").read_bytes()
    assert b"NATIVE_POLICY_PUBLICATION_API" in support
    assert b"publish_compatible" in support
    assert b"policy_publication_status" in support


def test_full_cohort_inverse_accepted_mixed_cohort_refused(retained_stage):
    builder, output = retained_stage
    before = builder.provider_fleet_launch_repair_files()
    after = json.loads((output / "native-manifest.json").read_bytes())
    original_before, original_after = dict(before), dict(after)
    builder.validate_go_source_transition(before, after)
    assert before == original_before and after == original_after
    assert builder._normalize_native43_retained_successor(before, after) is not None
    mixed = dict(after)
    name = "ext/native_plan_worker.py"
    mixed[name] = builder.NATIVE43_RETAINED_MEMBERS[name][0]
    with pytest.raises(ValueError, match="native43 retained-five exact whole-source cohort differs"):
        builder.validate_go_source_transition(before, mixed)
    altered = dict(after)
    altered["ext/support_bundle.py"] = "0" * 64
    with pytest.raises(ValueError, match="native43 retained-five exact whole-source cohort differs"):
        builder.validate_go_source_transition(before, altered)


def test_retained_five_go_dependency_parent_is_exact_and_view_only(retained_stage):
    """The exact published126 Go dependencies project to the reviewed fleet119."""
    builder, output = retained_stage
    after = json.loads((output / "native-manifest.json").read_bytes())
    base = builder._application_base(after)
    original_base = dict(base)
    assert len(base) == 119
    parent = builder.before_quota_reset_recovery(base)
    original_parent = dict(parent)
    assert builder._manifest_digest(parent) == builder.NATIVE43_GO_DEPENDENCY_PARENT_SHA256
    historical = builder._project_native43_go_dependency_parent(parent)
    assert historical is not parent
    assert builder._manifest_digest(historical) == builder.NATIVE43_GO_DEPENDENCY_HISTORICAL_SHA256
    record, _, _ = builder.provider_fleet_launch_repair_record()
    assert builder._manifest_digest(historical) == record["application_after_manifest_sha256"]
    assert set(name for name in parent if parent[name] != historical[name]) == set(
        builder.NATIVE43_RETAINED_MEMBERS)
    assert builder.before_provider_application(parent)
    assert parent == original_parent and base == original_base
    component = json.loads((output / "external-go-component/component.json").read_bytes())
    candidates = {name: row["sha256"] for name, row in component["dependencies"].items()}
    staged = builder.go_staged_dependency_hashes(base, candidates)
    assert staged == component["native_stage_dependencies"]
    builder.validate_go_base_manifest(base, staged)
    assert parent == original_parent and base == original_base


@pytest.mark.parametrize("member", [
    "ext/experiential_bridge.py", "ext/experiential_host_context.py",
    "ext/experiential_plan_policy.py", "ext/experiential_transport.py",
    "ext/native_plan_worker.py",
])
def test_retained_five_go_dependency_mixed_119_refused(retained_stage, member):
    builder, output = retained_stage
    after = json.loads((output / "native-manifest.json").read_bytes())
    parent = builder.before_quota_reset_recovery(builder._application_base(after))
    mixed = dict(parent)
    mixed[member] = builder.NATIVE43_RETAINED_MEMBERS[member][0]
    assert builder._manifest_digest(mixed) != builder.NATIVE43_GO_DEPENDENCY_PARENT_SHA256
    with pytest.raises(ValueError):
        builder.before_provider_fleet_launch_repair(mixed)
    with pytest.raises(ValueError):
        builder.before_provider_application(mixed)


def test_retained_five_installer_validates_real_go_component(retained_stage):
    """The actual installed-owner verifier consumes the complete staged source."""
    builder, output = retained_stage
    # Reuse the incumbent installer test's isolated module binding; never touch
    # a physical generation, selector, account, secret or service.
    sys.path.insert(0, str(BUILDER.parents[1] / "tests"))
    from test_go_native_stage import installer
    manifest = json.loads((output / "native-manifest.json").read_bytes())
    component = json.loads((output / "external-go-component/component.json").read_bytes())
    result = installer._go_component(
        output / "external-go-component", Path(component["stable_ext"]), manifest)
    assert len(result) == 3
    assert result[0] == hashlib.sha256(
        (output / "external-go-component/component.json").read_bytes()).hexdigest()

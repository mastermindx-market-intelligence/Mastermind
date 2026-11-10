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

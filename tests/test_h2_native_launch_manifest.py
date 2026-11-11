"""Pure public build-manifest mirror; no build, host or secret input."""
import copy
import json

import pytest

from ops.executive_os.os_release_assets import _decode_launch_binding, decode_launch_manifest


def manifest():
    return {"v": 1, "workstream": "WS:H2-FIXTURE", "priority": 0, "attemptLimit": 1,
            "projects": [{"ref": "executive-infrastructure", "label": "Infrastructure"}],
            "profiles": [{"ref": "research_only", "label": "Research"},
                         {"ref": "native_research_only", "label": "Direct native research"}]}


def test_explicit_native_catalog_roundtrips_exact_canonical_bytes():
    value = manifest()
    raw = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    assert decode_launch_manifest(raw) == raw
    assert _decode_launch_binding(value) == value


@pytest.mark.parametrize("fault", ["absent-attempt", "two-attempts", "bool-attempt", "write", "test", "unknown", "selector", "native-only", "reverse-order", "extra-project"])
def test_native_catalog_refuses_nonread_grant_or_selector(fault):
    value = copy.deepcopy(manifest())
    if fault == "absent-attempt": value.pop("attemptLimit")
    if fault == "two-attempts": value["attemptLimit"] = 2
    if fault == "bool-attempt": value["attemptLimit"] = True
    if fault == "write": value["allowedWritePaths"] = ["research/change.md"]
    if fault == "test": value["validation"] = {"git_diff_check": True}
    if fault == "unknown": value["profiles"][1]["ref"] = "native-anything"
    if fault == "selector": value["worker_id"] = "codex-01"
    if fault == "native-only": value["profiles"] = value["profiles"][1:]
    if fault == "reverse-order": value["profiles"].reverse()
    if fault == "extra-project": value["projects"].append({"ref": "extra-project", "label": "Other"})
    assert _decode_launch_binding(value) is None


def test_legacy_research_manifest_keeps_its_existing_optional_attempt_behavior():
    value = manifest()
    value["profiles"] = value["profiles"][:1]
    value.pop("attemptLimit")
    assert _decode_launch_binding(value) == value

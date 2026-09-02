from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = ROOT / ".github/workflows/codeintel-experiment-bundle.yml"

EXPECTED_ACTIONS = {
    "actions/checkout": "3d3c42e5aac5ba805825da76410c181273ba90b1",
    "actions/setup-python": "5fda3b95a4ea91299a34e894583c3862153e4b97",
    "actions/upload-artifact": "043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
    "actions/download-artifact": "3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c",
}


def _workflow() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def test_workflow_is_manual_closed_surface_with_exact_action_pins():
    source = _workflow()

    assert "workflow_dispatch:" in source
    assert "pull_request:" not in source
    assert "push:" not in source
    assert "schedule:" not in source
    assert "workflow_call:" not in source
    input_block = source.split("\npermissions:", maxsplit=1)[0]
    assert re.findall(r"^ {6}([a-z_]+):", input_block, re.MULTILINE) == [
        "mode",
        "consumer_sha",
        "consumer_tree_sha",
        "operation_key",
    ]
    uses = dict(re.findall(r"uses:\s+([^@\s]+)@([0-9a-f]{40})", source))
    assert uses == EXPECTED_ACTIONS
    assert "actions/cache" not in source
    assert re.search(r"\b(unshare -n)\b", source)
    assert "unshare -n -- /usr/bin/env -i PATH=/usr/bin:/bin true" in source
    assert "if unshare -n" not in source
    assert source.index("Validate closed inputs, consumer identity, and B0 lock") < source.index(
        "Checkout exact consumer source"
    )


def test_workflow_has_no_ambient_package_installer_or_caller_selected_execution_surface():
    source = _workflow()

    for forbidden in ("npx ", "npm install", "pip install", "apt-get", "${{ inputs.command", "${{ inputs.path", "${{ inputs.runner", "${{ inputs.image", "${{ inputs.credential", "${{ inputs.cache"):
        assert forbidden not in source
    assert "${{ inputs.mode }}" in source
    assert "${{ inputs.consumer_sha }}" in source
    assert "${{ inputs.consumer_tree_sha }}" in source
    assert "${{ inputs.operation_key }}" in source

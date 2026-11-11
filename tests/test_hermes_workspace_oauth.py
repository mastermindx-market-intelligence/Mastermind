"""Exact source transformation and incumbent release-owner qualification.

No OAuth SDK, host, account, socket or daemon is used by these source checks.
The separately pinned engine_cases.py executes the actual OAuth/HTTP stack.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from integrations.hermes_qualification.workspace_oauth_privacy import qualify
from ops.executive_os import native_gateway_sources as source


def originals():
    provenance = json.loads((qualify.ROOT / "fixtures/provenance.json").read_bytes())
    output = {}
    for path, row in provenance["files"].items():
        data = (qualify.ROOT / "fixtures" / row["fixture"]).read_bytes()
        assert len(data) == row["bytes"]
        assert hashlib.sha256(data).hexdigest() == row["sha256"]
        assert hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest() == row["git_blob"]
        output[path] = data
    return {path: output[path] for path in qualify.PATHS}


def test_complete_single_transformation_preserves_accepted_privacy_and_release_custody():
    inputs = originals()
    saved = deepcopy(inputs)
    output = qualify.prepare_sources(inputs)
    assert inputs == saved and set(output) == set(source.WORKSPACE_OAUTH_DERIVATION_POSTIMAGES)
    assert {path: qualify.digest(data) for path, data in output.items()} == source.WORKSPACE_OAUTH_DERIVATION_POSTIMAGES
    assert all(qualify.digest(output[path]) == digest for path, digest in source.PRIVACY_DERIVATION_POSTIMAGES.items())
    assert qualify.manifest()["patch_sha256"] == source.WORKSPACE_OAUTH_DERIVATION_PATCH
    assert qualify.digest((qualify.ROOT / "UPSTREAM_LICENSE").read_bytes()) == source.PRIVACY_LICENSE_SHA256
    root = Path(__file__).resolve().parents[1]
    owner = SimpleNamespace(root=root, source=lambda relative: (root / relative).read_bytes(), check=lambda: None)
    assert source._guard(owner, source.WORKSPACE_OAUTH_DERIVATION_KIND) is qualify


@pytest.mark.parametrize("path", qualify.PATHS)
def test_any_changed_preimage_is_refused(path):
    inputs = originals()
    inputs[path] += b"\n# unselected source\n"
    with pytest.raises(qualify.QualificationError, match="^DONOR_PREIMAGE_MISMATCH$"):
        qualify.prepare_sources(inputs)


@pytest.mark.parametrize("change", ["new_vendor_file", "missing_file", "stacked_patch"])
def test_source_membership_and_patch_stacking_stay_closed(change):
    inputs = originals()
    if change == "new_vendor_file":
        inputs["tools/another_oauth_owner.py"] = b""
    elif change == "missing_file":
        inputs.pop("tools/mcp_oauth_provider.py")
    else:
        inputs = qualify.prepare_sources(inputs)
    with pytest.raises(qualify.QualificationError):
        qualify.prepare_sources(inputs)


def test_modified_patch_cannot_requalify_original_sources(tmp_path, monkeypatch):
    inputs = originals()
    for name in ("manifest.json", "guard.patch"):
        (tmp_path / name).write_bytes((qualify.ROOT / name).read_bytes())
    with (tmp_path / "guard.patch").open("ab") as output:
        output.write(b"\n# unselected patch\n")
    monkeypatch.setattr(qualify, "ROOT", tmp_path)
    with pytest.raises(qualify.QualificationError, match="^PATCH_DIGEST_MISMATCH$"):
        qualify.prepare_sources(inputs)


def test_held_owner_rejects_unmatched_data_bytes_before_qualifier(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    owner = SimpleNamespace(root=root, source=lambda relative: b"unheld bytes", check=lambda: None)
    with pytest.raises(source.NativeSourceRefusal):
        source._guard(owner, source.WORKSPACE_OAUTH_DERIVATION_KIND)


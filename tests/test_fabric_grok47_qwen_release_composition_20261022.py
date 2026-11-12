"""Native seq16 Grok 4.7 + Qwen 429 repair source composition.

The accepted Grok 4.7 overlay is canonical in merged Mastermind PR #1691.
This verifies that adding Qwen selection fixes does not silently revert it.
No live generation, provider, account, bridge, lease or runner is touched.

2026-10-22 release-composition extension: the builder first checks all nine
exact protected overlay bases, then substitutes the four
previously-reviewed candidate-forward bytes plus three new finite-runtime
forward candidates (not independently reviewed or installed). This file adds the closed
protected four-name historical map plus three bounded new names, absolute SHA-256 pinning for the four
protected Qwen files, symlinked-candidate and tampered-accepted-base
negatives (typed mismatch, no completed manifest). Existing guarded runtime
suites qualify freshness and caller UTC behavior separately. Every negative
fixture is cloned under tmp_path; repository state is only ever read.

S14 adds only the exact reviewed artifact-delivery forward composition. Its
protected overlay base remains independently pinned and checked before staging.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

REPO = Path(__file__).resolve().parents[1]
NATIVE = REPO / "ops/native_fabric/quota_continuity"
GROK = REPO / "ops/native_fabric/grok47/overlay"
NAMES = (
    "artifact_delivery.py", "fabric_operator_client.py",
    "fabric_operator_contract.py", "native_remote.py", "pick.py",
    "remote_sub.sh", "remote_sub_exec.py", "remote_sub_helpers.py", "sub.sh",
)
QWEN = ("bailian_keys.py", "lease_broker.py",
        "glm_host_account_probe.py", "glm_host_account_source.py")
HISTORICAL_FORWARD_NAMES = ("pick.py", "remote_sub.sh", "remote_sub_exec.py", "remote_sub_helpers.py")
LONG_HORIZON_FORWARD_NAMES = ("fabric_operator_contract.py", "native_remote.py", "sub.sh")
# Current delivery forward composes S14 with the exact reviewed advertised
# recovery. The historical nine-source Grok map stays unchanged below.
S14_FORWARD_DIGESTS = {
    "artifact_delivery.py": "6848a4bfa60708a85dcea130d5b0be8f0d56bba0386b27bf3b5fd355d433494d",
}
FORWARD_NAMES = HISTORICAL_FORWARD_NAMES + LONG_HORIZON_FORWARD_NAMES + tuple(S14_FORWARD_DIGESTS)
BASE_ONLY_OVERLAY_NAMES = ("fabric_operator_client.py",)
PROTECTED_QWEN_SOURCE_DIGESTS = {
    "bailian_keys.py":
        "a6a775dd3204c4e508dedf9a892d80d3dd42069e88c1e9462c049e9cedbee085",
    "glm_host_account_probe.py":
        "2dbbdf5c7585b45c34269d8d19a8eb68c3919423b91164a024d8a558b42d3325",
    "glm_host_account_source.py":
        "34501b394c24fffd13374894c2c375d2b123c28580ed02335c5e7e19a29d83ab",
    "lease_broker.py":
        "a2847a29abe590cb168c2cd8ae34e0b1c3222b6e92ab4c00f252a342d56e6406",
}

# Keep the exact historical Qwen map above. The restrictive context-reader
# join and the composed application-turn/fair-share broker each have one exact
# forward digest; remaining Qwen payloads retain their original bytes.
REVIEWED_QWEN_FORWARD_DIGESTS = {
    "lease_broker.py": "5dedf63c1c8f2a7c098ca6669d509971e5118a4693f8341d27c2f17f8b0b836a",
    "glm_host_account_source.py": "cf2be3503d31d8b3f5d2098ebab5d6c2e61e46842468db73baf2f7d8f8b70855",
}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_builder():
    file = NATIVE / "rollout/build_review_stage.py"
    spec = importlib.util.spec_from_file_location("qwen_grok_stage_builder", file)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded



def read_current_source_fixture():
    file = NATIVE / "rollout/test_native_current_source.py"
    spec = importlib.util.spec_from_file_location("grok_current_source_fixture", file)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def current_source_closure():
    """Bind current candidates separately from immutable historical overlays."""
    raw = (NATIVE / "rollout/native-manifest.json").read_bytes()
    # Current host-pull successor; historical overlay pins remain independent.
    assert digest(raw) == "22905ae361e7076226aa239e947553433274c56f0c3db73c51cad0a317754ada"
    manifest, inventory = read_current_source_fixture().expected_current_source_closure(NATIVE)
    assert len(manifest) == len(inventory["files"]) == 107
    assert set(manifest) == set(inventory["files"])
    for name, sha in manifest.items():
        assert inventory["files"][name]["sha256"] == sha
    collector = "ext/original_delivery_collector.py"
    assert manifest[collector] == "5219fb35f940831752638d348feefd92d02ad00ba9394fa9d66cf1d281091a9d"
    assert inventory["files"][collector]["bytes"] == 106002
    assert inventory["files"][collector]["source"] == "candidate/original_delivery_collector.py"
    return manifest, inventory


def test_grok47_merged_source_digest_is_pinned():
    builder = read_builder()
    assert set(builder.GROK47_MERGED_SOURCE_DIGESTS) == set(NAMES)
    manifest, inventory = current_source_closure()
    assert len(manifest) == len(inventory["files"]) == len(read_builder().BASE_FILES | read_builder().ADDITIONS) + 1
    for name in NAMES:
        path = GROK / name
        assert path.is_file() and not path.is_symlink()
        expected = builder.GROK47_MERGED_SOURCE_DIGESTS[name]
        assert digest(path.read_bytes()) == expected
        forward = builder.GROK47_CANDIDATE_COMPOSITION_DIGESTS.get(name)
        if forward is not None:
            assert digest((NATIVE / "candidate" / name).read_bytes()) == manifest["ext/" + name]
        published = manifest["ext/" + name] if forward else expected
        source = "candidate/" + name if forward else "../grok47/overlay/" + name
        assert manifest["ext/" + name] == published
        assert inventory["files"]["ext/" + name]["sha256"] == published
        assert inventory["files"]["ext/" + name]["source"] == source
    for name in QWEN:
        blob = (NATIVE / "candidate" / name).read_bytes()
        assert manifest["ext/" + name] == digest(blob)
        assert inventory["files"]["ext/" + name]["source"] == "candidate/" + name


def test_rebuild_staged_manifest_is_exact(tmp_path):
    stage = tmp_path / "stage"
    result = subprocess.run(
        [sys.executable, str(NATIVE / "rollout/build_review_stage.py"),
         "--output", str(stage)],
        text=True, capture_output=True, timeout=25,
    )
    assert result.returncode == 0, result.stderr
    builder = read_builder()
    hashes = read_current_source_fixture().verify_current_stage(
        stage, NATIVE,
        {"ext/" + name for name in builder.BASE_FILES | builder.ADDITIONS} | {"pool"})
    assert len(hashes) == len(read_builder().BASE_FILES | read_builder().ADDITIONS) + 1
    for path, digest_value in hashes.items():
        assert digest((stage / "native-code-stage" / path).read_bytes()) == digest_value


# ---------------------------------------------------------------------------
# Converge 2121 broker-busy epoch twins (probe-law relocation block).
#
# Everything above is byte-identical to origin/master and still exercises the
# default (non-busy) composition. The twins below re-run the same composition
# law against the busy-scoped epoch: closures resolve through
# expected_broker_busy_closure / verify_broker_busy_stage and the busy
# directory publishes the six AUTO pre-release members.
# ---------------------------------------------------------------------------

BROKER_BUSY_LEASE_BROKER_SHA256 = "5af51da91f8c13cedca525a906d211e0e03f53cdd19c041d638d35d85e60a24c"
BROKER_BUSY_PREIMAGE_ANCHOR = "a84752dc40598bbf8411d7b992d32cda6c76156d534c4925c2eca5083f097360"
BROKER_BUSY_PICKER_SHA256 = "c433384faab5862a05dcc4bd84273ee1b5aa9293271166079c2874375e46a057"


def read_broker_busy_source_fixture():
    file = NATIVE / "rollout/test_native_broker_busy_source.py"
    spec = importlib.util.spec_from_file_location("grok_broker_busy_source_fixture", file)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def current_broker_busy_closure():
    """Bind current busy-epoch members separately from historical overlays."""
    raw = (NATIVE / "rollout/native-manifest.json").read_bytes()
    # Current host-pull successor; historical overlay pins remain independent.
    assert digest(raw) == "22905ae361e7076226aa239e947553433274c56f0c3db73c51cad0a317754ada"
    manifest, inventory = read_broker_busy_source_fixture().expected_broker_busy_closure(NATIVE)
    assert len(manifest) == len(inventory["files"]) == 107
    assert set(manifest) == set(inventory["files"])
    for name, sha in manifest.items():
        assert inventory["files"][name]["sha256"] == sha
    collector = "ext/original_delivery_collector.py"
    assert manifest[collector] == "5219fb35f940831752638d348feefd92d02ad00ba9394fa9d66cf1d281091a9d"
    assert inventory["files"][collector]["bytes"] == 106002
    assert inventory["files"][collector]["source"] == "candidate/original_delivery_collector.py"
    return manifest, inventory




def test_busy_merged_source_digest_is_pinned():
    builder = read_builder()
    fixture = read_broker_busy_source_fixture()
    assert set(builder.GROK47_MERGED_SOURCE_DIGESTS) == set(NAMES)
    manifest, inventory = current_broker_busy_closure()
    assert len(manifest) == len(inventory["files"]) == len(read_builder().BASE_FILES | read_builder().ADDITIONS) + 1
    for name in NAMES:
        path = GROK / name
        assert path.is_file() and not path.is_symlink()
        expected = builder.GROK47_MERGED_SOURCE_DIGESTS[name]
        assert digest(path.read_bytes()) == expected
        forward = builder.GROK47_CANDIDATE_COMPOSITION_DIGESTS.get(name)
        # The six AUTO pre-release members publish from their busy-scoped
        # directory; every other forward member publishes its candidate/ bytes.
        source = (("../grok47/overlay/" if forward is None else
                   (fixture.BROKER_BUSY_SOURCE_DIRECTORY if name in fixture.BUSY_CORE
                    else "candidate") + "/") + name)
        if forward is not None:
            # The published source bytes carry exactly the published digest;
            # the un-converged default candidate keeps the seal pin.
            assert digest((NATIVE / source).read_bytes()) == manifest["ext/" + name]
        published = manifest["ext/" + name] if forward else expected
        assert manifest["ext/" + name] == published
        assert inventory["files"]["ext/" + name]["sha256"] == published
        assert inventory["files"]["ext/" + name]["source"] == source
    for name in QWEN:
        source = ((fixture.BROKER_BUSY_SOURCE_DIRECTORY if name in fixture.BUSY_CORE
                   else "candidate") + "/" + name)
        blob = (NATIVE / source).read_bytes()
        assert manifest["ext/" + name] == digest(blob)
        assert inventory["files"]["ext/" + name]["source"] == source


def test_busy_rebuild_staged_manifest_is_exact(tmp_path):
    stage = tmp_path / "stage"
    result = subprocess.run(
        [sys.executable, str(NATIVE / "rollout/build_review_stage.py"),
         "--output", str(stage), "--broker-busy-epoch"],
        text=True, capture_output=True, timeout=25,
    )
    assert result.returncode == 0, result.stderr
    builder = read_builder()
    hashes = read_broker_busy_source_fixture().verify_broker_busy_stage(
        stage, NATIVE,
        {"ext/" + name for name in builder.BASE_FILES | builder.ADDITIONS} | {"pool"})
    assert len(hashes) == len(read_builder().BASE_FILES | read_builder().ADDITIONS) + 1
    for path, digest_value in hashes.items():
        assert digest((stage / "native-code-stage" / path).read_bytes()) == digest_value


@pytest.mark.parametrize("name", ("artifact_delivery.py", "pick.py"))
def test_busy_builder_refuses_tampered_overlay_base_despite_valid_forward(tmp_path, name):
    """A valid forward candidate never excuses a changed accepted overlay base."""
    clone_root, candidate_native = _clone_composition_fixture(tmp_path)
    builder = read_builder()
    fixture = read_broker_busy_source_fixture()
    manifest, _ = current_broker_busy_closure()
    for forward in FORWARD_NAMES:
        # The published epoch source carries exactly the published digest: the
        # six AUTO members publish from the busy-scoped directory, every other
        # forward member from candidate/.
        source = ((fixture.BROKER_BUSY_SOURCE_DIRECTORY if forward in fixture.BUSY_CORE
                   else "candidate") + "/" + forward)
        assert digest((candidate_native / source).read_bytes()) == manifest["ext/" + forward]
    changed = clone_root / "grok47/overlay" / name
    changed.write_bytes(changed.read_bytes() + b"\n# tampered accepted overlay base\n")
    stage = tmp_path / "stage"
    proc = subprocess.run(
        [sys.executable, str(candidate_native / "rollout/build_review_stage.py"),
         "--output", str(stage)],
        capture_output=True, text=True, timeout=25,
    )
    assert proc.returncode != 0
    assert "accepted Grok 4.7 source digest mismatch: " + name in proc.stderr
    assert not (stage / "native-manifest.json").exists()
    assert not (stage / "native-source-inventory.json").exists()


def test_busy_protected_qwen_files_and_exact_context_reader_forward():
    """The four protected Qwen files are pinned to absolute source digests."""
    builder = read_builder()
    assert set(PROTECTED_QWEN_SOURCE_DIGESTS) == set(QWEN)
    assert len(set(PROTECTED_QWEN_SOURCE_DIGESTS.values())) == 4
    assert not set(PROTECTED_QWEN_SOURCE_DIGESTS) & set(NAMES)
    assert not set(PROTECTED_QWEN_SOURCE_DIGESTS) & set(builder.GROK47_CANDIDATE_COMPOSITION_DIGESTS)
    fixture = read_broker_busy_source_fixture()
    manifest, inventory = current_broker_busy_closure()
    assert set(REVIEWED_QWEN_FORWARD_DIGESTS) == {"glm_host_account_source.py", "lease_broker.py"}
    assert builder.BROKER_BUSY_PREIMAGES["lease_broker.py"] == BROKER_BUSY_PREIMAGE_ANCHOR
    assert builder.BROKER_BUSY_DIGESTS["lease_broker.py"] == BROKER_BUSY_LEASE_BROKER_SHA256
    # The busy broker publishes from its busy-scoped source; the default
    # candidate keeps master's reviewed GLM-composed successor.
    busy_broker = digest((NATIVE / fixture.BROKER_BUSY_SOURCE_DIRECTORY / "lease_broker.py").read_bytes())
    assert busy_broker == BROKER_BUSY_LEASE_BROKER_SHA256
    assert digest((NATIVE / "candidate/lease_broker.py").read_bytes()) == builder.GLM_CORE_DIGESTS["lease_broker.py"]
    for name, original in sorted(PROTECTED_QWEN_SOURCE_DIGESTS.items()):
        expected = REVIEWED_QWEN_FORWARD_DIGESTS.get(name, original)
        assert name in builder.BASE_FILES
        source = ((fixture.BROKER_BUSY_SOURCE_DIRECTORY if name in fixture.BUSY_CORE
                   else "candidate") + "/" + name)
        candidate = NATIVE / source
        assert candidate.is_file() and not candidate.is_symlink()
        if name != "lease_broker.py":
            assert manifest["ext/" + name] == expected
        current = manifest["ext/" + name]
        assert digest(candidate.read_bytes()) == current
        row = inventory["files"]["ext/" + name]
        assert row["sha256"] == current
        assert row["source"] == source
        assert row["installed_preimage_sha256"]


def _current_broker_busy_closure_fixture(root):
    fixture = read_broker_busy_source_fixture()
    relatives = (
        "rollout/native-manifest.json", "rollout/native-source-inventory.json",
        *(fixture.GLM_CORE_SOURCE_DIRECTORY + "/" + name
          for name in fixture.GLM_CORE_PREIMAGE_SOURCES),
        *(fixture.BROKER_BUSY_SOURCE_DIRECTORY + "/" + name
          for name in fixture.BUSY_CORE),
    )
    for relative in relatives:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((NATIVE / relative).read_bytes())
    return root


def test_busy_current_projection_preserves_all_other_historical_rows(tmp_path):
    fixture = read_broker_busy_source_fixture()
    native = _current_broker_busy_closure_fixture(tmp_path / "source")
    baseline = json.loads((native / "rollout/native-manifest.json").read_bytes())
    baseline_inventory = json.loads((native / "rollout/native-source-inventory.json").read_bytes())
    manifest, inventory = fixture.expected_broker_busy_closure(native)
    # Only the six busy members advance their digests; the two GLM core
    # members keep their preimage digests but rebind source (and bytes) to
    # the sealed preimage directory.
    busy = {"ext/" + name for name in fixture.BUSY_CORE}
    glm = {"ext/" + name for name in fixture.GLM_CORE_PREIMAGE_SOURCES}
    assert {name for name in manifest if manifest[name] != baseline[name]} == busy
    assert {name for name in inventory["files"]
            if inventory["files"][name] != baseline_inventory["files"][name]} == busy | glm
    assert len(manifest) == len(inventory["files"]) == 107


def test_busy_current_closure_refuses_changed_baseline_or_candidate(tmp_path):
    fixture = read_broker_busy_source_fixture()
    relatives = [
        "rollout/native-manifest.json", "rollout/native-source-inventory.json",
        *(fixture.GLM_CORE_SOURCE_DIRECTORY + "/" + name
          for name in fixture.GLM_CORE_PREIMAGE_SOURCES),
        *(fixture.BROKER_BUSY_SOURCE_DIRECTORY + "/" + name
          for name in fixture.BUSY_CORE),
    ]
    for index, relative in enumerate(relatives):
        native = _current_broker_busy_closure_fixture(tmp_path / str(index))
        target = native / relative
        target.write_bytes(target.read_bytes() + b"\n# unqualified\n")
        with pytest.raises(AssertionError):
            fixture.expected_broker_busy_closure(native)


def test_busy_current_closure_refuses_symlinked_core_even_with_exact_bytes(tmp_path):
    fixture = read_broker_busy_source_fixture()
    relatives = {name: fixture.BROKER_BUSY_SOURCE_DIRECTORY + "/" + name
                 for name in fixture.BUSY_CORE}
    relatives.update({name: fixture.GLM_CORE_SOURCE_DIRECTORY + "/" + name
                      for name in fixture.GLM_CORE_PREIMAGE_SOURCES})
    for index, (name, relative) in enumerate(sorted(relatives.items())):
        native = _current_broker_busy_closure_fixture(tmp_path / str(index))
        target = native / relative
        retained = native / ("retained-" + name)
        target.rename(retained)
        target.symlink_to(retained)
        with pytest.raises(AssertionError, match="not regular"):
            fixture.expected_broker_busy_closure(native)


def test_busy_current_stage_refuses_changed_emitted_records_before_payload_reads(tmp_path):
    fixture = read_broker_busy_source_fixture()
    native = _current_broker_busy_closure_fixture(tmp_path / "source")
    records = fixture.expected_broker_busy_closure(native)
    names = ("native-manifest.json", "native-source-inventory.json")
    for index, changed in enumerate(names):
        output = tmp_path / ("output-" + str(index))
        output.mkdir()
        for name, record in zip(names, records):
            (output / name).write_bytes(fixture.canonical(record))
        target = output / changed
        target.write_bytes(target.read_bytes() + b" ")
        with pytest.raises(AssertionError, match="source closure differs"):
            fixture.verify_broker_busy_stage(output, native, set(records[0]))



def test_published_bundle_keeps_protected_worker_ceiling_and_operator_scope(tmp_path):
    """Test what the native stage actually publishes, never just candidate files."""
    root = tmp_path / "published-stage"
    p = subprocess.run([sys.executable,
        str(NATIVE / "rollout/build_review_stage.py"), "--output", str(root)],
        text=True, capture_output=True, timeout=25)
    assert p.returncode == 0, p.stderr
    ext = root / "native-code-stage/ext"
    manifest = json.loads((root / "native-manifest.json").read_text())
    files = ("sub.sh", "remote_sub_helpers.py", "fabric_operator_client.py")
    for name in files:
        assert digest((ext / name).read_bytes()) == manifest["ext/" + name]
    sub = (ext / "sub.sh").read_text()
    assert "POOL_REQUEST_MAX_TURNS" in sub
    assert "LOCAL_GROK_MODEL_REFUSED unsupported_model" in sub
    assert "LOCAL_CURSOR_MODEL_REFUSED unsupported_model" in sub
    body = sub.split('CLAUDE_WORKER_MAX_TURNS=120\n', 1)[1]
    body = body.split('\n}\n', 1)[0] + '\n}\n'
    bash = ('CLAUDE_WORKER_MAX_TURNS=120\n' + body
            + '\n_claude_worker_profile glm glm-5.3 || exit $?\n'
            + 'printf "%s\n" "$CLAUDE_WORKER_MAX_TURNS"\n')
    env = {"PATH": "/usr/bin:/bin", "POOL_TASK_COMPLEXITY": "C0_MECHANICAL",
           "POOL_MAX_TURNS": "40", "POOL_REQUEST_MAX_TURNS": "7"}
    call = subprocess.run(["bash", "-c", bash], env=env,
                          text=True, capture_output=True, timeout=5)
    assert call.returncode == 0, call.stderr
    assert call.stdout.strip() == "7"
    forwarded = subprocess.run([sys.executable, str(ext / "remote_sub_helpers.py"),
                                "routing-env"], env=env, text=True,
                               capture_output=True, timeout=5)
    assert forwarded.returncode == 0, forwarded.stderr
    assert "POOL_REQUEST_MAX_TURNS=7" in forwarded.stdout
    helper = (ext / "remote_sub_helpers.py").read_text()
    assert "mastermind.grok_usage.v2" in helper
    assert "requested_cli_only" in helper
    operator = (ext / "fabric_operator_client.py").read_text()
    assert "('grok', 'grok-4.7')" in operator
    assert "Submit fabric_child_request ONCE" in operator
    assert "Never resubmit an uncertain/dispatched request" in operator
    assert "unexpired grant" in operator


def test_published_paid_model_and_grok_controls_composed(tmp_path):
    """New protected canonical paid GLM additions must survive Grok overlay."""
    stage = tmp_path / "composed-stage"
    result = subprocess.run([sys.executable,
        str(NATIVE / "rollout/build_review_stage.py"), "--output", str(stage)],
        text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr
    manifest = json.loads((stage / "native-manifest.json").read_text())
    inventory = json.loads((stage / "native-source-inventory.json").read_text())
    assert len(manifest) == len(inventory["files"]) == len(read_builder().BASE_FILES | read_builder().ADDITIONS) + 1
    assert "qualified_pure_yaml" in inventory
    ext = stage / "native-code-stage/ext"
    for name in ("remote_sub.sh", "remote_sub_exec.py", "remote_sub_helpers.py"):
        data = (ext / name).read_bytes()
        assert digest(data) == manifest["ext/" + name]
        source = ("candidate/" if name in read_builder().GROK47_CANDIDATE_COMPOSITION_DIGESTS
                  else "../grok47/overlay/") + name
        assert inventory["files"]["ext/" + name]["source"] == source
    transport = (ext / "remote_sub.sh").read_text()
    assert "FABRIC_CANONICAL_PAID_MODE" in transport
    assert "CANONICAL_PAID_STATE_REFUSED" in transport
    assert "LOCAL_GROK_MODEL_REFUSED" in (ext / "sub.sh").read_text()
    executor = (ext / "remote_sub_exec.py").read_text()
    assert "_canonical_model_command" in executor
    assert "CANONICAL_PAID_RESULT_RETENTION_UNCONFIRMED" in executor
    assert "grok" in executor.lower()
    helper = (ext / "remote_sub_helpers.py").read_text()
    assert "POOL_REQUEST_MAX_TURNS" in helper
    assert "from paid_incumbent_state import policy_source, read_policy" in helper
    assert "mastermind.grok_usage.v2" in helper


def test_builder_rejects_changed_accepted_grok_source(tmp_path):
    clone_root, candidate_native = _clone_composition_fixture(tmp_path)
    changed = clone_root / "grok47/overlay/remote_sub_exec.py"
    changed.write_bytes(changed.read_bytes() + b"\n# deliberate tamper\n")
    stage = tmp_path / "stage"
    proc = subprocess.run(
        [sys.executable, str(candidate_native / "rollout/build_review_stage.py"),
         "--output", str(stage)],
        capture_output=True, text=True, timeout=25,
    )
    assert proc.returncode != 0
    assert "accepted Grok 4.7 source digest mismatch: remote_sub_exec.py" in proc.stderr
    assert not (stage / "native-manifest.json").exists()

def test_approved_grok_bytes_stay_pinned_after_concurrent_source_change(tmp_path, monkeypatch):
    """The accepted bytes are staged once, even if their source changes."""
    clone_root, candidate_native = _clone_composition_fixture(tmp_path)
    changed = clone_root / "grok47/overlay/artifact_delivery.py"
    spec = importlib.util.spec_from_file_location(
        "raced_qwen_grok_builder", candidate_native / "rollout/build_review_stage.py"
    )
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    original = Path.read_bytes
    seen = {"changed": False}

    def read_then_mutate(path):
        raw = original(path)
        if path == changed and not seen["changed"]:
            seen["changed"] = True
            changed.write_bytes(raw + b"\n# source modified after first read\n")
        return raw

    stage = tmp_path / "stage"
    monkeypatch.setattr(Path, "read_bytes", read_then_mutate)
    monkeypatch.setattr(sys, "argv", ["build_review_stage.py", "--output", str(stage)])
    builder.main()
    assert seen["changed"]
    manifest = json.loads((stage / "native-manifest.json").read_text())
    base_pin = read_builder().GROK47_MERGED_SOURCE_DIGESTS["artifact_delivery.py"]
    assert base_pin == "447ab9d65264f46acfe5662d60e38c1f4db97198afc9113c2717109e298db9c3"
    pin = S14_FORWARD_DIGESTS["artifact_delivery.py"]
    assert builder.GROK47_CANDIDATE_COMPOSITION_DIGESTS["artifact_delivery.py"] == pin
    assert manifest["ext/artifact_delivery.py"] == pin
    assert digest((stage / "native-code-stage/ext/artifact_delivery.py").read_bytes()) == pin
    assert digest(changed.read_bytes()) != base_pin


@pytest.mark.parametrize("name", ("artifact_delivery.py", "pick.py", "remote_sub.sh", "remote_sub_helpers.py"))
@pytest.mark.parametrize("damage", ("changed", "missing", "symlink"))
def test_builder_refuses_unqualified_forward_composition(tmp_path, name, damage):
    clone_root, candidate_native = _clone_composition_fixture(tmp_path)
    changed = candidate_native / "candidate" / name
    if damage == "changed":
        changed.write_bytes(changed.read_bytes() + b"\n# unreviewed forward bytes\n")
    elif damage == "symlink":
        # Even a symlink whose target carries the exact reviewed bytes is
        # refused: the builder requires a regular candidate file.
        reviewed = tmp_path / "reviewed-forward-bytes"
        reviewed.write_bytes(changed.read_bytes())
        changed.unlink()
        changed.symlink_to(reviewed)
    else:
        changed.unlink()
    stage = tmp_path / "stage"
    proc = subprocess.run([sys.executable, str(candidate_native / "rollout/build_review_stage.py"),
                           "--output", str(stage)], capture_output=True, text=True, timeout=25)
    assert proc.returncode != 0
    assert "accepted Grok forward composition mismatch: " + name in proc.stderr
    assert not (stage / "native-manifest.json").exists()
    assert not (stage / "native-source-inventory.json").exists()


def _clone_composition_fixture(tmp_path):
    """Clone the reviewed builder inputs under tmp_path; never touch real state."""
    clone_root = tmp_path / "ops/native_fabric"
    candidate_native = clone_root / "quota_continuity"
    for directory in ("candidate", "source", "rollout"):
        shutil.copytree(NATIVE / directory, candidate_native / directory,
                        ignore=shutil.ignore_patterns("native-code-stage", "__pycache__"))
    shutil.copytree(GROK, clone_root / "grok47/overlay")
    # Current protected native builder reads the exact locked PyYAML
    # provenance from the repository root, not from its rollout subdirectory.
    pure_yaml = json.loads((NATIVE / "candidate/paid_pyyaml_provenance.json").read_text())
    lock = pure_yaml["lock_path"]
    lock_source = REPO / lock
    raw = lock_source.read_bytes()
    assert digest(raw) == pure_yaml["lock_sha256"]
    lock_target = tmp_path / lock
    lock_target.parent.mkdir(parents=True, exist_ok=True)
    lock_target.write_bytes(raw)
    return clone_root, candidate_native


@pytest.mark.parametrize("name", ("artifact_delivery.py", "pick.py"))
def test_builder_refuses_tampered_overlay_base_despite_valid_forward(tmp_path, name):
    """A valid forward candidate never excuses a changed accepted overlay base."""
    clone_root, candidate_native = _clone_composition_fixture(tmp_path)
    builder = read_builder()
    manifest, _ = current_source_closure()
    for forward in FORWARD_NAMES:
        assert (digest((candidate_native / "candidate" / forward).read_bytes())
                == manifest["ext/" + forward])
    changed = clone_root / "grok47/overlay" / name
    changed.write_bytes(changed.read_bytes() + b"\n# tampered accepted overlay base\n")
    stage = tmp_path / "stage"
    proc = subprocess.run(
        [sys.executable, str(candidate_native / "rollout/build_review_stage.py"),
         "--output", str(stage)],
        capture_output=True, text=True, timeout=25,
    )
    assert proc.returncode != 0
    assert "accepted Grok 4.7 source digest mismatch: " + name in proc.stderr
    assert not (stage / "native-manifest.json").exists()
    assert not (stage / "native-source-inventory.json").exists()


def test_forward_map_retains_original_four_and_adds_three_long_horizon_bounds():
    """Keep historical four/three maps and the one exact reviewed S14 join."""
    builder = read_builder()
    manifest, inventory = current_source_closure()
    forward = builder.GROK47_CANDIDATE_COMPOSITION_DIGESTS
    merged = builder.GROK47_MERGED_SOURCE_DIGESTS
    assert len(merged) == 9 and set(merged) == set(NAMES)
    assert set(HISTORICAL_FORWARD_NAMES) == {"pick.py", "remote_sub.sh", "remote_sub_exec.py", "remote_sub_helpers.py"}
    assert set(LONG_HORIZON_FORWARD_NAMES) == {"fabric_operator_contract.py", "native_remote.py", "sub.sh"}
    assert set(S14_FORWARD_DIGESTS) == {"artifact_delivery.py"}
    assert set(forward) == set(FORWARD_NAMES) and len(forward) == 8
    for name, value in S14_FORWARD_DIGESTS.items():
        assert forward[name] == value
    assert set(forward) < set(merged)
    assert set(merged) - set(forward) == set(BASE_ONLY_OVERLAY_NAMES)
    for name, value in sorted(forward.items()):
        assert len(value) == 64
        assert all(ch in "0123456789abcdef" for ch in value)
        assert value != merged[name]
        candidate = NATIVE / "candidate" / name
        assert candidate.is_file() and not candidate.is_symlink()
        # Carrier-cohort names stage the exact current APPLICATION successor
        # bytes; their forward pin stays the immutable carrier preimage and
        # is never overwritten with the staged successor digest.
        carrier = builder.application_carrier_candidate_digests(NATIVE).get(name)
        current = digest(candidate.read_bytes())
        # The composed f57b085 x d0c543 carrier stages the sparse-index-advice
        # executor preimage endpoint; the historical forward pin stays valid.
        accepted = (carrier,) if carrier is not None else (
            (value,) if name != "remote_sub_exec.py"
            else (value, builder.SPARSE_INDEX_ADVICE_EXECUTOR_PREIMAGE))
        assert current in accepted
        if carrier is not None:
            # Composed endpoint: the carrier preimage map may carry the
            # sparse-index-advice executor endpoint alongside the historical
            # forward pin for the same member.
            assert builder.APPLICATION_CARRIER_PREIMAGES[name] in (
                (value,) if name != "remote_sub_exec.py"
                else (value, builder.SPARSE_INDEX_ADVICE_EXECUTOR_PREIMAGE))


def test_protected_qwen_files_and_exact_context_reader_forward():
    """The four protected Qwen files are pinned to absolute source digests."""
    builder = read_builder()
    assert set(PROTECTED_QWEN_SOURCE_DIGESTS) == set(QWEN)
    assert len(set(PROTECTED_QWEN_SOURCE_DIGESTS.values())) == 4
    assert not set(PROTECTED_QWEN_SOURCE_DIGESTS) & set(NAMES)
    assert not set(PROTECTED_QWEN_SOURCE_DIGESTS) & set(builder.GROK47_CANDIDATE_COMPOSITION_DIGESTS)
    manifest, inventory = current_source_closure()
    assert set(REVIEWED_QWEN_FORWARD_DIGESTS) == {"glm_host_account_source.py", "lease_broker.py"}
    for name, original in sorted(PROTECTED_QWEN_SOURCE_DIGESTS.items()):
        expected = REVIEWED_QWEN_FORWARD_DIGESTS.get(name, original)
        assert name in builder.BASE_FILES
        candidate = NATIVE / "candidate" / name
        assert candidate.is_file() and not candidate.is_symlink()
        if name != "lease_broker.py":
            assert manifest["ext/" + name] == expected
        current = manifest["ext/" + name]
        assert digest(candidate.read_bytes()) == current
        row = inventory["files"]["ext/" + name]
        assert row["sha256"] == current
        assert row["source"] == "candidate/" + name
        assert row["installed_preimage_sha256"]


# Runtime freshness and caller UTC behavior are qualified by the existing
# guarded eligibility/outcome/not-before suites. Exact source digests above
# bind those checked functions; string or identifier ordering is not gate proof.


def _current_closure_fixture(root):
    fixture = read_current_source_fixture()
    for relative in (
        "rollout/native-manifest.json", "rollout/native-source-inventory.json",
        *("candidate/" + name for name in fixture.REVIEWED_CORE),
    ):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((NATIVE / relative).read_bytes())
    return root


def test_current_projection_preserves_all_other_historical_rows(tmp_path):
    fixture = read_current_source_fixture()
    native = _current_closure_fixture(tmp_path / "source")
    baseline = json.loads((native / "rollout/native-manifest.json").read_bytes())
    baseline_inventory = json.loads((native / "rollout/native-source-inventory.json").read_bytes())
    manifest, inventory = fixture.expected_current_source_closure(native)
    changed = {"ext/" + name for name in fixture.REVIEWED_CORE}
    assert {name for name in manifest if manifest[name] != baseline[name]} == changed
    assert {name for name in inventory["files"]
            if inventory["files"][name] != baseline_inventory["files"][name]} == changed
    assert len(manifest) == len(inventory["files"]) == 107


def test_current_closure_refuses_changed_baseline_or_candidate(tmp_path):
    fixture = read_current_source_fixture()
    relatives = [
        "rollout/native-manifest.json", "rollout/native-source-inventory.json",
        *("candidate/" + name for name in fixture.REVIEWED_CORE),
    ]
    for index, relative in enumerate(relatives):
        native = _current_closure_fixture(tmp_path / str(index))
        target = native / relative
        target.write_bytes(target.read_bytes() + b"\n# unqualified\n")
        with pytest.raises(AssertionError):
            fixture.expected_current_source_closure(native)


def test_current_closure_refuses_symlinked_core_even_with_exact_bytes(tmp_path):
    fixture = read_current_source_fixture()
    for index, name in enumerate(fixture.REVIEWED_CORE):
        native = _current_closure_fixture(tmp_path / str(index))
        target = native / "candidate" / name
        retained = native / ("retained-" + name)
        target.rename(retained)
        target.symlink_to(retained)
        with pytest.raises(AssertionError, match="not regular"):
            fixture.expected_current_source_closure(native)


def test_current_stage_refuses_changed_emitted_records_before_payload_reads(tmp_path):
    fixture = read_current_source_fixture()
    native = _current_closure_fixture(tmp_path / "source")
    records = fixture.expected_current_source_closure(native)
    names = ("native-manifest.json", "native-source-inventory.json")
    for index, changed in enumerate(names):
        output = tmp_path / ("output-" + str(index))
        output.mkdir()
        for name, record in zip(names, records):
            (output / name).write_bytes(fixture.canonical(record))
        target = output / changed
        target.write_bytes(target.read_bytes() + b" ")
        with pytest.raises(AssertionError, match="source closure differs"):
            fixture.verify_current_stage(output, native, set(records[0]))

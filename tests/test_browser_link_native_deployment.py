"""Closed Browser Link native bundle through the incumbent filesystem transaction."""
from dataclasses import replace
import base64
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from integrations.mastermind_browser_link.native_channel import LinkEnrollment
from integrations.chairman_surfaces import browser_link_native_deployment as native
from integrations.chairman_surfaces import web_sol_deployment as d
from integrations.chairman_surfaces import web_sol_deployment_apply as a
from scripts import web_sol_deployment_apply as cli
from tests.test_web_sol_browser_link_overlay import _request


def bundle_at(tmp_path):
    root = tmp_path / "NativeMessagingHosts"
    root.mkdir(mode=0o700)
    release = tmp_path / "release 'quoted' $() `literal`"
    enrollment = LinkEnrollment("a" * 32, "b" * 64, Path("/tmp/mmx-native-install-fixture.sock"))
    return native.render_browser_link_native_bundle(
        source_commit="c" * 40, native_hosts_root=root, release_root=release,
        python_executable=Path(sys.executable), enrollment=enrollment)


def prepare(bundle, current=None):
    root = bundle.native_hosts_root
    return a.prepare_deployment(bundle, d.plan_deployment(bundle, current or {}),
        install_root=root, expected_uid=root.stat().st_uid, expected_gid=root.stat().st_gid,
        operation_key="browser-link-native-fixture")


def rehash_state(state):
    state.pop("state_digest", None)
    state["state_digest"] = hashlib.sha256(cli._canonical_bytes(state)).hexdigest()


def test_native_publishes_registration_last_and_rolls_back_first_through_saved_states(tmp_path, monkeypatch):
    bundle = bundle_at(tmp_path)
    sentinel = bundle.native_hosts_root / "com.mastermind.web_sol.existing.json"
    sentinel.write_bytes(b"existing Web Sol registration")
    sentinel.chmod(0o600)
    sentinel_before = sentinel.stat()
    manifest = bundle.artifacts[-1]
    # Lexical sorting would publish the registration before its dependencies.
    assert sorted(bundle.artifacts, key=lambda row: str(row.destination))[0] == manifest
    prepared = prepare(bundle)
    assert tuple(row.path for row in prepared.preimages) == tuple(row.destination for row in bundle.artifacts)
    assert cli._decode_bundle(bundle.private_document()) == bundle
    state = cli._private_state_document(request_document=_request(bundle, prepared),
                                       prepared=prepared, phase="PREPARED")
    _, request, recovered, _, _ = cli._decode_private_state(state)
    writes, removals = [], []
    install, restore = a._install_absent_target_at, a._restore_file
    def record_install(parent, temporary, target, artifact, transaction):
        if artifact == manifest:
            assert all(row.destination.read_bytes() == row.content for row in bundle.artifacts[:-1])
        writes.append(artifact.destination)
        return install(parent, temporary, target, artifact, transaction)
    def record_restore(row, artifact, transaction):
        removals.append(row.path)
        if row.path != manifest.destination:
            assert not manifest.destination.exists()
        return restore(row, artifact, transaction)
    monkeypatch.setattr(a, "_install_absent_target_at", record_install)
    monkeypatch.setattr(a, "_restore_file", record_restore)
    applied = a.apply_deployment(recovered)
    assert writes == [row.destination for row in bundle.artifacts]
    assert a.verify_applied_deployment(applied)["target_count"] == 3
    assert all(row.destination.stat().st_mode & 0o777 == row.mode for row in bundle.artifacts)
    wire = cli._private_state_document(request_document=request, prepared=recovered, phase="APPLIED", applied=applied)
    _, _, _, restored, _ = cli._decode_private_state(wire)
    a.rollback_deployment(restored)
    assert removals == list(reversed(writes))
    assert not (bundle.native_hosts_root / "mastermind-browser-link").exists()
    assert sentinel.read_bytes() == b"existing Web Sol registration"
    assert sentinel.stat().st_ino == sentinel_before.st_ino
    assert bundle.public_receipt["scope"] == "native_host_installation"
    assert "package_version" not in bundle.public_receipt
    assert str(bundle.native_hosts_root) not in json.dumps(bundle.public_receipt)


def test_launcher_uses_fixed_isolated_bootstrap_and_preserves_origin_argument(tmp_path):
    bundle = bundle_at(tmp_path)
    script = bundle.release_root / "scripts/mastermind_browser_link_native_host.py"
    script.parent.mkdir(parents=True)
    script.write_text('import json,sys\nprint(json.dumps({"argv":sys.argv[1:],"isolated":sys.flags.isolated,'
                      '"no_site":sys.flags.no_site,"no_bytecode":sys.dont_write_bytecode}))\n')
    applied = a.apply_deployment(prepare(bundle))
    try:
        origin = "chrome-extension://" + bundle.enrollment.extension_id + "/"
        result = subprocess.run([str(bundle.artifacts[1].destination), origin], check=True,
                                capture_output=True, text=True, timeout=5)
        observed = json.loads(result.stdout)
        assert observed == {"argv": ["--config", str(bundle.artifacts[0].destination), origin],
                            "isolated": 1, "no_site": 1, "no_bytecode": True}
        assert json.loads(bundle.artifacts[2].content)["allowed_origins"] == [origin]
        assert json.loads(bundle.artifacts[0].content) == bundle.enrollment.document()
    finally:
        a.rollback_deployment(applied)


@pytest.mark.parametrize("defect", ["order", "launcher", "argument", "origin", "host", "instance", "destination", "mode", "extra"])
def test_typed_bundle_refuses_rehashed_unqualified_payload(tmp_path, defect):
    bundle = bundle_at(tmp_path)
    fields = dict(vars(bundle))
    artifacts = list(bundle.artifacts)
    if defect == "order":
        artifacts.reverse()
    elif defect == "launcher":
        artifacts[1] = replace(artifacts[1], content=artifacts[1].content + b"unreviewed-command\n")
    elif defect == "argument":
        fields["wrapper_argv"] = (*bundle.wrapper_argv[:-1], "/tmp/foreign-config")
    elif defect == "origin":
        body = json.loads(artifacts[2].content)
        body["allowed_origins"].append("chrome-extension://" + "b" * 32 + "/")
        artifacts[2] = replace(artifacts[2], content=d._canonical_bytes(body) + b"\n")
    elif defect == "host":
        fields["native_host_name"] = "com.mastermind.browser_link"
    elif defect == "instance":
        fields["instance_id"] = "d" * 64
    elif defect == "destination":
        artifacts[0] = replace(artifacts[0], destination=bundle.native_hosts_root / "foreign.json")
    elif defect == "mode":
        artifacts[0] = replace(artifacts[0], mode=0o700)
    else:
        artifacts.append(replace(artifacts[0], kind="foreign_artifact",
                                 destination=bundle.native_hosts_root / "extra"))
    fields["artifacts"] = tuple(artifacts)
    fields["bundle_digest"] = native._native_digest(fields)
    with pytest.raises(d.WebSolDeploymentError):
        native.BrowserLinkNativeBundle(**fields)
    wire = bundle.private_document()
    wire.update({key: fields[key] for key in ("instance_id", "native_host_name", "bundle_digest")})
    wire["wrapper_argv"] = list(fields["wrapper_argv"])
    wire["artifacts"] = [{"kind": row.kind, "destination": str(row.destination), "mode": row.mode,
                          "sha256": row.sha256, "content_base64": base64.b64encode(row.content).decode()}
                         for row in artifacts]
    with pytest.raises(a.WebSolDeploymentApplyError, match="INVALID_INPUT"):
        cli._decode_bundle(wire)
    assert list(bundle.native_hosts_root.iterdir()) == []


@pytest.mark.parametrize("defect", ["enrollment_v1", "enrollment_extra", "request_root", "noncanonical_root"])
def test_native_closed_decoder_refuses_schema_and_root_crossing(tmp_path, defect):
    bundle = bundle_at(tmp_path)
    request = _request(bundle, prepare(bundle))
    if defect == "enrollment_v1":
        request["bundle"]["enrollment"]["schema"] = "mastermind.browser_link.enrollment.v1"
    elif defect == "enrollment_extra":
        request["bundle"]["enrollment"]["chrome_pid"] = 123
    elif defect == "request_root":
        request["install_root"] = str(bundle.native_hosts_root.parent)
    else:
        request["bundle"]["native_hosts_root"] += "/."
    with pytest.raises(a.WebSolDeploymentApplyError, match="INVALID_INPUT"):
        cli._decode_request(request)


@pytest.mark.parametrize("phase", ["PREPARED", "APPLIED"])
@pytest.mark.parametrize("defect", ["order", "root"])
def test_rehashed_private_state_cannot_change_native_order_or_root(tmp_path, phase, defect):
    bundle = bundle_at(tmp_path)
    prepared = prepare(bundle)
    applied = a.apply_deployment(prepared) if phase == "APPLIED" else None
    state = cli._private_state_document(request_document=_request(bundle, prepared),
                                       prepared=prepared, phase=phase, applied=applied)
    if defect == "order":
        state["prepared"]["preimages"].reverse()
    else:
        state["request"]["install_root"] = str(bundle.native_hosts_root.parent)
    rehash_state(state)
    with pytest.raises(a.WebSolDeploymentApplyError):
        cli._decode_private_state(state)
    if applied is not None:
        if defect == "root":
            prepared.install_root = bundle.native_hosts_root.parent
            with pytest.raises(a.WebSolDeploymentApplyError, match="NATIVE_ROOT_MISMATCH"):
                a.rollback_deployment(applied)
            assert applied._state == prepared._state == "APPLIED"
            prepared.install_root = bundle.native_hosts_root
        a.rollback_deployment(applied)


@pytest.mark.parametrize("position", [1, 2, 3])
def test_dependency_failure_never_leaves_registered_partial_host(tmp_path, monkeypatch, position):
    bundle = bundle_at(tmp_path)
    prepared = prepare(bundle)
    install = a._install_absent_target_at
    count = 0
    def fail(parent, temporary, target, artifact, transaction):
        nonlocal count
        count += 1
        if count == position:
            raise OSError("bounded injected install failure")
        return install(parent, temporary, target, artifact, transaction)
    monkeypatch.setattr(a, "_install_absent_target_at", fail)
    with pytest.raises(a.WebSolDeploymentApplyError, match="APPLY_ABORTED_ROLLED_BACK"):
        a.apply_deployment(prepared)
    assert list(bundle.native_hosts_root.iterdir()) == []


@pytest.mark.parametrize("preexisting", ["foreign", "partial", "symlink"])
def test_existing_registration_or_partial_fresh_plan_refuses_before_effect(tmp_path, preexisting):
    bundle = bundle_at(tmp_path)
    manifest = bundle.artifacts[-1]
    if preexisting == "symlink":
        target = tmp_path / "foreign"
        target.write_bytes(b"foreign")
        manifest.destination.symlink_to(target)
        current = {}
    elif preexisting == "foreign":
        manifest.destination.write_bytes(b"foreign registration")
        manifest.destination.chmod(0o600)
        current = {str(manifest.destination): b"foreign registration"}
    else:
        first = bundle.artifacts[0]
        first.destination.parent.mkdir(parents=True, mode=0o700)
        first.destination.parent.parent.chmod(0o700)
        first.destination.write_bytes(first.content)
        first.destination.chmod(first.mode)
        current = {str(first.destination): first.content}
    with pytest.raises(a.WebSolDeploymentApplyError):
        prepare(bundle, current)
    assert not bundle.artifacts[1].destination.exists()


def test_existing_complete_identical_bundle_is_noop_and_retains_original_inodes(tmp_path):
    bundle = bundle_at(tmp_path)
    first = a.apply_deployment(prepare(bundle))
    before = {row.destination: row.destination.stat().st_ino for row in bundle.artifacts}
    second = a.apply_deployment(prepare(bundle, bundle.as_files()))
    assert second.changed_paths == ()
    a.rollback_deployment(second)
    assert {row.destination: row.destination.stat().st_ino for row in bundle.artifacts} == before
    a.rollback_deployment(first)


@pytest.mark.parametrize("effect", ["absent", "complete", "mixed"])
def test_interrupted_native_install_uses_original_saved_transaction_without_replay(tmp_path, monkeypatch, effect):
    bundle = bundle_at(tmp_path)
    prepared = prepare(bundle)
    state = cli._private_state_document(request_document=_request(bundle, prepared),
                                       prepared=prepared, phase="PREPARED")
    if effect == "complete":
        a.apply_deployment(prepared)
    elif effect == "mixed":
        class SimulatedProcessDeath(BaseException):
            pass
        install = a._install_absent_target_at
        def die_before_publication(parent, temporary, target, artifact, transaction):
            if artifact.kind == "browser_link_native_manifest":
                raise SimulatedProcessDeath()
            return install(parent, temporary, target, artifact, transaction)
        monkeypatch.setattr(a, "_install_absent_target_at", die_before_publication)
        with pytest.raises(SimulatedProcessDeath):
            a.apply_deployment(prepared)
    _, _, recovered, _, _ = cli._decode_private_state(state)
    if effect == "mixed":
        with pytest.raises(a.WebSolDeploymentApplyError, match="APPLY_EFFECT_UNKNOWN"):
            a.reconcile_prepared_deployment(recovered)
        assert not bundle.artifacts[-1].destination.exists()
        assert all(row.destination.exists() for row in bundle.artifacts[:-1])
    else:
        reconciled = a.reconcile_prepared_deployment(recovered)
        if effect == "absent":
            assert reconciled is None
            assert list(bundle.native_hosts_root.iterdir()) == []
        else:
            assert reconciled is not None
            assert reconciled.reconciled_paths == tuple(row.destination for row in bundle.artifacts)
            a.rollback_deployment(reconciled)


def forged_prepared_digest(state):
    """Construct an internally rehashed capsule without trusting its preimage claim."""
    request, prepared = state["request"], state["prepared"]
    changes = {row["path"]: row for row in request["plan"]["changes"]}
    targets = []
    for row in prepared["preimages"]:
        change = changes[row["path"]]
        targets.append({**{key: row[key] for key in
                          ("kind", "path_digest", "prior_state", "prior_sha256", "prior_mode", "prior_uid", "prior_gid")},
                        "action": change["action"], "next_sha256": change["next_sha256"], "next_mode": change["mode"]})
    directories = [{key: row[key] for key in
                    ("path_digest", "prior_state", "prior_dev", "prior_ino", "prior_mode", "prior_uid", "prior_gid")}
                   for row in sorted(prepared["directory_preimages"],
                                     key=lambda row: (len(Path(row["path"]).parts), row["path"]))]
    return d._sha256(d._canonical_bytes({
        "schema": "mastermind.web_sol_deployment_prepared.v1",
        "operation_key": request["operation_key"], "bundle_digest": request["bundle"]["bundle_digest"],
        "expected_uid": request["expected_uid"], "expected_gid": request["expected_gid"],
        "cleanup_nonce": prepared["cleanup_nonce"], "directories": directories, "targets": targets}))


@pytest.mark.parametrize("phase", ["PREPARED", "APPLIED"])
def test_rehashed_create_preimage_cannot_restore_foreign_registration(tmp_path, phase):
    bundle = bundle_at(tmp_path)
    prepared = prepare(bundle)
    applied = a.apply_deployment(prepared) if phase == "APPLIED" else None
    state = cli._private_state_document(request_document=_request(bundle, prepared),
                                       prepared=prepared, phase=phase, applied=applied)
    assert forged_prepared_digest(state) == prepared.prepared_digest
    foreign = b'{"name":"foreign","path":"/unqualified/launcher"}'
    row = state["prepared"]["preimages"][-1]
    row.update(prior_state="PRESENT", prior_bytes_base64=base64.b64encode(foreign).decode(),
               prior_sha256=d._sha256(foreign), prior_mode=0o600,
               prior_uid=prepared.expected_uid, prior_gid=prepared.expected_gid)
    state["prepared"]["prepared_digest"] = forged_prepared_digest(state)
    rehash_state(state)
    with pytest.raises(a.WebSolDeploymentApplyError):
        cli._decode_private_state(state)
    if applied is not None:
        original_rows, original_digest = prepared.preimages, prepared.prepared_digest
        prepared.preimages = (*original_rows[:-1], replace(original_rows[-1],
            prior_state="PRESENT", prior_bytes=foreign, prior_sha256=d._sha256(foreign), prior_mode=0o600,
            prior_uid=prepared.expected_uid, prior_gid=prepared.expected_gid))
        prepared.prepared_digest = state["prepared"]["prepared_digest"]
        with pytest.raises(a.WebSolDeploymentApplyError, match="PREPARED_INTEGRITY_MISMATCH"):
            a.rollback_deployment(applied)
        assert prepared._state == applied._state == "APPLIED"
        assert bundle.artifacts[-1].destination.read_bytes() == bundle.artifacts[-1].content
        prepared.preimages, prepared.prepared_digest = original_rows, original_digest
        a.rollback_deployment(applied)
    assert not bundle.artifacts[-1].destination.exists()

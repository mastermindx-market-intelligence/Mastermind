"""Native source preparation stays inert inside the original config owner."""
import copy
import json
from types import SimpleNamespace

import pytest

from scripts import executive_os_phase1c as service
from ops.executive_os import attended_control_staging as staging
from ops.executive_os import autonomy_control as owner
from tests.test_attended_control_staging import installed, retained_disarm, stage, SHA
from tests.test_attended_worker_definition import inputs
from tests.test_finite_initial_composition import composed, reader, native, bound, enrolled, root_stats

NATIVE = {"macro_release": "b" * 40, "producer_sha256": "c" * 64}
ARMS = ("coo_autonomy_armed", "coo_operator_harness_armed",
        "coo_foreground_only", "ceo_submit_armed", "fabric_bridge_armed")


def staged_raw():
    return dict(
        fabric_bindings_path="/fixture/bindings",
        fabric_bindings_sha256="a" * 64,
        fabric_attended_probe={"worker_config_path": "/fixture/worker"},
        native_capacity_v2=dict(NATIVE),
        **{name: False for name in ARMS},
    )


def test_wholly_disarmed_native_definition_is_valid():
    assert service._validate_fabric_bridge_config(staged_raw())


@pytest.mark.parametrize("name", [n for n in ARMS if n != "coo_foreground_only"])
@pytest.mark.parametrize("value", [True, 1, "false", None])
def test_native_staging_refuses_partial_or_nonboolean_arm(name, value):
    raw = staged_raw()
    raw[name] = value
    with pytest.raises(service.ServiceError):
        service._validate_fabric_bridge_config(raw)


@pytest.mark.parametrize("fault", ["extra", "path", "digest", "probe"])
def test_disarmed_does_not_relax_source_shape(fault):
    raw = staged_raw()
    if fault == "extra":
        raw["native_capacity_v2"]["enabled"] = True
    if fault == "path":
        raw["native_capacity_v2"]["macro_release"] = "../source"
    if fault == "digest":
        raw["native_capacity_v2"]["producer_sha256"] = True
    if fault == "probe":
        del raw["fabric_attended_probe"]
    with pytest.raises(service.ServiceError):
        service._validate_fabric_bridge_config(raw)


def test_native_stage_rebinds_original_disarm_receipt(installed):
    s = installed
    prior = retained_disarm(s)
    s.delta["native_capacity_v2"] = dict(NATIVE)
    transaction_id = stage(s)
    control = json.loads(owner.CONTROL_CONFIG.read_bytes())
    receipt, metadata = owner.load_receipt_file(owner.AUTONOMY_RECEIPT)
    assert control["native_capacity_v2"] == NATIVE
    assert all(control.get(name, False) is False for name in ARMS)
    assert receipt["transaction_id"] == transaction_id
    correlation = {"control_config_sha256", "prior_control_config_sha256", "transaction_id"}
    assert {k: v for k, v in receipt.items() if k not in correlation} == {
        k: v for k, v in prior.items() if k not in correlation}
    assert not s.marker.exists()


def test_lost_native_stage_reply_reconciles_original_postimage(installed, monkeypatch):
    s = installed
    retained_disarm(s)
    s.delta["native_capacity_v2"] = dict(NATIVE)
    original = s.host.publish_disarmed_receipt
    writes = []

    def lost(tx):
        original(tx)
        writes.append(tx.transaction_id)
        raise OSError("response lost after original postimage")

    monkeypatch.setattr(s.host, "publish_disarmed_receipt", lost)
    with pytest.raises(owner.TransactionEffectUnknown):
        stage(s)
    s.host._release_transaction_owner()
    s.host.reconcile_staging(SHA)
    assert len(writes) == 1
    assert json.loads(owner.CONTROL_CONFIG.read_bytes())["native_capacity_v2"] == NATIVE
    assert not s.marker.exists()


def test_disarmed_service_does_not_construct_native_acquisition(
        composed, tmp_path, monkeypatch, root_stats):
    from control_plane.fabric_attended_canary import AttendedControlProbeSource
    from control_plane.native_capacity_acquisition import NativeCapacitySource
    from control_plane import executive_worker_broker as broker
    from tests.test_ceo_submit_armed_composition import _raw, _write

    source, observation = composed
    raw = _raw(tmp_path)
    raw.update(staged_raw())
    monkeypatch.setattr(service, "_staged_fabric_binding_source", lambda _: source.bindings)
    raw = service.load_control_config(_write(tmp_path, raw))
    probe = AttendedControlProbeSource.from_startup(
        tmp_path / "control.json", raw, {"config_sha256": "a" * 64})
    monkeypatch.setattr(
        NativeCapacitySource, "from_startup",
        classmethod(lambda *args: pytest.fail("staging cannot create acquisition")))
    monkeypatch.setattr(broker, "WorkerBrokerClient", lambda *a, **kw: object())
    monkeypatch.setattr(service, "activate_launchd_socket", lambda name: object())
    captured = {}

    def holder(config, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(config=config)

    monkeypatch.setattr(service, "ExecutiveControlService", holder)
    service._service_from_config(
        raw, fabric_worker_binding_source=source.bindings,
        fabric_attended_probe_source=probe)
    assert captured["attended_worker_registration"] is None
    assert observation.requests == []


@pytest.fixture
def qualified_source(monkeypatch):
    from ops.executive_os import capacity_host_artifacts as closure
    from ops.executive_os import capacity_source_contract as source
    content = b'"""Inert test source; must never execute."""\nraise AssertionError("not executable")\n'
    manifest = {"material": [{"path": "engine/provider_capacity_v2.py",
                             "sha256": owner.sha256_bytes(content), "size": len(content)}]}
    calls = []

    def verify(root, commit):
        assert root == source.SYSTEM_ROOT / "capacity-sources/macro" / ("b" * 40)
        assert commit == "b" * 40
        calls.append((root, commit))
        return copy.deepcopy(manifest), object()

    monkeypatch.setattr(closure, "_verify_installed_repair_source", verify)
    return SimpleNamespace(content=content, manifest=manifest, calls=calls)


def test_native_stage_pin_comes_from_existing_export_and_sealed_producer(bound, qualified_source):
    from ops.executive_os import capacity_source_contract as source
    bound.publish()
    worker = bound.f.config
    worker["native_capacity_enrollment"]["enrollment_state"] = "unenrolled"
    producer = (source.SYSTEM_ROOT / "capacity-sources/macro" /
                worker["native_capacity_enrollment"]["registration_source"]["release_commit"] /
                "engine/provider_capacity_v2.py")
    producer.parent.mkdir(parents=True)
    content = b'"""Inert test source; must never execute."""\nraise AssertionError("not executable")\n'
    producer.write_bytes(content)
    pin = staging._native_source_pin(worker)
    assert pin == {"macro_release": "b" * 40,
                   "producer_sha256": owner.sha256_bytes(content)}
    assert worker["native_capacity_enrollment"]["enrollment_state"] == "unenrolled"
    assert len(qualified_source.calls) == 1


@pytest.mark.parametrize("fault", ["missing", "empty", "oversize", "revoked", "source", "digest"])
def test_unqualified_source_cannot_stage_native_pin(bound, fault):
    from ops.executive_os import capacity_source_contract as source
    bound.publish()
    worker = bound.f.config
    producer = source.SYSTEM_ROOT / "capacity-sources/macro" / ("b" * 40) / "engine/provider_capacity_v2.py"
    producer.parent.mkdir(parents=True)
    producer.write_bytes(b"source")
    if fault == "missing":
        producer.unlink()
    if fault == "empty":
        producer.write_bytes(b"")
    if fault == "oversize":
        producer.write_bytes(b"x" * 65537)
    if fault == "revoked":
        bound.row["registration_state"] = "revoked"
        bound.publish()
    if fault == "source":
        worker["native_capacity_enrollment"]["registration_source"]["release_commit"] = "d" * 40
    if fault == "digest":
        worker["native_capacity_enrollment"]["registration_source"]["export_sha256"] = "0" * 64
    with pytest.raises((ValueError, OSError)):
        staging._native_source_pin(worker)


def test_legacy_definition_does_not_read_or_infer_native_pin(monkeypatch):
    from control_plane import codex_provider_realm as realm
    monkeypatch.setattr(realm, "_native_read_config",
                        lambda *args: pytest.fail("legacy staging cannot read native source"))
    assert staging._native_source_pin({"worker_id": "minimax-finite-01"}) is None


def test_native_stage_refuses_source_revocation_between_reads(bound, monkeypatch, qualified_source):
    from control_plane import codex_provider_realm as realm
    from ops.executive_os import capacity_source_contract as source
    bound.publish()
    producer = source.SYSTEM_ROOT / "capacity-sources/macro" / ("b" * 40) / "engine/provider_capacity_v2.py"
    producer.parent.mkdir(parents=True)
    producer.write_bytes(qualified_source.content)
    original = realm._native_read_config
    reads = []

    def changed(path, digest):
        result = original(path, digest)
        if path == bound.export:
            reads.append(path)
            if len(reads) == 1:
                bound.export.write_bytes(b"{}")
        return result

    monkeypatch.setattr(realm, "_native_read_config", changed)
    with pytest.raises(ValueError):
        staging._native_source_pin(bound.f.config)


def native_artifacts(inputs):
    from ops.executive_os import attended_worker_definition as render
    from control_plane.fabric_attended_routing import FINITE_DEFINITION_DIR, FINITE_SOCKET_PATH
    enrollment = {
        "schema_version": "mastermind.native_subscription_capacity_enrollment/v1",
        "host_ref": "host-" + "1" * 64,
        "os_principal_ref": "principal-" + "2" * 64,
        "config_custody_ref": "custody-" + "3" * 64,
        "enrollment_state": "unenrolled",
        "registration_source": {"release_commit": "b" * 40,
                                "previous_release_commit": "c" * 40,
                                "material_source_digest": "d" * 64,
                                "export_sha256": "e" * 64},
    }
    return render.build_finite_worker_artifacts(**{
        **inputs, "worker_id": "minimax-finite-01", "worker_user": "_mastermind_minimax",
        "worker_group": "_mastermind_minimax", "worker_uid": 470, "worker_gid": 470,
        "definition_dir": FINITE_DEFINITION_DIR, "socket_path": FINITE_SOCKET_PATH,
        "host_ref": enrollment["host_ref"], "capacity_capability_id": "cap.fixture",
        "native_capacity_enrollment": enrollment,
    })


def test_renderer_preserves_native_pin_and_leaves_all_execution_off(inputs):
    from ops.executive_os import attended_worker_definition as render
    artifacts = native_artifacts(inputs)
    pin = dict(NATIVE)
    delta = render.build_finite_control_delta(
        definition_dir=staging.FINITE_DEFINITION_DIR,
        worker_artifacts=artifacts, native_capacity_v2=pin)
    assert delta["native_capacity_v2"] == NATIVE
    assert set(delta) == staging.NATIVE_FIELDS
    assert all(delta.get(name, False) is False for name in ARMS)
    pin["producer_sha256"] = "0" * 64
    assert delta["native_capacity_v2"] == NATIVE


@pytest.mark.parametrize("fault", ["source", "extra", "legacy"])
def test_renderer_cannot_repoint_or_invent_native_source(inputs, fault):
    from ops.executive_os import attended_worker_definition as render
    artifacts = native_artifacts(inputs)
    pin = dict(NATIVE)
    if fault == "source":
        pin["macro_release"] = "f" * 40
    if fault == "extra":
        pin["provider_enabled"] = True
    if fault == "legacy":
        worker = json.loads(artifacts["worker.json"])
        del worker["native_capacity_enrollment"]
        artifacts["worker.json"] = render._json(worker)
        bindings = json.loads(artifacts["bindings.json"])
        bindings["bindings"][0]["worker_source_config_digest"] = owner.sha256_bytes(artifacts["worker.json"])
        artifacts["bindings.json"] = render._json(bindings)
    with pytest.raises(ValueError):
        render.build_finite_control_delta(
            definition_dir=staging.FINITE_DEFINITION_DIR,
            worker_artifacts=artifacts, native_capacity_v2=pin)


def test_native_pin_does_not_accept_unprotected_source_file(bound, monkeypatch):
    from control_plane import codex_provider_realm as realm
    from ops.executive_os import capacity_source_contract as source
    bound.publish()
    producer = source.SYSTEM_ROOT / "capacity-sources/macro" / ("b" * 40) / "engine/provider_capacity_v2.py"
    producer.parent.mkdir(parents=True)
    producer.write_bytes(b"source")
    original = realm._native_open
    def strict_producer(path, **kwargs):
        if path == producer:
            return bound.f.original_open(path, **kwargs)
        return original(path, **kwargs)
    monkeypatch.setattr(realm, "_native_open", strict_producer)
    with pytest.raises(ValueError):
        staging._native_source_pin(bound.f.config)


@pytest.mark.parametrize("fault", ["producer-bytes", "unlisted", "size", "duplicate", "closure-refusal"])
def test_native_source_origin_failure_preserves_original_staging_preimage(
        bound, installed, qualified_source, monkeypatch, fault):
    from ops.executive_os import capacity_source_contract as source
    from ops.executive_os import capacity_host_artifacts as closure
    bound.export.write_bytes(json.dumps(bound.document, sort_keys=True, separators=(",", ":")).encode())
    bound.f.config["native_capacity_enrollment"]["registration_source"]["export_sha256"] = owner.sha256_bytes(bound.export.read_bytes())
    bound.f.config["native_capacity_enrollment"]["enrollment_state"] = "unenrolled"
    producer = source.SYSTEM_ROOT / "capacity-sources/macro" / ("b" * 40) / "engine/provider_capacity_v2.py"
    producer.parent.mkdir(parents=True)
    producer.write_bytes(qualified_source.content)
    export_before = bound.export.read_bytes()
    mode_before = producer.stat().st_mode
    if fault == "producer-bytes":
        producer.write_bytes(b"substituted source with unchanged protected metadata")
    elif fault == "unlisted":
        qualified_source.manifest["material"] = []
    elif fault == "size":
        qualified_source.manifest["material"][0]["size"] += 1
    elif fault == "duplicate":
        qualified_source.manifest["material"] *= 2
    elif fault == "closure-refusal":
        def refuse(*args):
            raise closure.CapacityHostArtifactError("SOURCE_GIT_BLOB_MISMATCH")
        monkeypatch.setattr(closure, "_verify_installed_repair_source", refuse)
    retained_disarm(installed)
    prior_control = owner.CONTROL_CONFIG.read_bytes()
    prior_worker = owner.WORKER_CONFIG.read_bytes()
    prior_receipt = owner.AUTONOMY_RECEIPT.read_bytes()

    delta_reads = []

    def native_delta():
        delta_reads.append(True)
        return dict(installed.delta, native_capacity_v2=staging._native_source_pin(bound.f.config))

    monkeypatch.setattr(installed.host, "read_delta", native_delta)
    with pytest.raises((ValueError, owner.HostControlError)):
        stage(installed)
    assert delta_reads == [True]
    if fault != "closure-refusal":
        assert len(qualified_source.calls) == 1
    assert producer.stat().st_mode == mode_before
    assert bound.export.read_bytes() == export_before
    assert owner.CONTROL_CONFIG.read_bytes() == prior_control
    assert owner.WORKER_CONFIG.read_bytes() == prior_worker
    assert owner.AUTONOMY_RECEIPT.read_bytes() == prior_receipt
    assert not installed.marker.exists()

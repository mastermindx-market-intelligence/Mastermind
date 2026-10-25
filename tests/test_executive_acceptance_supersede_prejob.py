"""Only a fully preserved pre-Job interruption may carry to a fresh release."""
import grp
import json
import os
import pwd
import shutil
from types import SimpleNamespace
from pathlib import Path

import pytest

from ops.executive_os import acceptance_maintenance as m
from tests.test_executive_acceptance_supersede_unstarted import (
    A, S, N, _fixture as unstarted_fixture, _rewrite,
)


WORKER_ID = "minimax-worker-1"


def attended_membership(**overrides):
    """The ten-field value ``Acceptance._attended_worker_membership`` returns."""
    value = {
        "worker_user": "_mastermind_minimax", "worker_uid": 460,
        "worker_group": "_mastermind_minimax", "worker_gid": 461,
        "provider_home": f"/private/var/db/mastermind-executive/workers/{WORKER_ID}/provider-home",
        "worker_id": WORKER_ID,
        "worker_config_path": "/Library/Application Support/MastermindExecutive/finite/minimax.json",
        "worker_config_sha256": "a" * 64, "bindings_sha256": "b" * 64,
        "physical_binding_sha256": "c" * 64,
    }
    value.update(overrides)
    return value


def group_receipt(**overrides):
    """``protected-group-membership.json`` exactly as ``Acceptance`` writes it (eight keys)."""
    value = {
        "passed": True, "effective_members": {"_mastermind_control": ["_mastermind_control"]},
        "attended_worker_membership": attended_membership(),
        "control_definition_sha256": "d" * 64,
        "primary_gid_census": "COMPLETE", "name_members": "EXACT",
        "uuid_members": "EXACT", "nested_groups": "ABSENT",
    }
    value.update(overrides)
    return value


def receipt_prefix(runtime, selected, monkeypatch, marker_schema=None):
    monkeypatch.setattr(pwd, "getpwnam", lambda name: SimpleNamespace(pw_uid=os.getuid()))
    monkeypatch.setattr(grp, "getgrnam", lambda name: SimpleNamespace(gr_gid=os.getgid()))
    root = runtime / "control/acceptance" / selected["successor_sha"]
    root.parent.chmod(0o700)
    os.chown(root.parent, -1, os.getgid())
    root.mkdir(mode=0o700)
    os.chown(root, -1, os.getgid())
    docs = {
        "nonexecutive-launchd-before.json": {"sha256": "1" * 64, "labels_excluded": 2},
        "protected-group-membership.json": group_receipt(),
    }
    for name, doc in docs.items():
        (root / name).write_text(json.dumps(doc))
        (root / name).chmod(0o400)
        os.chown(root / name, -1, os.getgid())
    m.write_sealed(m.bundle_path(selected["successor_sha"]) / "run-started.json", {
        "schema_version": marker_schema or selected["schema_version"],
        "descriptor_sha256": m.digest(selected),
    }, public=True)
    return root


def fixture(tmp_path, monkeypatch):
    d, selected, before, artifacts, canary, bundle, runtime = unstarted_fixture(tmp_path, monkeypatch)
    root = receipt_prefix(runtime, selected, monkeypatch)
    del d["superseded_unstarted_sha"]
    d.update(schema_version=m.SCHEMA_PREJOB, interrupted_prejob_sha=S,
             prejob_evidence_sha256=m.prejob_evidence(S))
    return d, selected, before, artifacts, canary, bundle, root


def unstarted_successor_fixture(tmp_path, monkeypatch, marker_schema=None):
    """A pre-Job candidate selecting a release that was itself minted with
    ``--supersede-unstarted-sha`` (the installed S2 shape): its sealed descriptor
    and run marker carry ``supersede_unstarted_v1``; its own inner link is the
    unstarted V2 ancestor."""
    d, leaf, before, artifacts, canary, leaf_bundle, runtime = unstarted_fixture(tmp_path, monkeypatch)
    sha = "1" * 40
    bundle = m.bundle_path(sha)
    shutil.copytree(leaf_bundle, bundle)
    successor = dict(leaf, schema_version=m.SCHEMA_SUPERSEDE, successor_sha=sha,
                     superseded_unstarted_sha=S, superseded_descriptor_sha256=m.digest(leaf))
    _rewrite(bundle / "descriptor.json", successor)
    _rewrite(bundle / "preparing.json", {"schema_version": m.SCHEMA_SUPERSEDE})
    root = receipt_prefix(runtime, successor, monkeypatch, marker_schema)
    del d["superseded_unstarted_sha"]
    d.update(schema_version=m.SCHEMA_PREJOB, interrupted_prejob_sha=sha,
             superseded_descriptor_sha256=m.digest(successor),
             prejob_evidence_sha256=m.prejob_evidence(sha))
    return d, successor, leaf, before, artifacts, canary, bundle, leaf_bundle, root, runtime


def test_prejob_over_unstarted_successor_walks_to_the_v2_ancestor(tmp_path, monkeypatch):
    d, successor, leaf, before, artifacts, canary, bundle, leaf_bundle, root, runtime = (
        unstarted_successor_fixture(tmp_path, monkeypatch))
    paths = [*bundle.iterdir(), *leaf_bundle.iterdir(), *root.iterdir()]
    original = {str(p): p.read_bytes() for p in paths}
    links = []
    real = m._validate_superseded_link

    def spy(descriptor, **kwargs):
        selected = real(descriptor, **kwargs)
        links.append((descriptor["schema_version"], selected["schema_version"]))
        return selected

    monkeypatch.setattr(m, "_validate_superseded_link", spy)
    m.validate_superseded_binding(d, before=before, artifacts=artifacts, prior_canary=canary)
    assert links == [(m.SCHEMA_PREJOB, m.SCHEMA_SUPERSEDE), (m.SCHEMA_SUPERSEDE, m.SCHEMA_V2)]
    assert original == {str(p): p.read_bytes() for p in paths}
    new = m.bundle_path(N)
    new.mkdir()
    m.write_sealed(new / "descriptor.json", d, public=True)
    assert m.descriptor_for(N) == d
    assert not (new / "run-started.json").exists()
    assert not (leaf_bundle / "run-started.json").exists()


@pytest.mark.parametrize("marker,refused", [
    (None, False),  # the selected release's own schema: supersede_unstarted_v1
    ("v2", True), ("prejob", True), ("v1", True),
], ids=["own-schema", "v2-marker", "prejob-marker", "v1-marker"])
def test_prejob_marker_must_carry_the_selected_releases_own_schema(tmp_path, monkeypatch, marker, refused):
    schema = {None: None, "v2": m.SCHEMA_V2, "prejob": m.SCHEMA_PREJOB, "v1": m.SCHEMA}[marker]
    d, successor, leaf, before, artifacts, canary, *_ = unstarted_successor_fixture(
        tmp_path, monkeypatch, marker_schema=schema)
    if refused:
        with pytest.raises(m.MaintenanceError, match="interrupted pre-Job evidence drifted"):
            m.validate_superseded_binding(d, before=before, artifacts=artifacts, prior_canary=canary)
    else:
        m.validate_superseded_binding(d, before=before, artifacts=artifacts, prior_canary=canary)


@pytest.mark.parametrize("fault", ["acceptance-dir", "baseline", "started", "carry"])
def test_inner_unstarted_link_stays_sealed_under_a_prejob_candidate(tmp_path, monkeypatch, fault):
    d, successor, leaf, before, artifacts, canary, bundle, leaf_bundle, root, runtime = (
        unstarted_successor_fixture(tmp_path, monkeypatch))
    if fault == "acceptance-dir":  # an older Runtime acceptance directory exists
        (runtime / "control/acceptance" / S).mkdir()
    elif fault == "baseline":  # the inner release's sealed baseline differs from live
        _rewrite(leaf_bundle / "baseline.json", {"drift": True})
    elif fault == "started":  # the inner release was in fact started
        m.write_sealed(leaf_bundle / "run-started.json", {
            "schema_version": m.SCHEMA_V2, "descriptor_sha256": m.digest(leaf)}, public=True)
    else:
        m.write_sealed(leaf_bundle / "carry-forward.json", {})
    with pytest.raises((m.MaintenanceError, OSError)):
        m.validate_superseded_binding(d, before=before, artifacts=artifacts, prior_canary=canary)


def test_exact_prejob_prefix_is_preserved_and_never_grants_replay(tmp_path, monkeypatch):
    d, selected, before, artifacts, canary, bundle, root = fixture(tmp_path, monkeypatch)
    original = {str(p): p.read_bytes() for p in [*bundle.iterdir(), *root.iterdir()]}
    m.validate_superseded_binding(d, before=before, artifacts=artifacts, prior_canary=canary)
    new = m.bundle_path(N)
    new.mkdir()
    m.write_sealed(new / "descriptor.json", d, public=True)
    assert m.descriptor_for(N) == d
    assert original == {str(p): p.read_bytes() for p in [*bundle.iterdir(), *root.iterdir()]}
    owner = object.__new__(m.Maintenance)
    owner.descriptor = d
    assert owner.predecessor_recovery_required is False
    assert m.recovery_permitted(None, "old", N, "worker", "proof") is False
    assert not (new / "run-started.json").exists()
    assert not (bundle / "carry-forward.json").exists()


@pytest.mark.parametrize("fault", [
    "marker-missing", "marker-digest", "marker-schema", "extra-bundle", "carry",
    "receipt-missing", "receipt-extra", "summary", "canary-receipt", "receipt-change",
    "receipt-mode", "receipt-link", "receipt-hardlink", "receipt-schema", "receipt-owner",
    "receipt-group", "receipt-acl", "receipt-race", "root-mode", "root-link", "root-acl",
    "parent-mode", "baseline", "live-job", "live-attempt", "live-event", "live-quota",
    "inventory", "canary", "root-identity", "selected-digest", "evidence-digest",
    "selected-schema", "selected-carry", "path-alias", "marker-supersede",
])
def test_prejob_refuses_drift_or_any_later_acceptance_state(tmp_path, monkeypatch, fault):
    d, selected, before, artifacts, canary, bundle, root = fixture(tmp_path, monkeypatch)
    receipt = root / "nonexecutive-launchd-before.json"
    if fault == "marker-missing":
        (bundle / "run-started.json").unlink()
    elif fault.startswith("marker-"):
        _rewrite(bundle / "run-started.json", {
            "schema_version": {"marker-schema": m.SCHEMA, "marker-supersede": m.SCHEMA_SUPERSEDE}.get(
                fault, m.SCHEMA_V2),
            "descriptor_sha256": "0" * 64 if fault == "marker-digest" else m.digest(selected),
        })
    elif fault in {"extra-bundle", "carry", "selected-carry"}:
        m.write_sealed(bundle / ("carry-forward.json" if fault != "extra-bundle" else "unknown.json"), {})
    elif fault == "receipt-missing":
        receipt.unlink()
    elif fault in {"receipt-extra", "summary", "canary-receipt"}:
        (root / {"receipt-extra": "unknown.json", "summary": "acceptance-summary.json",
                 "canary-receipt": "secret-canary.json"}[fault]).write_text("{}")
    elif fault in {"receipt-change", "receipt-schema"}:
        _rewrite(receipt, {"sha256": "2" * 64, "labels_excluded": 3 if fault == "receipt-schema" else 2})
    elif fault == "receipt-mode":
        receipt.chmod(0o600)
    elif fault == "receipt-link":
        target = tmp_path / "receipt"
        receipt.rename(target)
        receipt.symlink_to(target)
    elif fault == "receipt-hardlink":
        os.link(receipt, tmp_path / "receipt-link")
    elif fault in {"receipt-owner", "receipt-group"}:
        if fault == "receipt-owner":
            monkeypatch.setattr(pwd, "getpwnam", lambda name: SimpleNamespace(pw_uid=os.getuid()+1))
        else:
            monkeypatch.setattr(grp, "getgrnam", lambda name: SimpleNamespace(gr_gid=os.getgid()+1))
    elif fault in {"receipt-acl", "root-acl"}:
        from ops.executive_os import autonomy_control as ac
        monkeypatch.setattr(ac, "_has_acl", lambda path: path == receipt)
        if fault == "root-acl":
            monkeypatch.setattr(m, "has_macos_acl", lambda path: path == root)
    elif fault == "receipt-race":
        from ops.executive_os import autonomy_control as ac
        original = ac._root_json
        def racing(path, **kwargs):
            result = original(path, **kwargs)
            if path == receipt:
                _rewrite(path, {"sha256": "7" * 64, "labels_excluded": 2})
            return result
        monkeypatch.setattr(ac, "_root_json", racing)
    elif fault in {"root-mode", "parent-mode"}:
        (root if fault == "root-mode" else root.parent).chmod(0o755)
    elif fault == "root-link":
        target = tmp_path / "receipts"
        root.rename(target)
        root.symlink_to(target)
    elif fault == "path-alias":
        target = root.parent.with_name("actual-acceptance")
        root.parent.rename(target)
        root.parent.symlink_to(target)
    elif fault == "baseline":
        _rewrite(bundle / "baseline.json", {"changed": True})
    elif fault.startswith("live-"):
        before["tables"][fault.removeprefix("live-")] = [{"changed": True}]
    elif fault == "inventory":
        artifacts["changed"] = True
    elif fault == "canary":
        canary["changed"] = True
    elif fault == "root-identity":
        d["root_job_id"] = "foreign"
    elif fault == "selected-digest":
        d["superseded_descriptor_sha256"] = "0" * 64
    elif fault == "evidence-digest":
        d["prejob_evidence_sha256"] = "0" * 64
    elif fault == "selected-schema":
        selected["schema_version"] = m.SCHEMA_PREJOB
        _rewrite(bundle / "descriptor.json", selected)
    with pytest.raises((m.MaintenanceError, OSError)):
        m.validate_superseded_binding(d, before=before, artifacts=artifacts, prior_canary=canary)


GROUP_RECEIPT = "protected-group-membership.json"
SCHEMA_DRIFT = "interrupted acceptance receipt schema drifted"
MEMBERSHIP_KEYS = sorted(attended_membership())


def _write_group_receipt(root, value):
    _rewrite(root / GROUP_RECEIPT, value)


def test_group_receipt_fixture_is_the_producers_eight_key_form(tmp_path, monkeypatch):
    d, selected, before, artifacts, canary, bundle, root = fixture(tmp_path, monkeypatch)
    assert set(json.loads((root / GROUP_RECEIPT).read_text())) == m._GROUP_RECEIPT_KEYS == {
        "passed", "effective_members", "attended_worker_membership", "control_definition_sha256",
        "primary_gid_census", "name_members", "uuid_members", "nested_groups"}
    assert set(attended_membership()) == m._ATTENDED_MEMBERSHIP_KEYS
    assert m.prejob_evidence(S) == d["prejob_evidence_sha256"]


def test_group_receipt_without_a_finite_worker_stanza_is_accepted(tmp_path, monkeypatch):
    # ``_attended_worker_membership`` returns None when control.json has no fabric_attended_probe.
    d, selected, before, artifacts, canary, bundle, root = fixture(tmp_path, monkeypatch)
    _write_group_receipt(root, group_receipt(attended_worker_membership=None))
    assert len(m.prejob_evidence(S)) == 64


def _legacy_six_key_receipt():
    return {"passed": True, "effective_members": {"control": ["fixture"]},
            "primary_gid_census": "COMPLETE", "name_members": "EXACT",
            "uuid_members": "EXACT", "nested_groups": "ABSENT"}


def _without(key):
    value = group_receipt()
    del value[key]
    return value


@pytest.mark.parametrize("receipt", [
    group_receipt(unexpected="x"),
    _without("control_definition_sha256"),
    _without("attended_worker_membership"),
    group_receipt(control_definition_sha256="z" * 64),
    group_receipt(control_definition_sha256="D" * 64),
    group_receipt(control_definition_sha256="d" * 63),
    group_receipt(control_definition_sha256=None),
    group_receipt(control_definition_sha256=int("1" * 64)),
    group_receipt(attended_worker_membership=attended_membership(unexpected="x")),
    group_receipt(attended_worker_membership=["a"]),
    group_receipt(attended_worker_membership="membership"),
    group_receipt(attended_worker_membership={}),
    group_receipt(attended_worker_membership=attended_membership(worker_uid="460")),
    group_receipt(attended_worker_membership=attended_membership(worker_gid="461")),
    group_receipt(attended_worker_membership=attended_membership(worker_uid=True)),
    group_receipt(attended_worker_membership=attended_membership(worker_uid=500)),
    group_receipt(attended_worker_membership=attended_membership(worker_gid=399)),
    group_receipt(attended_worker_membership=attended_membership(worker_user="minimax")),
    group_receipt(attended_worker_membership=attended_membership(worker_user="_mastermind_" + "x" * 20)),
    group_receipt(attended_worker_membership=attended_membership(worker_group="_Mastermind_minimax")),
    group_receipt(attended_worker_membership=attended_membership(worker_id="")),
    group_receipt(attended_worker_membership=attended_membership(worker_config_path="finite/minimax.json")),
    group_receipt(attended_worker_membership=attended_membership(
        provider_home="/private/var/db/mastermind-executive/workers/other/provider-home")),
    group_receipt(attended_worker_membership=attended_membership(worker_config_sha256="z" * 64)),
    group_receipt(attended_worker_membership=attended_membership(bindings_sha256="b" * 63)),
    group_receipt(attended_worker_membership=attended_membership(physical_binding_sha256=7)),
    group_receipt(passed=False),
    group_receipt(effective_members=["x"]),
    group_receipt(primary_gid_census="PARTIAL"),
    group_receipt(name_members="INEXACT"),
    group_receipt(uuid_members="INEXACT"),
    group_receipt(nested_groups="PRESENT"),
    _legacy_six_key_receipt(),
], ids=[
    "extra-top-level-key", "missing-control-definition", "missing-attended-membership",
    "control-definition-non-hex", "control-definition-uppercase", "control-definition-short",
    "control-definition-none", "control-definition-int",
    "membership-extra-key", "membership-list", "membership-str", "membership-empty",
    "uid-str", "gid-str", "uid-bool", "uid-out-of-range", "gid-out-of-range",
    "user-pattern", "user-too-long", "group-pattern", "worker-id-empty", "config-path-relative",
    "provider-home-not-derived", "config-sha-non-hex", "bindings-sha-short", "physical-sha-int",
    "passed-false", "effective-members-list", "gid-census-partial", "name-members-inexact",
    "uuid-members-inexact", "nested-groups-present", "legacy-six-key-form",
])
def test_group_receipt_must_match_the_producers_exact_shape(tmp_path, monkeypatch, receipt):
    d, selected, before, artifacts, canary, bundle, root = fixture(tmp_path, monkeypatch)
    _write_group_receipt(root, receipt)
    with pytest.raises(m.MaintenanceError, match=SCHEMA_DRIFT):
        m.prejob_evidence(S)
    with pytest.raises(m.MaintenanceError, match=SCHEMA_DRIFT):  # the sealed binding refuses it too
        m.validate_superseded_binding(d, before=before, artifacts=artifacts, prior_canary=canary)


@pytest.mark.parametrize("key", MEMBERSHIP_KEYS)
def test_group_receipt_membership_requires_every_field(tmp_path, monkeypatch, key):
    d, selected, before, artifacts, canary, bundle, root = fixture(tmp_path, monkeypatch)
    membership = attended_membership()
    del membership[key]
    _write_group_receipt(root, group_receipt(attended_worker_membership=membership))
    with pytest.raises(m.MaintenanceError, match=SCHEMA_DRIFT):
        m.prejob_evidence(S)


def test_unstarted_stays_strict_with_the_same_prejob_prefix(tmp_path, monkeypatch):
    d, selected, before, artifacts, canary, bundle, root = fixture(tmp_path, monkeypatch)
    del d["interrupted_prejob_sha"], d["prejob_evidence_sha256"]
    d.update(schema_version=m.SCHEMA_SUPERSEDE, superseded_unstarted_sha=S)
    with pytest.raises(m.MaintenanceError, match="partial state"):
        m.validate_superseded_binding(d, before=before, artifacts=artifacts, prior_canary=canary)


@pytest.mark.parametrize("mutation", [
    {"interrupted_prejob_sha": A}, {"interrupted_prejob_sha": N},
    {"interrupted_prejob_sha": "bad"}, {"prejob_evidence_sha256": "bad"}, {"extra": True},
])
def test_prejob_descriptor_is_closed_and_binds_distinct_releases(tmp_path, monkeypatch, mutation):
    d, *_ = fixture(tmp_path, monkeypatch)
    d.update(mutation)
    root = m.bundle_path(N)
    root.mkdir()
    m.write_sealed(root / "descriptor.json", d, public=True)
    with pytest.raises(m.MaintenanceError):
        m.descriptor_for(N)


@pytest.mark.parametrize("drift", [False, True])
def test_prejob_is_revalidated_before_new_run_marker(tmp_path, monkeypatch, drift):
    d, selected, before, artifacts, canary, bundle, root = fixture(tmp_path, monkeypatch)
    runtime = root.parent.parent.parent
    new = m.bundle_path(N)
    new.mkdir()
    for name in ("baseline.json", "inventory.json", "prior-secret-canary.json", "prestate.sqlite3"):
        (new / name).write_bytes((bundle / name).read_bytes())
        (new / name).chmod(0o400)
    m.write_sealed(new / "descriptor.json", d, public=True)
    monkeypatch.setattr(m, "validate_prior_carry_binding", lambda descriptor: None)
    monkeypatch.setattr(m, "require_stopped", lambda: None)
    monkeypatch.setattr(m, "verify_inventory", lambda value: None)
    database = runtime / "data/control_plane/executive.sqlite3"
    database.parent.mkdir(parents=True)
    database.write_bytes((bundle / "prestate.sqlite3").read_bytes())
    live_canary = tmp_path / "live-canary.json"
    live_canary.write_text(json.dumps(canary))
    from control_plane.executive_runtime import Runtime
    monkeypatch.setattr(Runtime, "at", lambda *a, **kw: SimpleNamespace(
        jobs=SimpleNamespace(get_job=lambda job: SimpleNamespace(job_id=job))))
    monkeypatch.setattr(m, "terminal_carry_fields", lambda *a: (None, {
        key: d[key] for key in m._DESCRIPTOR_V2_KEYS - m._DESCRIPTOR_KEYS}))
    config = dict(runtime_root=str(runtime), secret_canary_receipt_path=str(live_canary),
                  ceo_submit_armed=False, coo_autonomy_armed=False, coo_operator_harness_armed=False)
    if drift:
        _rewrite(root / "nonexecutive-launchd-before.json", {"sha256": "9" * 64, "labels_excluded": 2})
        with pytest.raises(m.MaintenanceError):
            m.Maintenance(N, m.digest(d), config)
        assert not (new / "run-started.json").exists()
    else:
        owner = m.Maintenance(N, m.digest(d), config)
        assert owner.predecessor_recovery_required is False
        assert m.sealed_json(new / "run-started.json") == {
            "schema_version": m.SCHEMA_PREJOB, "descriptor_sha256": m.digest(d)}
        with pytest.raises(FileExistsError):
            m.Maintenance(N, m.digest(d), config)


@pytest.mark.parametrize("fault", [None, "absolute", "target", "owner", "changed", "descendant", "linux"])
def test_existing_prejob_receipts_accept_only_trusted_var_alias(tmp_path, monkeypatch, fault):
    from ops.executive_os import autonomy_control as ac
    d, selected, before, artifacts, canary, bundle, root = fixture(tmp_path, monkeypatch)
    physical = tmp_path / "private/var"
    (physical / "db").mkdir(parents=True)
    root.parent.parent.parent.rename(physical / "db/mastermind-executive")
    alias = tmp_path / "var"
    alias.symlink_to(physical if fault == "absolute" else "private/var")
    monkeypatch.setattr(m, "_MACOS_VAR_ALIAS", alias)
    monkeypatch.setattr(m, "_MACOS_VAR_PHYSICAL", physical)
    # Isolate the target-platform branch without changing the real ACL host.
    monkeypatch.setattr(m, "sys", SimpleNamespace(platform="linux" if fault == "linux" else "darwin"))
    monkeypatch.setattr(ac, "RUNTIME_ROOT", alias / "db/mastermind-executive")
    if fault == "target":
        alias.unlink()
        alias.symlink_to("private/./var")
    elif fault == "owner":
        original = Path.lstat
        def foreign(path, *args, **kwargs):
            info = original(path, *args, **kwargs)
            if path == alias:
                return SimpleNamespace(**{key: getattr(info, key) for key in dir(info)
                    if key.startswith("st_") and key != "st_uid"}, st_uid=info.st_uid+1)
            return info
        monkeypatch.setattr(Path, "lstat", foreign)
    elif fault == "descendant":
        parent = physical / "db/mastermind-executive/control/acceptance"
        moved = tmp_path / "moved"
        parent.rename(moved)
        parent.symlink_to(moved)
    elif fault == "changed":
        original = ac._root_json
        def changed(path, **kwargs):
            result = original(path, **kwargs)
            alias.unlink()
            alias.symlink_to("private/./var")
            return result
        monkeypatch.setattr(ac, "_root_json", changed)
    if fault in {None, "absolute"}:
        m.validate_superseded_binding(d, before=before, artifacts=artifacts, prior_canary=canary)
    else:
        with pytest.raises((m.MaintenanceError, OSError)):
            m.validate_superseded_binding(d, before=before, artifacts=artifacts, prior_canary=canary)

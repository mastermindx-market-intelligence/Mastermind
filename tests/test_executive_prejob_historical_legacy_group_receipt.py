"""An already-sealed pre-Job link may carry the legacy six-key group receipt; a candidate may not.

``supersede_prejob_v1`` descriptors minted before the eight-key receipt (the Oct 11
``protected-group-membership.json`` generation) seal ``prejob_evidence_sha256`` over those
receipt bytes. The carry-chain walk (``validate_prior_carry_binding``, the single
``historical=True`` site) re-validates such links as ``historical``. ``prepare`` and the strict
``validate_superseded_binding`` check in ``Maintenance.__init__`` leave the flag unset and keep
requiring the current eight-key form; at acceptance start the walk also visits the candidate's
own selected link once, and the strict check that follows it still refuses the legacy form.
Exactly two generations are admitted; any other shape is refused with the same schema-drift error.
"""
import argparse
import ast
import dataclasses
import hashlib
import json
import os
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from ops.executive_os import acceptance_maintenance as m
from tests.test_executive_acceptance_supersede_prejob import (
    GROUP_RECEIPT, SCHEMA_DRIFT, _legacy_six_key_receipt, _without, _write_group_receipt,
    attended_membership, fixture as prejob_fixture, group_receipt, receipt_prefix,
    unstarted_successor_fixture,
)
from tests.test_executive_acceptance_supersede_unstarted import A, N, S, _rewrite

LAUNCHD_RECEIPT = "nonexecutive-launchd-before.json"


def legacy_prejob(tmp_path, monkeypatch):
    """The shared pre-Job fixture with the group receipt rewritten to the pre-1609 six-key form
    and the descriptor sealed over those exact bytes, as ``supersede_prejob_v1`` links were."""
    d, selected, before, artifacts, canary, bundle, root = prejob_fixture(tmp_path, monkeypatch)
    _write_group_receipt(root, _legacy_six_key_receipt())
    d["prejob_evidence_sha256"] = m.prejob_evidence(S, historical=True)
    return d, selected, before, artifacts, canary, bundle, root


def seal_as_historical_link(monkeypatch, d):
    """Publish ``d`` as an accepted, carried ancestor so the real carry walk reaches it.

    Only the accepted ancestor ``A`` (which has no descriptor here) and the control-owned
    acceptance summary are stubbed; ``prior_carry_material`` / ``validate_carry_receipt`` /
    ``validate_prior_carry_binding`` / ``validate_superseded_binding`` all run for real.
    """
    bundle = m.bundle_path(d["successor_sha"])
    bundle.mkdir()
    m.write_sealed(bundle / "descriptor.json", d, public=True)
    summary = b"accepted-summary"
    m.write_sealed(bundle / "carry-forward.json", dict(
        schema_version=d["schema_version"], passed=True, baseline_preserved=True,
        descriptor_sha256=m.digest(d), acceptance_summary_sha256=hashlib.sha256(summary).hexdigest()),
        public=True)
    ancestor = {key: d[key] for key in
                ("root_job_id", "root_identity_sha256", "root_event_id", "root_event_sha256")}
    material = {key: d[key] for key in
                ("prior_descriptor_sha256", "prior_carry_sha256", "prior_summary_sha256", "frozen_base_sha")}
    real = m.prior_carry_material
    monkeypatch.setattr(m, "summary_document", lambda sha: ({}, summary))
    monkeypatch.setattr(m, "prior_carry_material", lambda sha, **kw: (
        (ancestor, {}, material) if sha == A else real(sha, **kw)))
    return bundle


def future_descriptor(d):
    """A later release carrying ``d`` forward (schema V2: no supersession check of its own)."""
    _prior, _summary, material = m.prior_carry_material(d["successor_sha"])
    return dict(d, schema_version=m.SCHEMA_V2, predecessor_sha=d["successor_sha"],
                successor_sha="e" * 40, **material)


# --- (a) the historical walk admits the legacy generation ------------------------------------

def test_legacy_receipt_digest_is_a_function_of_the_sealed_bytes_only(tmp_path, monkeypatch):
    d, selected, before, artifacts, canary, bundle, root = legacy_prejob(tmp_path, monkeypatch)
    assert m._LEGACY_GROUP_RECEIPT_KEYS == {
        "passed", "effective_members", "primary_gid_census", "name_members", "uuid_members",
        "nested_groups"}
    assert set(json.loads((root / GROUP_RECEIPT).read_text())) == m._LEGACY_GROUP_RECEIPT_KEYS
    manifest = {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                for name in (LAUNCHD_RECEIPT, GROUP_RECEIPT)}
    assert m.prejob_evidence(S, historical=True) == d["prejob_evidence_sha256"] == m.digest(manifest)


def test_current_generation_digest_does_not_depend_on_the_flag(tmp_path, monkeypatch):
    # The flag widens the admitted shapes only; it never changes how the manifest is built.
    d, *_ = prejob_fixture(tmp_path, monkeypatch)
    assert m.prejob_evidence(S, historical=True) == m.prejob_evidence(S) == d["prejob_evidence_sha256"]


def test_historical_link_with_legacy_receipt_is_admitted_and_nothing_is_modified(tmp_path, monkeypatch):
    d, selected, before, artifacts, canary, bundle, root = legacy_prejob(tmp_path, monkeypatch)
    paths = [*bundle.iterdir(), *root.iterdir()]
    original = {str(p): p.read_bytes() for p in paths}
    m.validate_superseded_binding(d, historical=True)  # the walk's shape: sealed bundle only
    m.validate_superseded_binding(d, before=before, artifacts=artifacts, prior_canary=canary,
                                  historical=True)
    assert original == {str(p): p.read_bytes() for p in paths}
    assert {p.name for p in root.iterdir()} == {LAUNCHD_RECEIPT, GROUP_RECEIPT}


@pytest.mark.parametrize("generation", ["legacy", "current"])
def test_full_carry_walk_admits_a_sealed_prejob_link_of_either_generation(tmp_path, monkeypatch, generation):
    prepare = legacy_prejob if generation == "legacy" else prejob_fixture
    d, selected, before, artifacts, canary, bundle, root = prepare(tmp_path, monkeypatch)
    seal_as_historical_link(monkeypatch, d)
    future = future_descriptor(d)
    calls = []
    real = m.prejob_evidence

    def spy(sha, **kwargs):
        result = real(sha, **kwargs)
        calls.append((sha, kwargs, result))
        return result

    monkeypatch.setattr(m, "prejob_evidence", spy)
    m.validate_prior_carry_binding(future)
    # The sealed link was recomputed through the historical flag and matched its sealed digest.
    assert calls == [(S, {"historical": True}, d["prejob_evidence_sha256"])]
    # The same descriptor validated without the flag (the strict candidate call) refuses the legacy shape.
    if generation == "legacy":
        with pytest.raises(m.MaintenanceError, match=SCHEMA_DRIFT):
            m.validate_superseded_binding(d, before=before, artifacts=artifacts, prior_canary=canary)


def test_full_carry_walk_depends_on_the_historical_flag(tmp_path, monkeypatch):
    # Control: with the flag pinned off the same chain is refused, so the walk really relies on it.
    d, *_ = legacy_prejob(tmp_path, monkeypatch)
    seal_as_historical_link(monkeypatch, d)
    future = future_descriptor(d)
    real = m.prejob_evidence
    monkeypatch.setattr(m, "prejob_evidence", lambda sha, **kw: real(sha, historical=False))
    with pytest.raises(m.MaintenanceError, match=SCHEMA_DRIFT):
        m.validate_prior_carry_binding(future)


def test_flag_reaches_every_link_of_a_nested_chain(tmp_path, monkeypatch):
    d, successor, leaf, before, artifacts, canary, bundle, leaf_bundle, root, runtime = (
        unstarted_successor_fixture(tmp_path, monkeypatch))
    sha = d["interrupted_prejob_sha"]
    _write_group_receipt(root, _legacy_six_key_receipt())
    d["prejob_evidence_sha256"] = m.prejob_evidence(sha, historical=True)
    seen = []
    real = m._validate_superseded_link

    def spy(descriptor, **kwargs):
        selected = real(descriptor, **kwargs)
        seen.append((descriptor["schema_version"], selected["schema_version"], kwargs["historical"]))
        return selected

    monkeypatch.setattr(m, "_validate_superseded_link", spy)
    m.validate_superseded_binding(d, historical=True)
    assert seen == [(m.SCHEMA_PREJOB, m.SCHEMA_SUPERSEDE, True), (m.SCHEMA_SUPERSEDE, m.SCHEMA_V2, True)]
    seen.clear()
    with pytest.raises(m.MaintenanceError, match=SCHEMA_DRIFT):
        m.validate_superseded_binding(d, before=before, artifacts=artifacts, prior_canary=canary)
    assert seen == []  # refused at the first link, before any nested walk


# --- (b) candidate paths stay strict ---------------------------------------------------------

def test_candidate_helpers_refuse_the_legacy_shape(tmp_path, monkeypatch):
    d, selected, before, artifacts, canary, bundle, root = legacy_prejob(tmp_path, monkeypatch)
    with pytest.raises(m.MaintenanceError, match=SCHEMA_DRIFT):
        m.prejob_evidence(S)
    with pytest.raises(m.MaintenanceError, match=SCHEMA_DRIFT):
        m.prejob_evidence(S, historical=False)
    with pytest.raises(m.MaintenanceError, match=SCHEMA_DRIFT):
        m.validate_superseded_binding(d, before=before, artifacts=artifacts, prior_canary=canary)
    with pytest.raises(m.MaintenanceError, match=SCHEMA_DRIFT):
        m.validate_superseded_binding(d)


def prejob_prepare_harness(tmp_path, monkeypatch, *, legacy):
    """The ``prepare`` harness of ``test_preparation_publishes_one_new_descriptor_*`` (pre-Job mode),
    with the interrupted release's protected-group receipt in the requested generation."""
    from control_plane.executive_runtime import Runtime
    from ops.executive_os import autonomy_control as ac
    from tests.test_executive_acceptance_maintenance_v2 import _terminal_fixture
    runtime, root, before, config, prior, material, proof, _, _ = _terminal_fixture(tmp_path, monkeypatch)
    accepted, selected_sha, successor = "b" * 40, "e" * 40, "f" * 40
    root = dataclasses.replace(root, constraints={**root.constraints, "operator_harness_armed": False})
    prior["root_identity_sha256"] = m.root_identity(root)
    original = runtime.jobs.get_job
    monkeypatch.setattr(runtime.jobs, "get_job", lambda job: root if job == root.job_id else original(job))
    monkeypatch.setattr(Runtime, "at", lambda *args, **kwargs: runtime)
    system = tmp_path / "system"
    (system / "config").mkdir(parents=True)
    monkeypatch.setattr(m, "SYSTEM_ROOT", system)
    monkeypatch.setattr(m, "_TRUSTED_UID", os.getuid())
    monkeypatch.setattr(m, "_TRUSTED_GID", os.getgid())
    monkeypatch.setattr(m, "_sealed_ancestors", lambda path: [])
    monkeypatch.setattr(m, "has_macos_acl", lambda *args, **kwargs: False)
    monkeypatch.setattr(m.os, "geteuid", lambda: 0)
    monkeypatch.setattr(m, "sys", SimpleNamespace(platform="darwin"))
    monkeypatch.setattr(m, "require_stopped", lambda: None)
    runtime_root = tmp_path / "runtime"
    (runtime_root / "control" / "acceptance").mkdir(parents=True)
    monkeypatch.setattr(ac, "RUNTIME_ROOT", runtime_root)
    config.update(runtime_root=str(runtime_root), proof_base_sha=selected_sha,
                  ceo_submit_armed=False, coo_autonomy_armed=False, coo_operator_harness_armed=False)
    for key in ("proof_workspace_root", "worker_runs_root", "receipts_root", "backup_root"):
        path = tmp_path / "artifacts" / key
        path.mkdir(parents=True)
        config[key] = str(path)
    canary_fixtures = runtime_root.parent.parent / "canary-fixtures"
    canary_fixtures.mkdir(exist_ok=True)
    canary_path = tmp_path / "prior-canary.json"
    canary = {"passed": True}
    canary_path.write_text(json.dumps(canary))
    config["secret_canary_receipt_path"] = str(canary_path)
    (system / "config" / "control.json").write_text(json.dumps(config))
    (system / "config" / "worker-codex.json").write_text('{"operator_harness_armed":false}')
    artifacts = m.inventory([Path(config[key]) for key in
        ("proof_workspace_root", "worker_runs_root", "receipts_root", "backup_root")] + [canary_fixtures])
    _proof, fields = m.terminal_carry_fields(runtime, root, config, before, accepted)
    bundle = m.bundle_path(selected_sha)
    bundle.mkdir(parents=True)
    with sqlite3.connect(runtime.store.path) as source, sqlite3.connect(bundle / "prestate.sqlite3") as dest:
        source.backup(dest)
    (bundle / "prestate.sqlite3").chmod(0o400)
    selected = dict(schema_version=m.SCHEMA_V2, predecessor_sha=accepted, successor_sha=selected_sha,
        root_job_id=root.job_id, root_identity_sha256=m.root_identity(root), root_event_id=prior["root_event_id"],
        root_event_sha256=prior["root_event_sha256"], worker_id=config["worker_id"], quota_class=config["quota_class"],
        baseline_sha256=m.digest(before), inventory_sha256=m.digest(artifacts), prior_canary_sha256=m.digest(canary),
        backup_sha256=m._file_digest(bundle / "prestate.sqlite3"), **fields)
    for filename, value in [("descriptor.json", selected), ("preparing.json", {"schema_version": m.SCHEMA_V2}),
                            ("baseline.json", before), ("inventory.json", artifacts),
                            ("prior-secret-canary.json", canary)]:
        m.write_sealed(bundle / filename, value, public=filename == "descriptor.json")
    receipts = receipt_prefix(runtime_root, selected, monkeypatch)
    if legacy:
        _write_group_receipt(receipts, _legacy_six_key_receipt())
    args = argparse.Namespace(predecessor_sha=accepted, successor_sha=successor, root_job_id=root.job_id,
        recovery_job_id=None, recovery_attempt_id=None, carry_terminal_dispatch=True,
        supersede_unstarted_sha=None, supersede_prejob_sha=selected_sha,
        superseded_descriptor_sha256=m.digest(selected))
    return args, runtime, before, bundle, receipts


@pytest.mark.parametrize("legacy", [False, True], ids=["current-eight-key", "legacy-six-key"])
def test_prepare_requires_the_current_receipt_shape_for_the_candidate(tmp_path, monkeypatch, legacy):
    args, runtime, before, bundle, receipts = prejob_prepare_harness(tmp_path, monkeypatch, legacy=legacy)
    originals = {p.name: p.read_bytes() for p in [*bundle.iterdir(), *receipts.iterdir()]}
    if legacy:
        with pytest.raises(m.MaintenanceError, match=SCHEMA_DRIFT):
            m.prepare(args)
        assert not m.bundle_path(args.successor_sha).exists()
        assert not list(m.bundle_path(args.successor_sha).parent.glob(".preparing-*"))
    else:  # control: the same harness prepares when the interrupted receipt is current
        result = m.prepare(args)
        descriptor = m.descriptor_for(args.successor_sha)
        assert result == m.bundle_path(args.successor_sha)
        assert descriptor["schema_version"] == m.SCHEMA_PREJOB
        assert descriptor["interrupted_prejob_sha"] == args.supersede_prejob_sha
    assert originals == {p.name: p.read_bytes() for p in [*bundle.iterdir(), *receipts.iterdir()]}
    assert m.snapshot(runtime.store.path) == before


def test_acceptance_start_requires_the_current_receipt_shape(tmp_path, monkeypatch):
    d, selected, before, artifacts, canary, bundle, root = legacy_prejob(tmp_path, monkeypatch)
    runtime = root.parent.parent.parent
    new = m.bundle_path(N)
    new.mkdir()
    for name in ("baseline.json", "inventory.json", "prior-secret-canary.json", "prestate.sqlite3"):
        (new / name).write_bytes((bundle / name).read_bytes())
        (new / name).chmod(0o400)
    m.write_sealed(new / "descriptor.json", d, public=True)
    # The carry walk at the top of ``Maintenance.__init__`` is stubbed out (its prior-carry material
    # is out of scope here). In production that walk is the historical path and would admit the
    # legacy form for this link once; the refusal asserted below comes from the strict
    # ``validate_superseded_binding`` check that follows it, which does not set ``historical``.
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
    with pytest.raises(m.MaintenanceError, match=SCHEMA_DRIFT):
        m.Maintenance(N, m.digest(d), config)
    assert not (new / "run-started.json").exists()


def test_historical_flag_is_set_at_exactly_one_site_the_carry_chain_walk():
    tree = ast.parse(Path(m.__file__).read_text())
    sites = []
    for function in ast.walk(tree):
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(function):
            if isinstance(node, ast.Call) and any(
                    kw.arg == "historical" and isinstance(kw.value, ast.Constant) and kw.value.value is True
                    for kw in node.keywords):
                sites.append((function.name, getattr(node.func, "id", getattr(node.func, "attr", None))))
    assert sites == [("validate_prior_carry_binding", "validate_superseded_binding")]


# --- (c) the admitted shapes are closed: exactly two generations -----------------------------

def _legacy(**overrides):
    return {**_legacy_six_key_receipt(), **overrides}


def _legacy_without(key):
    value = _legacy_six_key_receipt()
    del value[key]
    return value


UNKNOWN_SHAPES = [
    _legacy(unexpected="x"),                                   # legacy + one extra key (7 keys)
    _legacy(control_definition_sha256="d" * 64),               # a third, half-upgraded generation
    _legacy(attended_worker_membership=None),
    _legacy(attended_worker_membership=attended_membership()),
    _legacy_without("passed"),
    _legacy_without("effective_members"),
    _legacy_without("primary_gid_census"),
    _legacy_without("name_members"),
    _legacy_without("uuid_members"),
    _legacy_without("nested_groups"),
    _legacy(passed=False),
    _legacy(passed=1),
    _legacy(nested_groups="PRESENT"),
    _legacy(nested_groups="absent"),
    _legacy(primary_gid_census="PARTIAL"),
    _legacy(name_members="INEXACT"),
    _legacy(uuid_members="INEXACT"),
    _legacy(effective_members=["x"]),
    {},
    group_receipt(attended_worker_membership=attended_membership(unexpected="x")),
    group_receipt(attended_worker_membership="membership"),
    group_receipt(attended_worker_membership={}),
    group_receipt(attended_worker_membership=attended_membership(worker_uid="460")),
    group_receipt(control_definition_sha256="z" * 64),
    group_receipt(control_definition_sha256=None),
    _without("control_definition_sha256"),
    _without("attended_worker_membership"),
    group_receipt(unexpected="x"),
    group_receipt(passed=False),
    group_receipt(nested_groups="PRESENT"),
]
UNKNOWN_IDS = [
    "legacy-plus-extra-key", "legacy-plus-control-definition", "legacy-plus-membership-none",
    "legacy-plus-membership", "legacy-minus-passed", "legacy-minus-effective-members",
    "legacy-minus-gid-census", "legacy-minus-name-members", "legacy-minus-uuid-members",
    "legacy-minus-nested-groups", "legacy-passed-false", "legacy-passed-int",
    "legacy-nested-present", "legacy-nested-lowercase", "legacy-gid-census-partial",
    "legacy-name-inexact", "legacy-uuid-inexact", "legacy-effective-members-list", "empty",
    "current-membership-extra-key", "current-membership-str", "current-membership-empty",
    "current-membership-uid-str", "current-control-definition-non-hex",
    "current-control-definition-none", "current-minus-control-definition",
    "current-minus-membership", "current-extra-key", "current-passed-false",
    "current-nested-present",
]


@pytest.mark.parametrize("receipt", UNKNOWN_SHAPES, ids=UNKNOWN_IDS)
def test_historical_walk_still_refuses_every_other_shape(tmp_path, monkeypatch, receipt):
    d, selected, before, artifacts, canary, bundle, root = prejob_fixture(tmp_path, monkeypatch)
    _write_group_receipt(root, receipt)
    with pytest.raises(m.MaintenanceError, match=SCHEMA_DRIFT):
        m.prejob_evidence(S, historical=True)
    with pytest.raises(m.MaintenanceError, match=SCHEMA_DRIFT):
        m.validate_superseded_binding(d, historical=True)


def test_historical_walk_does_not_loosen_the_launchd_receipt(tmp_path, monkeypatch):
    d, selected, before, artifacts, canary, bundle, root = legacy_prejob(tmp_path, monkeypatch)
    for receipt in ({"sha256": "1" * 64, "labels_excluded": 2, "extra": 1},
                    {"sha256": "1" * 63, "labels_excluded": 2},
                    {"sha256": "1" * 64, "labels_excluded": 3}):
        _rewrite(root / LAUNCHD_RECEIPT, receipt)
        with pytest.raises(m.MaintenanceError, match=SCHEMA_DRIFT):
            m.prejob_evidence(S, historical=True)


@pytest.mark.parametrize("change", ["other-value", "reformatted"])
def test_legacy_receipt_bytes_changed_after_sealing_are_refused(tmp_path, monkeypatch, change):
    d, selected, before, artifacts, canary, bundle, root = legacy_prejob(tmp_path, monkeypatch)
    value = _legacy_six_key_receipt()
    if change == "other-value":
        value["effective_members"] = {"control": ["someone-else"]}
        _rewrite(root / GROUP_RECEIPT, value)
    else:  # same parsed value, different bytes: the seal covers bytes, not meaning
        (root / GROUP_RECEIPT).chmod(0o600)
        (root / GROUP_RECEIPT).write_text(json.dumps(value, indent=2))
        (root / GROUP_RECEIPT).chmod(0o400)
    assert set(json.loads((root / GROUP_RECEIPT).read_text())) == m._LEGACY_GROUP_RECEIPT_KEYS
    with pytest.raises(m.MaintenanceError, match="interrupted pre-Job evidence drifted"):
        m.validate_superseded_binding(d, historical=True)


def test_legacy_receipt_must_still_be_a_read_only_control_owned_file(tmp_path, monkeypatch):
    d, selected, before, artifacts, canary, bundle, root = legacy_prejob(tmp_path, monkeypatch)
    (root / GROUP_RECEIPT).chmod(0o600)
    with pytest.raises(m.MaintenanceError, match="interrupted acceptance receipt is unsafe"):
        m.prejob_evidence(S, historical=True)
    with pytest.raises(m.MaintenanceError, match="interrupted acceptance receipt is unsafe"):
        m.validate_superseded_binding(d, historical=True)

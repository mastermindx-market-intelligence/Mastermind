"""Preserved runtime history and sealed maintenance evidence are fail-closed."""
from copy import deepcopy
from pathlib import Path
import json
import os
import sqlite3

import pytest

from ops.executive_os import acceptance_maintenance as m


def test_snapshot_is_canonical_across_insert_order_and_backup(tmp_path):
    paths = [tmp_path/"first.sqlite3", tmp_path/"second.sqlite3"]
    for path, order in zip(paths, [(3,1,2),(2,3,1)]):
        with sqlite3.connect(path) as c:
            c.execute("CREATE TABLE values_owned (key INTEGER PRIMARY KEY, value TEXT)")
            c.executemany("INSERT INTO values_owned VALUES (?,?)", [(i,str(i)) for i in order])
    assert m.snapshot(paths[0]) == m.snapshot(paths[1])


def test_inventory_detects_directory_replacement_and_leaf_changes(tmp_path):
    root = tmp_path/"artifacts"
    root.mkdir()
    (root/"artifact").write_text("original")
    baseline = m.inventory([root])
    m.verify_inventory(baseline)
    moved = tmp_path/"preserved"
    root.rename(moved)
    root.mkdir()
    (root/"artifact").write_text("original")
    with pytest.raises(m.MaintenanceError, match="changed"):
        m.verify_inventory(baseline)


@pytest.fixture
def sealed_reader(monkeypatch):
    monkeypatch.setattr(m, "_TRUSTED_UID", os.getuid())
    # Host ancestor policy is tested separately; temp roots are user-owned.
    monkeypatch.setattr(m, "_sealed_ancestors", lambda path: [])
    return m.sealed_json


def test_sealed_reader_rejects_mode_links_and_hardlinks(tmp_path, sealed_reader):
    target = tmp_path/"receipt.json"
    target.write_text('{"passed":true}')
    target.chmod(0o444)
    assert sealed_reader(target) == {"passed":True}
    target.chmod(0o644)
    with pytest.raises(m.MaintenanceError):
        sealed_reader(target)
    target.chmod(0o444)
    link = tmp_path/"alias"
    link.symlink_to(target)
    with pytest.raises(m.MaintenanceError):
        sealed_reader(link)
    hardlink = tmp_path/"hardlink"
    os.link(target,hardlink)
    with pytest.raises(m.MaintenanceError):
        sealed_reader(target)


def test_sealed_reader_detects_mutation_during_read(tmp_path, sealed_reader, monkeypatch):
    target=tmp_path/"receipt.json"
    target.write_text('{"passed":true}')
    target.chmod(0o444)
    original=m.json.load
    def mutate(stream):
        value=original(stream)
        target.chmod(0o644)
        target.write_text('{"passed":false}')
        target.chmod(0o444)
        return value
    monkeypatch.setattr(m.json,"load",mutate)
    with pytest.raises(m.MaintenanceError,match="changed"):
        sealed_reader(target)


def test_no_descriptor_preserves_normal_acceptance(monkeypatch):
    monkeypatch.setattr(m,"descriptor_for",lambda sha:None)
    m.validate_carry_receipt("a"*40,"b"*64)


@pytest.mark.parametrize("fault", ["missing","failed","foreign_descriptor","foreign_summary","extra"])
def test_carry_receipt_requires_exact_descriptor_and_summary(monkeypatch,fault):
    descriptor={"root_job_id":"JOB-preserved"}
    receipt=dict(schema_version=m.SCHEMA,passed=True,baseline_preserved=True,
                 descriptor_sha256=m.digest(descriptor),acceptance_summary_sha256="b"*64)
    monkeypatch.setattr(m,"descriptor_for",lambda sha:descriptor)
    if fault=="failed": receipt["passed"]=False
    if fault=="foreign_descriptor": receipt["descriptor_sha256"]="c"*64
    if fault=="foreign_summary": receipt["acceptance_summary_sha256"]="c"*64
    if fault=="extra": receipt["unexpected"]=True
    def read(path):
        if fault=="missing": raise FileNotFoundError(path)
        return receipt
    monkeypatch.setattr(m,"sealed_json",read)
    with pytest.raises((m.MaintenanceError,OSError)):
        m.validate_carry_receipt("a"*40,"b"*64)


def test_current_root_never_reads_maintenance_evidence(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(m,"descriptor_for",lambda sha:pytest.fail("unexpected maintenance read"))
    current={"base_sha":"a"*40}
    assert m.frozen_binding(SimpleNamespace(constraints=current),current,None) is current


def test_disarmed_precondition_requires_closed_triad():
    config=dict(ceo_submit_armed=False,coo_autonomy_armed=False,coo_operator_harness_armed=False)
    m.require_disarmed(config)
    for name in config:
        with pytest.raises(m.MaintenanceError):
            m.require_disarmed(dict(config,**{name:True}))
    with pytest.raises(m.MaintenanceError):
        m.require_disarmed({})

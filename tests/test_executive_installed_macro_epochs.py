"""Real normal-producer coordinates across immutable installed Macro epochs.

Macro paths here are inert absolute producer inputs, not live Macro custody or
provider proof. Existing explicit Root/ACL/install/platform observations stay
fixture inputs; real held bytes, FD guards, SQLite/evidence/receipt and normal
producer/finish/carry owners run. No host/provider effects.
"""
import copy
import hashlib
import json
from pathlib import Path

import pytest
from tests.test_executive_persistent_origin import filesystem
from ops.executive_os import acceptance_maintenance as m
from ops.executive_os import prepare_control_successor as producer
from tests import test_executive_installed_migration_successor as installed
from tests import test_executive_installed_preparation_chain as chain
from tests import test_executive_prepared_migration_successor as prepared

P, F, G = chain.P, chain.F, chain.G

@pytest.fixture(autouse=True)
def _current_data_anchor_fixture(filesystem):
    yield filesystem


def _install_macro(f, sha, macro):
    source = m.sealed_bytes(m.bundle_path(sha)/m._INSTALLED_PARENT_CONTROL_NAME,
                            m._MAX_DOCUMENT_BYTES)
    value = producer.build_successor(producer._parse(source), source_sha=sha, macro_root=macro)
    raw = (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False,
                      allow_nan=False)+'\n').encode()
    f.config.clear(); f.config.update(value)
    chain._rewrite(m.SYSTEM_ROOT/'config/control.json', raw)
    return raw


def _args(f, sha, parent):
    args = copy.deepcopy(f.new_args)
    args.successor_sha = sha
    args.supersede_unstarted_migration_preparation_sha = None
    args.supersede_installed_unstarted_migration_preparation_sha = parent
    args.superseded_migration_preparation_descriptor_sha256 = m.digest(m.descriptor_for(parent))
    args.expected_installed_parent_control_config_sha256 = hashlib.sha256(
        (m.SYSTEM_ROOT/'config/control.json').read_bytes()).hexdigest()
    return args


def _epochs(tmp_path, monkeypatch):
    f = installed._installed_fixture(tmp_path, monkeypatch)
    original_macro = f.config['ceo_ingress_app_macro_root']
    m.prepare(f.new_args)
    f.macro_one, f.macro_two = str(tmp_path/'macro-epoch-one'), str(tmp_path/'macro-epoch-two')
    assert len({original_macro, f.macro_one, f.macro_two}) == 3
    f.epoch_current = [F]
    chain._strict_install(f, monkeypatch, f.epoch_current)
    f.epoch_F_raw = _install_macro(f, F, f.macro_one)
    chain._stage_release(monkeypatch, G)
    return f


def test_distinct_macro_epochs_prepare_admit_finish_and_later_carry(tmp_path, monkeypatch):
    f = _epochs(tmp_path, monkeypatch)
    old_F, old_P = chain._bundle_state(F), chain._bundle_state(P)
    result = m.prepare(_args(f, G, F))
    descriptor = m.descriptor_for(G)
    assert descriptor['root_job_id'] == m.descriptor_for(F)['root_job_id']
    assert descriptor['predecessor_sha'] == m.descriptor_for(F)['predecessor_sha']
    assert (result/m._INSTALLED_PARENT_CONTROL_NAME).read_bytes() == f.epoch_F_raw
    assert m._installed_preparation_snapshot(descriptor, result) == f.epoch_F_raw
    f.epoch_current[0] = G
    raw_G = _install_macro(f, G, f.macro_two)
    assert json.loads(raw_G)['ceo_ingress_app_macro_root'] == f.macro_two
    # Historical F's snapshot keeps M0 and G's snapshot keeps M1 even while
    # current installed G uses M2. No global/current Macro substitution.
    assert json.loads((m.bundle_path(F)/m._INSTALLED_PARENT_CONTROL_NAME).read_bytes())[
        'ceo_ingress_app_macro_root'] not in {f.macro_one, f.macro_two}
    assert m._installed_preparation_snapshot(descriptor, result) == f.epoch_F_raw
    owner = m.Maintenance(G, m.digest(descriptor), f.config)
    proof_ids, summary = chain._accept(f, G, tmp_path, monkeypatch, owner)
    carry = m.sealed_json(result/'carry-forward.json')
    assert carry['passed'] is True
    chain._later_carry(f, descriptor, carry, summary, G,
                      'later unrelated three-Macro-epoch fixture job')
    assert chain._bundle_state(F) == old_F and chain._bundle_state(P) == old_P
    prepared._assert_parent_unchanged(f)
    assert f.install_checks == [P, P, F, F, G, G]


@pytest.mark.parametrize('field', ['model', 'effort', 'worker_provider_home',
                                  'ceo_ingress_app_boot_python'])
def test_valid_unrelated_policy_drift_reaches_whole_config_refusal(tmp_path, monkeypatch, field):
    f = _epochs(tmp_path, monkeypatch)
    altered = copy.deepcopy(f.config)
    changes = {'model': 'foreign-reviewed-model', 'effort': 'medium',
               'worker_provider_home': str(tmp_path/'foreign-provider-home'),
               'ceo_ingress_app_boot_python': str(tmp_path/'foreign-python/bin/python3.12')}
    assert altered.get(field) != changes[field]
    altered[field] = changes[field]
    # Prove the REAL existing producer accepts this well-typed whole input.
    # This negative must not pass through invalid-schema/arms/seal errors.
    assert producer.build_successor(altered, source_sha=F,
                                   macro_root=f.macro_one)[field] == changes[field]
    raw = (json.dumps(altered, sort_keys=True, indent=2, ensure_ascii=False)+'\n').encode()
    chain._rewrite(m.SYSTEM_ROOT/'config/control.json', raw)
    with pytest.raises(m.MaintenanceError, match='config or original root binding differs'):
        m.prepare(_args(f, G, F))
    assert not m.bundle_path(G).exists()
    assert not list(m.bundle_path(G).parent.glob('.preparing-'+G+'-*'))


def test_arms_remain_closed_under_macro_transition(tmp_path, monkeypatch):
    f = _epochs(tmp_path, monkeypatch)
    altered = dict(f.config, coo_autonomy_armed=True)
    assert producer.build_successor(altered, source_sha=F,
                                   macro_root=f.macro_one)['coo_autonomy_armed'] is True
    chain._rewrite(m.SYSTEM_ROOT/'config/control.json',
        (json.dumps(altered, sort_keys=True, indent=2)+'\n').encode())
    with pytest.raises(m.MaintenanceError, match='arms closed'):
        m.prepare(_args(f, G, F))
    assert not m.bundle_path(G).exists()


def test_historical_snapshot_retains_own_macro_but_refuses_unrelated_policy(tmp_path, monkeypatch):
    f = _epochs(tmp_path, monkeypatch)
    result = m.prepare(_args(f, G, F))
    descriptor = m.descriptor_for(G)
    assert m._installed_preparation_snapshot(descriptor, result) == f.epoch_F_raw
    snapshot = result/m._INSTALLED_PARENT_CONTROL_NAME
    altered = producer._parse(snapshot.read_bytes())
    altered['model'] = 'foreign-reviewed-model'
    assert producer.build_successor(altered, source_sha=F,
                                   macro_root=f.macro_one)['model'] == altered['model']
    raw = (json.dumps(altered, sort_keys=True, indent=2, ensure_ascii=False)+'\n').encode()
    chain._rewrite(snapshot, raw)  # real0400seal retained
    forged = dict(descriptor, installed_parent_control_config_sha256=hashlib.sha256(raw).hexdigest())
    chain._rewrite(result/'descriptor.json',
        (json.dumps(forged, sort_keys=True, indent=2)+'\n').encode())
    assert m.descriptor_for(G) == forged and m.sealed_bytes(snapshot, m._MAX_DOCUMENT_BYTES) == raw
    with pytest.raises(m.MaintenanceError, match='installed preparation source config differs'):
        m._installed_preparation_snapshot(forged, result)


def test_late_valid_macro_transition_still_refuses_current_config_drift(tmp_path, monkeypatch):
    f = _epochs(tmp_path, monkeypatch)
    real = m._requalify_unstarted_preproof_v5_to_v7
    def late(*args, **kwargs):
        result = real(*args, **kwargs)
        _install_macro(f, F, f.macro_two)
        return result
    monkeypatch.setattr(m, '_requalify_unstarted_preproof_v5_to_v7', late)
    with pytest.raises(m.MaintenanceError):
        m.prepare(_args(f, G, F))
    assert not m.bundle_path(G).exists()
    assert list(m.bundle_path(G).parent.glob('.preparing-'+G+'-*'))

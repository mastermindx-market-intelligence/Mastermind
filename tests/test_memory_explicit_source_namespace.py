"""Fixed source-only namespace; installation/UID fixtures confer no real authority."""
import hashlib
import json
from pathlib import Path
import pytest
from control_plane import protected_memory_economic_owner as owner
from control_plane import paid_fabric_backend as backend

ROOT=Path(__file__).resolve().parents[1]
PREFIX='ops/native_fabric/provider_plans/memory118/native_owner/'
NAMES=['scripts/protected_memory_economic_helper.py']+[PREFIX+n for n in (
    'fabric_operator_contract.py','fabric_operator_owner.py','fabric_memory_view.py',
    'protected_memory_economic.py','lease_broker.py','artifact_delivery.py',
    'fabric_task.py','provider_outcome.py','run_observation_delivery.py')]+[
    'ops/native_fabric/quota_continuity/candidate/'+n for n in ('pool_ledger.py','pick.py')]+[
    'ops/native_fabric/quota_continuity/source/'+n for n in ('model_tier.py','fabric_policy_snapshot.py')]

@pytest.mark.parametrize('fault',[None,'changed-private-source','missing-private-source','foreign-release'])
def test_actual_fixed_helper_qualifier_has_no_default_native_fallback(tmp_path,monkeypatch,fault):
    # Explicit inert root-owned-source premise only, exercising the real fixed qualifier.
    release=tmp_path/('a'*40);release.mkdir();entries=[];observed=[]
    for name in NAMES:
        raw=(ROOT/name).read_bytes();path=release/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        entries.append({'path':name,'sha256':hashlib.sha256(raw).hexdigest(),'size':len(raw)})
    manifest={'commit_sha':release.name,'entries':entries}
    if fault=='foreign-release':manifest['commit_sha']='b'*40
    (release/'.executive-release-manifest.json').write_text(json.dumps(manifest))
    target=release/(PREFIX+'fabric_operator_owner.py')
    if fault=='changed-private-source':target.write_bytes(target.read_bytes()+b'\n# foreign source\n')
    if fault=='missing-private-source':target.unlink()
    # A same-named default candidate must never satisfy the missing fixed private source.
    decoy=release/'ops/native_fabric/quota_continuity/candidate/fabric_operator_owner.py'
    decoy.parent.mkdir(parents=True,exist_ok=True);decoy.write_bytes((ROOT/(PREFIX+'fabric_operator_owner.py')).read_bytes())
    def source(path):
        observed.append(Path(path))
        return Path(path).read_bytes()
    monkeypatch.setattr(backend,'_root_source',source)
    monkeypatch.setattr(owner,'HELPER',release/'scripts/protected_memory_economic_helper.py')
    if fault:
        with pytest.raises((owner.peer.ProtectedMemoryRefused,FileNotFoundError)):owner.qualify_helper_source()
    else:
        owner.qualify_helper_source()
        assert {release/n for n in NAMES}<=set(observed)
    assert decoy not in observed
    assert not (release/'broker').exists()

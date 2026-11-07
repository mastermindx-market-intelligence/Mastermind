"""Finite prospective cohort over authentic protected107; no install effects."""
import copy
import hashlib
import json
from pathlib import Path
import pytest
from ops.native_fabric.quota_continuity.rollout import build_review_stage as b
ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT/'tests/fixtures/memory-protected-parent-107.json'


def current():
    raw=PARENT.read_bytes()
    assert hashlib.sha256(raw).hexdigest()==b.MEMORY_OWNER_PARENT_MANIFEST_SHA256
    value=json.loads(raw)
    assert len(value)==107
    value.update(b.MEMORY_OWNER_DIGESTS);value.update(b.MEMORY_OWNER_ADDITIONS)
    return value


def dependencies(value):return {n:value['ext/'+n] for n in b.GO_APPLICATION_DEPENDENCIES}


def test_exact_memory_source_restores_only_seven_members_and_two_additions():
    value=current();before=copy.deepcopy(value);parent=json.loads(PARENT.read_bytes())
    assert len(value)==109 and len(b.MEMORY_OWNER_DIGESTS)==7 and len(b.MEMORY_OWNER_ADDITIONS)==2
    assert b.before_memory_owner_integrity(value)==parent and value==before
    b.validate_go_base_manifest(value,dependencies(value))
    b.validate_go_base_manifest(parent,dependencies(parent))
    assert b.before_memory_owner_integrity(parent)==parent


@pytest.mark.parametrize('fault',['missing-helper','foreign-helper','partial-replacement','foreign-parent-member','extra-member','forged-captured-broker'])
def test_memory_source_projection_cannot_admit_mixed_or_forged_closure(fault):
    value=current();captured=dependencies(value)
    if fault=='missing-helper':del value['ext/fabric_memory_view.py']
    elif fault=='foreign-helper':value['ext/protected_memory_economic.py']='f'*64
    elif fault=='partial-replacement':value['ext/lease_broker.py']=b.MEMORY_OWNER_PREIMAGES['ext/lease_broker.py']
    elif fault=='foreign-parent-member':value['ext/artifact_reader.py']='f'*64
    elif fault=='extra-member':value['ext/foreign_reader.py']='f'*64
    else:captured['lease_broker.py']=b.MEMORY_OWNER_PREIMAGES['ext/lease_broker.py']
    with pytest.raises(ValueError):b.validate_go_base_manifest(value,captured)


def test_source_records_match_actual_source_generator_bytes():
    base=ROOT/'ops/native_fabric/quota_continuity';manifest=json.loads((base/'rollout/native-manifest.json').read_bytes());inventory=json.loads((base/'rollout/native-source-inventory.json').read_bytes())
    assert manifest==current() and inventory['native_code_files']==109 and set(inventory['files'])==set(manifest)
    for name,row in inventory['files'].items():
        raw=(base/row['source']).read_bytes()
        assert len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==manifest[name]==row['sha256']

"""Exact candidate seals never suppress source/path/site/extra identity drift."""
import copy
import hashlib
from pathlib import Path
import pytest
from tests.executive_identity_review import REVIEWED_FILES,reviewed_literal_spans
from tests.test_ceo_submit_armed_composition import _scan_added_identity_diff
ROOT=Path(__file__).resolve().parents[1]

@pytest.mark.parametrize('name',[
    'control_plane/protected_memory_evaluation_assignment.py',
    'control_plane/protected_memory_evaluation_source.py',
    'control_plane/protected_memory_evaluation_execution.py',
    'integrations/mastermind_executive_app/coo.py',
    'ops/native_fabric/provider_plans/memory118/native_owner/artifact_delivery.py',
    'ops/native_fabric/provider_plans/memory118/native_owner/fabric_task.py',
    'ops/native_fabric/provider_plans/memory118/native_owner/lease_broker.py',
    'ops/native_fabric/provider_plans/memory118/native_owner/protected_memory_economic.py',
    'ops/native_fabric/provider_plans/memory118/native_owner/provider_outcome.py',
])
def test_exact_evaluation_site_boundaries(name,monkeypatch):
    source=(ROOT/name).read_text();record=REVIEWED_FILES[name]
    assert reviewed_literal_spans(name,source)
    assert reviewed_literal_spans(name+'.unqualified',source)==()
    assert reviewed_literal_spans(name,source+'\n# changed bytes\n')==()
    wrong=copy.deepcopy(record);wrong['sites']=[list(site) for site in wrong['sites']];wrong['sites'][0][1]+=1
    monkeypatch.setitem(REVIEWED_FILES,name,wrong)
    assert reviewed_literal_spans(name,source)==()
    # Even a matching replacement body hash cannot mask an unrecorded identity.
    extra=source+'\nunreviewed_identity = 501\n'
    changed=copy.deepcopy(record);changed['sha256']=hashlib.sha256(extra.encode()).hexdigest()
    monkeypatch.setitem(REVIEWED_FILES,name,changed)
    diff=f'diff --git a/{name} b/{name}\n--- a/{name}\n+++ b/{name}\n@@ -0,0 +{len(source.splitlines())+1},2 @@\n+\n+unreviewed_identity = 501\n'
    assert '501' in _scan_added_identity_diff(diff,source_postimages={name:extra})

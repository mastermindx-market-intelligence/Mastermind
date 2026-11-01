"""Real routing-policy DATA checks only; no worker or host admission."""
import hashlib

import pytest

from ops.native_fabric.quota_continuity.source import fabric_policy_snapshot as policy
from tests.test_paid_provider_entry_linux import _FIXTURE_POLICY


def private_policy_pair(tmp_path):
    stable=tmp_path/'lanes/ext';(stable/'active').mkdir(parents=True)
    path=stable.parent/'orch/fabric';path.mkdir(parents=True)
    (path/'pools.yaml').write_bytes(_FIXTURE_POLICY)
    snapshot=tmp_path/'snapshot.yaml';snapshot.write_bytes(_FIXTURE_POLICY)
    return snapshot,stable,path/'pools.yaml'


def test_finite_private_policy_passes_real_publication_compatibility(tmp_path):
    snapshot,stable,_=private_policy_pair(tmp_path)
    value=policy.validate_publication(snapshot,stable)
    digest=hashlib.sha256(_FIXTURE_POLICY).hexdigest()
    assert value['snapshot_sha256']==value['stable_sha256']==digest
    assert value['critical_sha256']==policy.critical_fingerprint(_FIXTURE_POLICY)


def test_missing_stable_policy_is_not_replaced_by_a_fixture_stub(tmp_path):
    snapshot,stable,path=private_policy_pair(tmp_path);path.unlink()
    with pytest.raises(FileNotFoundError):policy.validate_publication(snapshot,stable)


def test_invalid_or_critical_mismatched_policy_still_refuses(tmp_path):
    snapshot,stable,path=private_policy_pair(tmp_path)
    path.write_bytes(b'pools: {}\n')
    with pytest.raises(ValueError,match='ROUTING_POLICY_SHAPE'):
        policy.validate_publication(snapshot,stable)
    path.write_bytes(b'{"routing":{"fixture_only":true},"pools":{"grok":{"windows":{"weekly":{}}}}}\n')
    with pytest.raises(ValueError,match='ROUTING_CRITICAL_POLICY_MISMATCH'):
        policy.validate_publication(snapshot,stable)

"""Only the one independently reviewed original-principal comparison is masked."""
from pathlib import Path
import pytest
from tests.executive_identity_review import reviewed_literal_spans
from tests.test_executive_a2_identity_review import scan

PATH='control_plane/finite_initial_registration.py'


def test_exact_principal_site_does_not_hide_other_identity():
    source=(Path(__file__).parents[1]/PATH).read_text()
    assert len(reviewed_literal_spans(PATH,source))==1
    assert scan(source,PATH)==[]
    assert scan(source+'\nnew_peer_uid=471\n',PATH)==['471']
    assert reviewed_literal_spans('control_plane/unreviewed.py',source)==()


@pytest.mark.parametrize('before,after',[
    ("!='_mastermind_minimax'","=='_mastermind_minimax'"),
    ("'_mastermind_minimax'","'_mastermind_other'"),
    ("definition.get('worker_gid')!=physical.worker_gid","False"),
    ("    guard()\n    return runtime.workers.register_worker","    return runtime.workers.register_worker"),
])
def test_guard_or_semantic_drift_exposes_account(before,after):
    source=(Path(__file__).parents[1]/PATH).read_text();assert before in source
    changed=source.replace(before,after)
    assert reviewed_literal_spans(PATH,changed)==()
    assert scan(changed,PATH)


# Independent MiniMax review finite-initial-implementation-review-01a0e0c7-20261016-v1.
# Retained output SHA256 00c376d75609427ad842fb669477d85fab2d4397112edad1981ff338beb74fbe.
# One guarded existing-account comparison; surrounding source stays scanned.
REVIEWED_ANCHORS_BY_PATH = {'control_plane/finite_initial_registration.py': {'register_initial': {'node_type': 'FunctionDef',
                                                                       'ast_sha256': '8ae6e9f26c1f2ecb99df931aa14b7fa4550865e17d7b56b4d15ec55b4988e8e8',
                                                                       'sites': ((('body',
                                                                                   8,
                                                                                   'test',
                                                                                   'values',
                                                                                   1,
                                                                                   'comparators',
                                                                                   0),
                                                                                  'str',
                                                                                  '_mastermind_minimax',
                                                                                  "'_mastermind_minimax'"),)}}}

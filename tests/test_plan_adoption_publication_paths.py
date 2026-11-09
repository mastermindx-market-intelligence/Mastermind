"""Actual pinned Agent OS decision-key bound, no observation/grant invented."""
from copy import deepcopy
import pytest
from common.plan_adoption_publication_contract import validate_adoption_sources


def sources(key):
    selection=dict(action='ADOPT_PLAN',request_id='mmos-project-adopt-'+'a'*40,work_ref='WS:PLAN-TEST')
    paths=['agentos/workstreams/WS-PLAN-TEST.md','agentos/decisions/DEC-PLAN-ADOPTION-'+'A'*40+'.md',
        'agentos/decisions/DEC-'+key+'.md']
    return selection,[dict(repository='macro',commit='b'*40,path=p,content_sha256='c'*64) for p in paths]


@pytest.mark.parametrize('key',['AA','A'*128])
def test_actual_canonical_decision_key_bound_is_retained(key):
    assert len(validate_adoption_sources(*sources(key)))==3


@pytest.mark.parametrize('key',['A','A'*129,'A-','A/FOREIGN','A_1'])
def test_noncanonical_predecessor_path_never_enters_closed_observation(key):
    with pytest.raises(ValueError):validate_adoption_sources(*sources(key))

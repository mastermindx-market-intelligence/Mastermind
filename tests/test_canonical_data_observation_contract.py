"""Pure closed facts; positive actual Event/reader witness lives in joined test."""
from copy import deepcopy
import pytest
from common.canonical_project_data_observation_contract import validate

def base():
 return dict(schema='mastermind.canonical_project_data_observation.v1',repository='mastermindx-market-intelligence/macro',default_ref='main',executable_macro_commit='a'*40,canonical_data_commit='a'*40,canonical_commit_at='2026-11-04T12:00:00+00:00',canonical_observed_at_ms=1793793600000,publication_recorded_at_ms=None,publication_time=None,source_operation=None,reader_closure_sha256='b'*64,code_config_relation='IDENTICAL_READER_CLOSURE',authority='OBSERVATION_ONLY')
def test_fixed_snapshot_witness_is_detached_data():
 value=base();out=validate(value);value['authority']='changed';assert out['authority']=='OBSERVATION_ONLY'
@pytest.mark.parametrize('key,value',[('canonical_data_commit','c'*40),('publication_recorded_at_ms',123),('publication_time','2026-11-04'),('canonical_commit_at','2026-11-04'),('canonical_commit_at','private-not-a-date'),('canonical_observed_at_ms',True),('authority','EXECUTE'),('code_config_relation','ANY_CODE'),('default_ref','../main'),('repository','foreign')])
def test_unqualified_or_malformed_facts_refuse(key,value):
 candidate=base();candidate[key]=value
 with pytest.raises(ValueError,match='^INVALID_CANONICAL_DATA_OBSERVATION$'):validate(candidate)
def test_unlisted_metadata_does_not_pass_through():
 candidate=base();candidate['raw_provider_snapshot']={'private':'value'}
 with pytest.raises(ValueError,match='^INVALID_CANONICAL_DATA_OBSERVATION$'):validate(candidate)

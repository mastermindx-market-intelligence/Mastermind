"""Actual Resources DATA DTOs with explicit synthetic collector CODE frames.

C is independently retained from each original prepare/initial source snapshot;
never from DATA N or an observation claim. Nominal context issuance itself is
qualified in S7's existing collector/HTTP join, not this pure contract test.
"""
import copy
import json
from pathlib import Path
import pytest
from common.workspace_project_knowledge_contract import validate_catalogue,validate_memory,validate_source
FIXTURE=json.loads((Path(__file__).parents[1]/"app/mastermind_os/src/fixtures/knowledge-data-observation-owner.json").read_bytes())
READER="07e317ef5b6e0107fcfca9228f179c7d269bb234"


def attach(case,kind):
    value=copy.deepcopy(case[kind])
    value["code_context"]={"schema":"mastermind.project_knowledge_code_context.v1","work_ref":case["prepared_request"]["work_ref"],
        "executable_macro_commit":case["prepared_request"]["source_commit"],"reader_source_commit":READER}
    value["data_observation"]=copy.deepcopy(case["data_observation"])
    return value


@pytest.mark.parametrize("memory",[False,True])
@pytest.mark.parametrize("kind,validator",[("catalogue",validate_catalogue),("memory",validate_memory),("source",validate_source)])
def test_actual_closed_code_and_data_facts_preserve_independent_refs(memory,kind,validator):
    case=FIXTURE["memory_edit"] if memory else FIXTURE
    value=attach(case,kind);actual=validator(value)
    assert actual==value and actual is not value
    assert actual["code_context"]["executable_macro_commit"]!=actual["data_observation"]["canonical_data_commit"]
    assert actual["data_observation"]["publication_time"] is None
    assert actual["data_observation"]["publication_recorded_at_ms"]==actual["data_observation"]["source_operation"]["recorded_at_ms"]


@pytest.mark.parametrize("change",["missing_code","foreign_code","foreign_reader","foreign_data","foreign_work","forged_time","extra","no_observation"])
def test_forged_or_unpaired_new_provenance_cannot_widen_the_v1_body(change):
    value=attach(FIXTURE,"catalogue")
    if change=="missing_code":del value["code_context"]
    elif change=="foreign_code":value["code_context"]["executable_macro_commit"]="f"*40
    elif change=="foreign_reader":value["code_context"]["reader_source_commit"]="not-a-commit"
    elif change=="foreign_data":value["data_observation"]["canonical_data_commit"]="f"*40
    elif change=="foreign_work":value["data_observation"]["source_operation"]["selection"]["work_ref"]="WS:OTHER"
    elif change=="forged_time":value["data_observation"]["publication_time"]="2026-11-04T00:00:00Z"
    elif change=="extra":value["code_context"]["can_write"]=True
    elif change=="no_observation":del value["data_observation"]
    with pytest.raises(ValueError):validate_catalogue(value)


def test_legacy_body_stays_unchanged_without_implying_new_code_data_capability():
    legacy=copy.deepcopy(FIXTURE["initial_catalogue"])
    assert validate_catalogue(legacy)==legacy
    assert "code_context" not in legacy and "data_observation" not in legacy

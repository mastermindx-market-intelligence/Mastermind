"""Pure public/direct discriminators; these tests grant no host capability."""
import copy
import pytest
from control_plane import ceo_request, ceo_intent


def request():
    return dict(operation_key="h2-native-source-contract-v1", objective="Read the supplied source contract.",
                department="executive-infrastructure", priority=0,
                execution_profile="native_research_only", workstream="WS:EXECUTIVE-ECOSYSTEM-COMPLETION",
                attempt_limit=1)


def direct_intent():
    value = ceo_request.build_trusted_envelope(
        ceo_request.normalize_high_level_request(request()), intent_id="ceo-native-contract-v1",
        workspace_root="/tmp/control-workspaces", grounding={"mastermind_sha":"a"*40,"macro_sha":"b"*40})
    value.update(schema=ceo_intent.INTENT_SCHEMA_DIRECT, intent_kind="direct_native_readonly",business_impact="routine")
    return value


def test_native_profile_has_only_read_authorities():
    value = ceo_request.normalize_high_level_request(request())
    assert ceo_request.derive_authorities(value["execution_profile"]) == ["READ", "RESEARCH"]
    assert value["attempt_limit"] == 1 and value["allowed_write_paths"] == [] and value["validation"] == {}
    intent=ceo_intent.validate_intent(direct_intent())
    assert intent["schema"]==ceo_intent.INTENT_SCHEMA_DIRECT


@pytest.mark.parametrize("patch", [
    {"attempt_limit":2}, {"attempt_limit":True}, {"attempt_limit":"1"},
    {"allowed_write_paths":["src/file.py"]}, {"validation":{"git_diff_check":True}},
    {"principal_scope":"0"*64}, {"worker_id":"codex-01"}, {"execution_mode":"direct"},
    {"strict_v2":False}, {"execution_binding":{}},
])
def test_public_direct_profile_refuses_writes_selectors_or_attempt_expansion(patch):
    value=request();value.update(patch)
    with pytest.raises(ceo_request.CeoRequestError):
        ceo_request.normalize_high_level_request(value)


@pytest.mark.parametrize("key,value", [
    ("intent_kind","executive_coo_cycle"),("business_impact","material"),
    ("attempt_limit",2),("requested_authorities",["READ","WRITE_BRANCH"]),
    ("allowed_write_paths",["x"]),("validation_commands",[["git","diff","--check"]]),
])
def test_direct_envelope_never_widens_or_relabels(key,value):
    intent=direct_intent()
    target=intent if key in {"intent_kind","business_impact"} else intent["execution_contract"]
    target[key]=copy.deepcopy(value)
    with pytest.raises(ceo_intent.CeoIntentError):ceo_intent.validate_intent(intent)


def test_old_research_profile_and_schema_stay_unchanged():
    value=request();value["execution_profile"]="research_only";value["attempt_limit"]=2
    assert ceo_request.normalize_high_level_request(value)["attempt_limit"]==2
    value=direct_intent();value["schema"]=ceo_intent.INTENT_SCHEMA_V2
    value["intent_kind"]="executive_coo_cycle"
    assert ceo_intent.validate_intent(value)["schema"]==ceo_intent.INTENT_SCHEMA_V2


def test_direct_discriminator_alone_cannot_reach_runtime():
    class NoRuntime:
        def __getattr__(self, name):
            raise AssertionError('pure discriminator reached Runtime: ' + name)
    with pytest.raises(ceo_intent.CeoIntentError, match='host admission is not composed'):
        ceo_intent.submit_intent(NoRuntime(), direct_intent(), workspace_root='/tmp/control-workspaces')

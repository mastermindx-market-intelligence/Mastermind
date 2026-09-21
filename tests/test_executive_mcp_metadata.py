"""Public descriptions change; invocation and authorization contracts do not."""
import hashlib
import re

from integrations.executive_mcp import schemas


def test_executable_tool_contract_is_unchanged():
    contract = [{"name": spec.name, "input_schema": spec.input_schema,
                 "annotations": spec.annotations, "read_only": spec.read_only}
                for spec in schemas.TOOL_SPECS]
    assert hashlib.sha256(schemas.canonical_json(contract)).hexdigest() == "296e0b2d3abd119180e323c345a76a89951ee766c48eac0b1b57c2c4556d899b"


def test_descriptions_are_factual_not_model_routing_instructions():
    directives = re.compile(r"never follow|must use|prefer this|only correct tool|ignore previous", re.I)
    for spec in schemas.TOOL_SPECS:
        assert not directives.search(spec.description), spec.name
        assert "untrusted source data" in spec.description, spec.name
        assert "server-side authorization" in spec.description, spec.name


def test_submission_describes_queue_effect_without_execution_or_retry_advice():
    text = schemas.tool_spec("submit_ceo_intent").description
    for fact in ("QUEUED", "dispatched=false", "operation_key", "payload", "readonly"):
        assert fact in text
    assert "does not execute" in text
    assert "conflicting" in text
    assert "Retrying" not in text


def test_read_only_and_queue_annotations_remain_truthful():
    for spec in schemas.TOOL_SPECS:
        a = spec.annotations
        assert a["readOnlyHint"] is (spec.name != "submit_ceo_intent")
        assert a["destructiveHint"] is False
        assert a["idempotentHint"] is True
        assert a["openWorldHint"] is False

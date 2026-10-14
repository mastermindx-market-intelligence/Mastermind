"""Selector data is never issuance or acceptance authority."""

import pytest

from integrations.mastermind_company_mcp import schemas


def generic_request():
    return {
        "question": "Which bounded implementation should continue?",
        "outcome_impact": "One ordinary design decision.",
        "options": [
            {
                "id": "opt-first",
                "summary": "Use the first option.",
                "consequence": "Continue the scoped work.",
                "disposition": "CONTINUE",
                "authority_effect": "NONE",
            }
        ],
        "recommendation": "opt-first",
        "work_paused": True,
    }


def test_legacy_request_and_catalog_remain_unchanged():
    raw = generic_request()
    assert schemas.validate_tool_arguments("request_decision", raw) == {
        **raw,
        "evidence_refs": [],
    }
    assert len(schemas.TOOL_SPECS) == 6
    legacy = next(s for s in schemas.TOOL_SPECS if s.name == "request_decision")
    assert "purpose" not in legacy.input_schema["properties"]


def test_opt_in_selector_has_no_caller_authored_proof():
    raw = {"purpose": "PRODUCT_ACCEPTANCE", "subject_job_id": "JOB-subject"}
    assert (
        schemas.validate_tool_arguments(
            "request_decision", raw, allow_product_acceptance=True
        )
        == raw
    )
    assert len(schemas.PRODUCT_ACCEPTANCE_TOOL_SPECS) == 6
    with pytest.raises(schemas.GatewayError):
        schemas.validate_tool_arguments("request_decision", raw)


@pytest.mark.parametrize(
    "raw",
    [
        {"purpose": "PRODUCT_ACCEPTANCE"},
        {"subject_job_id": "JOB-subject"},
        {"purpose": "ACCEPT", "subject_job_id": "JOB-subject"},
        {"purpose": "PRODUCT_ACCEPTANCE", "subject_job_id": ""},
        {"purpose": "PRODUCT_ACCEPTANCE", "subject_job_id": True},
        {"purpose": "PRODUCT_ACCEPTANCE", "subject_job_id": "../foreign"},
        {
            "purpose": "PRODUCT_ACCEPTANCE",
            "subject_job_id": "JOB-subject",
            "reviewer_job_id": "JOB-author",
        },
        {
            "purpose": "PRODUCT_ACCEPTANCE",
            "subject_job_id": "JOB-subject",
            "result_envelope_digest": "a" * 64,
        },
        {
            "purpose": "PRODUCT_ACCEPTANCE",
            "subject_job_id": "JOB-subject",
            **generic_request(),
        },
    ],
)
def test_mixed_or_forged_selector_is_rejected(raw):
    with pytest.raises(schemas.GatewayError):
        schemas.validate_tool_arguments(
            "request_decision", raw, allow_product_acceptance=True
        )


def test_opt_in_does_not_enable_other_tools_or_mutate_legacy_schema():
    with pytest.raises(schemas.GatewayError):
        schemas.validate_tool_arguments(
            "progress",
            {"purpose": "PRODUCT_ACCEPTANCE", "subject_job_id": "JOB-subject"},
            allow_product_acceptance=True,
        )
    old = next(s for s in schemas.TOOL_SPECS if s.name == "request_decision")
    new = next(
        s for s in schemas.PRODUCT_ACCEPTANCE_TOOL_SPECS if s.name == "request_decision"
    )
    assert new is not old and new.input_schema is not old.input_schema
    assert "purpose" not in old.input_schema["properties"]


def test_opt_in_catalogue_is_a_valid_mcp_six_tool_surface():
    pytest.importorskip("mcp")
    import jsonschema
    from integrations.mastermind_company_mcp.server import build_tools

    ordinary = build_tools()
    enrolled = build_tools(product_acceptance=True)
    assert [tool.name for tool in enrolled] == [tool.name for tool in ordinary]
    assert len(enrolled) == 6
    selected = next(tool for tool in enrolled if tool.name == "request_decision")
    jsonschema.Draft202012Validator.check_schema(selected.inputSchema)
    validator = jsonschema.Draft202012Validator(selected.inputSchema)
    validator.validate(
        {"purpose": "PRODUCT_ACCEPTANCE", "subject_job_id": "JOB-subject"}
    )
    validator.validate(generic_request())
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(
            {
                "purpose": "PRODUCT_ACCEPTANCE",
                "subject_job_id": "JOB-subject",
                "accepted": True,
            }
        )
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(
            {
                "purpose": "PRODUCT_ACCEPTANCE",
                "subject_job_id": "JOB-subject",
                **generic_request(),
            }
        )

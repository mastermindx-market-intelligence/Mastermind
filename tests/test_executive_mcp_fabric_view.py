"""Executive MCP composition for the canonical Fabric job view."""

from __future__ import annotations

import pytest

from integrations.executive_mcp.schemas import (
    GatewayError,
    tool_names,
    tool_spec,
    validate_tool_arguments,
)


def test_executive_fabric_is_read_only_and_advertised() -> None:
    spec = tool_spec("executive_fabric")

    assert spec.read_only is True
    assert "executive_fabric" in tool_names()
    assert spec.input_schema["additionalProperties"] is False
    assert spec.input_schema["required"] == ["view"]


def test_executive_fabric_validates_closed_modes() -> None:
    assert validate_tool_arguments("executive_fabric", {"view": "roots"}) == {
        "view": "roots",
        "limit": 50,
    }
    assert validate_tool_arguments(
        "executive_fabric", {"view": "roots", "limit": 7}
    ) == {"view": "roots", "limit": 7}
    assert validate_tool_arguments(
        "executive_fabric", {"view": "root", "root_job_id": "JOB-7"}
    ) == {"view": "root", "root_job_id": "JOB-7"}


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"view": "roots", "root_job_id": "JOB-1"},
        {"view": "root"},
        {"view": "root", "root_job_id": "JOB-1", "limit": 5},
        {"view": "roots", "limit": 0},
        {"view": "roots", "limit": 51},
        {"view": "roots", "limit": True},
        {"view": "other"},
        {"view": "root", "root_job_id": "job-1"},
    ],
)
def test_executive_fabric_rejects_ambiguous_or_unbounded_inputs(
    payload: dict[str, object],
) -> None:
    with pytest.raises(GatewayError) as exc:
        validate_tool_arguments("executive_fabric", payload)

    assert exc.value.code == "invalid_input"

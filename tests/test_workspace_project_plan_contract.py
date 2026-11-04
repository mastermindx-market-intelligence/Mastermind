"""Closed public decoder/fence checks for canonical project-plan records."""
import copy

import pytest

from common import workspace_project_plan_contract as wire
from tests.test_agentos_project_plan_source import source_git, read
from tests.test_workspace_project_plan_read import request


def test_closed_frame_reuses_existing_workspace_read_principal():
    value = request()
    assert wire.validate_frame(value) == value
    value["principal"]["scopes"] = ["mastermind.executive.send"]
    with pytest.raises(ValueError): wire.validate_frame(value)


@pytest.mark.parametrize("selector", ["WS:ONE\n", "WS:ONE\r", "WS:ONE/../../secret", "WS:one", "WS:ONE--TWO"])
def test_no_selector_regex_trailing_newline_or_path_escape(selector):
    with pytest.raises(ValueError): wire.validate_selection({"work_ref": selector})


def test_body_roundtrip_is_detached(source_git):
    body = read(source_git[0])
    decoded = wire.validate_body(body)
    assert decoded == body
    decoded["plan"]["waves"][0]["title"] = "Edited locally"
    assert body["plan"]["waves"][0]["title"] == "Qualify the source"


@pytest.mark.parametrize("mutation", ["extra_body", "extra_plan", "extra_wave", "adoption", "history_hash", "history_duplicate", "history_time", "source_newline", "selector", "reason"])
def test_malformed_owner_body_never_crosses_transport(source_git, mutation):
    value = read(source_git[0])
    if mutation == "extra_body": value["private_payload"] = "do not leak"
    if mutation == "extra_plan": value["plan"]["raw_markdown"] = "do not leak"
    if mutation == "extra_wave": value["plan"]["waves"][0]["lease"] = "do not leak"
    if mutation == "adoption": value["plan"]["adoption"] = {"state": "ADOPTED"}
    if mutation == "history_hash": value["plan"]["version_history"]["revisions"][0]["content_sha256"] = "e" * 64
    if mutation == "history_duplicate": value["plan"]["version_history"]["revisions"] *= 2
    if mutation == "history_time": value["plan"]["version_history"]["revisions"][0]["committed_at"] = "2026-11-03"
    if mutation == "source_newline": value["source"]["commit"] += "\n"
    if mutation == "selector": value["selection"]["root_job_id"] = "JOB-1"
    if mutation == "reason": value["reason_codes"] = ["SOURCE_UNAVAILABLE"]
    with pytest.raises(ValueError): wire.validate_body(value)


@pytest.mark.parametrize("reason", wire.REASON_CODES)
def test_closed_unavailability_has_no_partial_plan(reason):
    value = wire.unavailable("WS:ONE", reason)
    assert wire.validate_body(value) == value
    value["source"] = {}
    with pytest.raises(ValueError): wire.validate_body(value)


@pytest.mark.parametrize("pr", [True, 9007199254740992, 0, "123"])
def test_pr_numbers_are_positive_javascript_safe_integers(source_git, pr):
    value = read(source_git[0])
    value["plan"]["waves"][0]["prs"] = [pr]
    with pytest.raises(ValueError): wire.validate_body(value)

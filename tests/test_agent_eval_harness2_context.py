"""Source-bound native context contract tests; metadata is not live authentication."""
from __future__ import annotations

import copy
import json

import pytest

from scripts.agent_eval.harness2_context import Harness2ContextError, read_context_bundle
from scripts.agent_eval.harness2_native import sha256_bytes
from scripts.agent_eval.errors import ContractError
from tests.agent_eval_factories import REPO_REF_BASE

SHA = "a" * 40


def bundle_fixture():
    experience = {
        "schema": "agentos.harness_experience.v1", "domain": "accounting",
        "harness_artifact": {"artifact_ref": "artifact:fixture/adopted-harness", "digest": "sha256:" + "b" * 64},
        "source_run_ids": ["run:00000000-0000-4000-8000-000000000001",
                           "run:00000000-0000-4000-8000-000000000002"],
        "method_source_ref": REPO_REF_BASE, "claim": "Keep signed ledger values.",
        "falsifier": "pytest tests/test_agent_eval_harness2_context.py",
        "so_what": "Preserve credits and debits.", "verified_by": "fixture command",
        "verified_at": "2026-08-10", "confidence": "verified",
    }
    discovery = {"kind": "discovery", "key": "DSC:LEDGER", "authority_class": "A3",
                 "path": "agentos/discoveries/DSC-LEDGER.md", "locator": "agentos/discoveries/DSC-LEDGER.md#frontmatter",
                 "status": "verified", "excerpt": "clipped prose", "harness_experience": experience}
    result = {"schema": "context_bundle.v1", "repo_sha": SHA,
              "generated_at": "2026-08-12T00:00:00Z", "source_records_digest": "sha256:" + "c" * 64,
              "target": {"workstream": "WS:TARGET", "resolution": "explicit"},
              "sections": [{"id": key, "items": []} for key in
                           ("higher_law", "workstream", "decisions", "discoveries", "handoff", "artifacts")],
              "excluded": [{"key": "DSC:OLD", "reason": "superseded"}],
              "omitted_due_to_budget": [{"key": "DSC:LARGE", "reason": "budget"}],
              "degraded": ["PR snapshot unavailable; not evidence of runtime liveness"]}
    result["sections"][0]["items"] = [{"key": "DNR:NO-DUPLICATE", "excerpt": "Never create a second runtime."}]
    result["sections"][1]["items"] = [{"key": "WS:TARGET", "excerpt": "A bounded authorized experiment only."}]
    result["sections"][3]["items"] = [discovery]
    return result


def inputs(bundle=None):
    raw = json.dumps(bundle if bundle is not None else bundle_fixture(), ensure_ascii=False).encode()
    return {"bundle_bytes": raw, "expected_bundle_digest": sha256_bytes(raw),
            "expected_repository_sha": SHA, "expected_workstream": "WS:TARGET",
            "task_domain": "accounting", "not_after": "2026-08-12T01:00:00Z"}


def test_complete_source_context_and_uncertainty_are_preserved():
    args = inputs()
    original = copy.deepcopy(args)
    read = read_context_bundle(**args)
    assert len(read.experience) == 1
    assert read.experience[0]["claim"] == "Keep signed ledger values."
    assert read.experience[0]["confidence"] == "verified"
    assert read.experience[0]["source_ref"].startswith("context:sha256:")
    assert read.bundle == bundle_fixture()
    assert read.bundle["sections"][0]["items"][0]["key"] == "DNR:NO-DUPLICATE"
    assert read.bundle["excluded"] and read.bundle["omitted_due_to_budget"] and read.bundle["degraded"]
    assert read.evidence_scope == "BYTE_AND_IDENTITY_CHECKED_NOT_AUTHENTICATED"
    assert args == original


@pytest.mark.parametrize("change", [
    lambda d: d.update(schema="wrong"),
    lambda d: d.update(repo_sha="b" * 40),
    lambda d: d["target"].update(workstream="WS:OTHER"),
    lambda d: d["target"].update(resolution="ambiguous"),
    lambda d: d.update(generated_at="2026-08-13T00:00:00Z"),
    lambda d: d.update(generated_at="2026-08-12T00:00:00"),
    lambda d: d.pop("degraded"),
    lambda d: d["sections"].pop(),
    lambda d: d["sections"][2].update(id="higher_law"),
    lambda d: d["excluded"].append({"key": "DSC:LEDGER", "reason": "conflict"}),
    lambda d: d["sections"][3]["items"].append(copy.deepcopy(d["sections"][3]["items"][0])),
    lambda d: d["sections"][3]["items"][0].update(authority_class="A0"),
    lambda d: d["sections"][3]["items"][0]["harness_experience"].update(extra=True),
    lambda d: d["sections"][3]["items"][0]["harness_experience"].update(confidence="suspected"),
    lambda d: d["sections"][3]["items"][0]["harness_experience"].update(source_run_ids=["invented", "invented"]),
    lambda d: d["sections"][3]["items"][0]["harness_experience"].update(method_source_ref="moving:main"),
])
def test_source_mismatch_or_malformed_metadata_fails_without_repair(change):
    bundle = bundle_fixture()
    change(bundle)
    with pytest.raises((Harness2ContextError, ContractError)):
        read_context_bundle(**inputs(bundle))


def test_byte_change_is_detected_even_when_json_stays_valid():
    args = inputs()
    args["bundle_bytes"] += b" "
    with pytest.raises(Harness2ContextError, match="CONTEXT_BYTES_CHANGED"):
        read_context_bundle(**args)


def test_old_compiler_excerpt_is_not_parsed_into_fake_complete_experience():
    bundle = bundle_fixture()
    del bundle["sections"][3]["items"][0]["harness_experience"]
    read = read_context_bundle(**inputs(bundle))
    assert read.experience == ()
    assert read.experience_exclusions == ({"key": "DSC:LEDGER", "reason": "NO_STRUCTURED_HARNESS_EXPERIENCE"},)
    assert read.bundle["sections"][3]["items"][0]["excerpt"] == "clipped prose"


@pytest.mark.parametrize("change,reason", [
    ({"domain": "other"}, "OTHER_DOMAIN"),
    ({"verified_at": "2026-08-13"}, "VERIFICATION_POSTDATES_CONTEXT"),
])
def test_held_out_of_prior_library_without_deleting_original_source(change, reason):
    bundle = bundle_fixture()
    bundle["sections"][3]["items"][0]["harness_experience"].update(change)
    read = read_context_bundle(**inputs(bundle))
    assert read.experience == ()
    assert read.experience_exclusions[0]["reason"] == reason
    assert read.bundle == bundle


@pytest.mark.parametrize("confidence", ["probable", "suspected"])
def test_less_certain_lessons_are_not_upgraded(confidence):
    bundle = bundle_fixture()
    item = bundle["sections"][3]["items"][0]
    item["status"] = item["harness_experience"]["confidence"] = confidence
    read = read_context_bundle(**inputs(bundle))
    assert read.experience[0]["confidence"] == confidence


def test_too_many_complete_lessons_are_not_silently_truncated():
    bundle = bundle_fixture()
    prototype = bundle["sections"][3]["items"][0]
    rows = []
    for i in range(33):
        row = copy.deepcopy(prototype)
        row["key"] = "DSC:ITEM-" + str(i)
        rows.append(row)
    bundle["sections"][3]["items"] = rows
    with pytest.raises(Harness2ContextError, match="COUNT_BOUND"):
        read_context_bundle(**inputs(bundle))

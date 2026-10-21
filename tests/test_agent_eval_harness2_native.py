"""Synthetic upstream-format/native-EVAL composition; no provider or efficacy claim."""
from __future__ import annotations

import copy
import json

import pytest

from scripts.agent_eval import contracts, store
from scripts.agent_eval.canonical import canonical_json_bytes
from scripts.agent_eval.harness2_native import (
    BINDING_SCHEMA, UPSTREAM_SOURCE_REF, Harness2ImportError, decode_json,
    finalize_selected_run, harness_digest, harness_manifest, import_selected_run,
    sha256_bytes, upstream_fingerprint,
)
from tests.agent_eval_factories import (
    REPO_REF_BASE, build_baseline_scenario, build_baseline_configuration,
    build_alternate_configuration, build_two_arm_experiment, build_run_draft,
)


def _ref(name):
    return REPO_REF_BASE + "#harness2_fixture/" + name


def fixture(mode="agg", k=1):
    files = {"AGENTS.md": b"Read evidence before describing the result.\n",
             ".agents/skills/review/SKILL.md": b"---\ndescription: Review artifacts\n---\nInspect facts.\n"}
    scenario = build_baseline_scenario()
    config = build_baseline_configuration()
    config.pop("schema")
    config.pop("configuration_digest")
    config["procedure"]["instruction_bundle"] = {
        "artifact_ref": _ref("harness.json"), "digest": harness_digest(files)}
    config = contracts.build_configuration(config)
    other = build_alternate_configuration()
    experiment = build_two_arm_experiment(scenario, config, other)
    draft = build_run_draft(scenario, config, experiment, arm_id="arm_a", replicate_index=1)
    output = b"Executive OS owns runtime lifecycle.\n"
    draft["evidence"]["output"] = {"artifact_ref": _ref("answer.txt"), "digest": sha256_bytes(output)}
    label = "agg1" if mode == "agg" else "c1"
    upstream_run_id = f"demo-cx-{mode}{k}/task-1/{label}"
    summary = {
        "task_id": "task-1", "domain": "engineering", "k": k, "seed": 42,
        "status": "ok", "base": [], "errors": [],
        "modes": {mode: {"mode": mode, "task_id": "task-1", "k": k,
            "ok": True, "errors": [], "fell_back": [],
            "finals": [f"{'agg' if mode == 'agg' else 'c'}{i}" for i in range(1, k + 1)]}},
        "selections": {mode: {"task_id": "task-1", "mode": mode, "k": k,
            "chosen_id": "A", "chosen_label": label, "chosen_run_id": upstream_run_id,
            "chosen_is_base": False, "why": "fixture", "id_map": {"A": label},
            "ok": True, "fallback": False, "error": "", "usd": 0.0,
            "chosen_run_dir": "/must/not/be/read", "harness_fingerprint": upstream_fingerprint(files)}},
    }
    summary_bytes = json.dumps(summary).encode()
    draft_bytes = canonical_json_bytes(draft)
    binding = {
        "schema": BINDING_SCHEMA, "upstream_source_ref": UPSTREAM_SOURCE_REF,
        "task_id": "task-1", "domain": "engineering", "mode": mode, "k": k,
        "upstream_run_id": upstream_run_id, "native_run_id": draft["run_id"],
        "summary": {"artifact_ref": _ref("summary.json"), "digest": sha256_bytes(summary_bytes)},
        "native_observation": {"artifact_ref": _ref("observation.json"), "digest": sha256_bytes(draft_bytes)},
        "harness": dict(config["procedure"]["instruction_bundle"]),
        "output": dict(draft["evidence"]["output"]),
    }
    binding_bytes = canonical_json_bytes(binding)
    return dict(binding_bytes=binding_bytes, expected_binding_digest=sha256_bytes(binding_bytes),
                summary_bytes=summary_bytes, native_observation_bytes=draft_bytes,
                output_bytes=output, harness_files=files,
                scenario=scenario, configuration=config, experiment=experiment), other


def rebind(inputs, field, content):
    result = copy.deepcopy(inputs)
    result[field] = content
    binding = decode_json(result["binding_bytes"])
    key = {"summary_bytes": "summary", "native_observation_bytes": "native_observation"}[field]
    binding[key]["digest"] = sha256_bytes(content)
    result["binding_bytes"] = canonical_json_bytes(binding)
    result["expected_binding_digest"] = sha256_bytes(result["binding_bytes"])
    return result


def finalize(inputs):
    return finalize_selected_run(**inputs, validator_id="mastermind.test.validator.v1",
        validator_version="1.0.0", validator_code_ref=REPO_REF_BASE,
        validated_at="2026-08-26T00:00:00Z", created_at="2026-08-26T00:00:00Z")


@pytest.mark.parametrize("mode,k", [("agg", 1), ("agg", 2), ("seq", 1), ("seq", 3)])
def test_real_native_store_round_trip(tmp_path, mode, k):
    inputs, other = fixture(mode, k)
    before = copy.deepcopy(inputs)
    result = import_selected_run(**inputs)
    assert result.promotion == "NONE"
    assert result.evidence_scope == "BYTE_AND_IDENTITY_CHECKED_NOT_AUTHENTICATED"
    assert len(result.draft["evidence"]["artifacts"]) == 3
    assert inputs == before
    run = finalize(inputs)
    assert run["validity"]["status"] == "VALID"
    native = store.ArtifactStore(tmp_path / "native")
    for document in (inputs["scenario"], inputs["configuration"], other, inputs["experiment"], run):
        native.create(document)
    assert native.resolve_run(run["run_id"]) == run
    assert finalize(inputs) == run
    native.create(run)  # incumbent exact-byte idempotency


@pytest.mark.parametrize("field", ["binding_bytes", "summary_bytes", "native_observation_bytes", "output_bytes"])
def test_changed_bytes_are_refused(field):
    inputs, _ = fixture()
    inputs[field] += b" "
    with pytest.raises(Harness2ImportError, match="CHANGED"):
        import_selected_run(**inputs)


@pytest.mark.parametrize("change", [
    lambda s: s.update(task_id="other"),
    lambda s: s.update(domain="other"),
    lambda s: s.update(k=True),
    lambda s: s.update(status="partial"),
    lambda s: s.update(errors=["failure"]),
    lambda s: s["modes"]["agg"].update(finals=[]),
    lambda s: s["modes"]["agg"].update(fell_back=["inv1"]),
    lambda s: s["modes"]["agg"].update(ok=False),
    lambda s: s["selections"]["agg"].update(task_id="other"),
    lambda s: s["selections"]["agg"].update(chosen_run_id="other"),
    lambda s: s["selections"]["agg"].update(chosen_label="base1"),
    lambda s: s["selections"]["agg"].update(chosen_is_base=True),
    lambda s: s["selections"]["agg"].update(fallback=True),
    lambda s: s["selections"]["agg"].update(error="failure"),
    lambda s: s["selections"]["agg"].update(harness_fingerprint="0" * 16),
])
def test_correlated_summary_refusals_even_after_rehash(change):
    inputs, _ = fixture()
    summary = decode_json(inputs["summary_bytes"])
    change(summary)
    inputs = rebind(inputs, "summary_bytes", json.dumps(summary).encode())
    with pytest.raises(Harness2ImportError):
        import_selected_run(**inputs)


@pytest.mark.parametrize("raw", [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1e999}',
    b'{"x":"\\ud800"}', b'[]', b'\xff', b'{"x":' + b'[' * 40 + b'0' + b']' * 40 + b'}'])
def test_strict_json(raw):
    with pytest.raises(Harness2ImportError):
        decode_json(raw)


@pytest.mark.parametrize("path", ["../secret", "/absolute", "a\\b", "a//b", "./a", ".git/config",
    "__pycache__/x", "x.pyc", ".adapt_complete", "a/../b", "a /b", "A:", "a./b"])
def test_harness_paths_refused(path):
    with pytest.raises(Harness2ImportError):
        harness_manifest({path: b"text"})


def test_case_alias_and_tree_bytes_refused():
    with pytest.raises(Harness2ImportError, match="ALIAS"):
        harness_digest({"AGENTS.md": b"x", "agents.md": b"y"})
    inputs, _ = fixture()
    inputs["harness_files"]["AGENTS.md"] += b"changed"
    with pytest.raises(Harness2ImportError, match="HARNESS_BYTES_CHANGED"):
        import_selected_run(**inputs)


@pytest.mark.parametrize("field,change,expected", [
    ("effect", {"state": "EFFECT_UNKNOWN", "operation_ref": "op:unknown", "reconciliation_ref": None}, "INVALID_EFFECT_UNKNOWN"),
    ("cleanup", {"status": "UNPROVEN", "proof": None}, "INVALID_CLEANUP"),
])
def test_native_failure_not_laundered(field, change, expected):
    inputs, _ = fixture()
    draft = decode_json(inputs["native_observation_bytes"], canonical=True)
    draft[field] = change
    inputs = rebind(inputs, "native_observation_bytes", canonical_json_bytes(draft))
    imported = import_selected_run(**inputs)
    assert imported.draft[field] == change
    assert finalize(inputs)["validity"]["status"] == expected


def test_native_model_and_freshness_not_invented():
    inputs, _ = fixture()
    draft = decode_json(inputs["native_observation_bytes"], canonical=True)
    draft["execution"].update(model_served="different-served-model", fresh_session_observed=False)
    inputs = rebind(inputs, "native_observation_bytes", canonical_json_bytes(draft))
    result = import_selected_run(**inputs)
    assert result.draft["execution"]["model_served"] == "different-served-model"
    assert result.draft["execution"]["fresh_session_observed"] is False
    assert finalize(inputs)["validity"]["status"] == "INVALID_CONFIGURATION"


def test_native_output_binding_not_overwritten():
    inputs, _ = fixture()
    draft = decode_json(inputs["native_observation_bytes"], canonical=True)
    draft["evidence"]["output"]["digest"] = "sha256:" + "0" * 64
    inputs = rebind(inputs, "native_observation_bytes", canonical_json_bytes(draft))
    with pytest.raises(Harness2ImportError, match="NATIVE_OUTPUT"):
        import_selected_run(**inputs)


def test_missing_native_model_is_rejected_not_fabricated():
    from scripts.agent_eval.errors import ContractError
    inputs, _ = fixture()
    draft = decode_json(inputs["native_observation_bytes"], canonical=True)
    draft["execution"]["model_served"] = None
    inputs = rebind(inputs, "native_observation_bytes", canonical_json_bytes(draft))
    with pytest.raises(ContractError, match="model_served"):
        import_selected_run(**inputs)


def test_binding_closed_and_source_pinned():
    for change in (lambda d: d.update(extra=True),
                   lambda d: d.update(upstream_source_ref=UPSTREAM_SOURCE_REF[:-1] + "0"),
                   lambda d: d.update(k=True),
                   lambda d: d.update(mode="future"),
                   lambda d: d.update(native_run_id="run:invalid")):
        inputs, _ = fixture()
        binding = decode_json(inputs["binding_bytes"])
        change(binding)
        inputs["binding_bytes"] = canonical_json_bytes(binding)
        inputs["expected_binding_digest"] = sha256_bytes(inputs["binding_bytes"])
        from scripts.agent_eval.errors import ContractError
        with pytest.raises((Harness2ImportError, ContractError)):
            import_selected_run(**inputs)


def test_byte_bound_rejection_precedes_json():
    inputs, _ = fixture()
    inputs["binding_bytes"] = b"x" * 1_048_577
    with pytest.raises(Harness2ImportError, match="BINDING_BYTE_BOUND"):
        import_selected_run(**inputs)


def test_manifest_order_independent_and_changed_path_changes_identity():
    a = {"AGENTS.md": b"a", "skills/x/SKILL.md": b"b"}
    assert harness_digest(a) == harness_digest(dict(reversed(list(a.items()))))
    assert harness_digest(a) != harness_digest({"AGENTS.md": b"a", "skills/y/SKILL.md": b"b"})


def test_conflicting_run_cannot_replace_existing_native_receipt(tmp_path):
    from scripts.agent_eval.errors import ArtifactConflictError
    inputs, other = fixture()
    native = store.ArtifactStore(tmp_path / "native")
    run = finalize(inputs)
    for d in (inputs["scenario"], inputs["configuration"], other, inputs["experiment"], run):
        native.create(d)
    draft = decode_json(inputs["native_observation_bytes"])
    draft["resources"]["input_tokens"] += 1
    changed = rebind(inputs, "native_observation_bytes", canonical_json_bytes(draft))
    with pytest.raises(ArtifactConflictError):
        native.create(finalize(changed))
    assert native.resolve_run(run["run_id"]) == run

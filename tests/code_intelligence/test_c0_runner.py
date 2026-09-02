"""C0 falsifier — runner, result schema and the no-fabricated-decision guard.

The single most important test in this file is
``test_synthetic_trials_can_never_produce_a_decision``: it is what stops the
experiment from reporting a backend selection that was never empirically earned.
"""

from __future__ import annotations

import copy
import functools
import hashlib
import json
import sys
from pathlib import Path

import jsonschema
import pytest

from experiments.code_intelligence.backend import ExecutableSpec
from experiments.code_intelligence.c0_runner import (
    ARTIFACT_VERSION,
    OPERATION_KEY,
    SCHEMA_PATH,
    RunnerError,
    build_result,
    is_stand_in,
    make_disposable_corpus,
    result_digest,
    validate_result,
)
from experiments.code_intelligence.semantic_contract import SEMANTIC_TOOL_NAMES

PYTHON = Path(sys.executable).resolve()
STAND_IN = (Path(__file__).parent / "servers" / "fake_lsp_server.py").resolve()

SOURCE = {
    "repository": "mastermindx-market-intelligence/Mastermind",
    "branch": "sol/codeintel-c0-semantic-falsifier-20260830",
    "head_sha": "0" * 40,
    "base_sha": "1" * 40,
    "changed_paths": ["experiments/code_intelligence/c0_runner.py"],
}


@functools.lru_cache(maxsize=1)
def _python_digest() -> str:
    return hashlib.sha256(PYTHON.read_bytes()).hexdigest()


@functools.lru_cache(maxsize=1)
def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _build(
    tmp_path: Path, *, with_stand_in: bool = False, workspace: Path | None = None
) -> dict:
    workspace = workspace or make_disposable_corpus(tmp_path / "workspace")
    return build_result(
        workspace=workspace,
        scratch_parent=tmp_path / "scratch",
        lsp_binary=PYTHON if with_stand_in else None,
        lsp_sha256=_python_digest() if with_stand_in else None,
        lsp_argv=(str(STAND_IN), "ok") if with_stand_in else (),
        serena_bundle=None,
        source=SOURCE,
    )


class TestBlockedResult:
    def test_no_bundles_produces_a_blocked_result(self, tmp_path: Path) -> None:
        result = _build(tmp_path)
        assert result["decision_state"] == "BLOCKED_MISSING_PINNED_DEPENDENCY"
        assert "decision" not in result
        assert result["blocking_reason"]

    def test_blocked_result_validates_against_the_schema(self, tmp_path: Path) -> None:
        validate_result(_build(tmp_path))

    def test_both_candidates_are_reported_as_unexercised(self, tmp_path: Path) -> None:
        result = _build(tmp_path)
        kinds = {c["kind"]: c for c in result["candidates"]}
        assert kinds["direct_lsp"]["status"] == "UNEXERCISED_MISSING_BUNDLE"
        assert "LSP_BINARY_UNAVAILABLE" in kinds["direct_lsp"]["hard_failures"]
        assert kinds["serena"]["status"] == "UNEXERCISED_MISSING_BUNDLE"
        assert "SERENA_BUNDLE_UNAVAILABLE" in kinds["serena"]["hard_failures"]

    def test_artifact_identity_fields(self, tmp_path: Path) -> None:
        result = _build(tmp_path)
        assert result["artifact_version"] == ARTIFACT_VERSION
        assert result["operation_key"] == OPERATION_KEY
        assert result["wave_status"] == "DISPOSABLE FALSIFIER / PRODUCTION_INERT"

    def test_exposed_tool_census_is_exactly_six(self, tmp_path: Path) -> None:
        assert _build(tmp_path)["exposed_tool_census"] == list(SEMANTIC_TOOL_NAMES)

    def test_next_action_names_the_provisioning_step(self, tmp_path: Path) -> None:
        assert "949a27ef1e5fda1a6e7b561e777bcece345c6ffd" in _build(tmp_path)["next_action"]


class TestStandInHandling:
    def test_stand_in_is_detected(self) -> None:
        spec = ExecutableSpec(
            path=PYTHON, sha256=_python_digest(), argv_suffix=(str(STAND_IN), "ok")
        )
        assert is_stand_in(spec)

    def test_a_real_binary_is_not_a_stand_in(self) -> None:
        spec = ExecutableSpec(path=PYTHON, sha256=_python_digest(), argv_suffix=())
        assert not is_stand_in(spec)

    def test_stand_in_runs_trials_but_stays_blocked(self, tmp_path: Path) -> None:
        result = _build(tmp_path, with_stand_in=True)
        lsp = next(c for c in result["candidates"] if c["kind"] == "direct_lsp")
        assert lsp["status"] == "EXERCISED"
        assert lsp["trials"]
        assert all(trial["synthetic"] for trial in lsp["trials"])
        assert result["decision_state"] == "BLOCKED_MISSING_PINNED_DEPENDENCY"
        assert "decision" not in result

    def test_stand_in_trials_are_actually_correct(self, tmp_path: Path) -> None:
        # The adapter maps real results: the harness works, only the backend is
        # missing. This keeps the blocked verdict from hiding a broken harness.
        result = _build(tmp_path, with_stand_in=True)
        lsp = next(c for c in result["candidates"] if c["kind"] == "direct_lsp")
        assert all(trial["correct"] for trial in lsp["trials"]), [
            (t["case"], t["actual"], t["expected"], t["error"]) for t in lsp["trials"]
        ]

    def test_stand_in_result_still_validates(self, tmp_path: Path) -> None:
        validate_result(_build(tmp_path, with_stand_in=True))


class TestSchemaGuards:
    def test_synthetic_trials_can_never_produce_a_decision(self, tmp_path: Path) -> None:
        """The structural guard against a fabricated backend selection."""
        result = _build(tmp_path, with_stand_in=True)
        forged = copy.deepcopy(result)
        forged["decision_state"] = "DECIDED"
        forged["decision"] = "DIRECT_LSP"
        forged.pop("blocking_reason", None)
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(_schema()).validate(forged)

    def test_decided_without_a_decision_is_invalid(self, tmp_path: Path) -> None:
        forged = copy.deepcopy(_build(tmp_path))
        forged["decision_state"] = "DECIDED"
        forged.pop("blocking_reason", None)
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(_schema()).validate(forged)

    def test_blocked_carrying_a_decision_is_invalid(self, tmp_path: Path) -> None:
        forged = copy.deepcopy(_build(tmp_path))
        forged["decision"] = "NO_SAFE_BACKEND"
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(_schema()).validate(forged)

    def test_decision_enum_is_closed(self, tmp_path: Path) -> None:
        forged = copy.deepcopy(_build(tmp_path))
        forged["decision_state"] = "DECIDED"
        forged["decision"] = "SERENA_PROBABLY"
        forged.pop("blocking_reason", None)
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(_schema()).validate(forged)

    def test_unknown_top_level_field_is_invalid(self, tmp_path: Path) -> None:
        forged = copy.deepcopy(_build(tmp_path))
        forged["backdoor"] = True
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(_schema()).validate(forged)

    def test_a_decided_result_with_real_trials_is_accepted(self, tmp_path: Path) -> None:
        # Proves the guard blocks fabrication, not decisions as such.
        forged = copy.deepcopy(_build(tmp_path, with_stand_in=True))
        forged["decision_state"] = "DECIDED"
        forged["decision"] = "DIRECT_LSP"
        forged.pop("blocking_reason", None)
        for candidate in forged["candidates"]:
            candidate["status"] = "EXERCISED"
            candidate["trials"] = [
                {
                    "case": "O1", "language": "python", "correct": True,
                    "expected": [], "actual": [], "latency_ms": 1, "synthetic": False,
                }
            ]
        jsonschema.Draft202012Validator(_schema()).validate(forged)


class TestHostileAndDeterminism:
    def test_every_hostile_check_refused(self, tmp_path: Path) -> None:
        result = _build(tmp_path)
        allowed = [c for c in result["hostile_results"] if c["outcome"] != "REFUSED_AS_REQUIRED"]
        assert not allowed, allowed

    def test_hostile_suite_covers_the_named_families(self, tmp_path: Path) -> None:
        checks = {c["check"] for c in _build(tmp_path)["hostile_results"]}
        for expected in (
            "contract_refuses_root_selection",
            "contract_refuses_path_traversal",
            "payload_guard_refuses_secret",
            "seal_detects_candidate_tree_write",
            "seal_refuses_symlink_root",
            "two_worktrees_carry_distinct_seals",
            "scratch_refuses_candidate_tree",
        ):
            assert expected in checks

    def test_result_is_deterministic_apart_from_time(self, tmp_path: Path) -> None:
        # Same sealed workspace twice: the seal binds inode and resolved root, so
        # two different directories are legitimately expected to differ.
        workspace = make_disposable_corpus(tmp_path / "workspace")
        first = _build(tmp_path / "a", workspace=workspace)
        second = _build(tmp_path / "b", workspace=workspace)
        for result in (first, second):
            result.pop("generated_unix_ms")
            result["binding_receipt"].pop("startup_unix_ms", None)
        assert result_digest(first) == result_digest(second)

    def test_artifact_never_publishes_an_absolute_host_path(self, tmp_path: Path) -> None:
        rendered = json.dumps(_build(tmp_path, with_stand_in=True))
        for marker in ("/Users/", "/private/", "/var/folders", "/opt/", "/usr/"):
            assert marker not in rendered, marker
        for token in rendered.replace('"', " ").replace(",", " ").split():
            # A bare "/" is a separator (e.g. "<commit> / v1.7.0"), not a path.
            assert not (token.startswith("/") and len(token) > 1), token

    def test_symlinked_workspace_is_refused(self, tmp_path: Path) -> None:
        real = make_disposable_corpus(tmp_path / "real")
        link = tmp_path / "link"
        link.symlink_to(real, target_is_directory=True)
        with pytest.raises(RunnerError) as excinfo:
            build_result(
                workspace=link, scratch_parent=tmp_path / "scratch",
                lsp_binary=None, lsp_sha256=None, lsp_argv=(),
                serena_bundle=None, source=SOURCE,
            )
        assert excinfo.value.code == "SYMLINK_REFUSED"

    def test_digest_mismatch_on_the_lsp_binary_is_a_hard_failure(self, tmp_path: Path) -> None:
        workspace = make_disposable_corpus(tmp_path / "workspace")
        result = build_result(
            workspace=workspace, scratch_parent=tmp_path / "scratch",
            lsp_binary=PYTHON, lsp_sha256="0" * 64, lsp_argv=(str(STAND_IN), "ok"),
            serena_bundle=None, source=SOURCE,
        )
        lsp = next(c for c in result["candidates"] if c["kind"] == "direct_lsp")
        assert "EXECUTABLE_DIGEST_MISMATCH" in lsp["hard_failures"]

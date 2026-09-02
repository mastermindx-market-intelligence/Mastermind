"""C0 falsifier — runner, result schema and the no-fabricated-decision guards.

The load-bearing tests here are the B4 discriminating mutants: each one takes a
plausible-looking artifact and proves the schema (or the cross-field winner law)
refuses it. Together they are what stops a backend selection that was never
empirically earned.
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
    cross_check_result,
    is_stand_in,
    make_disposable_corpus,
    result_digest,
    semantic_evidence_digest,
    validate_result,
)
from experiments.code_intelligence.decision import REQUIRED_CASES
from experiments.code_intelligence.semantic_contract import SEMANTIC_TOOL_NAMES
from experiments.code_intelligence.serena_backend import (
    SERENA_PINNED_COMMIT,
    SERENA_PINNED_VERSION,
    bundle_digest,
)

PYTHON = Path(sys.executable).resolve()
SERVERS = (Path(__file__).parent / "servers").resolve()
LSP_STAND_IN = SERVERS / "fake_lsp_server.py"
SERENA_STAND_IN = SERVERS / "fake_serena_server.py"

SOURCE = {
    "repository": "mastermindx-market-intelligence/Mastermind",
    "branch": "sol/codeintel-c0-semantic-falsifier-20260830",
    "head_sha": "0" * 40, "base_sha": "1" * 40,
    "changed_paths": ["experiments/code_intelligence/c0_runner.py"],
}


@functools.lru_cache(maxsize=1)
def _python_digest() -> str:
    return hashlib.sha256(PYTHON.read_bytes()).hexdigest()


@functools.lru_cache(maxsize=1)
def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _lsp_inputs() -> dict:
    entry = {"binary": str(PYTHON), "sha256": _python_digest(),
             "argv": [str(LSP_STAND_IN), "ok"]}
    return {"python": dict(entry), "typescript": dict(entry),
            "serena_launcher": {"binary": str(PYTHON), "sha256": _python_digest(),
                                "argv": [str(SERENA_STAND_IN), "clean"]}}


def _make_bundle(base: Path):
    from experiments.code_intelligence.serena_backend import SerenaBundle

    root = base / "serena-bundle"
    root.mkdir(parents=True, exist_ok=True)
    (root / "VERSION").write_text(f"{SERENA_PINNED_VERSION}\n", encoding="utf-8")
    (root / "COMMIT").write_text(f"{SERENA_PINNED_COMMIT}\n", encoding="utf-8")
    return SerenaBundle(root=root, source_commit=SERENA_PINNED_COMMIT,
                        version=SERENA_PINNED_VERSION, sha256=bundle_digest(root))


def _build(tmp_path: Path, *, with_stand_ins: bool = False) -> dict:
    bundle = _make_bundle(tmp_path / "bundles") if with_stand_ins else None
    return build_result(
        scratch_parent=tmp_path / "scratch",
        lsp_binaries=_lsp_inputs() if with_stand_ins else {},
        serena_bundle=bundle.root if bundle else None,
        serena_sha256=bundle.sha256 if bundle else None,
        source=SOURCE,
    )


class TestBlockedResult:
    def test_no_inputs_produces_a_blocked_result(self, tmp_path: Path) -> None:
        result = _build(tmp_path)
        assert result["decision_state"] == "BLOCKED_MISSING_PINNED_DEPENDENCY"
        assert "decision" not in result
        assert result["blocking_reason"]

    def test_blocked_result_validates(self, tmp_path: Path) -> None:
        validate_result(_build(tmp_path))

    def test_both_candidates_report_their_missing_bundle(self, tmp_path: Path) -> None:
        kinds = {c["kind"]: c for c in _build(tmp_path)["candidates"]}
        assert any("LSP_BINARY_UNAVAILABLE" in f for f in kinds["direct_lsp"]["hard_failures"])
        assert "SERENA_BUNDLE_UNAVAILABLE" in kinds["serena"]["hard_failures"]

    def test_identity_fields(self, tmp_path: Path) -> None:
        result = _build(tmp_path)
        assert result["artifact_version"] == ARTIFACT_VERSION
        assert result["operation_key"] == OPERATION_KEY
        assert result["exposed_tool_census"] == list(SEMANTIC_TOOL_NAMES)

    def test_next_action_names_the_pinned_bundles(self, tmp_path: Path) -> None:
        assert SERENA_PINNED_COMMIT in _build(tmp_path)["next_action"]


class TestFullMatrixWithStandIns:
    """Sol's requirement: prove the harness RUNS the whole matrix, cannot win."""

    def test_both_candidates_run_both_languages(self, tmp_path: Path) -> None:
        result = _build(tmp_path, with_stand_ins=True)
        for candidate in result["candidates"]:
            languages = {t["language"] for t in candidate["trials"]}
            assert languages == {"python", "typescript"}, candidate["kind"]

    def test_every_required_case_and_phase_is_executed(self, tmp_path: Path) -> None:
        result = _build(tmp_path, with_stand_ins=True)
        for candidate in result["candidates"]:
            assert {t["case"] for t in candidate["trials"]} == set(REQUIRED_CASES)
            assert {t["phase"] for t in candidate["trials"]} == {"cold", "warm"}

    def test_all_stand_in_trials_are_marked_synthetic(self, tmp_path: Path) -> None:
        result = _build(tmp_path, with_stand_ins=True)
        for candidate in result["candidates"]:
            assert all(t["synthetic"] for t in candidate["trials"])

    def test_stand_ins_still_cannot_produce_a_decision(self, tmp_path: Path) -> None:
        result = _build(tmp_path, with_stand_ins=True)
        assert result["decision_state"] == "BLOCKED_MISSING_PINNED_DEPENDENCY"
        assert "decision" not in result

    def test_direct_lsp_stand_in_answers_correctly_on_both_languages(
        self, tmp_path: Path
    ) -> None:
        # Keeps a blocked verdict from hiding a broken harness.
        result = _build(tmp_path, with_stand_ins=True)
        lsp = next(c for c in result["candidates"] if c["kind"] == "direct_lsp")
        wrong = [t for t in lsp["trials"] if not t["correct"]]
        assert not wrong, [(t["language"], t["case"], t["actual"], t["expected"]) for t in wrong]

    def test_failed_trials_are_preserved_not_dropped(self, tmp_path: Path) -> None:
        # Serena's admitted tool set has no implementations/diagnostics: those
        # trials must be RECORDED as failures, never silently omitted.
        result = _build(tmp_path, with_stand_ins=True)
        serena = next(c for c in result["candidates"] if c["kind"] == "serena")
        failed = [t for t in serena["trials"] if not t["correct"]]
        assert failed, "a candidate that cannot serve a case must show failed trials"
        assert all(t["error"] for t in failed if t["actual"] is None)
        assert {t["case"] for t in failed} >= {
            "A3_implementations_of_protocol", "diagnostics_planted_undefined_name"
        }

    def test_stand_in_result_validates(self, tmp_path: Path) -> None:
        validate_result(_build(tmp_path, with_stand_ins=True))

    def test_stand_ins_are_detected(self) -> None:
        assert is_stand_in(ExecutableSpec(path=PYTHON, sha256=_python_digest(),
                                          argv_suffix=(str(LSP_STAND_IN), "ok")))
        assert not is_stand_in(ExecutableSpec(path=PYTHON, sha256=_python_digest(),
                                              argv_suffix=()))


class TestB4DiscriminatingMutants:
    """Each mutant is a plausible artifact the schema or winner law must refuse."""

    @pytest.fixture
    def decided(self, tmp_path: Path) -> dict:
        result = _build(tmp_path, with_stand_ins=True)
        forged = copy.deepcopy(result)
        forged["decision_state"] = "DECIDED"
        forged["decision"] = "DIRECT_LSP"
        forged.pop("blocking_reason", None)
        for candidate in forged["candidates"]:
            candidate["hard_failures"] = []
            for trial in candidate["trials"]:
                trial["synthetic"] = False
                trial["correct"] = True
        return forged

    def test_a_fully_real_decided_artifact_is_accepted(self, decided: dict) -> None:
        # Proves the mutants below fail for their stated reason, not because a
        # DECIDED artifact can never validate.
        jsonschema.Draft202012Validator(_schema()).validate(decided)

    def test_synthetic_trials_cannot_produce_a_decision(self, decided: dict) -> None:
        for candidate in decided["candidates"]:
            for trial in candidate["trials"]:
                trial["synthetic"] = True
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(_schema()).validate(decided)

    def test_missing_typescript_coverage_is_refused(self, decided: dict) -> None:
        for candidate in decided["candidates"]:
            candidate["trials"] = [t for t in candidate["trials"] if t["language"] != "typescript"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(_schema()).validate(decided)

    def test_missing_python_coverage_is_refused(self, decided: dict) -> None:
        for candidate in decided["candidates"]:
            candidate["trials"] = [t for t in candidate["trials"] if t["language"] != "python"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(_schema()).validate(decided)

    def test_missing_required_case_is_refused(self, decided: dict) -> None:
        for candidate in decided["candidates"]:
            candidate["trials"] = [
                t for t in candidate["trials"]
                if t["case"] != "A3_implementations_of_protocol"
            ]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(_schema()).validate(decided)

    def test_missing_warm_phase_is_refused(self, decided: dict) -> None:
        for candidate in decided["candidates"]:
            candidate["trials"] = [t for t in candidate["trials"] if t["phase"] != "warm"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(_schema()).validate(decided)

    def test_duplicate_candidate_kind_is_refused(self, decided: dict) -> None:
        decided["candidates"][1] = copy.deepcopy(decided["candidates"][0])
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(_schema()).validate(decided)

    def test_missing_candidate_kind_is_refused(self, decided: dict) -> None:
        decided["candidates"] = decided["candidates"][:1]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(_schema()).validate(decided)

    def test_decided_without_a_decision_is_refused(self, decided: dict) -> None:
        decided.pop("decision")
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(_schema()).validate(decided)

    def test_blocked_carrying_a_decision_is_refused(self, tmp_path: Path) -> None:
        forged = _build(tmp_path)
        forged["decision"] = "NO_SAFE_BACKEND"
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(_schema()).validate(forged)

    def test_decision_enum_is_closed(self, decided: dict) -> None:
        decided["decision"] = "SERENA_PROBABLY"
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(_schema()).validate(decided)

    def test_unknown_field_in_a_privileged_object_is_refused(self, decided: dict) -> None:
        decided["candidates"][0]["backdoor"] = True
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(_schema()).validate(decided)

    def test_unknown_top_level_field_is_refused(self, decided: dict) -> None:
        decided["backdoor"] = True
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(_schema()).validate(decided)

    def test_hard_failure_winner_is_refused_by_the_winner_law(self, decided: dict) -> None:
        decided["candidates"][0]["hard_failures"] = ["CANDIDATE_TREE_WRITE_DETECTED"]
        decided["decision"] = (
            "DIRECT_LSP" if decided["candidates"][0]["kind"] == "direct_lsp" else "SERENA"
        )
        with pytest.raises(RunnerError) as excinfo:
            cross_check_result(decided)
        assert excinfo.value.code == "RESULT_DECISION_INCONSISTENT"

    def test_incorrect_trials_cannot_carry_a_winner(self, decided: dict) -> None:
        for candidate in decided["candidates"]:
            for trial in candidate["trials"]:
                trial["correct"] = False
        with pytest.raises(RunnerError) as excinfo:
            cross_check_result(decided)
        assert excinfo.value.code == "RESULT_DECISION_INCONSISTENT"

    def test_a_consistent_decided_artifact_passes_the_winner_law(self, decided: dict) -> None:
        cross_check_result(decided)


class TestHostileDeterminismAndCleanup:
    def test_every_hostile_check_refused_or_declared_not_run(self, tmp_path: Path) -> None:
        allowed = [
            c for c in _build(tmp_path)["hostile_results"] if c["outcome"] == "ALLOWED"
        ]
        assert not allowed, allowed

    def test_serena_config_differential_runs_when_a_bundle_exists(
        self, tmp_path: Path
    ) -> None:
        result = _build(tmp_path, with_stand_ins=True)
        check = next(c for c in result["hostile_results"]
                     if c["check"] == "serena_repository_config_differential")
        assert check["outcome"] == "REFUSED_AS_REQUIRED"

    def test_artifact_never_publishes_an_absolute_host_path(self, tmp_path: Path) -> None:
        rendered = json.dumps(_build(tmp_path, with_stand_ins=True))
        for marker in ("/Users/", "/private/", "/var/folders", "/opt/", "/usr/"):
            assert marker not in rendered, marker

    def test_semantic_evidence_digest_is_stable_across_runs(self, tmp_path: Path) -> None:
        first = _build(tmp_path / "a", with_stand_ins=True)
        second = _build(tmp_path / "b", with_stand_ins=True)
        assert first["semantic_evidence_digest"] == second["semantic_evidence_digest"]
        assert result_digest(first) != result_digest(second), (
            "the raw digest SHOULD move with observation; only the semantic one is stable"
        )

    def test_semantic_evidence_digest_moves_when_evidence_moves(self, tmp_path: Path) -> None:
        base = _build(tmp_path, with_stand_ins=True)
        mutated = copy.deepcopy(base)
        mutated["candidates"][0]["trials"][0]["correct"] = not (
            mutated["candidates"][0]["trials"][0]["correct"]
        )
        assert semantic_evidence_digest(mutated) != base["semantic_evidence_digest"]

    def test_scratch_is_cleaned_with_a_receipt(self, tmp_path: Path) -> None:
        result = _build(tmp_path, with_stand_ins=True)
        cleanup = result["cleanup"]
        assert cleanup["removed"] is True
        assert cleanup["retained_paths"] == 0
        assert cleanup["failure"] is None
        assert cleanup["scratch_files_before"] > 0
        assert not (tmp_path / "scratch").exists()

    def test_sandbox_is_recorded_with_an_attestation(self, tmp_path: Path) -> None:
        environment = _build(tmp_path)["environment"]
        assert environment["sandbox"]["available"] is True
        assert environment["sandbox"]["network_denied"] is True
        assert environment["network_policy"] == "enforced_and_attested"
        assert "RLIMIT_AS" in environment["sandbox"]["unenforced_limits"]

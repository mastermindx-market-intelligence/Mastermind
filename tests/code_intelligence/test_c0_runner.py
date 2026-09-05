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
from experiments.code_intelligence.ground_truth import TERMINAL_MIGRATE_LEGACY_PIN
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


def _python_tree_digest(files: list[dict[str, str]]) -> str:
    return hashlib.sha256(
        b"".join(
            row["name"].encode("utf-8") + b"\0"
            + row["sha256"].encode("ascii") + b"\n"
            for row in sorted(files, key=lambda item: item["name"])
        )
    ).hexdigest()


def _lsp_inputs() -> dict:
    lsp_digest = hashlib.sha256(LSP_STAND_IN.read_bytes()).hexdigest()
    serena_digest = hashlib.sha256(SERENA_STAND_IN.read_bytes()).hexdigest()
    entry = {
        "binary": str(PYTHON),
        "sha256": _python_digest(),
        "argv": [str(LSP_STAND_IN), "ok"],
        "targets": [{
            "name": "lsp:stand-in",
            "file": str(LSP_STAND_IN),
            "sha256": lsp_digest,
            "ecosystem": "stand_in",
            "package": "mastermind-tests",
            "version": "source",
            "binding": "argv_file:1",
        }],
    }
    return {"python": dict(entry), "typescript": dict(entry),
            "serena_launcher": {
                "binary": str(PYTHON), "sha256": _python_digest(),
                "argv": [str(SERENA_STAND_IN), "clean"],
                "targets": [{
                    "name": "serena:stand-in",
                    "file": str(SERENA_STAND_IN),
                    "sha256": serena_digest,
                    "ecosystem": "stand_in",
                    "package": "mastermind-tests",
                    "version": "source",
                    "binding": "argv_file:1",
                }],
            }}


def _make_bundle(base: Path):
    from experiments.code_intelligence.serena_backend import SerenaBundle

    root = base / "serena-bundle"
    root.mkdir(parents=True, exist_ok=True)
    (root / "VERSION").write_text(f"{SERENA_PINNED_VERSION}\n", encoding="utf-8")
    (root / "COMMIT").write_text(f"{SERENA_PINNED_COMMIT}\n", encoding="utf-8")
    return SerenaBundle(root=root, source_commit=SERENA_PINNED_COMMIT,
                        version=SERENA_PINNED_VERSION, sha256=bundle_digest(root))


# A full build costs seconds (git inits, sandboxed subprocess launches, 40
# trials). Rebuilding it per assertion made the repository gate take 25 minutes
# for its first 1% and the CI job was cancelled. Each distinct build is performed
# ONCE and deep-copied; tests that genuinely need a fresh run opt out.
_BUILD_CACHE: dict[bool, dict] = {}


def _build(tmp_path: Path, *, with_stand_ins: bool = False, fresh: bool = False) -> dict:
    if not fresh and with_stand_ins in _BUILD_CACHE:
        return copy.deepcopy(_BUILD_CACHE[with_stand_ins])
    bundle = _make_bundle(tmp_path / "bundles") if with_stand_ins else None
    result = build_result(
        scratch_parent=tmp_path / "scratch",
        lsp_binaries=_lsp_inputs() if with_stand_ins else {},
        serena_bundle=bundle.root if bundle else None,
        serena_sha256=bundle.sha256 if bundle else None,
        source=SOURCE,
    )
    if not fresh:
        _BUILD_CACHE[with_stand_ins] = copy.deepcopy(result)
    return result


class TestBlockedResult:
    def test_no_inputs_produces_a_blocked_result(self, tmp_path: Path) -> None:
        result = _build(tmp_path)
        assert result["decision_state"] == "NON_DECISION"
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

    def test_missing_terminal_or_identity_closure_is_nondecision_not_no_safe_backend(
        self, tmp_path: Path
    ) -> None:
        result = _build(tmp_path, with_stand_ins=True)
        assert result["decision_state"] == "NON_DECISION"
        assert "decision" not in result
        assert "terminal" in result["blocking_reason"].lower()

    def test_machine_artifact_requires_toolchain_and_execution_identity(self, tmp_path: Path) -> None:
        result = _build(tmp_path, with_stand_ins=True)
        assert set(result["toolchain"]) == {
            "python_packages", "npm_packages", "resolution_manifests", "executions"
        }
        assert result["toolchain"]["executions"]
        execution = result["toolchain"]["executions"][0]
        assert set(execution) >= {
            "candidate", "corpus_id", "language", "provenance",
            "launcher", "canonical_argv", "argv_file_digests", "targets",
            "backend_identity_digest",
        }
        assert execution["launcher"]["sha256"] == _python_digest()
        assert execution["targets"][0]["sha256"] != _python_digest()

    def test_provenance_is_machine_derived_and_changes_semantic_identity(self, tmp_path: Path) -> None:
        result = _build(tmp_path, with_stand_ins=True)
        assert {row["provenance"]["kind"] for row in result["toolchain"]["executions"]} == {
            "stand_in"
        }
        assert any("stand-in" in risk for risk in result["residual_risks"])
        mutated = copy.deepcopy(result)
        mutated["toolchain"]["executions"][0]["provenance"]["kind"] = "real"
        assert semantic_evidence_digest(mutated) != result["semantic_evidence_digest"]

    def test_receipt_trial_cross_check_refuses_a_missing_execution(self, tmp_path: Path) -> None:
        result = _build(tmp_path, with_stand_ins=True)
        result["binding_receipt"]["per_execution"].pop()
        with pytest.raises(RunnerError) as excinfo:
            cross_check_result(result)
        assert excinfo.value.code == "RESULT_EXECUTION_TRIAL_MISMATCH"

    def test_declared_target_digest_is_measured_not_trusted(self, tmp_path: Path) -> None:
        inputs = _lsp_inputs()
        inputs["python"]["targets"] = [{
            "name": "python:fake-lsp",
            "file": str(LSP_STAND_IN),
            "sha256": "0" * 64,
            "ecosystem": "stand_in",
            "package": "mastermind-tests",
            "version": "source",
            "binding": "argv_file:1",
        }]
        with pytest.raises(RunnerError) as excinfo:
            build_result(
                scratch_parent=tmp_path / "scratch",
                lsp_binaries=inputs,
                source=SOURCE,
            )
        assert excinfo.value.code == "TARGET_DIGEST_MISMATCH"

    def test_declared_target_must_be_the_bound_argv_file(self, tmp_path: Path) -> None:
        inputs = _lsp_inputs()
        inputs["python"]["targets"][0].update({
            "file": str(SERENA_STAND_IN),
            "sha256": hashlib.sha256(SERENA_STAND_IN.read_bytes()).hexdigest(),
        })
        with pytest.raises(RunnerError) as excinfo:
            build_result(
                scratch_parent=tmp_path / "scratch",
                lsp_binaries=inputs,
                source=SOURCE,
            )
        assert excinfo.value.code == "TARGET_INVOCATION_MISMATCH"

    def test_launcher_without_an_explicit_target_cannot_clear_identity(
        self, tmp_path: Path
    ) -> None:
        inputs = _lsp_inputs()
        inputs["python"].pop("targets")
        result = build_result(
            scratch_parent=tmp_path / "scratch",
            lsp_binaries=inputs,
            source=SOURCE,
        )
        direct = next(row for row in result["candidates"] if row["kind"] == "direct_lsp")
        assert direct["identity_complete"] is False
        assert "EXECUTABLE_TARGET_MISSING" in direct["identity_failures"]

    def test_verified_serena_bundle_does_not_replace_a_selected_launch_target(
        self, tmp_path: Path
    ) -> None:
        inputs = _lsp_inputs()
        inputs["serena_launcher"].pop("targets")
        bundle = _make_bundle(tmp_path / "bundles")
        result = build_result(
            scratch_parent=tmp_path / "scratch",
            lsp_binaries=inputs,
            serena_bundle=bundle.root,
            serena_sha256=bundle.sha256,
            source=SOURCE,
        )
        serena = next(row for row in result["candidates"] if row["kind"] == "serena")
        assert serena["identity_complete"] is False
        assert "TARGET_INVOCATION_UNBOUND" in serena["identity_failures"]

    def test_python_closure_manifest_rehashes_installed_files(self, tmp_path: Path) -> None:
        installed = tmp_path / "site-packages" / "serena" / "__init__.py"
        installed.parent.mkdir(parents=True)
        installed.write_text("__version__ = '1.7.0'\n", encoding="utf-8")
        manifest = tmp_path / "python-closure.json"
        manifest.write_text(json.dumps([{
            "name": "serena",
            "version": "1.7.0",
            "files": [{
                "name": "serena/__init__.py",
                "source": str(installed),
                "sha256": "0" * 64,
            }],
        }]), encoding="utf-8")
        manifest_sha = hashlib.sha256(manifest.read_bytes()).hexdigest()
        with pytest.raises(RunnerError) as excinfo:
            build_result(
                scratch_parent=tmp_path / "scratch",
                python_closure_manifest=manifest,
                python_closure_sha256=manifest_sha,
                source=SOURCE,
            )
        assert excinfo.value.code == "PACKAGE_FILE_DIGEST_MISMATCH"

    def test_npm_closure_is_parsed_from_expected_digest_lockfile(self, tmp_path: Path) -> None:
        lock = tmp_path / "package-lock.json"
        lock.write_text(json.dumps({
            "lockfileVersion": 3,
            "packages": {
                "": {"name": "c0"},
                "node_modules/pyright": {
                    "version": "1.1.403",
                    "resolved": "https://registry.npmjs.org/pyright/-/pyright-1.1.403.tgz",
                    "integrity": "sha512-fixture",
                },
            },
        }), encoding="utf-8")
        result = build_result(
            scratch_parent=tmp_path / "scratch",
            npm_lock_manifest=lock,
            npm_lock_sha256=hashlib.sha256(lock.read_bytes()).hexdigest(),
            source=SOURCE,
        )
        assert result["toolchain"]["npm_packages"] == [{
            "name": "pyright",
            "version": "1.1.403",
            "resolved": "https://registry.npmjs.org/pyright/-/pyright-1.1.403.tgz",
            "integrity": "sha512-fixture",
        }]
        assert result["toolchain"]["resolution_manifests"][0]["ecosystem"] == "npm"


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
        assert result["decision_state"] == "NON_DECISION"
        assert "decision" not in result

    def test_materialized_terminal_case_runs_cold_and_warm_for_both_candidates(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        payload = (
            b"export function migrateLegacy(value: unknown) { return value; }\n"
            b"export const alias = migrateLegacy;\n"
        )
        monkeypatch.setattr(
            "experiments.code_intelligence.c0_runner.materialize_terminal_case",
            lambda _repository: {
                "case": "terminal_migrate_legacy",
                "tool": "find_references",
                "arguments": {"name": "migrateLegacy", "limit": 50},
                "expected": [
                    [TERMINAL_MIGRATE_LEGACY_PIN["path"], 1],
                    [TERMINAL_MIGRATE_LEGACY_PIN["path"], 2],
                ],
                "source": dict(TERMINAL_MIGRATE_LEGACY_PIN),
                "payload": payload,
            },
        )
        terminal_repository = tmp_path / "terminal-repository"
        terminal_repository.mkdir()
        bundle = _make_bundle(tmp_path / "bundles")
        result = build_result(
            scratch_parent=tmp_path / "scratch",
            lsp_binaries=_lsp_inputs(),
            serena_bundle=bundle.root,
            serena_sha256=bundle.sha256,
            terminal_repository=terminal_repository,
            source=SOURCE,
        )
        for candidate in result["candidates"]:
            terminal_trials = [
                trial for trial in candidate["trials"]
                if trial["corpus_id"] == "terminal_migrate_legacy"
            ]
            assert {trial["phase"] for trial in terminal_trials} == {"cold", "warm"}
        assert sum(
            row["corpus_id"] == "terminal_migrate_legacy"
            for row in result["binding_receipt"]["per_execution"]
        ) == 2
        validate_result(result)

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
        forged["toolchain"]["python_packages"] = []
        forged["toolchain"]["npm_packages"] = [
            {"name": "pyright", "version": "1.1.403",
             "resolved": "https://registry.npmjs.org/pyright/-/pyright-1.1.403.tgz",
             "integrity": "sha512-fixture"}
        ]
        forged["toolchain"]["resolution_manifests"] = [
            {"ecosystem": "python", "sha256": "3" * 64,
             "closure_sha256": "6" * 64,
             "provenance": "host-supplied immutable lock"},
            {"ecosystem": "npm", "sha256": "4" * 64,
             "closure_sha256": "7" * 64,
             "provenance": "host-supplied immutable lock"},
        ]
        forged["corpora"].append({
            "corpus_id": "terminal_migrate_legacy",
            "language": "typescript",
            "manifest_digest": "5" * 64,
            "ground_truth": {
                "kind": "derived_external_git_source",
                "source": dict(TERMINAL_MIGRATE_LEGACY_PIN),
            },
        })
        for candidate in forged["candidates"]:
            candidate["hard_failures"] = []
            candidate["identity_complete"] = True
            candidate["identity_failures"] = []
            if candidate["identity"]:
                candidate["identity"]["provenance"] = "real"
                candidate["identity"]["dependency_manifests"] = [
                    {"ecosystem": "python", "sha256": "3" * 64},
                    {"ecosystem": "npm", "sha256": "4" * 64},
                ]
            for trial in candidate["trials"]:
                trial["synthetic"] = False
                trial["correct"] = True
            template = next(
                trial for trial in candidate["trials"]
                if trial["language"] == "typescript" and trial["phase"] == "cold"
            )
            for phase in ("cold", "warm"):
                terminal_trial = copy.deepcopy(template)
                terminal_trial.update({
                    "case": "terminal_migrate_legacy",
                    "corpus_id": "terminal_migrate_legacy",
                    "phase": phase,
                    "correct": True,
                    "synthetic": False,
                })
                candidate["trials"].append(terminal_trial)

            receipt_template = next(
                row for row in forged["binding_receipt"]["per_execution"]
                if row["candidate"] == candidate["kind"]
                and row["language"] == "typescript"
            )
            terminal_receipt = copy.deepcopy(receipt_template)
            terminal_receipt["corpus_id"] = "terminal_migrate_legacy"
            terminal_receipt["provenance"] = {"kind": "real", "derived": True}
            forged["binding_receipt"]["per_execution"].append(terminal_receipt)
            execution = {
                key: terminal_receipt[key]
                for key in (
                    "candidate", "corpus_id", "language", "provenance", "launcher",
                    "canonical_argv", "argv_file_digests", "targets", "backend_identity",
                    "dependency_manifests", "backend_identity_digest",
                )
            }
            forged["toolchain"]["executions"].append(execution)

        for row in forged["binding_receipt"]["per_execution"]:
            row["provenance"] = {"kind": "real", "derived": True}
            for target in row["targets"]:
                target.update(
                    {"ecosystem": "npm", "package": "pyright", "version": "1.1.403"}
                    if row["candidate"] == "direct_lsp"
                    else {"ecosystem": "python", "package": "serena",
                          "version": SERENA_PINNED_VERSION}
                )
            row["dependency_manifests"] = [
                {"ecosystem": "python", "sha256": "3" * 64},
                {"ecosystem": "npm", "sha256": "4" * 64},
            ]
            row["backend_identity"]["provenance"] = "real"
            row["backend_identity"]["targets"] = [
                [target["name"], target["sha256"], target["ecosystem"],
                 target["package"], target["version"], target["binding"]]
                for target in row["targets"]
            ]
            row["backend_identity"]["dependency_manifests"] = [
                ["python", "3" * 64], ["npm", "4" * 64]
            ]
            row["backend_identity_digest"] = hashlib.sha256(
                json.dumps(
                    row["backend_identity"], sort_keys=True, separators=(",", ":")
                ).encode("ascii")
            ).hexdigest()
        for row in forged["toolchain"]["executions"]:
            row["provenance"] = {"kind": "real", "derived": True}
            for target in row["targets"]:
                target.update(
                    {"ecosystem": "npm", "package": "pyright", "version": "1.1.403"}
                    if row["candidate"] == "direct_lsp"
                    else {"ecosystem": "python", "package": "serena",
                          "version": SERENA_PINNED_VERSION}
                )
            row["dependency_manifests"] = [
                {"ecosystem": "python", "sha256": "3" * 64},
                {"ecosystem": "npm", "sha256": "4" * 64},
            ]
            row["backend_identity"]["provenance"] = "real"
            row["backend_identity"]["targets"] = [
                [target["name"], target["sha256"], target["ecosystem"],
                 target["package"], target["version"], target["binding"]]
                for target in row["targets"]
            ]
            row["backend_identity"]["dependency_manifests"] = [
                ["python", "3" * 64], ["npm", "4" * 64]
            ]
            row["backend_identity_digest"] = hashlib.sha256(
                json.dumps(
                    row["backend_identity"], sort_keys=True, separators=(",", ":")
                ).encode("ascii")
            ).hexdigest()
        serena_target_digests = sorted({
            target["sha256"]
            for row in forged["toolchain"]["executions"]
            if row["candidate"] == "serena"
            for target in row["targets"]
        })
        python_files = [
            {"name": f"serena/measured-{index}", "sha256": digest}
            for index, digest in enumerate(serena_target_digests, start=1)
        ]
        forged["toolchain"]["python_packages"] = [{
            "name": "serena",
            "version": SERENA_PINNED_VERSION,
            "files": python_files,
            "tree_sha256": _python_tree_digest(python_files),
        }]
        forged["residual_risks"] = [
            risk for risk in forged["residual_risks"]
            if "stand-in" not in risk.lower()
            and "identity is incomplete" not in risk.lower()
            and "terminal migratelegacy" not in risk.lower()
        ]
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

    def test_target_substitution_breaks_the_backend_identity_digest(self, decided: dict) -> None:
        for container in (
            decided["binding_receipt"]["per_execution"],
            decided["toolchain"]["executions"],
        ):
            container[0]["targets"][0]["sha256"] = "f" * 64
        with pytest.raises(RunnerError) as excinfo:
            cross_check_result(decided)
        assert excinfo.value.code == "RESULT_EXECUTION_IDENTITY_MISMATCH"

    def test_missing_package_closure_invalidates_identity(self, decided: dict) -> None:
        decided["toolchain"]["npm_packages"] = []
        with pytest.raises(RunnerError) as excinfo:
            cross_check_result(decided)
        assert excinfo.value.code == "RESULT_IDENTITY_CLOSURE_INCONSISTENT"
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(_schema()).validate(decided)

    def test_terminal_source_substitution_is_refused(self, decided: dict) -> None:
        terminal = next(
            row for row in decided["corpora"]
            if row["corpus_id"] == "terminal_migrate_legacy"
        )
        terminal["ground_truth"]["source"]["blob"] = "f" * 40
        with pytest.raises(RunnerError) as excinfo:
            cross_check_result(decided)
        assert excinfo.value.code == "RESULT_TERMINAL_PIN_MISMATCH"
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(_schema()).validate(decided)

    def test_target_must_bind_to_a_measured_package_coordinate(self, decided: dict) -> None:
        for collection in (
            decided["binding_receipt"]["per_execution"],
            decided["toolchain"]["executions"],
        ):
            row = next(item for item in collection if item["candidate"] == "direct_lsp")
            row["targets"][0]["package"] = "unrelated-package"
            row["backend_identity"]["targets"][0][3] = "unrelated-package"
            row["backend_identity_digest"] = hashlib.sha256(
                json.dumps(
                    row["backend_identity"], sort_keys=True, separators=(",", ":")
                ).encode("ascii")
            ).hexdigest()
        with pytest.raises(RunnerError) as excinfo:
            cross_check_result(decided)
        assert excinfo.value.code == "RESULT_IDENTITY_CLOSURE_INCONSISTENT"

    def test_target_binding_must_match_the_measured_invocation(self, decided: dict) -> None:
        for collection in (
            decided["binding_receipt"]["per_execution"],
            decided["toolchain"]["executions"],
        ):
            row = next(item for item in collection if item["candidate"] == "direct_lsp")
            row["targets"][0]["binding"] = "argv_file:2"
            row["backend_identity"]["targets"][0][5] = "argv_file:2"
            row["backend_identity_digest"] = hashlib.sha256(
                json.dumps(
                    row["backend_identity"], sort_keys=True, separators=(",", ":")
                ).encode("ascii")
            ).hexdigest()
        with pytest.raises(RunnerError) as excinfo:
            cross_check_result(decided)
        assert excinfo.value.code == "RESULT_IDENTITY_CLOSURE_INCONSISTENT"

    def test_python_target_digest_must_match_the_measured_package(self, decided: dict) -> None:
        files = decided["toolchain"]["python_packages"][0]["files"]
        for row in files:
            row["sha256"] = "e" * 64
        decided["toolchain"]["python_packages"][0]["tree_sha256"] = (
            _python_tree_digest(files)
        )
        with pytest.raises(RunnerError) as excinfo:
            cross_check_result(decided)
        assert excinfo.value.code == "RESULT_IDENTITY_CLOSURE_INCONSISTENT"


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
        first = _build(tmp_path / "a", with_stand_ins=True, fresh=True)
        second = _build(tmp_path / "b", with_stand_ins=True, fresh=True)
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
        result = _build(tmp_path, with_stand_ins=True, fresh=True)
        cleanup = result["cleanup"]
        assert cleanup["removed"] is True
        assert cleanup["retained_paths"] == 0
        assert cleanup["failure"] is None
        assert cleanup["scratch_files_before"] > 0
        assert not (tmp_path / "scratch").exists()

    def test_sandbox_state_is_recorded_truthfully_for_this_host(
        self, tmp_path: Path
    ) -> None:
        from experiments.code_intelligence.sandbox import sandbox_launcher_available

        environment = _build(tmp_path)["environment"]
        sandbox = environment["sandbox"]
        # The artifact must record what this host ACTUALLY does - never a fixed
        # platform answer, and never "enforced" without an attestation.
        assert sandbox["available"] is sandbox_launcher_available()
        if sandbox["available"]:
            # Invariant: the policy label must track the measured attestation.
            assert (
                environment["network_policy"] == "enforced_and_attested"
            ) is sandbox["network_denied"]
            named = set(sandbox["enforced_limits"]) | set(sandbox["unenforced_limits"])
            assert named == {"RLIMIT_CPU", "RLIMIT_AS", "RLIMIT_NOFILE", "RLIMIT_NPROC"}
        else:
            assert environment["network_policy"] == "unattested"
            assert sandbox.get("code")

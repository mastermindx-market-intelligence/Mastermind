"""C0 falsifier — ground truth must be LSP-independent.

If ground truth came from a language server, the experiment would be grading
each candidate against itself. This census is pure `ast`: no LSP, no backend,
no network. It is also the falsifier for the hand-written answer key.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from experiments.code_intelligence.ground_truth import (
    source_files,
    census_definitions,
    census_diagnostics,
    census_references,
    load_answer_key,
)

CORPUS = Path("tests/fixtures/code_intelligence/python_sample")


@pytest.fixture
def answer_key() -> dict:
    return load_answer_key(CORPUS)


class TestAnswerKeyIsHonest:
    def test_declared_definitions_match_the_ast_census(self, answer_key: dict) -> None:
        declared = {
            (row["symbol"], row["relative_file"], row["line"])
            for row in answer_key["definitions"]
        }
        actual = {
            (row["symbol"], row["relative_file"], row["line"])
            for row in census_definitions(CORPUS)
        }
        assert declared == actual

    @pytest.mark.parametrize(
        "symbol",
        ["make_producer", "make_dead_producer", "consume", "LiveProducer", "DeadProducer"],
    )
    def test_declared_references_match_the_ast_census(
        self, answer_key: dict, symbol: str
    ) -> None:
        declared = {
            (row["relative_file"], row["line"])
            for row in answer_key["references"][symbol]
        }
        actual = {
            (row["relative_file"], row["line"])
            for row in census_references(CORPUS, symbol)
        }
        assert declared == actual

    def test_declared_diagnostics_match_the_ast_census(self, answer_key: dict) -> None:
        declared = [
            (row["relative_file"], row["line"], row["symbol"])
            for row in answer_key["diagnostics"]
        ]
        actual = [
            (row["relative_file"], row["line"], row["symbol"])
            for row in census_diagnostics(CORPUS)
        ]
        assert declared == actual

    def test_exactly_one_planted_diagnostic(self) -> None:
        assert len(census_diagnostics(CORPUS)) == 1


class TestCorpusDiscriminates:
    def test_dead_sibling_is_textually_similar_to_the_live_one(self) -> None:
        source = (CORPUS / "src" / "sample" / "producer.py").read_text()
        assert source.count("def produce(self) -> str:") == 3
        # A name-only grep for the method cannot separate live from dead.

    def test_consumer_imports_only_the_live_wrapper(self) -> None:
        source = (CORPUS / "src" / "sample" / "consumer.py").read_text()
        assert "make_producer" in source
        assert "make_dead_producer" not in source
        assert "DeadProducer" not in source

    def test_live_answer_is_declared(self, answer_key: dict) -> None:
        assert answer_key["live_path"]["answer"] == "LiveProducer"
        assert "DeadProducer" in answer_key["dead_siblings"]

    def test_census_is_deterministic(self) -> None:
        assert census_definitions(CORPUS) == census_definitions(CORPUS)
        assert census_references(CORPUS, "consume") == census_references(CORPUS, "consume")

    def test_census_is_sorted(self) -> None:
        rows = census_definitions(CORPUS)
        keys = [(row["relative_file"], row["line"], row["symbol"]) for row in rows]
        assert keys == sorted(keys)

    def test_answer_key_is_valid_json_on_disk(self) -> None:
        json.loads((CORPUS / "answer_key.json").read_text())


class TestCorpusIsDataNotTests:
    """B1 — the corpus must contribute zero `tests/**/test_*.py` paths.

    The repository gate (`scripts/ci_pytest.py`) discovers with
    `rglob("test_*.py")` and then passes each path to pytest **explicitly**.
    pytest's ignore contract — `pytest_ignore_collect` and `collect_ignore`
    alike — does not apply to paths given explicitly on the command line, so no
    conftest hook can protect the corpus. The only durable guard is that the
    corpus contains no file matching `test_*.py` at all.
    """

    def _gate(self):
        spec = importlib.util.spec_from_file_location(
            "_c0_ci_pytest", Path("scripts/ci_pytest.py").resolve()
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_repository_gate_discovers_no_corpus_test_module(self) -> None:
        discovered = self._gate().discover_test_modules(Path(".").resolve())
        corpus = [p for p in discovered if "fixtures/code_intelligence" in p]
        assert corpus == [], (
            "the C0 corpus must contribute no repository test paths; the gate "
            f"passes these explicitly and pytest cannot ignore them: {corpus}"
        )

    def test_no_corpus_file_matches_the_gate_glob(self) -> None:
        offenders = sorted(
            path.as_posix()
            for path in Path("tests/fixtures/code_intelligence").rglob("test_*.py")
        )
        assert offenders == [], offenders

    def test_bounded_subprocess_collection_of_the_corpus_is_clean(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/fixtures/code_intelligence",
             "--collect-only", "-q"],
            capture_output=True, text=True, timeout=180, shell=False,
        )
        # Exit code 5 is pytest's EXIT_NOTESTSCOLLECTED — the desired proof that
        # the corpus contributes no tests at all. A collection *error* would be 2/3.
        assert result.returncode == 5, (
            f"expected no tests collected, got rc={result.returncode}\n"
            + result.stdout[-1500:] + result.stderr[-800:]
        )
        assert "error" not in result.stdout.lower(), result.stdout[-1500:]

    def test_corpus_consumer_case_is_still_present_under_its_data_name(self) -> None:
        assert (CORPUS / "tests" / "consumer_case.py").is_file()


TS_CORPUS = Path("tests/fixtures/code_intelligence/typescript_sample")


class TestTypeScriptAnswerKeyIsHonest:
    """B7 — the TS/TSX corpus needs the same LSP-independent falsification."""

    @pytest.fixture
    def ts_key(self) -> dict:
        return load_answer_key(TS_CORPUS)

    def test_declared_definitions_match_the_census(self, ts_key: dict) -> None:
        declared = {
            (row["symbol"], row["relative_file"], row["line"])
            for row in ts_key["definitions"]
        }
        actual = {
            (row["symbol"], row["relative_file"], row["line"])
            for row in census_definitions(TS_CORPUS)
        }
        assert declared == actual

    @pytest.mark.parametrize(
        "symbol",
        ["makeProducer", "makeDeadProducer", "consume", "LiveProducer", "DeadProducer"],
    )
    def test_declared_references_match_the_census(self, ts_key: dict, symbol: str) -> None:
        declared = {
            (row["relative_file"], row["line"]) for row in ts_key["references"][symbol]
        }
        actual = {
            (row["relative_file"], row["line"])
            for row in census_references(TS_CORPUS, symbol)
        }
        assert declared == actual

    def test_declared_diagnostics_match_the_census(self, ts_key: dict) -> None:
        declared = [
            (r["relative_file"], r["line"], r["symbol"]) for r in ts_key["diagnostics"]
        ]
        actual = [
            (r["relative_file"], r["line"], r["symbol"])
            for r in census_diagnostics(TS_CORPUS)
        ]
        assert declared == actual

    def test_exactly_one_planted_diagnostic(self) -> None:
        assert len(census_diagnostics(TS_CORPUS)) == 1

    def test_tsx_file_is_part_of_the_corpus(self) -> None:
        files = {relative for relative, _ in source_files(TS_CORPUS)}
        assert "src/widget.tsx" in files, "the TSX path must be exercised, not just .ts"

    def test_dead_sibling_is_textually_similar(self) -> None:
        source = (TS_CORPUS / "src" / "producer.ts").read_text()
        assert source.count("produce(): string {") == 2
        assert "implements Producer" in source

    def test_consumer_imports_only_the_live_wrapper(self) -> None:
        source = (TS_CORPUS / "src" / "consumer.ts").read_text()
        assert "makeProducer" in source
        assert "makeDeadProducer" not in source
        assert "DeadProducer" not in source

    def test_corpus_contributes_no_python_test_paths(self) -> None:
        assert list(TS_CORPUS.rglob("test_*.py")) == []


class TestTerminalMigrateLegacyMaterialization:
    def _repo(self, tmp_path: Path) -> tuple[Path, dict[str, str]]:
        from experiments.code_intelligence.ground_truth import git_blob_sha

        repo = tmp_path / "terminal"
        source = repo / "terminal" / "lib" / "workspaceMigrate.ts"
        source.parent.mkdir(parents=True)
        source.write_text(
            "export function migrateLegacy(value: unknown) {\n"
            "  return value;\n"
            "}\n"
            "export const migrateAgain = migrateLegacy;\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "-C", str(repo), "init", "-q", "-b", "main"], check=True)
        subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
        subprocess.run(
            ["git", "-C", str(repo), "remote", "add", "origin",
             "https://github.com/mastermindx-market-intelligence/mastermind-terminal.git"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(repo), "-c", "user.name=c0", "-c",
             "user.email=c0@example.invalid", "commit", "-q", "-m", "fixture"],
            check=True,
        )
        commit = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
        tree = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD^{tree}"], text=True).strip()
        return repo, {
            "commit": commit,
            "tree": tree,
            "path": "terminal/lib/workspaceMigrate.ts",
            "blob": git_blob_sha(source.read_bytes()),
        }

    def test_terminal_case_is_derived_from_exact_git_source_not_an_answer_key(
        self, tmp_path: Path
    ) -> None:
        from experiments.code_intelligence.ground_truth import materialize_terminal_case

        repo, pin = self._repo(tmp_path)
        case = materialize_terminal_case(
            repo,
            expected_commit=pin["commit"],
            expected_tree=pin["tree"],
            expected_path=pin["path"],
            expected_blob=pin["blob"],
        )
        assert case["case"] == "terminal_migrate_legacy"
        assert case["tool"] == "find_references"
        assert case["arguments"] == {"name": "migrateLegacy", "limit": 50}
        assert case["expected"] == [
            ["terminal/lib/workspaceMigrate.ts", 1],
            ["terminal/lib/workspaceMigrate.ts", 4],
        ]
        assert case["source"]["blob"] == pin["blob"]
        assert "answer_key" not in case

    def test_wrong_terminal_pin_is_refused_before_materialization(self, tmp_path: Path) -> None:
        from experiments.code_intelligence.ground_truth import GroundTruthError, materialize_terminal_case

        repo, pin = self._repo(tmp_path)
        with pytest.raises(GroundTruthError) as excinfo:
            materialize_terminal_case(
                repo,
                expected_commit="f" * 40,
                expected_tree=pin["tree"],
                expected_path=pin["path"],
                expected_blob=pin["blob"],
            )
        assert excinfo.value.code == "TERMINAL_COMMIT_MISMATCH"

    def test_wrong_terminal_origin_is_refused(self, tmp_path: Path) -> None:
        from experiments.code_intelligence.ground_truth import GroundTruthError, materialize_terminal_case

        repo, pin = self._repo(tmp_path)
        subprocess.run(
            ["git", "-C", str(repo), "remote", "set-url", "origin",
             "https://github.com/example/not-terminal.git"],
            check=True,
        )
        with pytest.raises(GroundTruthError) as excinfo:
            materialize_terminal_case(
                repo,
                expected_commit=pin["commit"],
                expected_tree=pin["tree"],
                expected_path=pin["path"],
                expected_blob=pin["blob"],
            )
        assert excinfo.value.code == "TERMINAL_REPOSITORY_MISMATCH"

    def test_protected_terminal_pin_constants_are_exact(self) -> None:
        from experiments.code_intelligence.ground_truth import TERMINAL_MIGRATE_LEGACY_PIN

        assert TERMINAL_MIGRATE_LEGACY_PIN == {
            "repository": "mastermindx-market-intelligence/mastermind-terminal",
            "commit": "fadd8b82f03ecaabe8a86d693da89f27be096d9f",
            "tree": "2ef6840d07c24456fc39e67029c45131fed53b1f",
            "path": "terminal/lib/workspaceMigrate.ts",
            "blob": "3b6feb5295d77cefa4f609b4cbafe5e6a68b5565",
        }

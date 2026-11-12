import hashlib
import json
from pathlib import Path
import contextlib
import io
import tempfile
import unittest
from unittest import mock

import yaml

from scripts import ci_workflow_inventory as inventory


def source(body="    runs-on: ubuntu-latest\n    steps: []\n", event="push"):
    return f"name: Example\non: {event}\njobs:\n  build:\n{body}"


def put(root, text, name="ci.yml"):
    folder = root / ".github" / "workflows"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(text)
    return folder / name



class WorkflowInventoryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def test_on_is_preserved_without_changing_global_yaml_resolver(self):
        text = source(event="[push, pull_request]")
        report = inventory.inspect_workflow(text, "ci.yml")
        assert report["events"] == ["push", "pull_request"]
        assert report["sha256"] == hashlib.sha256(text.encode()).hexdigest()
        assert yaml.safe_load("on: push") == {True: "push"}

    def test_duplicate_runner_key_is_explicit_error_not_last_value_wins(self):
        tmp_path = self.root
        put(tmp_path, source("    runs-on: ubuntu-latest\n    runs-on: self-hosted\n"))
        report = inventory.build_inventory(tmp_path)
        assert report["coverage"] == {"discovered_files": 1, "inspected_files": 0, "error_count": 1, "complete": False}
        assert report["errors"][0]["line"] == 6

    def test_job_permissions_replace_workflow_declaration_and_missing_defaults_stay_unknown(self):
        text = "permissions:\n  contents: read\n  id-token: write\n" + source("    runs-on: ubuntu-latest\n    permissions: {}\n")
        row = inventory.inspect_workflow(text, "ci.yml")["jobs"][0]
        assert row["permissions"] == {"source": "job", "declared": {}}
        unknown = inventory.inspect_workflow(source(), "ci.yml")["jobs"][0]
        assert unknown["permissions"] == {"source": "external_default_unknown", "declared": None}

    def test_inherited_permissions_are_identified_without_claiming_effective_token_access(self):
        text = "permissions: read-all\n" + source()
        row = inventory.inspect_workflow(text, "ci.yml")["jobs"][0]
        assert row["permissions"] == {"source": "inherited_workflow", "declared": "read-all"}

    def test_dynamic_matrix_keeps_choices_and_does_not_expand_or_certify_capacity(self):
        text = source("""    runs-on: ${{ matrix.os }}
    strategy:
      max-parallel: 2
      matrix:
        os: [ubuntu-latest, macos-14]
        secret_material: [do-not-emit]
        include:
          - os: windows-latest
        exclude:
          - os: macos-14
    steps: []
""")
        report = inventory.inspect_workflow(text, "ci.yml")
        row = report["jobs"][0]
        assert row["runner"]["kind"] == "dynamic"
        assert row["matrix"]["runner_choices"] == {"os": ["ubuntu-latest", "macos-14", "windows-latest"]}
        assert row["matrix"]["expansion"] == "not_evaluated"
        assert row["matrix"]["exclude_count"] == 1
        assert "do-not-emit" not in json.dumps(report)

    def test_reusable_workflow_delegates_runner_and_retains_cross_repo_reference(self):
        text = source("    uses: sample/shared/.github/workflows/test.yml@main\n")
        row = inventory.inspect_workflow(text, "ci.yml")["jobs"][0]
        assert row["runner"] == {"kind": "delegated", "selector": None}
        assert row["reusable_workflow"] == "sample/shared/.github/workflows/test.yml@main"
        with self.assertRaisesRegex(inventory.InventoryError, "reusable job"):
            inventory.inspect_workflow(text + "    runs-on: ubuntu-latest\n", "ci.yml")

    def test_nested_matrix_expressions_and_bracket_references_remain_explicit(self):
        for selector in ("${{ matrix.os }}", "${{ matrix['os'] }}", '${{ matrix["os"] }}'):
            with self.subTest(selector=selector):
                text = source("    runs-on: " + selector + "\n" + """    strategy:
      matrix:
        os: [ubuntu-latest, '${{ vars.RUNNER }}']
        include:
          - os: '${{ inputs.fallback }}'
""")
                matrix = inventory.inspect_workflow(text, "ci.yml")["jobs"][0]["matrix"]
                assert matrix["dynamic"]
                assert matrix["runner_choices"]["os"] == ["ubuntu-latest", "${{ vars.RUNNER }}", "${{ inputs.fallback }}"]
                assert matrix["unresolved_runner_references"] == []
        for selector, axes in (
            ("${{ matrix.missing }}", "        os: [ubuntu-latest]\n"),
            ("${{ matrix.os }}", "        os: []\n"),
            ("${{ matrix.os }}", "        os: {nested: ubuntu-latest}\n"),
            ("${{ matrix.os }}", "        include: '${{ fromJSON(inputs.rows) }}'\n"),
        ):
            with self.subTest(selector=selector, axes=axes):
                text = source("    runs-on: " + selector + "\n    strategy:\n      matrix:\n" + axes)
                matrix = inventory.inspect_workflow(text, "ci.yml")["jobs"][0]["matrix"]
                assert any("unresolved" in value for value in matrix["runner_choices"].values())
        text = source("    runs-on: ${{ matrix[inputs.axis] }}\n    strategy:\n      matrix:\n        os: [ubuntu-latest]\n")
        matrix = inventory.inspect_workflow(text, "ci.yml")["jobs"][0]["matrix"]
        assert matrix["unresolved_runner_references"] == ["unsupported matrix reference syntax"]

    def test_checkout_records_only_access_shape_not_tokens_scripts_or_environment_payloads(self):
        text = source("""    runs-on: [self-hosted, Linux, ARM64]
    environment:
      name: staging
      url: https://example.invalid/private
    container: python:3.12
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: do-not-emit-service-secret
    env:
      PASSWORD: do-not-emit-env-secret
    steps:
      - uses: actions/checkout@v4
        with:
          repository: sample/secondary
          token: do-not-emit-token
      - run: echo do-not-emit-script
        shell: bash
""")
        report = inventory.inspect_workflow(text, "ci.yml")
        row = report["jobs"][0]
        assert row["runner"]["kind"] == "self_hosted_labels"
        assert row["checkouts"] == [{"repository": "sample/secondary", "explicit_token_input": True,
                                      "explicit_ssh_key_input": False, "access": "not_verified"}]
        assert row["container_declared"] and row["services"] == ["postgres"]
        assert row["environment"] == "staging"
        assert "do-not-emit" not in json.dumps(report)
        assert "example.invalid" not in json.dumps(report)

    def test_group_and_custom_labels_are_not_claimed_to_be_available(self):
        grouped = inventory.inspect_workflow(source("    runs-on:\n      group: isolated\n      labels: linux-fast\n"), "ci.yml")
        assert grouped["jobs"][0]["runner"] == {"kind": "group_or_labels", "selector": {"group": "isolated", "labels": ["linux-fast"]}}
        custom = inventory.inspect_workflow(source("    runs-on: self-ubuntu\n"), "ci.yml")
        assert custom["jobs"][0]["runner"]["kind"] == "custom_labels"
        with self.assertRaisesRegex(inventory.InventoryError, "empty group and labels"):
            inventory.inspect_workflow(source("    runs-on: {labels: []}\n"), "ci.yml")

    def test_custom_shell_command_templates_are_hashed_not_emitted(self):
        shell = "bash -c 'echo do-not-emit-command; bash {0}'"
        text = source("    runs-on: ubuntu-latest\n    steps:\n      - run: true\n        shell: " + json.dumps(shell) + "\n")
        report = inventory.inspect_workflow(text, "ci.yml")
        row = report["jobs"][0]
        assert row["step_shells"] == []
        assert row["custom_shell_template_sha256"] == [hashlib.sha256(shell.encode()).hexdigest()]
        assert "do-not-emit" not in json.dumps(report)

    def test_missing_empty_and_oversized_inputs_never_look_complete(self):
        tmp_path = self.root
        assert not inventory.build_inventory(tmp_path)["coverage"]["complete"]
        path = put(tmp_path, source())
        path.unlink()
        assert not inventory.build_inventory(tmp_path)["coverage"]["complete"]
        path.write_text(source())
        with mock.patch.object(inventory, "MAX_FILE_BYTES", 10):
            report = inventory.build_inventory(tmp_path)
        assert report["coverage"]["inspected_files"] == 0
        assert report["errors"][0]["reason"] == "file exceeds inspection size limit"

    def test_malformed_yaml_has_bounded_error_without_echoing_input(self):
        tmp_path = self.root
        put(tmp_path, "on: push\njobs: [do-not-emit-malformed-secret\n")
        report = inventory.build_inventory(tmp_path)
        assert not report["coverage"]["complete"]
        assert "do-not-emit" not in json.dumps(report)

    def test_unsafe_or_unsupported_structures_are_reported(self):
        tmp_path = self.root
        for text in [
            "on: push\njobs: &loop {build: *loop}\n",
            "on: push\njobs: {build: !!python/object/apply:os.system ['false']}\n",
            "on: push\njobs: {}\n",
        ]:
            with self.subTest(text=text):
                put(tmp_path, text)
                report = inventory.build_inventory(tmp_path)
                assert report["coverage"]["error_count"] == 1
                assert report["workflows"] == []

    def test_scalar_constructor_failures_preserve_other_files_and_do_not_echo_source(self):
        put(self.root, source(), "good.yml")
        for invalid in ("2026-99-99", "!!int do-not-emit-integer", "!!bool do-not-emit-bool", "9" * 5000):
            with self.subTest(invalid=invalid[:30]):
                put(self.root, source() + "extra: " + invalid + "\n", "bad.yml")
                output, errors = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                    assert inventory.main(["--root", str(self.root)]) == 2
                report = json.loads(output.getvalue())
                assert report["coverage"] == {"discovered_files": 2, "inspected_files": 1, "error_count": 1, "complete": False}
                assert report["workflows"][0]["path"] == ".github/workflows/good.yml"
                assert report["errors"][0]["reason"] == "invalid YAML scalar construction"
                assert "do-not-emit" not in output.getvalue() + errors.getvalue()
                assert errors.getvalue() == ""

    def test_simple_yaml_aliases_can_be_inspected_without_resolving_expressions(self):
        text = "on: push\njobs:\n  first: &job\n    runs-on: ubuntu-latest\n    steps: []\n  second: *job\n"
        assert len(inventory.inspect_workflow(text, "ci.yml")["jobs"]) == 2

    def test_symlinked_file_and_directory_are_not_read(self):
        tmp_path = self.root
        outside = tmp_path / "outside.yml"
        outside.write_text(source())
        folder = tmp_path / "repo" / ".github" / "workflows"
        folder.mkdir(parents=True)
        (folder / "ci.yml").symlink_to(outside)
        report = inventory.build_inventory(tmp_path / "repo")
        assert report["coverage"]["error_count"] == 1
        assert report["workflows"] == []
        other = tmp_path / "other"
        other.mkdir()
        (other / ".github").symlink_to(tmp_path / "repo" / ".github", target_is_directory=True)
        assert inventory.build_inventory(other)["coverage"]["error_count"] == 1

    def test_cli_only_prints_report_and_returns_nonzero_for_incomplete_input(self):
        tmp_path = self.root
        path = put(tmp_path, source())
        before = path.read_bytes()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            assert inventory.main(["--root", str(tmp_path)]) == 0
        report = json.loads(output.getvalue())
        assert report["mode"] == "report_only" and report["coverage"]["complete"]
        assert path.read_bytes() == before
        assert sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file()) == [".github/workflows/ci.yml"]
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            assert inventory.main(["--root", str(tmp_path / "missing")]) == 2
        assert not json.loads(output.getvalue())["coverage"]["complete"]


if __name__ == "__main__":
    unittest.main()

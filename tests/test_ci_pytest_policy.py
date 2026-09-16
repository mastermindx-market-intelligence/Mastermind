"""Fail-closed policy for discovery-first hosted CI.

A new ``tests/**/test_*.py`` module runs automatically. Exact reviewed exclusions
are the only way to omit a module, and they cannot remove constitutional tests
or resurrect a positive workflow filename allowlist.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent


def _load_runner():
    path = _ROOT / "scripts" / "ci_pytest.py"
    spec = importlib.util.spec_from_file_location("ci_pytest_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cip = _load_runner()


def _write_manifest(root: Path, rows: list[dict] | None = None) -> None:
    lines = ["version = 1", ""]
    for row in rows or []:
        lines.append("[[exclude]]")
        lines.append(f'path = "{row["path"]}"')
        if "reason" in row:
            lines.append(f'reason = "{row["reason"]}"')
        if "replacement_gate" in row:
            lines.append(f'replacement_gate = "{row["replacement_gate"]}"')
        lines.append("")
    (root / "ci").mkdir(parents=True, exist_ok=True)
    (root / "ci" / "pytest_exclusions.toml").write_text("\n".join(lines), encoding="utf-8")


def _write_test(root: Path, relative: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("def test_ok():\n    assert True\n", encoding="utf-8")


def _fake_repo(tmp_path: Path, modules: list[str], rows: list[dict] | None = None) -> Path:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'ci-policy-fixture'\n", encoding="utf-8")
    for relative in modules:
        _write_test(tmp_path, relative)
    _write_manifest(tmp_path, rows)
    return tmp_path


def _plan(root: Path):
    discovered = cip.discover_test_modules(root)
    excluded = cip.validate_exclusions(root, cip.load_exclusions(root), discovered)
    included = cip.included_modules(discovered, excluded)
    return discovered, excluded, included


def test_new_test_is_included_automatically(tmp_path):
    root = _fake_repo(
        tmp_path,
        ["tests/test_existing.py", "tests/test_brand_new_future_test.py"],
    )
    discovered, excluded, included = _plan(root)
    assert excluded == ()
    assert "tests/test_existing.py" in included
    assert "tests/test_brand_new_future_test.py" in included
    assert set(included) == set(discovered)


def test_exact_exclusion_omits_only_that_path(tmp_path):
    root = _fake_repo(
        tmp_path,
        ["tests/test_keep.py", "tests/test_host_only.py"],
        [
            {
                "path": "tests/test_host_only.py",
                "reason": "Requires root, launchd and dedicated macOS service UIDs.",
                "replacement_gate": "Phase 1C-A real-host acceptance",
            }
        ],
    )
    discovered, excluded, included = _plan(root)
    assert excluded == ("tests/test_host_only.py",)
    assert "tests/test_host_only.py" not in included
    assert "tests/test_keep.py" in included
    assert set(included) | set(excluded) == set(discovered)
    assert set(included) & set(excluded) == set()


@pytest.mark.parametrize(
    "path",
    [
        "tests/test_executive_*.py",
        "tests/**",
        "tests/",
        "tests",
    ],
)
def test_wildcard_and_directory_exclusions_are_rejected(tmp_path, path):
    root = _fake_repo(tmp_path, ["tests/test_keep.py"])
    rows = [
        {
            "path": path,
            "reason": "should not be accepted",
            "replacement_gate": "none",
        }
    ]
    with pytest.raises(cip.PolicyError, match="forbidden|must be under tests"):
        cip.validate_exclusions(root, rows, cip.discover_test_modules(root))


def test_stale_exclusion_is_rejected(tmp_path):
    root = _fake_repo(tmp_path, ["tests/test_keep.py"])
    rows = [
        {
            "path": "tests/test_missing.py",
            "reason": "file was deleted",
            "replacement_gate": "none",
        }
    ]
    with pytest.raises(cip.PolicyError, match="stale exclusion"):
        cip.validate_exclusions(root, rows, cip.discover_test_modules(root))


@pytest.mark.parametrize(
    "path",
    [
        "../something.py",
        "/vendor/macro/tests/test_x.py",
        "vendor/macro/tests/test_x.py",
    ],
)
def test_path_escape_is_rejected(tmp_path, path):
    root = _fake_repo(tmp_path, ["tests/test_keep.py"])
    rows = [
        {
            "path": path,
            "reason": "escape attempt",
            "replacement_gate": "none",
        }
    ]
    with pytest.raises(cip.PolicyError, match="forbidden|must be under tests"):
        cip.validate_exclusions(root, rows, cip.discover_test_modules(root))


def test_duplicate_exclusion_is_rejected(tmp_path):
    root = _fake_repo(tmp_path, ["tests/test_host_only.py"])
    row = {
        "path": "tests/test_host_only.py",
        "reason": "Requires root, launchd and dedicated macOS service UIDs.",
        "replacement_gate": "Phase 1C-A real-host acceptance",
    }
    with pytest.raises(cip.PolicyError, match="duplicate exclusion"):
        cip.validate_exclusions(root, [row, dict(row)], cip.discover_test_modules(root))


def test_empty_reason_is_rejected(tmp_path):
    root = _fake_repo(tmp_path, ["tests/test_host_only.py"])
    rows = [
        {
            "path": "tests/test_host_only.py",
            "reason": "",
            "replacement_gate": "Phase 1C-A real-host acceptance",
        }
    ]
    with pytest.raises(cip.PolicyError, match="reason cannot be empty"):
        cip.validate_exclusions(root, rows, cip.discover_test_modules(root))


def test_protected_executive_test_cannot_be_excluded(tmp_path):
    root = _fake_repo(tmp_path, ["tests/test_executive_os_runtime.py"])
    rows = [
        {
            "path": "tests/test_executive_os_runtime.py",
            "reason": "should not be accepted",
            "replacement_gate": "none",
        }
    ]
    with pytest.raises(cip.PolicyError, match="protected test cannot be excluded"):
        cip.validate_exclusions(root, rows, cip.discover_test_modules(root))


def test_self_exclusion_of_ci_policy_is_rejected(tmp_path):
    root = _fake_repo(tmp_path, ["tests/test_ci_pytest_policy.py"])
    rows = [
        {
            "path": "tests/test_ci_pytest_policy.py",
            "reason": "should not be accepted",
            "replacement_gate": "none",
        }
    ]
    with pytest.raises(cip.PolicyError, match="protected test cannot be excluded"):
        cip.validate_exclusions(root, rows, cip.discover_test_modules(root))


def test_workflow_must_call_discovery_runner_and_reject_allowlists():
    cip.validate_workflow((_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    with pytest.raises(cip.PolicyError, match="must invoke"):
        cip.validate_workflow("name: CI\njobs:\n  test:\n    steps: []\n")
    allowlist = """
name: CI
jobs:
  test:
    steps:
      - name: Run repository test gate
        run: |
          python scripts/ci_pytest.py
          tests/test_foo.py
          tests/test_bar.py
          tests/test_baz.py
"""
    with pytest.raises(cip.PolicyError, match="positive tests/test_"):
        cip.validate_workflow(allowlist)
    comments_only = """
on:
  pull_request:
  merge_group:
    types: [checks_requested]
  push:
    branches:
      - master
  workflow_dispatch:
name: CI
jobs:
  test:
    steps:
      - name: Run repository test gate
        run: python scripts/ci_pytest.py
# Historical note only:
# tests/test_foo.py
# tests/test_bar.py
# tests/test_baz.py
"""
    cip.validate_workflow(comments_only)


def _workflow_text(on_block: str) -> str:
    return (
        f"{on_block}\n"
        "name: CI\n"
        "jobs:\n"
        "  test:\n"
        "    steps:\n"
        "      - name: Run repository test gate\n"
        "        run: python scripts/ci_pytest.py\n"
    )


def _valid_on_block() -> str:
    return (
        "on:\n"
        "  pull_request:\n"
        "  merge_group:\n"
        "    types: [checks_requested]\n"
        "  push:\n"
        "    branches:\n"
        "      - master\n"
        "  workflow_dispatch:\n"
    )


def test_validate_workflow_accepts_exact_event_contract():
    cip.validate_workflow(_workflow_text(_valid_on_block()))


def test_validate_workflow_rejects_missing_on_key():
    text = (
        "name: CI\n"
        "jobs:\n"
        "  test:\n"
        "    steps:\n"
        "      - name: Run repository test gate\n"
        "        run: python scripts/ci_pytest.py\n"
    )
    with pytest.raises(cip.PolicyError, match="missing an 'on' trigger"):
        cip.validate_workflow(text)


@pytest.mark.parametrize(
    "on_block",
    [
        "on:\n",
        "on: push\n",
        "on:\n  - push\n  - pull_request\n",
    ],
)
def test_validate_workflow_rejects_malformed_on_shapes(on_block):
    with pytest.raises(cip.PolicyError, match="must be a mapping"):
        cip.validate_workflow(_workflow_text(on_block))


def test_validate_workflow_rejects_missing_event():
    on_block = (
        "on:\n"
        "  pull_request:\n"
        "  push:\n"
        "    branches:\n"
        "      - master\n"
        "  workflow_dispatch:\n"
    )
    with pytest.raises(cip.PolicyError, match="missing required event"):
        cip.validate_workflow(_workflow_text(on_block))


def test_validate_workflow_rejects_extra_event():
    on_block = _valid_on_block() + "  schedule:\n    - cron: '0 0 * * *'\n"
    with pytest.raises(cip.PolicyError, match="unexpected event"):
        cip.validate_workflow(_workflow_text(on_block))


def test_validate_workflow_unexpected_event_error_is_redacted():
    literal_secret = "ghp_should_not_leak_1234567890abcdef"
    # RFC 4648 SS10 base64 test vector (base64("foobar") == "Zm9vYmFy"),
    # used as an accurately-known encoded-shaped secret stand-in alongside
    # the literal-shaped one above, without hand-computing base64 for an
    # arbitrary string.
    encoded_form_secret = "Zm9vYmFy"
    on_block = (
        _valid_on_block()
        + f"  {literal_secret}:\n"
        + f"  {encoded_form_secret}:\n"
    )
    with pytest.raises(cip.PolicyError) as excinfo:
        cip.validate_workflow(_workflow_text(on_block))
    message = str(excinfo.value)
    assert message == "workflow 'on' has unexpected event(s)"
    assert literal_secret not in message
    assert encoded_form_secret not in message


def test_validate_workflow_rejects_wrong_merge_group_types():
    on_block = (
        "on:\n"
        "  pull_request:\n"
        "  merge_group:\n"
        "    types: [checks_requested, labeled]\n"
        "  push:\n"
        "    branches:\n"
        "      - master\n"
        "  workflow_dispatch:\n"
    )
    with pytest.raises(cip.PolicyError, match="merge_group"):
        cip.validate_workflow(_workflow_text(on_block))


def test_validate_workflow_rejects_wrong_push_branches():
    on_block = (
        "on:\n"
        "  pull_request:\n"
        "  merge_group:\n"
        "    types: [checks_requested]\n"
        "  push:\n"
        "    branches:\n"
        "      - main\n"
        "  workflow_dispatch:\n"
    )
    with pytest.raises(cip.PolicyError, match="push"):
        cip.validate_workflow(_workflow_text(on_block))


def test_validate_workflow_rejects_pull_request_with_filters():
    on_block = (
        "on:\n"
        "  pull_request:\n"
        "    types: [opened]\n"
        "  merge_group:\n"
        "    types: [checks_requested]\n"
        "  push:\n"
        "    branches:\n"
        "      - master\n"
        "  workflow_dispatch:\n"
    )
    with pytest.raises(cip.PolicyError, match="pull_request"):
        cip.validate_workflow(_workflow_text(on_block))


def test_validate_workflow_rejects_missing_pull_request():
    on_block = (
        "on:\n"
        "  merge_group:\n"
        "    types: [checks_requested]\n"
        "  push:\n"
        "    branches:\n"
        "      - master\n"
        "  workflow_dispatch:\n"
    )
    with pytest.raises(cip.PolicyError, match="missing required event"):
        cip.validate_workflow(_workflow_text(on_block))


def test_validate_workflow_rejects_empty_merge_group():
    on_block = (
        "on:\n"
        "  pull_request:\n"
        "  merge_group: {}\n"
        "  push:\n"
        "    branches:\n"
        "      - master\n"
        "  workflow_dispatch:\n"
    )
    with pytest.raises(cip.PolicyError, match="merge_group"):
        cip.validate_workflow(_workflow_text(on_block))


def test_validate_workflow_rejects_filtered_workflow_dispatch():
    on_block = (
        "on:\n"
        "  pull_request:\n"
        "  merge_group:\n"
        "    types: [checks_requested]\n"
        "  push:\n"
        "    branches:\n"
        "      - master\n"
        "  workflow_dispatch:\n"
        "    inputs:\n"
        "      reason:\n"
        "        required: false\n"
        "        type: string\n"
    )
    with pytest.raises(cip.PolicyError, match="workflow_dispatch"):
        cip.validate_workflow(_workflow_text(on_block))


@pytest.mark.parametrize("keyword", ["On", "ON", "oN"])
def test_validate_workflow_rejects_cased_on_key_variant(keyword):
    on_block = _valid_on_block().replace("on:", f"{keyword}:", 1)
    with pytest.raises(cip.PolicyError, match="literal lowercase 'on'"):
        cip.validate_workflow(_workflow_text(on_block))


@pytest.mark.parametrize("on_key_spelling", ["on", "'on'", '"on"'])
def test_validate_workflow_accepts_lowercase_on_key_spellings(on_key_spelling):
    # Permanent coverage that the literal lowercase "on" key is accepted
    # regardless of quoting style: unquoted, single-quoted, and
    # double-quoted forms all construct to the identical Python string
    # "on" and must all be treated as the valid trigger key.
    on_block = _valid_on_block().replace("on:", f"{on_key_spelling}:", 1)
    cip.validate_workflow(_workflow_text(on_block))


def test_validate_workflow_rejects_merge_key_in_on_block():
    # Permanent regression guard: _reject_duplicate_mapping_keys replaces
    # PyYAML's default map constructor entirely, which also replaces the
    # default merge-key (`<<`) flattening behavior it would otherwise
    # perform. A `<<: *anchor` entry inside `on:` must never be silently
    # expanded (which would let an event get injected without appearing as
    # a literal key anyone reviewing the file would see) - it must fail
    # closed instead. The exact internal classification (generic YAML
    # error vs. unhashable-key error) is not asserted here since it
    # depends on unexecuted PyYAML internals; only the fail-closed
    # PolicyError outcome is asserted.
    text = (
        "name: CI\n"
        "hidden_defaults: &hidden_defaults\n"
        "  schedule:\n"
        "    - cron: '0 0 * * *'\n"
        "on:\n"
        "  <<: *hidden_defaults\n"
        "  pull_request:\n"
        "  merge_group:\n"
        "    types: [checks_requested]\n"
        "  push:\n"
        "    branches:\n"
        "      - master\n"
        "  workflow_dispatch:\n"
        "jobs:\n"
        "  test:\n"
        "    steps:\n"
        "      - name: Run repository test gate\n"
        "        run: python scripts/ci_pytest.py\n"
    )
    with pytest.raises(cip.PolicyError):
        cip.validate_workflow(text)


def test_validate_workflow_duplicate_key_cause_chain_is_redacted():
    sentinel = "DUPLICATE_KEY_SENTINEL_9f3ac21"
    text = (
        "name: CI\n"
        f"{sentinel}: first\n"
        f"{sentinel}: second\n"
        + _valid_on_block()
        + "jobs:\n"
        "  test:\n"
        "    steps:\n"
        "      - name: Run repository test gate\n"
        "        run: python scripts/ci_pytest.py\n"
    )
    with pytest.raises(cip.PolicyError) as excinfo:
        cip.validate_workflow(text)
    assert str(excinfo.value) == "workflow YAML contains a duplicate mapping key"
    assert sentinel not in str(excinfo.value)
    cause = excinfo.value.__cause__
    assert cause is not None
    assert sentinel not in str(cause)


def test_validate_workflow_unhashable_key_cause_chain_is_redacted():
    sentinel = "UNHASHABLE_KEY_SENTINEL_7be04d9"
    text = (
        "name: CI\n"
        f"? [{sentinel}, other]\n"
        ": value\n"
        + _valid_on_block()
        + "jobs:\n"
        "  test:\n"
        "    steps:\n"
        "      - name: Run repository test gate\n"
        "        run: python scripts/ci_pytest.py\n"
    )
    with pytest.raises(cip.PolicyError) as excinfo:
        cip.validate_workflow(text)
    assert str(excinfo.value) == "workflow YAML contains an unhashable mapping key"
    assert sentinel not in str(excinfo.value)
    cause = excinfo.value.__cause__
    assert cause is not None
    assert sentinel not in str(cause)


def test_validate_workflow_rejects_duplicate_unquoted_on():
    text = (
        "name: CI\n"
        "on:\n"
        "  pull_request:\n"
        "on:\n"
        "  merge_group:\n"
        "    types: [checks_requested]\n"
        "  push:\n"
        "    branches:\n"
        "      - master\n"
        "  workflow_dispatch:\n"
        "jobs:\n"
        "  test:\n"
        "    steps:\n"
        "      - name: Run repository test gate\n"
        "        run: python scripts/ci_pytest.py\n"
    )
    with pytest.raises(cip.PolicyError, match="duplicate"):
        cip.validate_workflow(text)


def test_validate_workflow_rejects_duplicate_quoted_on():
    text = (
        "name: CI\n"
        '"on":\n'
        "  pull_request:\n"
        '"on":\n'
        "  merge_group:\n"
        "    types: [checks_requested]\n"
        "  push:\n"
        "    branches:\n"
        "      - master\n"
        "  workflow_dispatch:\n"
        "jobs:\n"
        "  test:\n"
        "    steps:\n"
        "      - name: Run repository test gate\n"
        "        run: python scripts/ci_pytest.py\n"
    )
    with pytest.raises(cip.PolicyError, match="duplicate"):
        cip.validate_workflow(text)


def test_validate_workflow_rejects_quoted_and_unquoted_on():
    text = (
        "name: CI\n"
        '"on":\n'
        "  pull_request:\n"
        "on:\n"
        "  merge_group:\n"
        "    types: [checks_requested]\n"
        "  push:\n"
        "    branches:\n"
        "      - master\n"
        "  workflow_dispatch:\n"
        "jobs:\n"
        "  test:\n"
        "    steps:\n"
        "      - name: Run repository test gate\n"
        "        run: python scripts/ci_pytest.py\n"
    )
    with pytest.raises(cip.PolicyError, match="duplicate"):
        cip.validate_workflow(text)


def test_validate_workflow_loader_keeps_true_false_but_not_on_off_yes_no():
    import yaml

    text = (
        "name: CI\n"
        + _valid_on_block()
        + "jobs:\n"
        "  test:\n"
        "    flag_true: true\n"
        "    flag_false: false\n"
        "    literal_on: on\n"
        "    literal_off: off\n"
        "    literal_yes: yes\n"
        "    literal_no: no\n"
        "    steps:\n"
        "      - name: Run repository test gate\n"
        "        run: python scripts/ci_pytest.py\n"
    )
    cip.validate_workflow(text)
    payload = yaml.load(text, Loader=cip._WorkflowYAMLLoader)
    job = payload["jobs"]["test"]
    assert job["flag_true"] is True
    assert job["flag_false"] is False
    assert job["literal_on"] == "on"
    assert job["literal_off"] == "off"
    assert job["literal_yes"] == "yes"
    assert job["literal_no"] == "no"


@pytest.mark.parametrize("keyword", ["On", "ON", "oN"])
def test_validate_workflow_rejects_on_alongside_case_variant(keyword):
    text = (
        "name: CI\n"
        + _valid_on_block()
        + f"{keyword}:\n"
        "  schedule:\n"
        "    - cron: '0 0 * * *'\n"
        "jobs:\n"
        "  test:\n"
        "    steps:\n"
        "      - name: Run repository test gate\n"
        "        run: python scripts/ci_pytest.py\n"
    )
    with pytest.raises(cip.PolicyError, match="literal lowercase 'on'"):
        cip.validate_workflow(text)


def test_validate_workflow_rejects_unhashable_event_level_key():
    on_block = (
        "on:\n"
        "  pull_request:\n"
        "  merge_group:\n"
        "    types: [checks_requested]\n"
        "  push:\n"
        "    branches:\n"
        "      - master\n"
        "  workflow_dispatch:\n"
        "  ? [a, b]\n"
        "  : nested\n"
    )
    with pytest.raises(cip.PolicyError, match="unhashable"):
        cip.validate_workflow(_workflow_text(on_block))


def test_validate_workflow_rejects_unhashable_mapping_key():
    text = (
        "name: CI\n"
        "? [1, 2]\n"
        ": three\n"
        + _valid_on_block()
        + "jobs:\n"
        "  test:\n"
        "    steps:\n"
        "      - name: Run repository test gate\n"
        "        run: python scripts/ci_pytest.py\n"
    )
    with pytest.raises(cip.PolicyError, match="unhashable"):
        cip.validate_workflow(text)


def test_validate_workflow_reports_unrecognized_tag_as_generic_not_duplicate():
    # Regression fixture for the R3 version of this test: it replaced the
    # entire `jobs:` value with the bad-tag node, so the raw text no longer
    # contained the authoritative runner/step-name substrings and
    # validate_workflow raised its "must invoke" error before ever parsing
    # YAML - never exercising the tag-error path at all. Keep a fully valid
    # workflow/runner body and add the unsupported tag as an unrelated
    # extra field instead.
    text = (
        "name: CI\n"
        + _valid_on_block()
        + "extra: !!python/object:builtins.object {}\n"
        "jobs:\n"
        "  test:\n"
        "    steps:\n"
        "      - name: Run repository test gate\n"
        "        run: python scripts/ci_pytest.py\n"
    )
    with pytest.raises(cip.PolicyError, match="not valid YAML"):
        cip.validate_workflow(text)


def test_validate_workflow_rejects_literal_boolean_key_as_on_alias():
    text = (
        "name: CI\n"
        "true:\n"
        "  push:\n"
        "    branches:\n"
        "      - master\n"
        "jobs:\n"
        "  test:\n"
        "    steps:\n"
        "      - name: Run repository test gate\n"
        "        run: python scripts/ci_pytest.py\n"
    )
    with pytest.raises(cip.PolicyError, match="must be strings"):
        cip.validate_workflow(text)


def test_validate_workflow_rejects_boolean_scalar_on_value():
    text = _workflow_text("on: true\n")
    with pytest.raises(cip.PolicyError, match="must be a mapping"):
        cip.validate_workflow(text)


def test_validate_workflow_rejects_numeric_top_level_key():
    text = (
        "name: CI\n"
        + _valid_on_block()
        + "404: not-a-real-field\n"
        "jobs:\n"
        "  test:\n"
        "    steps:\n"
        "      - name: Run repository test gate\n"
        "        run: python scripts/ci_pytest.py\n"
    )
    with pytest.raises(cip.PolicyError, match="must be strings"):
        cip.validate_workflow(text)


def test_validate_workflow_non_string_key_error_is_redacted():
    secret_like_value = "super-secret-token-should-not-leak"
    text = (
        "name: CI\n"
        + _valid_on_block()
        + f"12345: {secret_like_value}\n"
        "jobs:\n"
        "  test:\n"
        "    steps:\n"
        "      - name: Run repository test gate\n"
        "        run: python scripts/ci_pytest.py\n"
    )
    with pytest.raises(cip.PolicyError) as excinfo:
        cip.validate_workflow(text)
    message = str(excinfo.value)
    assert message == "workflow top-level keys must be strings"
    assert "12345" not in message
    assert secret_like_value not in message


def test_validate_workflow_rejects_decoded_binary_top_level_key_without_leaking():
    # RFC 4648 SS10 base64 test vector: base64("foobar") == "Zm9vYmFy".
    # !!binary decodes to bytes (hashable, non-str), so this exercises a
    # top-level-key type distinct from the int/bool cases above, while
    # letting both the decoded and encoded forms be asserted accurately
    # without executing code to compute them.
    encoded = "Zm9vYmFy"
    decoded = "foobar"
    text = (
        "name: CI\n"
        f"? !!binary {encoded}\n"
        ": some-value\n"
        + _valid_on_block()
        + "jobs:\n"
        "  test:\n"
        "    steps:\n"
        "      - name: Run repository test gate\n"
        "        run: python scripts/ci_pytest.py\n"
    )
    with pytest.raises(cip.PolicyError) as excinfo:
        cip.validate_workflow(text)
    message = str(excinfo.value)
    assert message == "workflow top-level keys must be strings"
    assert decoded not in message
    assert encoded not in message


def test_validate_workflow_rejects_explicit_bool_tag_on_key():
    text = (
        "name: CI\n"
        "!!bool on:\n"
        "  push:\n"
        "    branches:\n"
        "      - master\n"
        "jobs:\n"
        "  test:\n"
        "    steps:\n"
        "      - name: Run repository test gate\n"
        "        run: python scripts/ci_pytest.py\n"
    )
    with pytest.raises(cip.PolicyError, match="must be strings"):
        cip.validate_workflow(text)


def test_validate_workflow_rejects_valid_on_alongside_explicit_bool_tag_on():
    text = (
        "name: CI\n"
        + _valid_on_block()
        + "!!bool on:\n"
        "  schedule:\n"
        "    - cron: '0 0 * * *'\n"
        "jobs:\n"
        "  test:\n"
        "    steps:\n"
        "      - name: Run repository test gate\n"
        "        run: python scripts/ci_pytest.py\n"
    )
    with pytest.raises(cip.PolicyError, match="must be strings"):
        cip.validate_workflow(text)


def test_validate_workflow_rejects_valid_on_alongside_bareword_true():
    text = (
        "name: CI\n"
        + _valid_on_block()
        + "true:\n"
        "  schedule:\n"
        "    - cron: '0 0 * * *'\n"
        "jobs:\n"
        "  test:\n"
        "    steps:\n"
        "      - name: Run repository test gate\n"
        "        run: python scripts/ci_pytest.py\n"
    )
    with pytest.raises(cip.PolicyError, match="must be strings"):
        cip.validate_workflow(text)


def test_validate_workflow_rejects_mixed_type_extra_keys():
    on_block = (
        "on:\n"
        "  pull_request:\n"
        "  merge_group:\n"
        "    types: [checks_requested]\n"
        "  push:\n"
        "    branches:\n"
        "      - master\n"
        "  workflow_dispatch:\n"
        "  123: {}\n"
    )
    with pytest.raises(cip.PolicyError, match="event name strings"):
        cip.validate_workflow(_workflow_text(on_block))


def test_all_discovered_tests_are_accounted_for():
    gate = cip.resolve_gate(_ROOT)
    discovered = set(gate["discovered"])
    excluded = set(gate["excluded"])
    included = set(gate["included"])
    independent = {
        path.relative_to(_ROOT).as_posix()
        for path in (_ROOT / "tests").rglob("test_*.py")
        if path.is_file()
    }
    assert discovered == independent
    assert included | excluded == discovered
    assert included & excluded == set()
    assert discovered
    assert included
    argv = cip.pytest_argv(gate["included"])
    assert argv[:4] == [cip.sys.executable, "-m", "pytest", "-q"]
    assert argv[4:] == list(gate["included"])


def test_hosted_full_gate_has_a_bounded_completion_window():
    """PR544 reached 98% when its old 25-minute job ceiling cancelled the gate."""
    import yaml

    workflow = yaml.safe_load(
        (_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    job = workflow["jobs"]["test"]
    assert job["timeout-minutes"] == 40
    assert workflow["permissions"] == {"contents": "read"}
    assert job.get("continue-on-error", False) is False
    gate_steps = [step for step in job["steps"]
                  if step.get("name") == "Run repository test gate"]
    assert len(gate_steps) == 1
    # The gate is still one job producing the single required check `test`
    # (branch protection on master requires exactly that context, with
    # enforce_admins true). `--jobs` shards inside the job; it is the only
    # argument the hosted gate may carry, and its value must be a positive
    # integer the runner can actually run in parallel.
    command = gate_steps[0]["run"].split()
    assert command[:2] == ["python", "scripts/ci_pytest.py"]
    assert command[2:3] == ["--jobs"], "the hosted gate takes no other argument"
    assert command[3].isdigit() and int(command[3]) >= 1
    assert len(command) == 4
    assert all(step.get("continue-on-error", False) is False for step in job["steps"])


def test_hosted_gate_stays_a_single_required_check_job():
    """A matrix here would rename the check to `test (0)`..., which branch
    protection on master (required context `test`, enforce_admins true) would
    never see satisfied -- blocking every merge. Parallelism must stay inside
    the job."""
    import yaml

    workflow = yaml.safe_load(
        (_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    assert list(workflow["jobs"]) == ["test"]
    job = workflow["jobs"]["test"]
    assert "strategy" not in job, "a matrix would rename the required check"
    assert job["runs-on"] == "ubuntu-latest"


# --- `--jobs` sharding: placement only, never a coverage reduction -----------
#
# The gate may split its resolved module set across concurrent pytest
# processes to cut wall-clock. The safety property under test is that the
# split can never quietly shrink what runs: every shard plan must be a
# total, disjoint cover of exactly the set the discovery/exclusion policy
# already produced, and any shard failing must fail the gate.


@pytest.mark.parametrize("jobs", [2, 3, 4, 5, 8])
def test_shard_plan_is_a_total_disjoint_cover(jobs):
    included = tuple(f"tests/test_m{index:03d}.py" for index in range(37))
    shards = cip.partition_modules(included, jobs=jobs)
    assert len(shards) == jobs
    flattened = [path for shard in shards for path in shard]
    assert sorted(flattened) == sorted(included)
    assert len(flattened) == len(set(flattened))


def test_real_shard_plan_stays_reasonably_balanced():
    # Hash assignment trades exact evenness for stability, so pin the real
    # repository's actual spread rather than an idealised one.
    gate = cip.resolve_gate(_ROOT)
    sizes = [len(shard) for shard in cip.partition_modules(gate["included"], jobs=4)]
    assert min(sizes) >= 0.75 * (len(gate["included"]) / 4)
    assert max(sizes) <= 1.25 * (len(gate["included"]) / 4)


def test_shard_plan_is_deterministic_across_processes():
    """sha256, never the salted builtin `hash()`.

    A per-process salt would shard the same checkout differently on every run,
    so a shard-specific failure could not be reproduced. Pin an exact expected
    assignment: this fails if the hash function or its input ever changes.
    """
    included = tuple(f"tests/test_m{index:03d}.py" for index in range(20))
    first = cip.partition_modules(included, jobs=4)
    assert first == cip.partition_modules(included, jobs=4)

    import hashlib

    expected: list[list[str]] = [[] for _ in range(4)]
    for path in included:
        digest = hashlib.sha256(path.encode("utf-8")).digest()
        expected[int.from_bytes(digest[:8], "big") % 4].append(path)
    assert first == tuple(tuple(bucket) for bucket in expected)


def test_adding_a_module_does_not_move_the_others():
    """The stability property that motivated hashing over round-robin.

    Sharding changes which modules share a pytest process, so a reshuffle can
    surface a latent cross-module ordering dependency. Round-robin moved every
    module after an insertion; hashing moves only the inserted one, keeping
    that blast radius on the PR that actually caused it.
    """
    before = tuple(f"tests/test_m{index:03d}.py" for index in range(40))
    after = tuple(sorted(before + ("tests/test_aaa_brand_new.py",)))
    placement_before = {
        path: index
        for index, shard in enumerate(cip.partition_modules(before, jobs=4))
        for path in shard
    }
    placement_after = {
        path: index
        for index, shard in enumerate(cip.partition_modules(after, jobs=4))
        for path in shard
    }
    moved = [p for p in before if placement_before[p] != placement_after[p]]
    assert moved == []


def test_single_job_shard_plan_is_the_whole_included_set():
    included = ("tests/test_a.py", "tests/test_b.py", "tests/test_c.py")
    assert cip.partition_modules(included, jobs=1) == (included,)


@pytest.mark.parametrize("jobs", [0, -1, -9])
def test_non_positive_job_count_is_rejected(jobs):
    with pytest.raises(cip.PolicyError, match="at least 1"):
        cip.partition_modules(("tests/test_a.py",), jobs=jobs)


def test_job_count_above_module_count_is_rejected():
    with pytest.raises(cip.PolicyError, match="cannot exceed"):
        cip.partition_modules(("tests/test_a.py", "tests/test_b.py"), jobs=3)


def test_dropped_module_in_a_shard_plan_is_rejected():
    included = ("tests/test_a.py", "tests/test_b.py", "tests/test_c.py")
    with pytest.raises(cip.PolicyError, match="resolved"):
        cip.verify_partition(included, (("tests/test_a.py",), ("tests/test_b.py",)))


def test_duplicated_module_hiding_a_dropped_one_is_rejected():
    # Same total count as `included`, so a length-only check would pass.
    included = ("tests/test_a.py", "tests/test_b.py", "tests/test_c.py")
    with pytest.raises(cip.PolicyError, match="exact cover"):
        cip.verify_partition(
            included, (("tests/test_a.py", "tests/test_a.py"), ("tests/test_b.py",))
        )


def test_substituted_module_in_a_shard_plan_is_rejected():
    included = ("tests/test_a.py", "tests/test_b.py")
    with pytest.raises(cip.PolicyError, match="exact cover"):
        cip.verify_partition(included, (("tests/test_a.py",), ("tests/test_zz.py",)))


def test_empty_shard_is_rejected():
    included = ("tests/test_a.py", "tests/test_b.py")
    with pytest.raises(cip.PolicyError, match="empty shard"):
        cip.verify_partition(included, (("tests/test_a.py", "tests/test_b.py"), ()))


def test_plan_line_reports_shard_sizes_and_default_omits_them():
    plan = {"discovered": 9, "excluded": 0, "running": 9}
    assert cip.format_plan(plan) == "discovered=9 excluded=0 running=9"
    shards = cip.partition_modules(
        tuple(f"tests/test_m{index}.py" for index in range(9)), jobs=3
    )
    rendered = cip.format_plan(plan, shards=shards)
    assert "jobs=3" in rendered
    # Sizes are whatever the hash produced; what the plan line must prove is
    # that the printed per-shard counts still add up to `running`.
    sizes = rendered.split("shard_modules=")[1].split()[0]
    assert len(sizes.split(",")) == 3
    assert sum(int(size) for size in sizes.split(",")) == plan["running"]


def test_sharded_gate_runs_every_resolved_module_once(tmp_path, monkeypatch):
    included = tuple(f"tests/test_m{index}.py" for index in range(10))
    shards = cip.partition_modules(included, jobs=3)
    seen: list[str] = []

    def fake_run(argv, cwd=None, check=False, capture_output=False, text=False):
        seen.extend(argv[argv.index("-q") + 1 :])
        return _Completed(0, "")

    monkeypatch.setattr(cip.subprocess, "run", fake_run)
    assert cip.run_shards(shards, root=tmp_path) == 0
    assert sorted(seen) == sorted(included)


class _Completed:
    def __init__(self, returncode: int, stdout: str) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = ""


def test_one_failing_shard_fails_the_whole_gate(tmp_path, monkeypatch):
    shards = (("tests/test_a.py",), ("tests/test_b.py",), ("tests/test_c.py",))

    def fake_run(argv, cwd=None, check=False, capture_output=False, text=False):
        failing = "tests/test_b.py" in argv
        return _Completed(1 if failing else 0, "boom" if failing else "ok")

    monkeypatch.setattr(cip.subprocess, "run", fake_run)
    assert cip.run_shards(shards, root=tmp_path) != 0


def test_every_shard_runs_even_after_an_earlier_one_fails(tmp_path, monkeypatch):
    shards = (("tests/test_a.py",), ("tests/test_b.py",), ("tests/test_c.py",))
    ran: list[str] = []

    def fake_run(argv, cwd=None, check=False, capture_output=False, text=False):
        module = argv[-1]
        ran.append(module)
        return _Completed(1 if module == "tests/test_a.py" else 0, "")

    monkeypatch.setattr(cip.subprocess, "run", fake_run)
    cip.run_shards(shards, root=tmp_path)
    assert sorted(ran) == ["tests/test_a.py", "tests/test_b.py", "tests/test_c.py"]


def test_shard_output_is_reported_under_an_attributable_banner(tmp_path, monkeypatch, capsys):
    shards = (("tests/test_a.py",), ("tests/test_b.py",))

    def fake_run(argv, cwd=None, check=False, capture_output=False, text=False):
        return _Completed(0, f"result for {argv[-1]}")

    monkeypatch.setattr(cip.subprocess, "run", fake_run)
    cip.run_shards(shards, root=tmp_path)
    out = capsys.readouterr().out
    assert "shard 1/2" in out and "shard 2/2" in out
    assert "result for tests/test_a.py" in out
    assert "result for tests/test_b.py" in out


def test_real_repository_shard_plan_covers_the_real_gate():
    gate = cip.resolve_gate(_ROOT)
    shards = cip.partition_modules(gate["included"], jobs=4)
    flattened = [path for shard in shards for path in shard]
    assert sorted(flattened) == sorted(gate["included"])
    assert len(flattened) == len(set(flattened))


def test_exit_code_is_the_lowest_failing_shard_not_the_first_to_finish(
    tmp_path, monkeypatch
):
    # Shard 0 fails slowly with 3; shard 2 fails quickly with 4. The reported
    # code must be shard 0's, so reruns of the same failure report the same
    # code regardless of scheduling.
    import time

    shards = (("tests/test_a.py",), ("tests/test_b.py",), ("tests/test_c.py",))

    def fake_run(argv, cwd=None, check=False, capture_output=False, text=False):
        module = argv[-1]
        if module == "tests/test_a.py":
            time.sleep(0.15)
            return _Completed(3, "slow failure")
        if module == "tests/test_c.py":
            return _Completed(4, "fast failure")
        return _Completed(0, "")

    monkeypatch.setattr(cip.subprocess, "run", fake_run)
    assert cip.run_shards(shards, root=tmp_path) == 3

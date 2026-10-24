"""Task-context consumer tests; no provider calls, native enrollment or runtime writes."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from scripts import ceo_boot_packet as cli

WS = "WS:EXECUTIVE-CAPACITY-FABRIC"
NOW = "2026-10-06T22:00:00Z"


@pytest.fixture(autouse=True)
def observed_fixture_source(monkeypatch):
    # Synthetic compiler roots are not Git workspaces. Existing source-pin tests
    # override this observation and still exercise both before/after joins.
    monkeypatch.setattr(cli, "git_sha", lambda root: "a" * 40)


def bundle():
    return {
        "schema": "context_bundle.v1",
        "target": {"workstream": WS, "task": None, "resolution": "explicit",
                   "candidates": [], "wait": None},
        "generated_at": NOW, "repo_sha": "a" * 40,
        "source_records_digest": "sha256:" + "b" * 64,
        "token_budget": 4000, "token_estimate": 4500,
        "sections": [{"name": "workstream_block", "items": [
            {"kind": "constraint", "excerpt": "DO_NOT_REDO: accepted phase A",
             "path": "agentos/workstreams/WS-EXECUTIVE-CAPACITY-FABRIC.md"}]}],
        "excluded": [{"path": "old.md", "reason": "superseded"}],
        "omitted_due_to_budget": [{"path": "large.md", "reason": "budget"}],
        "degraded": ["an attributed sibling citation is missing"],
        "no_answer_reason": None,
        "future_owner_field": {"preserve": "not consumer-owned"},
    }


def make_macro(tmp_path, *, payload=None, raw=None, code=0, body=None):
    root = tmp_path / "macro with spaces"
    (root / "scripts").mkdir(parents=True)
    (root / "agentos").mkdir()
    source = (
        "import json, sys\n"
        "from pathlib import Path\n"
        "args = sys.argv[1:]\n"
        "assert args[:2] == ['compile-context', '--workstream'], args\n"
        "assert args[2] == 'EXECUTIVE-CAPACITY-FABRIC', args\n"
        "assert args[3:6] == ['--json', '--budget', '4000'], args\n"
        "assert args[6:] in ([], ['--now', '2026-10-06T22:00:00Z']), args\n"
    )
    if body is None:
        output = raw if raw is not None else json.dumps(payload if payload is not None else bundle())
        body = f"sys.stdout.write({output!r})\nsys.exit({code})\n"
    (root / "scripts" / "agentos.py").write_text(source + body, encoding="utf-8")
    return root


def args(root, *extra):
    return ["--workstream", WS, "--macro-root", str(root),
            "--expected-macro-sha", "a" * 40, "--timeout", "5", *extra]


def snapshot(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


def test_context_is_canonical_owner_payload_not_global_brief(tmp_path, capsys, monkeypatch):
    root = make_macro(tmp_path)
    monkeypatch.setattr(cli, "build_packet", lambda **kw: pytest.fail("global brief invoked"))
    before = snapshot(root)
    assert cli.main(args(root, "--now", NOW)) == 0
    assert json.loads(capsys.readouterr().out) == bundle()
    assert snapshot(root) == before


def test_repeat_is_identical_and_never_creates_memory_marker(tmp_path, capsys):
    root = make_macro(tmp_path)
    assert cli.main(args(root, "--now", NOW)) == 0
    first = capsys.readouterr().out
    assert cli.main(args(root, "--now", NOW)) == 0
    assert capsys.readouterr().out == first
    assert not (root / "data").exists()


def test_bare_workstream_key_and_json_flag_are_supported(tmp_path, capsys):
    root = make_macro(tmp_path)
    argv = args(root, "--json")
    argv[1] = WS.removeprefix("WS:")
    assert cli.main(argv) == 0
    assert json.loads(capsys.readouterr().out)["target"]["workstream"] == WS


@pytest.mark.parametrize("change", [
    {"schema": "other.v1"}, {"target": {"workstream": "WS:OTHER"}},
    {"target": None}, {"sections": "truncated"}, {"degraded": None},
    {"excluded": {}}, {"omitted_due_to_budget": "omitted"},
])
def test_wrong_or_incomplete_owner_payload_is_not_emitted(tmp_path, capsys, change):
    payload = bundle()
    payload.update(change)
    root = make_macro(tmp_path, payload=payload)
    assert cli.main(args(root)) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "context" in output.err.lower()


@pytest.mark.parametrize("raw", ["not json", "[]", '{"schema":"context_bundle.v1","schema":"other"}', "NaN"])
def test_ambiguous_or_invalid_json_never_masquerades_as_context(tmp_path, capsys, raw):
    root = make_macro(tmp_path, raw=raw)
    assert cli.main(args(root)) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err


def test_unknown_workstream_failure_never_falls_back_or_leaks_process_output(tmp_path, capsys):
    root = make_macro(tmp_path, raw="upstream-private-diagnostic", code=1)
    assert cli.main(args(root)) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "upstream-private-diagnostic" not in output.err
    assert "exit 1" in output.err


def test_missing_explicit_root_is_context_failure_not_global_orientation(tmp_path, capsys):
    assert cli.main(args(tmp_path / "missing")) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "Macro" in output.err


def test_timeout_settles_reader_and_emits_no_partial_context(tmp_path, capsys):
    root = make_macro(tmp_path, body="import time\nprint('partial', flush=True)\ntime.sleep(10)\n")
    argv = args(root)
    argv[-1] = "0.05"
    assert cli.main(argv) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "timed out" in output.err


def test_output_ceiling_refuses_instead_of_clipping_constraints(tmp_path, capsys):
    root = make_macro(tmp_path, body="sys.stdout.write('x' * (2 * 1024 * 1024))\n")
    assert cli.main(args(root)) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "limit" in output.err


def test_invalid_utf8_is_not_emitted(tmp_path, capsys):
    root = make_macro(tmp_path, body="sys.stdout.buffer.write(b'\\xff')\n")
    assert cli.main(args(root)) == 1
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("extra", [["--since", "24h"], ["--context-budget", "0"],
                                    ["--timeout", "nan"], ["--timeout", "-1"]])
def test_invalid_context_options_are_rejected_before_reader(tmp_path, extra):
    with pytest.raises(SystemExit) as error:
        cli.main(args(tmp_path / "missing", *extra))
    assert error.value.code == 2


def test_context_budget_requires_explicit_workstream():
    with pytest.raises(SystemExit) as error:
        cli.main(["--context-budget", "4000"])
    assert error.value.code == 2


def test_unknown_context_answer_is_preserved_not_promoted_to_admission(tmp_path, capsys):
    payload = bundle()
    payload["no_answer_reason"] = "Canonical owner could not answer this assignment."
    root = make_macro(tmp_path, payload=payload)
    assert cli.main(args(root)) == 0
    assert json.loads(capsys.readouterr().out) == payload


def test_legacy_packet_mode_stays_exactly_unchanged(monkeypatch, capsys):
    expected = {"schema": "mastermind.ceo_boot_packet.v1", "degraded": ["missing Macro"]}
    monkeypatch.setattr(cli, "build_packet", lambda **kw: copy.deepcopy(expected))
    assert cli.main(["--json"]) == 0
    assert json.loads(capsys.readouterr().out) == expected


@pytest.mark.parametrize("observed", [None, "c" * 40])
def test_expected_source_pin_refuses_before_compiler(tmp_path, capsys, monkeypatch, observed):
    root = make_macro(tmp_path)
    monkeypatch.setattr(cli, "git_sha", lambda root: observed, raising=False)
    monkeypatch.setattr(cli, "bounded_subprocess_runner", lambda *a, **kw: pytest.fail("reader started"))
    assert cli.main(args(root, "--expected-macro-sha", "a" * 40)) == 1
    assert capsys.readouterr().out == ""


def test_expected_source_pin_is_joined_before_and_after_read(tmp_path, capsys, monkeypatch):
    root = make_macro(tmp_path)
    samples = []
    def observe(path):
        samples.append(path)
        return "a" * 40
    monkeypatch.setattr(cli, "git_sha", observe, raising=False)
    assert cli.main(args(root, "--expected-macro-sha", "a" * 40)) == 0
    assert json.loads(capsys.readouterr().out) == bundle()
    assert samples == [root.resolve(), root.resolve()]


def test_source_moving_during_read_is_not_emitted(tmp_path, capsys, monkeypatch):
    root = make_macro(tmp_path)
    samples = iter(["a" * 40, "c" * 40])
    monkeypatch.setattr(cli, "git_sha", lambda path: next(samples), raising=False)
    assert cli.main(args(root, "--expected-macro-sha", "a" * 40)) == 1
    assert capsys.readouterr().out == ""


def test_claimed_bundle_source_must_match_expected_checkout(tmp_path, capsys, monkeypatch):
    payload = bundle()
    payload["repo_sha"] = "c" * 40
    root = make_macro(tmp_path, payload=payload)
    monkeypatch.setattr(cli, "git_sha", lambda path: "a" * 40, raising=False)
    assert cli.main(args(root, "--expected-macro-sha", "a" * 40)) == 1
    assert capsys.readouterr().out == ""


def test_source_pin_requires_workstream():
    with pytest.raises(SystemExit) as error:
        cli.main(["--expected-macro-sha", "a" * 40])
    assert error.value.code == 2


@pytest.mark.parametrize("pin", ["main", "A" * 40, "a" * 39])
def test_source_pin_is_an_exact_lowercase_sha(tmp_path, pin):
    with pytest.raises(SystemExit) as error:
        cli.main(args(tmp_path / "missing", "--expected-macro-sha", pin))
    assert error.value.code == 2


def test_imports_cannot_create_bytecode_in_the_macro_source(tmp_path, capsys):
    root = make_macro(tmp_path, body=f"import local_context_helper\nsys.stdout.write({json.dumps(bundle())!r})\n")
    (root / "scripts" / "local_context_helper.py").write_text("VALUE = 1\n", encoding="utf-8")
    before = snapshot(root)
    assert cli.main(args(root)) == 0
    capsys.readouterr()
    assert snapshot(root) == before


@pytest.mark.parametrize("source_options", [
    [], ["--expected-macro-sha", "a" * 40],
    ["--macro-root", "explicit-root"],
    ["--macro-root", "", "--expected-macro-sha", "a" * 40],
])
def test_scoped_context_requires_explicit_root_and_pin_before_discovery(
    monkeypatch, source_options
):
    calls = []
    monkeypatch.setattr(cli, "_workstream_context", lambda args: calls.append(args) or 0)
    with pytest.raises(SystemExit) as error:
        cli.main(["--workstream", WS, *source_options])
    assert error.value.code == 2
    assert calls == []


def test_usable_environment_cannot_substitute_for_explicit_assignment_root(
    tmp_path, monkeypatch, capsys
):
    root = make_macro(tmp_path)
    monkeypatch.setenv(cli.ENV_MACRO_ROOT, str(root))
    with pytest.raises(SystemExit) as error:
        cli.main(["--workstream", WS, "--expected-macro-sha", "a" * 40])
    assert error.value.code == 2
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("value", [
    "unknown", "b" * 64, "sha256:" + "B" * 64,
    "sha256:" + "b" * 63, "sha256:" + "b" * 65,
    "sha256:" + "b" * 64 + "\n", " sha256:" + "b" * 64,
    "", None, True,
])
def test_context_requires_canonical_source_record_digest(tmp_path, capsys, value):
    data = bundle()
    data["source_records_digest"] = value
    root = make_macro(tmp_path, payload=data)
    assert cli.main(args(root)) == 1
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("value", ["unknown", "a" * 39, "A" * 40, "a" * 40 + "\n"])
def test_context_rejects_noncanonical_git_provenance(tmp_path, capsys, value):
    data = bundle()
    data["repo_sha"] = value
    root = make_macro(tmp_path, payload=data)
    assert cli.main(args(root)) == 1
    assert capsys.readouterr().out == ""

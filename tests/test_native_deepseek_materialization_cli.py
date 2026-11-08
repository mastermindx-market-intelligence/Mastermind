"""Execute the installer's actual optional shell paths with inert artifact children."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
TEXT = (ROOT/"ops/executive_os/install.sh").read_text()
NATIVE_KEYS = ("NATIVE_PACKAGE", "NATIVE_NODE", "NATIVE_WORKER_CONFIG",
               "NATIVE_WORKER_CONFIG_SHA256")


def section(name):
    return TEXT.split("# --- BEGIN "+name+" ---\n", 1)[1].split("# --- END "+name+" ---", 1)[0]


@pytest.fixture
def invocation(tmp_path):
    root = tmp_path/"inputs with spaces"
    root.mkdir()
    calls = root/"observations.jsonl"
    runner = root/"qualified python"
    trampoline = f"#!/bin/sh\n'''exec' {shlex.quote(sys.executable)} \"$0\" \"$@\"\n' '''\n"
    runner.write_text(trampoline + '''
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
while args and args[0] in ("-I", "-S", "-B"): args.pop(0)
if args[0] == "-":
    os.execv(sys.executable, [sys.executable, "-I", "-S", "-B", *args])
kind = Path(args[0]).name
with open(os.environ["CALLS"], "a") as stream:
    stream.write(json.dumps({"kind": kind, "argv": args})+"\\n")
fail = os.environ["FAIL"]
if kind == "worker_acp_profile.py":
    if fail == "acp": raise SystemExit(65)
    print(json.dumps({"state": "ACP_MATERIALIZED", "effect_state": "APPLIED"}))
else:
    assert kind == "package_attended.py"
    if fail == "native-empty": raise SystemExit(70)
    if fail == "native-malformed":
        print("[]")
        raise SystemExit(70)
    if fail == "native-typed":
        print(json.dumps({"state": "EFFECT_UNKNOWN", "targets": {
            "node": {"effect_state": "APPLIED"},
            "package": {"effect_state": "EFFECT_UNKNOWN"}}}))
        raise SystemExit(70)
    print(json.dumps({"state": "UNSELECTED_MATERIALIZED", "effect_state": "APPLIED"}))
''')
    runner.chmod(0o755)
    env = {key:value for key,value in os.environ.items() if key not in NATIVE_KEYS}
    env.update(STAGE_RELEASE_ONLY="1", STAGE_ADMIN_CHECKOUT_ONLY="0",
        WORKER_ACP_BUNDLE="", WORKER_ACP_BUNDLE_DIGEST="b"*64,
        WORKER_ACP_DEPENDENCIES='{"state":"FORGED_AMBIENT_RESULT"}',
        PYTHON_BINARY=str(runner), SOURCE_REPO=str(root/'original source "quoted"'),
        RELEASE_ROOT=str(root/"sealed source release"), EXPECTED_SHA="a"*40,
        OPERATOR_UID=str(os.getuid()), CALLS=str(calls), FAIL="",
        NATIVE_PACKAGE=str(root/"complete native package"),
        NATIVE_NODE=str(root/"signed Node"),
        NATIVE_WORKER_CONFIG=str(root/'original Worker "config".json'),
        NATIVE_WORKER_CONFIG_SHA256="c"*64)
    script = ("set -euo pipefail\n"
        + 'stage_sealed_release() { printf \'{"kind":"stage"}\\n\' >> "$CALLS"; [ "$FAIL" != stage ]; }\n'
        + section("native package staging guard")
        + section("stage-only dispatch")
        + '\nprintf \'{"kind":"SERVICE_EFFECT_MUST_NOT_BE_REACHED"}\\n\' >> "$CALLS"\n')
    def run(**updates):
        current = {**env, **updates}
        result = subprocess.run(["/bin/bash", "-c", script], env=current,
                                capture_output=True, text=True)
        observed = [json.loads(row) for row in calls.read_text().splitlines()] if calls.exists() else []
        assert not any(row["kind"] == "SERVICE_EFFECT_MUST_NOT_BE_REACHED" for row in observed)
        return result, observed, current
    return run


@pytest.mark.parametrize("with_acp", [False, True])
def test_native_stage_composes_original_owners_with_exact_spaced_arguments(invocation, with_acp):
    result, calls, env = invocation(WORKER_ACP_BUNDLE="/original inputs/ACP bundle.zip" if with_acp else "")
    assert result.returncode == 0, result.stderr
    assert [row["kind"] for row in calls] == (
        ["stage", "worker_acp_profile.py", "package_attended.py"] if with_acp
        else ["stage", "package_attended.py"])
    assert calls[-1]["argv"] == [
        env["RELEASE_ROOT"]+"/integrations/deepseek_harness/package_attended.py", "materialize-native",
        "--source-repo", env["SOURCE_REPO"], "--source-sha", env["EXPECTED_SHA"],
        "--worker-config", env["NATIVE_WORKER_CONFIG"],
        "--worker-config-sha256", env["NATIVE_WORKER_CONFIG_SHA256"],
        "--native-package", env["NATIVE_PACKAGE"], "--native-node", env["NATIVE_NODE"],
        "--operator-uid", env["OPERATOR_UID"]]
    value = json.loads(result.stdout)
    assert value["staged_unselected"] and value["commit_sha"] == env["EXPECTED_SHA"]
    assert value["native_materialization"]["state"] == "UNSELECTED_MATERIALIZED"
    assert value["worker_acp_dependencies"] == (
        {"state":"ACP_MATERIALIZED", "effect_state":"APPLIED"} if with_acp else None)
    assert not any(value[key] for key in value if key.endswith("_changed"))


@pytest.mark.parametrize("failure", ["native-typed", "native-empty", "native-malformed"])
def test_native_failure_retains_source_and_settled_acp_outcomes(invocation, failure):
    result, calls, env = invocation(FAIL=failure, WORKER_ACP_BUNDLE="/original inputs/ACP bundle.zip")
    assert result.returncode == 70, result.stderr
    assert [row["kind"] for row in calls] == ["stage", "worker_acp_profile.py", "package_attended.py"]
    value = json.loads(result.stdout)
    assert not value["ok"] and value["staged_unselected"]
    assert value["source_repo"] == env["SOURCE_REPO"]
    assert value["worker_config"] == env["NATIVE_WORKER_CONFIG"]
    assert value["worker_config_sha256"] == env["NATIVE_WORKER_CONFIG_SHA256"]
    assert value["worker_acp_dependencies"] == {"state":"ACP_MATERIALIZED", "effect_state":"APPLIED"}
    native = value["native_materialization"]
    if failure == "native-typed":
        assert native["targets"] == {"node":{"effect_state":"APPLIED"},
                                     "package":{"effect_state":"EFFECT_UNKNOWN"}}
    else:
        assert native["state"] == "OUTCOME_UNAVAILABLE"
        assert native["effect_state"] == "UNOBSERVED" and not native["retry_allowed"]
        raw = "" if failure == "native-empty" else "[]"
        assert native["return_sha256"] == hashlib.sha256(raw.encode()).hexdigest()
    assert not any(value[key] for key in value if key.endswith("_changed"))


@pytest.mark.parametrize("failure,expected", [("stage", ["stage"]),
    ("acp", ["stage", "worker_acp_profile.py"])])
def test_prior_owner_failure_cannot_start_native_or_later_service(invocation, failure, expected):
    result, calls, _ = invocation(FAIL=failure, WORKER_ACP_BUNDLE="/original inputs/ACP bundle.zip")
    assert result.returncode == 65 and not result.stdout
    assert [row["kind"] for row in calls] == expected


@pytest.mark.parametrize("updates", [
    {"NATIVE_NODE":""}, {"NATIVE_PACKAGE":""}, {"NATIVE_WORKER_CONFIG":""},
    {"NATIVE_WORKER_CONFIG_SHA256":""}, {"NATIVE_NODE":"relative"},
    {"NATIVE_WORKER_CONFIG_SHA256":"f"*63}, {"NATIVE_WORKER_CONFIG_SHA256":"A"*64},
    {"STAGE_RELEASE_ONLY":"0"}, {"STAGE_ADMIN_CHECKOUT_ONLY":"1"},
])
def test_partial_or_ineligible_native_inputs_refuse_before_any_effect(invocation, updates):
    result, calls, _ = invocation(**updates)
    assert result.returncode == 65 and not calls and not result.stdout


@pytest.mark.parametrize("options", [
    ["--native-package", ""],
    ["--native-node"],
    ["--native-package", "", "--native-package", "/second"],
    ["--native-package", "/first", "--native-package", "/second"],
    ["--native-worker-config", ""],
    ["--native-worker-config-sha256", ""],
])
def test_actual_option_parser_rejects_empty_missing_and_duplicate_inputs(options):
    arms = "\n".join(line for line in TEXT.splitlines() if line.startswith("    --native-"))
    assert len(arms.splitlines()) == 4
    script = ('set -euo pipefail\nusage() { exit 64; }\n'
        + "\n".join(key+'=""' for key in NATIVE_KEYS)
        + '\nwhile [ "$#" -gt 0 ]; do\n  case "$1" in\n' + arms
        + '\n    *) usage ;;\n  esac\ndone\nprintf "PARSED\\n"\n')
    result = subprocess.run(["/bin/bash", "-c", script, "native-options", *options],
                            capture_output=True, text=True)
    assert result.returncode == 64 and not result.stdout


@pytest.mark.parametrize("command", [None, "materialize-native", "reconcile-native-materialization",
                                     "publish-native-attestation", "reconcile-native-attestation"])
def test_package_entrypoint_imports_in_actual_isolated_interpreter(command):
    path = ROOT/"integrations/deepseek_harness/package_attended.py"
    argv = [sys.executable, "-I", "-S", "-B", str(path)]
    if command is not None:
        argv.append(command)
    result = subprocess.run([*argv, "--help"], cwd=ROOT.parent,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout and not result.stderr

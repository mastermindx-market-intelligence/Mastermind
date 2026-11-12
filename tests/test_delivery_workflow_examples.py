"""Exercise the documented release commands without network or deployment effects.

These hermetic CLI boundaries test what the guide actually invokes. They do not
claim to prove GitHub enforcement, authorization, or live deployment behavior.
"""

import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "docs/DELIVERY_WORKFLOW.md"
REVIEWED_HEAD = "a" * 40
MERGE_SHA = "c" * 40
REPOSITORY = "mastermindx-market-intelligence/Mastermind"

# Only these test executables run. Their deliberately small contracts mirror the
# observed head-leased native release request and the existing deploy
# wrapper's exact-current-origin guard, including its empty-argument fallback.
CLI_BOUNDARY = r'''
import json
import os
from pathlib import Path
import sys

tool = Path(sys.argv[0]).name
args = sys.argv[1:]

def record(**event):
    with open(os.environ["EXAMPLE_EVENTS"], "a", encoding="utf-8") as stream:
        stream.write(json.dumps(event) + "\n")

record(tool=tool, args=args)
if tool == "gh":
    if args[:2] == ["pr", "checks"]:
        sys.exit(8 if os.environ["CHECK_STATUS"] == "pending" else 0)
    if args[:2] == ["pr", "view"]:
        # Valid-looking output must not mask a failed receipt read.
        print(os.environ["MERGED_RECEIPT"])
        sys.exit(int(os.environ["VIEW_EXIT"]))
    if args[:2] == ["pr", "merge"]:
        if "--match-head-commit" in args:
            expected = args[args.index("--match-head-commit") + 1]
            if expected != os.environ["REMOTE_HEAD"]:
                sys.exit(1)
        record(effect="native_request", sha=os.environ["REMOTE_HEAD"])
        sys.exit(0)
elif tool == "git":
    if args[:1] == ["fetch"]:
        sys.exit(0)
    if args == ["rev-parse", "origin/master"]:
        print(os.environ["ORIGIN_HEAD"])
        sys.exit(0)
elif tool == "deploy_from_git.sh":
    requested = (args[0] if args else "") or os.environ["ORIGIN_HEAD"]
    if requested != os.environ["ORIGIN_HEAD"]:
        sys.exit(2)
    record(effect="deploy", sha=requested)
    sys.exit(0)
raise SystemExit("unexpected test-boundary invocation: " + tool + repr(args))
'''


def _example(containing: str) -> str:
    blocks = re.findall(r"```bash\n(.*?)```", GUIDE.read_text(encoding="utf-8"), re.S)
    matches = [block for block in blocks if containing in block]
    assert len(matches) == 1, f"expected one documented example containing {containing!r}"
    return matches[0]


def _run_example(tmp_path: Path, containing: str, **overrides: str | None):
    tools = tmp_path / "bin"
    tools.mkdir()
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    for path in (tools / "gh", tools / "git", scripts / "deploy_from_git.sh"):
        path.write_text(f"#!{sys.executable}\n" + CLI_BOUNDARY, encoding="utf-8")
        path.chmod(0o700)
    events_path = tmp_path / "events.jsonl"
    bash = shutil.which("bash")
    assert bash is not None, "documented Bash examples require Bash"
    script = _example(containing)
    if containing == "gh pr merge":
        # Bind only the guide's two explicit placeholders; flags and command
        # structure continue to come from the actual documented example.
        for token, value in (("<PR>", "42"), ("<CURRENT_40_HEX_HEAD>", REVIEWED_HEAD)):
            assert script.count(token) == 1
            script = script.replace(token, value)
    # No inherited BASH_ENV, exported functions, credentials, or real CLI PATH.
    env = {
        "PYTHONNOUSERSITE": "1",
        "PATH": str(tools),
        "EXAMPLE_EVENTS": str(events_path),
        "pr_number": "42",
        "REMOTE_HEAD": REVIEWED_HEAD,
        "MERGED_RECEIPT": MERGE_SHA,
        "ORIGIN_HEAD": MERGE_SHA,
        "CHECK_STATUS": "pending",
        "VIEW_EXIT": "0",
    }
    for key, value in overrides.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    result = subprocess.run(
        [bash, "-c", script],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    events = (
        [json.loads(line) for line in events_path.read_text().splitlines()]
        if events_path.exists()
        else []
    )
    return result, events


def test_delivery_entrypoint_preserves_current_release_owners() -> None:
    guide = " ".join(GUIDE.read_text(encoding="utf-8").split())
    assert "git merge-base --is-ancestor origin/master HEAD" not in guide
    assert "Rebase or merge the latest `origin/master` into the task branch" not in guide
    assert "Compare current governing instructions, owned paths and imported dependencies" in guide
    assert "no ancestry-only join, rebase or duplicate worker is required" in guide
    assert "The native merge queue provides exact integrated checks" in guide
    assert "may be **armed while required hosted CI is pending**" in guide
    assert (
        "a Draft, incomplete source, known failing check, conflict, "
        "missing/ambiguous enforcement evidence or binding hold must not be armed"
    ) in guide


def test_merge_example_binds_the_explicit_pr_repository_and_head(tmp_path: Path) -> None:
    result, events = _run_example(tmp_path, "gh pr merge")
    assert result.returncode == 0, result.stderr
    merge = next(e for e in events if e.get("args", [])[:2] == ["pr", "merge"])
    assert merge["args"] == [
        "pr", "merge", "42", "--repo", REPOSITORY,
        "--auto", "--squash", "--match-head-commit", REVIEWED_HEAD,
    ]
    assert {"effect": "native_request", "sha": REVIEWED_HEAD} in events
    assert not any(e.get("effect") == "merge" for e in events)
    assert "--admin" not in merge["args"]
    assert "--delete-branch" not in merge["args"]


def test_merge_example_refuses_a_changed_head(tmp_path: Path) -> None:
    result, events = _run_example(tmp_path, "gh pr merge", REMOTE_HEAD="b" * 40)
    assert not any(e.get("effect") == "native_request" for e in events)
    assert result.returncode != 0


def test_merge_example_keeps_pending_ci_as_a_native_dependency(tmp_path: Path) -> None:
    # Preflight eligibility is separate; this fixture models pending CI only.
    result, events = _run_example(tmp_path, "gh pr merge", CHECK_STATUS="pending")
    assert result.returncode == 0, result.stderr
    assert not any(e.get("args", [])[:2] == ["pr", "checks"] for e in events)
    assert {"effect": "native_request", "sha": REVIEWED_HEAD} in events


def test_deploy_example_uses_the_explicit_pr_merge_receipt(tmp_path: Path) -> None:
    result, events = _run_example(tmp_path, "./scripts/deploy_from_git.sh")
    assert result.returncode == 0, result.stderr
    view = next(e for e in events if e.get("args", [])[:2] == ["pr", "view"])
    assert view["args"] == [
        "pr", "view", "42", "--repo", REPOSITORY,
        "--json", "mergeCommit", "--jq", ".mergeCommit.oid",
    ]
    invocation = next(e for e in events if e.get("tool") == "deploy_from_git.sh")
    assert invocation["args"] == [MERGE_SHA]
    assert {"effect": "deploy", "sha": MERGE_SHA} in events


def test_deploy_example_never_substitutes_a_newer_branch_tip(tmp_path: Path) -> None:
    result, events = _run_example(
        tmp_path, "./scripts/deploy_from_git.sh", ORIGIN_HEAD="d" * 40
    )
    invocation = next(e for e in events if e.get("tool") == "deploy_from_git.sh")
    assert invocation["args"] == [MERGE_SHA]
    assert not any(e.get("effect") == "deploy" for e in events)
    assert result.returncode != 0


@pytest.mark.parametrize("receipt", ["", "null", "not-a-commit", "a" * 39, "a" * 41, "g" * 40])
def test_deploy_example_rejects_missing_or_malformed_receipts(
    tmp_path: Path, receipt: str
) -> None:
    result, events = _run_example(
        tmp_path, "./scripts/deploy_from_git.sh", MERGED_RECEIPT=receipt
    )
    assert not any(e.get("tool") == "deploy_from_git.sh" for e in events)
    assert result.returncode != 0


@pytest.mark.parametrize("receipt", ["", MERGE_SHA])
def test_deploy_example_stops_after_failed_receipt_read(
    tmp_path: Path, receipt: str
) -> None:
    result, events = _run_example(
        tmp_path, "./scripts/deploy_from_git.sh",
        VIEW_EXIT="8", MERGED_RECEIPT=receipt,
    )
    assert not any(e.get("tool") == "deploy_from_git.sh" for e in events)
    assert result.returncode != 0


@pytest.mark.parametrize("pr_number", ["", None])
def test_deploy_example_requires_the_accepted_pr_number(
    tmp_path: Path, pr_number: str | None
) -> None:
    result, events = _run_example(
        tmp_path, "./scripts/deploy_from_git.sh", pr_number=pr_number
    )
    assert not any(e.get("args", [])[:2] == ["pr", "view"] for e in events)
    assert not any(e.get("tool") == "deploy_from_git.sh" for e in events)
    assert result.returncode != 0

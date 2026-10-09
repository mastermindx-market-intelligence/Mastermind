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

# Only these test executables run. Their deliberately small contracts mirror the
# observed `gh pr merge --match-head-commit` option and the existing deploy
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
        sys.exit(int(os.environ["CHECK_EXIT"]))
    if args[:2] == ["pr", "view"]:
        if os.environ["VIEW_EXIT"] != "0":
            sys.exit(int(os.environ["VIEW_EXIT"]))
        print(os.environ["MERGED_RECEIPT"])
        sys.exit(0)
    if args[:2] == ["pr", "merge"]:
        if "--match-head-commit" in args:
            expected = args[args.index("--match-head-commit") + 1]
            if expected != os.environ["REMOTE_HEAD"]:
                sys.exit(1)
        record(effect="merge", sha=os.environ["REMOTE_HEAD"])
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


def _run_example(tmp_path: Path, containing: str, **overrides: str):
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
    # No inherited BASH_ENV, exported functions, credentials, or real CLI PATH.
    env = {
        "HOME": str(tmp_path),
        "PYTHONNOUSERSITE": "1",
        "PATH": str(tools),
        "EXAMPLE_EVENTS": str(events_path),
        "pr_number": "42",
        "reviewed_head_sha": REVIEWED_HEAD,
        "REMOTE_HEAD": REVIEWED_HEAD,
        "MERGED_RECEIPT": MERGE_SHA,
        "ORIGIN_HEAD": MERGE_SHA,
        "CHECK_EXIT": "0",
        "VIEW_EXIT": "0",
        **overrides,
    }
    result = subprocess.run(
        [bash, "-c", _example(containing)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    events = [json.loads(line) for line in events_path.read_text().splitlines()]
    return result, events


def test_delivery_entrypoint_uses_existing_review_reuse_owner() -> None:
    guide = " ".join(GUIDE.read_text(encoding="utf-8").split())
    assert "git merge-base --is-ancestor origin/master HEAD" not in guide
    assert "Rebase or merge the latest `origin/master` into the task branch" not in guide
    assert "docs/sol_skills/RECONCILE_STATE.md" in guide
    assert "2026-09-02-autonomy-release-compatibility-review-reuse.md" in guide
    assert "acquired base" in guide
    assert "latest-base integration proof" in guide
    assert "Unknown materiality" in guide


def test_merge_example_binds_the_explicit_pr_and_reviewed_head(tmp_path: Path) -> None:
    result, events = _run_example(tmp_path, "gh pr merge")
    assert result.returncode == 0, result.stderr
    merge = next(e for e in events if e.get("args", [])[:2] == ["pr", "merge"])
    assert "42" in merge["args"]
    assert "--match-head-commit" in merge["args"]
    assert merge["args"][merge["args"].index("--match-head-commit") + 1] == REVIEWED_HEAD
    assert {"effect": "merge", "sha": REVIEWED_HEAD} in events


def test_merge_example_refuses_a_changed_head(tmp_path: Path) -> None:
    result, events = _run_example(tmp_path, "gh pr merge", REMOTE_HEAD="b" * 40)
    assert not any(e.get("effect") == "merge" for e in events)
    assert result.returncode != 0


def test_merge_example_stops_after_failed_required_checks(tmp_path: Path) -> None:
    result, events = _run_example(tmp_path, "gh pr merge", CHECK_EXIT="8")
    assert not any(e.get("args", [])[:2] == ["pr", "merge"] for e in events)
    assert result.returncode != 0


def test_deploy_example_uses_the_explicit_pr_merge_receipt(tmp_path: Path) -> None:
    result, events = _run_example(tmp_path, "./scripts/deploy_from_git.sh")
    assert result.returncode == 0, result.stderr
    view = next(e for e in events if e.get("args", [])[:2] == ["pr", "view"])
    assert "42" in view["args"]
    assert "mergeCommit" in view["args"]
    assert {"effect": "deploy", "sha": MERGE_SHA} in events


def test_deploy_example_never_substitutes_a_newer_branch_tip(tmp_path: Path) -> None:
    result, events = _run_example(
        tmp_path, "./scripts/deploy_from_git.sh", ORIGIN_HEAD="d" * 40
    )
    invocation = next(e for e in events if e.get("tool") == "deploy_from_git.sh")
    assert invocation["args"] == [MERGE_SHA]
    assert not any(e.get("effect") == "deploy" for e in events)
    assert result.returncode != 0


@pytest.mark.parametrize("receipt", ["", "null", "not-a-commit", "a" * 39, "a" * 41])
def test_deploy_example_rejects_missing_or_malformed_receipts(
    tmp_path: Path, receipt: str
) -> None:
    result, events = _run_example(
        tmp_path, "./scripts/deploy_from_git.sh", MERGED_RECEIPT=receipt
    )
    assert not any(e.get("tool") == "deploy_from_git.sh" for e in events)
    assert result.returncode != 0


def test_deploy_example_stops_after_failed_receipt_read(tmp_path: Path) -> None:
    result, events = _run_example(
        tmp_path, "./scripts/deploy_from_git.sh", VIEW_EXIT="8"
    )
    assert not any(e.get("tool") == "deploy_from_git.sh" for e in events)
    assert result.returncode != 0

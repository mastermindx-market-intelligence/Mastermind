"""Exercise attended project recovery in an isolated workspace using a pinned Macro snapshot.

Run explicitly from an active Codex turn. Only the final report survives. The
source repository is used for a local archive, never as an import mirror.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import sys
import stat
import tarfile
import tempfile

SOURCE = Path(__file__).resolve().parents[2]
MACRO_PIN = "b03edd4902a5582ed59773ec12ff2c2fa37aadf7"
WORKSTREAM = "WS:ORCHESTRATOR-PROJECT-CONTINUITY"
PLAN = "research/ORCHESTRATOR_PROJECT_CONTINUITY_IMPLEMENTATION.md"
HANDOFF = "agentos/handoffs/WS-ORCHESTRATOR-PROJECT-CONTINUITY-2026-10-21.md"
OWNER = "continuity-source-review"
HELPER_SHA = "711ba4f46c80e518d99167877738db9e92182b78bf7b4e3052bcfee79316d54a"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def run(argv, *, cwd, env, timeout=75):
    result = subprocess.run([str(arg) for arg in argv], cwd=cwd, env=env,
                            capture_output=True, timeout=timeout)
    if result.returncode:
        raise ValueError(f"{Path(argv[0]).name} exited {result.returncode}: "
                         + result.stderr.decode(errors="replace")[:320])
    return result.stdout


def require(condition, message):
    if not condition:
        raise ValueError(message)


def install_read_guard(bin_dir, git, root, trace):
    # The compiler and helper call git by name. Their entire PATH contains
    # this read-only wrapper and Python; even a no-op pull must be reported.
    quote = shlex.quote
    code = f"""#!/bin/sh
deny() {{ printf '%s\\n' '{{"command":"rejected","allowed":false}}' >> {quote(str(trace))}; exit 77; }}
if [ "$1" = "-C" ]; then cd -P "$2" || deny; shift 2; fi
case "$(pwd -P)/" in {quote(str(root))}/*) ;; *) deny ;; esac
case "$1" in
    rev-parse|show|log|status|ls-files|cat-file|diff) ;;
    *) deny ;;
esac
for arg in "$@"; do
    case "$arg" in --output*|--exec*|--textconv*|--ext-diff*|--git-dir*|--work-tree*) deny;; esac
done
printf '{{"command":"%s","allowed":true}}\\n' "$1" >> {quote(str(trace))}
exec {quote(git)} "$@"
"""
    wrapper = bin_dir / "git"
    wrapper.write_text(code)
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR)
    (bin_dir / "python3").symlink_to(sys.executable)


def exercise(macro_repo, root, session):
    git = shutil.which("git")
    require(bool(git and session), "a local Git and an attended Codex session are required")
    home, tmp, mirror, charter, bin_dir = [root / n for n in
                                           ("home", "tmp", "macro", "charter", "bin")]
    for directory in (home, tmp, mirror, charter, bin_dir):
        directory.mkdir()   # The enclosing TemporaryDirectory is private.
    env = dict(HOME=str(home), TMPDIR=str(tmp), PATH=os.defpath, LC_ALL="C",
               CODEX_THREAD_ID=session, PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1",
               GIT_NO_LAZY_FETCH="1", GIT_ALLOW_PROTOCOL="", GIT_CONFIG_NOSYSTEM="1",
               GIT_CONFIG_GLOBAL=os.devnull, GIT_OPTIONAL_LOCKS="0",
               GIT_TERMINAL_PROMPT="0", MM_AGENTOS_MIRROR=str(mirror))
    # The compiler uses PyYAML. Copy only that installed dependency instead
    # of exposing the user's HOME or their entire user-site directory.
    import yaml
    deps = root / "python-dependencies"
    shutil.copytree(Path(yaml.__file__).resolve().parent, deps / "yaml",
                    ignore=shutil.ignore_patterns("__pycache__"))
    env["PYTHONPATH"] = str(deps)
    # Export only trusted, tracked bytes. Never use the donor .git, a remote,
    # worktree alternates, a live charter, or the process's real HOME.
    archive = run([git, "archive", MACRO_PIN, "agentos/workstreams/WS-ORCHESTRATOR-PROJECT-CONTINUITY.md",
                   HANDOFF, "scripts/agentos.py", "config", PLAN],
                  cwd=macro_repo, env=env)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(mirror, filter="data")
    # Stage in a private repository so both normal owners see a real commit.
    # This fixture commit is identified separately from the donor's revision.
    for args in (["init", "-q"], ["add", "--", "."],
                 ["-c", "core.hooksPath=" + os.devnull, "-c", "user.name=Fixture",
                  "-c", "user.email=fixture@localhost", "commit", "-qm", "Fixture snapshot"]):
        run([git, *args], cwd=mirror, env=env)
    require(not run([git, "remote"], cwd=mirror, env=env).strip()
            and not (mirror / ".git/objects/info/alternates").exists(), "shared fixture repository")
    scratch_sha = run([git, "rev-parse", "HEAD"], cwd=mirror, env=env).decode().strip()
    # Mastermind strategic lookup only needs a local, read-only source view.
    # Ensure Git invoked by either owner cannot reach a shared repository.
    local_mastermind = root / "mastermind"
    (local_mastermind / "config").mkdir(parents=True)
    for name in ("strategic_state.yml", "mastermind_programs.yml"):
        src = SOURCE / "config" / name
        if src.is_file():
            shutil.copyfile(src, local_mastermind / "config" / name)
    env["MACRO_MASTERMIND_REPO"] = str(local_mastermind)
    trace = root / "git.jsonl"
    install_read_guard(bin_dir, git, root, trace)
    env["PATH"] = str(bin_dir)
    env["GIT_CEILING_DIRECTORIES"] = str(root)
    # Use the actual entry point, not a synthetic SessionStart callback.
    helper = SOURCE / "integrations/session_bridge/mmtask_restore/payload/mmtask"
    require(digest(helper.read_bytes()) == HELPER_SHA, "helper source mismatch")
    project = [sys.executable, "-B", SOURCE / "integrations/session_bridge/project_owner_continuation.py",
               "--workspace-root", root, "--charter-root", charter, "--macro-root", mirror,
               "--workstream", WORKSTREAM, "--owner", OWNER, "--owner-session", session,
               "--budget", "800"]

    def project_read():
        return json.loads(run(project, cwd=root, env=env))

    def task(*args):
        return run([sys.executable, "-B", helper, "--dir", charter, *args], cwd=root, env=env)

    seed = dict(schema="mm.harness.tasks", schema_version="2.0.0",
                project="source-rehearsal", workstream=None, agentos={}, waves=[], tasks=[])
    (charter / "TASKS.json").write_text(json.dumps(seed))
    (charter / "HANDOFF.md").write_text("")
    empty = project_read()
    if empty["projection"]["state"] != "RECOVER_CONTEXT":
        commands = trace.read_text().splitlines() if trace.exists() else []
        raise ValueError(f"empty projection {empty['projection']!r}; last private git calls {commands[-4:]}")
    bundle = empty["context_bundle"]
    require(bundle["repo_sha"] == scratch_sha, "compiler used a different repository")
    refs = [row.get("path") for section in bundle["sections"] for row in section["items"]]
    refs.extend(row.get("path") for row in bundle["omitted_due_to_budget"])
    require(PLAN in refs and HANDOFF in refs, "canonical source references missing")
    # The compiler may only cite the plan owing to budget. Read the file itself.
    plan, handoff = (mirror / PLAN).read_bytes(), (mirror / HANDOFF).read_bytes()
    require(plan and handoff, "missing canonical plan or handoff")
    task("rebind", "--from", "null", "--to", WORKSTREAM, "--reason", "Isolated source rehearsal")
    task("import", "--mirror", mirror, "--no-fetch")
    (charter / "HANDOFF.md").write_bytes(handoff)
    task("add", "Verify reproducible helper source package", "--wave", "W3",
         "--owner", OWNER, "--ready", "--accept", "Verify all package members and hashes")
    candidate = project_read()["projection"]
    require(candidate["state"] == "CANDIDATE" and candidate["action_recommendation"] is False,
            "expected a single inert candidate")
    ident = candidate["candidate"]["task_id"]
    require(project_read()["projection"] == candidate, "unchanged observation drifted")
    task("start", ident)
    require(project_read()["projection"]["candidate"] is None, "started task reoffered")
    # The attending owner chooses a fixed, known source assertion. No command
    # is extracted or evaluated from task titles, canonical prose or handoffs.
    verified = json.loads(run([sys.executable, "-B", helper.parents[1] / "rehearse.py", "--verify-only"],
                              cwd=root, env=env))
    require(verified == {"status": "FROZEN_SOURCE_VERIFIED", "files": 7},
            "source acceptance action failed")
    evidence = "Verified all seven frozen package members"
    task("done", ident, "--evidence", evidence)
    task("accept", ident, "--evidence", evidence)
    accepted = json.loads(task("show", ident))
    final = project_read()["projection"]
    require(accepted["status"] == "accepted" and final["candidate"] is None
            and project_read()["projection"] == final, "consumed task reoffered")
    commands = [json.loads(line) for line in trace.read_text().splitlines()]
    require(commands and all(c["allowed"] for c in commands), "non-local or non-read Git command")
    return dict(status="PASS", input_macro_commit=MACRO_PIN, private_commit=scratch_sha,
                exported_source_sha256=digest(archive), plan_sha256=digest(plan),
                handoff_sha256=digest(handoff), empty_state=empty["projection"]["state"],
                candidate=candidate["candidate"], action=verified, accepted_task=ident,
                final=final, git_commands=sorted({c["command"] for c in commands}),
                session=session, native_model_delivery="unobserved")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--macro-repo", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    args = parser.parse_args()
    # Exclusive receipt creation prevents an accidental repeat/overwrite.
    with args.result.open("x") as receipt:
        try:
            with tempfile.TemporaryDirectory(prefix="project-owner-rehearsal-") as directory:
                report = exercise(args.macro_repo.resolve(strict=True), Path(directory).resolve(),
                                  os.environ.get("CODEX_THREAD_ID"))
        except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
            report = dict(status="FAILED", reason=str(exc))
        json.dump(report, receipt, indent=2)
        receipt.write("\n")
    print(report["status"])
    return int(report["status"] != "PASS")


if __name__ == "__main__":
    sys.exit(main())

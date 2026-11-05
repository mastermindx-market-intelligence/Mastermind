"""Bounded capture tests for the fixed Macro planning compiler source.

Disposable temporary Git repositories only: no real Macro root, no network, no
credentials and no publication.  The declaration and proposal-compiler roles
carry the exact captured ``agentos-plan-proposal-7c54`` fixture bytes, verified
by SHA-256 and Git blob identity before use.  The owner, contract and
creation-compiler roles carry minimal interface-faithful TEST STAND-INS,
clearly marked as such: the real production bytes for those three roles are
never faked for production use, and the actual factory integration stays
parent-owned.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
import types
import zlib
from pathlib import Path

import pytest

from control_plane.project_planning_compiler_source import (
    CAPTURE_SCHEMA,
    REPOSITORY,
    ProjectPlanningCompilerSourceChanged,
    ProjectPlanningCompilerUnavailable,
    capture_project_planning_compilers,
)

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures/agentos-plan-proposal-7c54.json").read_text(encoding="utf-8")
)
assert FIXTURE["repository"] == REPOSITORY

_ALIAS_NAMES = (
    "scripts",
    "scripts.agentos",
    "scripts.agentos_project_plan_contract",
    "scripts.agentos_project_proposal",
    "scripts.agentos_plan_proposal",
    "scripts.agentos_plan_proposal_recipe",
)

# ---------------------------------------------------------------- test stand-ins
# Interface-faithful TEST bytes only.  They exercise the exact capture surface
# the production owner/compiler/contract modules must satisfy without ever
# pretending to be the production bytes for those three roles.

OWNER_STANDIN = '''\
"""Test-only owner stand-in exposing the captured owner capture surface."""
import re

import yaml

OWNER_SOURCE_MARKER = "captured-owner-stand-in"
PROGRAMMES_SOURCE_PATH = "config/mastermind_programs.yml"
_FRONT_MATTER = re.compile(r"---\\n(.*?)\\n---[ \\t]*\\n?(.*)", re.DOTALL)


class _OwnerLawError(ValueError):
    pass


def _load_programs():
    names = yaml.safe_load(_PROGRAMS.read_text(encoding="utf-8"))
    if type(names) is not dict or not names:
        raise _OwnerLawError("INVALID_PROGRAMMES")
    return set(names)


def parse_record(record):
    found = _FRONT_MATTER.fullmatch(record.read_text(encoding="utf-8"))
    if found is None:
        raise _OwnerLawError("INVALID_RECORD")
    parsed = yaml.safe_load(found.group(1))
    if type(parsed) is not dict:
        raise _OwnerLawError("INVALID_RECORD")
    return parsed, found.group(2)


def check_workstream(record, path, prior):
    return []


def check_decision(record, path):
    return []


def select_project_plan_adoption(records, *, work_ref):
    for record in records:
        adoption = record.get("project_plan_adoption")
        if type(adoption) is dict and adoption.get("work_ref") == work_ref:
            return record
    return None


def parse_project_plan_proposal(raw, *, work_ref):
    found = _FRONT_MATTER.fullmatch(raw.decode("utf-8"))
    if found is None:
        raise _OwnerLawError("INVALID_RECORD")
    parsed = yaml.safe_load(found.group(1))
    if type(parsed) is not dict:
        raise _OwnerLawError("INVALID_RECORD")
    return parsed, found.group(2).encode("utf-8")


yaml = yaml
'''


CONTRACT_STANDIN = '''\
"""Test-only contract stand-in with the source-ref seams the compilers use."""
import copy
import hashlib

CONTRACT_SOURCE_MARKER = "captured-contract-stand-in"
_REF_KEYS = {"repository", "path", "commit", "content_sha256"}


def bind_source_ref(source, raw_bytes):
    if (type(source) is not dict or set(source) != _REF_KEYS
            or any(type(value) is not str for value in source.values())):
        raise ValueError("INVALID_SOURCE_REF")
    if hashlib.sha256(raw_bytes).hexdigest() != source["content_sha256"]:
        raise ValueError("SOURCE_BYTES_MISMATCH")
    return dict(source)


def validate_source_ref(source):
    if type(source) is not dict or set(source) != _REF_KEYS:
        raise ValueError("INVALID_SOURCE_REF")
    return dict(source)


def validate_proposal(header, *, work_ref, candidate_bytes):
    if (type(header) is not dict
            or header.get("candidate_sha256") != hashlib.sha256(candidate_bytes).hexdigest()):
        raise ValueError("INVALID_PROPOSAL")
    return copy.deepcopy(header)
'''


CREATION_STANDIN = '''\
"""Test-only creation-compiler stand-in with the captured compiler interface."""
import hashlib
import json

from scripts.agentos import OWNER_SOURCE_MARKER, PROGRAMMES_SOURCE_PATH

OUTPUT_SCHEMA = "agentos.project_proposal.v1"
DRAFT_STATE = "DRAFT_ONLY"
WORKSTREAM_DIR = "agentos/workstreams"
REQUEST_KEYS = frozenset({"request_id", "record", "expected_commit"})


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":")).encode("utf-8")


def compile_proposal(request, *, programs):
    if (type(request) is not dict or set(request) != REQUEST_KEYS
            or type(programs) not in (set, frozenset) or not programs
            or OWNER_SOURCE_MARKER != "captured-owner-stand-in"):
        raise ValueError("INVALID_COMPILER_REQUEST")
    record = request["record"]
    if type(record) is not dict or type(record.get("key")) is not str or not record["key"]:
        raise ValueError("INVALID_COMPILER_REQUEST")
    key = record["key"]
    body = "objective: " + str(record.get("objective", "")) + "\\n"
    return {
        "schema": OUTPUT_SCHEMA,
        "state": DRAFT_STATE,
        "request_id": request["request_id"],
        "request_sha256": hashlib.sha256(_canonical(request)).hexdigest(),
        "expected_commit": request["expected_commit"],
        "work_ref": "WS:" + key,
        "path": WORKSTREAM_DIR + "/WS-" + key + ".md",
        "content_utf8": body,
        "content_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
    }
'''


PROGRAMMES_YAML = (
    "weekly_macro_review:\n  cadence: weekly\n"
    "publish_daily_summary:\n  cadence: daily\n"
)
PROGRAMMES = frozenset({"weekly_macro_review", "publish_daily_summary"})

WORKSTREAM_RECORD = (
    "---\n"
    "key: PLAN-TEST\n"
    "job_id: JOB-001\n"
    "objective: Compare captured planning compilers.\n"
    "next_action: Review only; do not adopt.\n"
    "---\n"
    "Current workstream body\n"
)

OWNER_CURRENT = OWNER_STANDIN + "\n\nOWNER_CURRENT_MARKER = 'current-data-code'\n"


def _sha(raw):
    return hashlib.sha256(raw if type(raw) is bytes else raw.encode("utf-8")).hexdigest()


def _fixture_bytes():
    """Decode and verify the exact captured fixture bytes for the 7c54 pin."""
    files = {}
    for item in FIXTURE["files"]:
        raw = zlib.decompress(base64.b64decode(item["zlib_base64"], validate=True))
        assert _sha(raw) == item["sha256"], item["path"]
        assert hashlib.sha1(
            b"blob " + str(len(raw)).encode() + b"\0" + raw
        ).hexdigest() == item["blob"], item["path"]
        files[item["path"]] = raw
    return files


class RecordingRunner:
    """Bounded-runner contract stub that records every call and runs real Git."""

    def __init__(self):
        self.calls = []

    def __call__(self, argv, *, cwd, timeout, max_bytes, env=None, input_bytes=None):
        self.calls.append({
            "argv": [os.fspath(item) for item in argv],
            "cwd": os.fspath(cwd),
            "timeout": timeout,
            "max_bytes": max_bytes,
            "env": dict(env) if env is not None else None,
        })
        completed = subprocess.run(
            [os.fspath(item) for item in argv], cwd=os.fspath(cwd),
            env=dict(env) if env is not None else None, input=input_bytes,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=max(0.05, float(timeout)), check=False,
        )
        raw = completed.stdout
        exceeded = len(raw) > max_bytes
        raw = raw[:max_bytes]
        try:
            stdout = raw.decode("utf-8")
            invalid = False
        except UnicodeDecodeError:
            stdout, invalid = "", True
        return {
            "code": completed.returncode,
            "stdout": stdout,
            "stderr": completed.stderr.decode("utf-8", "replace"),
            "timed_out": False,
            "limit_exceeded": exceeded,
            "invalid_utf8": invalid,
        }


class _BrokenRunner:
    """Runs real Git, then corrupts the returned runner contract."""

    def __init__(self, mutate):
        self._mutate = mutate
        self._runner = RecordingRunner()

    def __call__(self, argv, **kwargs):
        return self._mutate(self._runner(argv, **kwargs))


def _repo_env():
    env = dict(os.environ)
    env.update({
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "fixture",
        "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
        "GIT_COMMITTER_NAME": "fixture",
        "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
        "GIT_AUTHOR_DATE": "2020-01-01T00:00:00Z",
        "GIT_COMMITTER_DATE": "2020-01-01T00:00:00Z",
    })
    return env


def _git(root, *args, env=None, input_bytes=None):
    completed = subprocess.run(
        ["git", "-C", str(root), *args], cwd=str(root),
        env=env if env is not None else _repo_env(), input=input_bytes,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    assert completed.returncode == 0, completed.stderr.decode("utf-8", "replace")
    return completed.stdout


def build_repository(
    tmp_path,
    *,
    owner_code=OWNER_STANDIN,
    owner_current=OWNER_CURRENT,
    contract_code=CONTRACT_STANDIN,
    creation_code=CREATION_STANDIN,
    programmes=PROGRAMMES_YAML,
    executable_owner=False,
    symlink_programmes=False,
    include_contract=True,
):
    root = tmp_path / "macro"
    root.mkdir()
    _git(root, "init", "-q")
    (root / "README.md").write_bytes(b"fixture base\n")
    _git(root, "add", "-A", "-f")
    _git(root, "commit", "-q", "-m", "Base")
    base = _git(root, "rev-parse", "HEAD").decode().strip()
    files = {
        "scripts/agentos.py": owner_code.encode("utf-8"),
        "scripts/agentos_project_plan_contract.py": contract_code.encode("utf-8"),
        "scripts/agentos_project_proposal.py": creation_code.encode("utf-8"),
        "config/mastermind_programs.yml": programmes.encode("utf-8"),
        "agentos/workstreams/WS-PLAN-TEST.md": WORKSTREAM_RECORD.encode("utf-8"),
    }
    files.update(_fixture_bytes())
    for path, raw in files.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    if not include_contract:
        (root / "scripts/agentos_project_plan_contract.py").unlink()
    if executable_owner:
        (root / "scripts/agentos.py").chmod(0o755)
    if symlink_programmes:
        (root / "config/mastermind_programs.yml").unlink()
        (root / "config/mastermind_programs.yml.link").write_bytes(programmes.encode("utf-8"))
        os.symlink("mastermind_programs.yml.link", root / "config/mastermind_programs.yml")
    _git(root, "add", "-A", "-f")
    _git(root, "commit", "-q", "-m", "Qualified code commit")
    code = _git(root, "rev-parse", "HEAD").decode().strip()
    # Advance current DATA without rewriting the pinned code commit.
    (root / "scripts/agentos.py").write_bytes(owner_current.encode("utf-8"))
    (root / "agentos/data").mkdir(parents=True, exist_ok=True)
    (root / "agentos/data/ledger.txt").write_bytes(b"current data advance\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "Current DATA advance")
    head = _git(root, "rev-parse", "HEAD").decode().strip()
    assert base != code and code != head and base != head
    return {"root": root, "base": base, "code": code, "head": head}


@pytest.fixture
def repo(tmp_path):
    return build_repository(tmp_path)


@pytest.fixture
def runner():
    return RecordingRunner()


def _capture(repo, runner, **overrides):
    args = {
        "macro_root": repo["root"],
        "expected_macro_sha": repo["head"],
        "code_commit": repo["code"],
        "runner": runner,
    }
    args.update(overrides)
    return capture_project_planning_compilers(**args)


def _expected_refs(repo):
    sha_by_path = {
        "scripts/agentos.py": _sha(OWNER_STANDIN),
        "scripts/agentos_project_plan_contract.py": _sha(CONTRACT_STANDIN),
        "scripts/agentos_project_proposal.py": _sha(CREATION_STANDIN),
        "config/mastermind_programs.yml": _sha(PROGRAMMES_YAML),
    }
    sha_by_path.update({item["path"]: item["sha256"] for item in FIXTURE["files"]})

    def refs(pairs):
        return {
            role: {
                "repository": REPOSITORY,
                "commit": repo["code"],
                "path": path,
                "content_sha256": sha_by_path[path],
            }
            for role, path in pairs
        }

    return (
        refs((
            ("compiler", "scripts/agentos_project_proposal.py"),
            ("owner", "scripts/agentos.py"),
            ("programs", "config/mastermind_programs.yml"),
        )),
        refs((
            ("compiler", "scripts/agentos_plan_proposal_recipe.py"),
            ("declaration", "scripts/agentos_plan_proposal.py"),
            ("owner", "scripts/agentos.py"),
            ("contract", "scripts/agentos_project_plan_contract.py"),
        )),
    )


def _creation_request(repo):
    return {
        "request_id": "mmos-project-create-" + "a" * 40,
        "record": {"key": "PLAN-TEST", "objective": "Compare captured compilers."},
        "expected_commit": repo["code"],
    }


def _plan_inputs(captured, repo):
    compiler = captured.proposal_compiler
    ws_path = "agentos/workstreams/WS-PLAN-TEST.md"
    ws_raw = _git(repo["root"], "show", repo["code"] + ":" + ws_path)

    def capture_ref(path, raw):
        return {
            "source": {
                "repository": REPOSITORY,
                "path": path,
                "commit": repo["code"],
                "content_sha256": _sha(raw),
            },
            "raw_bytes": raw,
        }

    ws_ref = capture_ref(ws_path, ws_raw)
    work = "WS:PLAN-TEST"
    selection = {"work_ref": work, "job_id": "JOB-001", "attempt_id": "a" * 32}
    request = {
        "schema": compiler.REQUEST_SCHEMA,
        "request_id": "mmos-project-plan-proposal-" + "b" * 40,
        "work_ref": work,
        "expected_commit": repo["code"],
        "expected_adoption": None,
        "base_source": ws_ref["source"],
        "selection": selection,
        "result_digest": "3" * 64,
    }
    proposal_path = "research/project-plans/PLAN-PLAN-TEST-" + "b" * 40 + ".md"
    snapshot = {
        "schema": compiler.SNAPSHOT_SCHEMA,
        "repository": REPOSITORY,
        "commit": repo["code"],
        "workstream": ws_ref,
        "decisions": [],
        "base": ws_ref,
        "proposal_target": {"path": proposal_path, "state": "ABSENT"},
        "evidence": [],
        "source_binding": {"fixture": "actual code pin"},
    }

    def result_for(current_state):
        payload = {
            "summary": "Human result summary",
            "current_state": current_state,
            "completed_steps": [],
            "next_actions": [],
        }
        return {
            "schema": compiler.RESULT_SCHEMA,
            "selection": selection,
            "stage": "plan",
            "result_digest": request["result_digest"],
            "payload": payload,
            "payload_sha256": _sha(compiler._canonical(payload)),
            "planning_context_sha256": "4" * 64,
            "planning_request_sha256": "5" * 64,
            "planning_input_artifact_sha256": "6" * 64,
            "principal_scope": "7" * 64,
            "origin_root": "original-root",
            "budget_ref": "original-budget",
            "return_ref": "original-parent",
        }

    declaration = {
        "schema": "mastermind.project_plan_candidate.v1",
        "work_ref": work,
        "base_source": ws_ref["source"],
        "base_adoption": None,
        "plan": {
            "objective": "A bounded comparison plan.",
            "waves": [{"id": "W1", "title": "Compare captured compilers", "status": "todo"}],
            "next_action": "Review only; do not adopt.",
            "body": "Exact proposed body\n",
        },
        "rationale": "Bounded explicit returned evidence.",
        "evidence": [],
    }
    actor = {"principal_id": "fixture-principal"}
    return {
        "compiler": compiler,
        "request": request,
        "snapshot": snapshot,
        "actor": actor,
        "result_declared": result_for(json.dumps(declaration)),
        "result_prose": result_for("Plain prose clarification, not a declaration."),
        "proposal_path": proposal_path,
        "candidate_marker": "objective: A bounded comparison plan.",
    }


def _restore_aliases(saved):
    for name, module in saved.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module


def _assert_scope_clean(saved):
    for name, module in saved.items():
        if module is None:
            assert name not in sys.modules
        else:
            assert sys.modules[name] is module


# ---------------------------------------------------------------------- tests


def test_capture_binds_exact_roles_at_one_code_commit(repo, runner):
    saved = {name: sys.modules.get(name) for name in _ALIAS_NAMES}
    captured = _capture(repo, runner)
    creation, proposal = _expected_refs(repo)
    assert captured.creation_source_binding == creation
    assert captured.proposal_source_binding == proposal
    assert len(captured.creation_source_binding) == 3
    assert len(captured.proposal_source_binding) == 4
    assert len({ref["commit"] for ref in captured.proposal_source_binding.values()}) == 1
    assert captured.programs == PROGRAMMES and type(captured.programs) is frozenset
    # the declaration and proposal-compiler roles are the exact fixture bytes
    assert captured.declaration.CANDIDATE_SCHEMA == "mastermind.project_plan_candidate.v1"
    assert captured.proposal_compiler.RECIPE_SCHEMA == "agentos.project_plan_proposal_recipe.v1"
    assert Path(captured.declaration.__file__) == repo["root"] / "scripts/agentos_plan_proposal.py"
    assert Path(captured.proposal_compiler.__file__) == (
        repo["root"] / "scripts/agentos_plan_proposal_recipe.py"
    )
    captured.check()
    for name, module in saved.items():
        if module is None:
            assert name not in sys.modules
        else:
            assert sys.modules[name] is module


def test_capture_reads_code_only_at_code_commit(repo, runner):
    current_bytes = (repo["root"] / "scripts/agentos.py").read_bytes()
    captured = _capture(repo, runner)
    assert captured.creation_source_binding["owner"]["content_sha256"] == _sha(OWNER_STANDIN)
    assert captured.creation_source_binding["owner"]["content_sha256"] != _sha(current_bytes)
    # current-DATA code is never executed
    assert not hasattr(captured.owner, "OWNER_CURRENT_MARKER")
    assert captured.owner.OWNER_SOURCE_MARKER == "captured-owner-stand-in"
    for call in runner.calls:
        for arg in call["argv"]:
            if type(arg) is str and (":scripts/" in arg or ":config/" in arg):
                assert arg.startswith(repo["code"] + ":")


def test_git_calls_are_read_only_sanitized_and_requalified(repo, runner):
    captured = _capture(repo, runner)
    captured.compile_creation(_creation_request(repo))
    # capture = 14 bounded reads plus the 8-identity post-capture
    # requalification; each wrapper call requalifies 8 identities before and 8
    # after the actual compiler call.
    assert len(runner.calls) == 14 + 8 + 16
    for call in runner.calls:
        argv = call["argv"]
        assert argv[:4] == ["git", "--no-optional-locks", "--no-replace-objects", "-C"]
        assert argv[4] == str(repo["root"])
        assert argv[5] in {"rev-parse", "merge-base", "ls-tree", "show"}
        assert call["cwd"] == str(repo["root"]) and type(call["max_bytes"]) is int
        env = call["env"]
        assert env["GIT_NO_LAZY_FETCH"] == "1" and env["GIT_NO_REPLACE_OBJECTS"] == "1"
        assert env["GIT_CONFIG_GLOBAL"] == "/dev/null" and env["GIT_CONFIG_NOSYSTEM"] == "1"
        assert env["GIT_TERMINAL_PROMPT"] == "0"
        for redirected in (
            "GIT_CONFIG_PARAMETERS",
            "GIT_CONFIG_COUNT",
            "GIT_DIR",
            "GIT_WORK_TREE",
            "GIT_INDEX_FILE",
        ):
            assert redirected not in env
        if argv[5] in {"ls-tree", "show"}:
            assert any(type(arg) is str and repo["code"] in arg for arg in argv[6:])
            assert not any(
                type(arg) is str and arg.startswith(repo["head"] + ":") for arg in argv
            )


def test_compile_creation_returns_closed_draft_and_detaches(repo, runner):
    saved = {name: sys.modules.get(name) for name in _ALIAS_NAMES}
    captured = _capture(repo, runner)
    request = _creation_request(repo)
    draft = captured.compile_creation(request)
    assert draft["schema"] == "agentos.project_proposal.v1" and draft["state"] == "DRAFT_ONLY"
    assert draft["expected_commit"] == repo["code"] and draft["work_ref"] == "WS:PLAN-TEST"
    assert draft["path"] == "agentos/workstreams/WS-PLAN-TEST.md"
    assert draft["request_id"] == request["request_id"]
    assert draft["content_sha256"] == _sha(draft["content_utf8"])
    again = captured.compile_creation(request)
    assert again["request_sha256"] == draft["request_sha256"]
    # mutating a returned draft cannot poison a later compile
    draft["work_ref"] = "MUTATED"
    assert captured.compile_creation(request)["work_ref"] == "WS:PLAN-TEST"
    # captured compiler refusals propagate unchanged; capture-surface refusals
    # stay closed
    with pytest.raises(ValueError) as excinfo:
        captured.compile_creation({"unexpected": True})
    assert "INVALID_COMPILER_REQUEST" in str(excinfo.value)
    with pytest.raises(ProjectPlanningCompilerUnavailable):
        captured.compile_creation("not a request")
    _assert_scope_clean(saved)


def test_head_drift_refuses_wrappers_without_invoking_compilers(repo, runner):
    captured = _capture(repo, runner)
    request = _creation_request(repo)
    invoked = []
    real_compile = captured.creation_compiler.compile_proposal

    def counting(payload, *, programs):
        invoked.append(payload)
        return real_compile(payload, programs=programs)

    captured.creation_compiler.compile_proposal = counting
    assert captured.compile_creation(request)["state"] == "DRAFT_ONLY"
    assert len(invoked) == 1
    (repo["root"] / "agentos/data").mkdir(parents=True, exist_ok=True)
    (repo["root"] / "agentos/data/advance.txt").write_bytes(b"advance\n")
    _git(repo["root"], "add", "-A")
    _git(repo["root"], "commit", "-q", "-m", "Head advance")
    with pytest.raises(ProjectPlanningCompilerSourceChanged):
        captured.check()
    with pytest.raises(ProjectPlanningCompilerSourceChanged):
        captured.compile_creation(request)
    with pytest.raises(ProjectPlanningCompilerSourceChanged):
        captured.compile_proposal_recipe({}, {}, {}, {})
    assert len(invoked) == 1  # never invoked after the drift
    with pytest.raises(ProjectPlanningCompilerSourceChanged):
        _capture(repo, runner)


def test_replace_refs_cannot_substitute_captured_code(repo, runner, tmp_path):
    forged_blob = _git(
        repo["root"], "hash-object", "-w", "--stdin",
        input_bytes=b"OWNER_SOURCE_MARKER = 'forged-replacement'\n",
    ).decode().strip()
    index_env = _repo_env()
    index_env["GIT_INDEX_FILE"] = str(tmp_path / "forge-index")
    _git(repo["root"], "read-tree", repo["code"], env=index_env)
    _git(repo["root"], "update-index", "--cacheinfo",
         "100644," + forged_blob + ",scripts/agentos.py", env=index_env)
    forged_tree = _git(repo["root"], "write-tree", env=index_env).decode().strip()
    parent = _git(repo["root"], "rev-parse", repo["code"] + "^").decode().strip()
    forged = _git(repo["root"], "commit-tree", forged_tree, "-p", parent,
                  "-m", "forged replacement").decode().strip()
    _git(repo["root"], "replace", "-f", repo["code"], forged)
    assert repo["code"] in _git(repo["root"], "replace", "-l").decode()
    # precondition: without the no-replace discipline the drift would be visible
    plain = subprocess.run(
        ["git", "-C", str(repo["root"]), "show", repo["code"] + ":scripts/agentos.py"],
        cwd=str(repo["root"]), env=_repo_env(), stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    assert plain.returncode == 0 and b"forged-replacement" in plain.stdout
    captured = _capture(repo, runner)
    assert captured.creation_source_binding["owner"]["content_sha256"] == _sha(OWNER_STANDIN)
    captured.check()
    assert captured.owner.OWNER_SOURCE_MARKER == "captured-owner-stand-in"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"executable_owner": True},
        {"symlink_programmes": True},
        {"owner_code": "# pad\n" * 180000},
        {"include_contract": False},
        {"programmes": "- a\n- b\n"},
        {"programmes": ""},
    ],
    ids=[
        "executable_owner",
        "symlink_programmes",
        "oversized_owner",
        "missing_contract",
        "programmes_list",
        "programmes_empty",
    ],
)
def test_malformed_fixed_sources_refuse(tmp_path, runner, kwargs):
    repo = build_repository(tmp_path, **kwargs)
    with pytest.raises(ProjectPlanningCompilerUnavailable):
        _capture(repo, runner)


@pytest.mark.parametrize(
    "field,value",
    [
        ("expected_macro_sha", "0" * 39),
        ("expected_macro_sha", "A" * 40),
        ("expected_macro_sha", None),
        ("expected_macro_sha", b"0" * 40),
        ("expected_macro_sha", 123),
        ("code_commit", "9" * 41),
        ("code_commit", ""),
        ("code_commit", "z" * 40),
        ("code_commit", "e" * 40),
        ("timeout", 0),
        ("timeout", -1.0),
        ("timeout", True),
        ("timeout", "10"),
        ("timeout", 15.01),
        ("timeout", None),
        ("macro_root", "relative/path"),
        ("macro_root", None),
        ("macro_root", 12345),
        ("runner", "not-callable"),
    ],
)
def test_malformed_arguments_refuse_closed(repo, field, value):
    args = {
        "macro_root": repo["root"],
        "expected_macro_sha": repo["head"],
        "code_commit": repo["code"],
    }
    args[field] = value
    with pytest.raises(ProjectPlanningCompilerUnavailable):
        capture_project_planning_compilers(**args)


def test_expected_head_identity_mismatch_refuses_as_source_changed(repo, runner):
    # the pinned code commit is an ancestor, but it is not the exact HEAD
    with pytest.raises(ProjectPlanningCompilerSourceChanged):
        _capture(repo, runner, expected_macro_sha=repo["code"])
    with pytest.raises(ProjectPlanningCompilerSourceChanged):
        _capture(repo, runner, expected_macro_sha=repo["base"])


def test_broken_captured_module_failure_surfaces_and_restores(tmp_path, runner):
    # a captured module that raises at exec surfaces its own failure and still
    # leaves the scoped aliases restored on the edge
    saved = {name: sys.modules.get(name) for name in _ALIAS_NAMES}
    repo = build_repository(
        tmp_path, contract_code="raise RuntimeError('broken contract module')\n"
    )
    try:
        with pytest.raises(RuntimeError):
            _capture(repo, runner)
        _assert_scope_clean(saved)
    finally:
        _restore_aliases(saved)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda result: None,
        lambda result: {**result, "code": 128},
        lambda result: {**result, "timed_out": True},
        lambda result: {**result, "limit_exceeded": True},
        lambda result: {**result, "invalid_utf8": True},
        lambda result: {**result, "stdout": None},
        lambda result: {**result, "stdout": 5},
    ],
    ids=[
        "non_dict_result",
        "nonzero_code",
        "timed_out",
        "limit_exceeded",
        "invalid_utf8",
        "stdout_none",
        "stdout_not_str",
    ],
)
def test_runner_contract_failures_refuse_closed(repo, mutate):
    with pytest.raises(ProjectPlanningCompilerUnavailable):
        _capture(repo, _BrokenRunner(mutate))


def test_scope_restored_when_capture_fails_after_exec(tmp_path, runner):
    repo = build_repository(tmp_path, programmes="- a list not a mapping\n")
    sentinel = types.ModuleType("scripts.agentos")
    sentinel.MARKER = "sentinel"
    package = types.ModuleType("scripts")
    package.__path__ = []
    saved = {name: sys.modules.get(name) for name in _ALIAS_NAMES}
    sys.modules["scripts"] = package
    sys.modules["scripts.agentos"] = sentinel
    old_path = list(sys.path)
    try:
        with pytest.raises(ProjectPlanningCompilerUnavailable):
            _capture(repo, runner)
        assert sys.modules["scripts"] is package
        assert sys.modules["scripts.agentos"] is sentinel
        assert sentinel.MARKER == "sentinel"
        assert sys.path == old_path
    finally:
        _restore_aliases({name: saved[name] for name in ("scripts", "scripts.agentos")})


def test_ambient_module_fakes_cannot_substitute_captured_bytes(repo, runner):
    fake = types.ModuleType("scripts.agentos")
    fake.OWNER_SOURCE_MARKER = "ambient-fake"
    fake._load_programs = lambda: {"ambient-fake-programme"}
    package = types.ModuleType("scripts")
    package.__path__ = []
    saved = {name: sys.modules.get(name) for name in ("scripts", "scripts.agentos")}
    sys.modules["scripts"] = package
    sys.modules["scripts.agentos"] = fake
    try:
        captured = _capture(repo, runner)
        # the capture itself restored the ambient fakes on its exit edge
        assert sys.modules["scripts"] is package
        assert sys.modules["scripts.agentos"] is fake
        assert fake.OWNER_SOURCE_MARKER == "ambient-fake"
        assert captured.programs == PROGRAMMES
        assert captured.creation_compiler.OWNER_SOURCE_MARKER == "captured-owner-stand-in"
        assert captured.compile_creation(_creation_request(repo))["state"] == "DRAFT_ONLY"
    finally:
        _restore_aliases(saved)
    assert sys.modules.get("scripts") is saved["scripts"]
    assert sys.modules.get("scripts.agentos") is saved["scripts.agentos"]


def test_proposal_recipe_compiles_the_captured_fixture_bytes(repo, runner):
    captured = _capture(repo, runner)
    plan = _plan_inputs(captured, repo)
    recipe = captured.compile_proposal_recipe(
        plan["request"], plan["snapshot"], plan["result_declared"], plan["actor"]
    )
    assert recipe["schema"] == "agentos.project_plan_proposal_recipe.v1"
    assert recipe["status"] == "DRAFT_ONLY" and recipe["edits"]
    assert recipe["work_ref"] == "WS:PLAN-TEST" and recipe["expected_commit"] == repo["code"]
    assert recipe["request_id"] == plan["request"]["request_id"]
    assert recipe["proposal_path"] == plan["proposal_path"]
    assert recipe["preview"]["publication_authority"] == "DISTINCT_GRANT_REQUIRED"
    # the captured contract is bound into the captured owner
    assert captured.owner._project_plan_contract().CONTRACT_SOURCE_MARKER == (
        "captured-contract-stand-in"
    )
    for edit in recipe["edits"]:
        assert edit["mode"] == "100644"
        assert edit["content_sha256"] == _sha(edit["content_utf8"])
    assert recipe["edits"][0]["path"] == plan["proposal_path"]
    assert plan["candidate_marker"] in recipe["edits"][0]["content_utf8"]
    assert recipe["edits"][-1]["path"] == "agentos/workstreams/WS-PLAN-TEST.md"
    again = captured.compile_proposal_recipe(
        plan["request"], plan["snapshot"], plan["result_declared"], plan["actor"]
    )
    assert again["recipe_fingerprint_sha256"] == recipe["recipe_fingerprint_sha256"]


def test_proposal_recipe_prose_result_is_no_proposal(repo, runner):
    captured = _capture(repo, runner)
    plan = _plan_inputs(captured, repo)
    noop = captured.compile_proposal_recipe(
        plan["request"], plan["snapshot"], plan["result_prose"], plan["actor"]
    )
    assert noop["status"] == "NO_PROPOSAL" and noop["reason"] == "NO_DECLARED_PLAN"
    assert noop["edits"] == []


def test_proposal_recipe_closed_refusal_propagates_untranslated(repo, runner):
    captured = _capture(repo, runner)
    plan = _plan_inputs(captured, repo)
    broken = dict(plan["request"])
    del broken["expected_adoption"]
    with pytest.raises(ValueError) as excinfo:
        captured.compile_proposal_recipe(broken, plan["snapshot"], plan["result_declared"], plan["actor"])
    assert getattr(excinfo.value, "code", None) == "INVALID_REQUEST"


def test_captures_are_independent_and_material_is_display_only(repo, runner):
    first = _capture(repo, runner)
    second = _capture(repo, runner)
    assert first is not second
    assert first.material() == second.material()
    assert first.creation_source_binding == second.creation_source_binding
    first.creation_source_binding["owner"]["content_sha256"] = "tampered"
    assert second.creation_source_binding["owner"]["content_sha256"] != "tampered"
    record = second.material()
    assert set(record) == {
        "schema",
        "repository",
        "head",
        "code_commit",
        "programs",
        "creation_source_binding",
        "proposal_source_binding",
        "outer_collector_seal",
    }
    assert record["schema"] == CAPTURE_SCHEMA
    assert record["outer_collector_seal"] == "PARENT_OWNED_REQUIRED_NOT_RECORDED_HERE"
    assert record["programs"] == sorted(PROGRAMMES)
    assert len(json.dumps(record)) < 65536
    # the default installed bounded-runner path also serves the same capture
    default = capture_project_planning_compilers(
        macro_root=repo["root"], expected_macro_sha=repo["head"], code_commit=repo["code"]
    )
    assert default.programs == PROGRAMMES


def test_capture_at_head_as_code_commit_is_allowed(repo, runner):
    captured = _capture(repo, runner, code_commit=repo["head"])
    assert captured.creation_source_binding["owner"]["content_sha256"] == _sha(OWNER_CURRENT)
    captured.check()

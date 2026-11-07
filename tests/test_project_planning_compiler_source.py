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
import threading
import time
import types
import zlib
from contextlib import contextmanager
from pathlib import Path

import pytest

from control_plane.project_planning_compiler_source import (
    CAPTURE_SCHEMA,
    REPOSITORY,
    CapturedProjectPlanningCompilers,
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


# ------------------------------------------------- concurrent alias windows
# Deterministic window-overlap tests for the two process-global alias mutation
# brackets (capture exec and compiler-call scope).  The exec'd/called bytes are
# test-authored race stand-ins that rendezvous through a probe registered in
# ``sys.modules``, so the overlap itself -- not the existence of a lock -- is
# what is asserted.

class _WindowRaceProbe:
    """Rendezvous two alias windows and record whether they ever overlapped.

    ``arrive(label, phase)`` is called from inside an alias window by the
    test-authored stand-in bytes.  The wait is satisfied only by the peer's
    arrival for the SAME (label, phase) window, so a stale arrival from an
    earlier window can never let the second arriver skip its blocking wait:
    one thread genuinely parks inside its window (releasing the GIL) until the
    peer's window opens, which is what makes the overlap deterministic.
    """

    def __init__(self, peer, wait_seconds=2.5):
        self.peer = dict(peer)
        self.wait_seconds = wait_seconds
        self.hold_timeout = 30.0
        self.max_inside = 0
        self.arrivals = []
        self.notes = {}
        self.hold_ready = threading.Event()
        self.hold_release = threading.Event()
        self._inside = 0
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)
        self._open = set()

    def arrive(self, label, phase):
        with self._condition:
            self._inside += 1
            self.max_inside = max(self.max_inside, self._inside)
            self.arrivals.append((label, phase))
            self._open.add((label, phase))
            target = self.peer[(label, phase)]
            deadline = time.monotonic() + self.wait_seconds
            while target not in self._open:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._condition.wait(remaining)
            saw_peer = target in self._open
            self._open.discard((label, phase))
            self._inside -= 1
            self.arrivals.append((label, phase, "saw_peer=" + str(saw_peer)))
            self._condition.notify_all()
        return saw_peer

    def note(self, label, value):
        with self._condition:
            self.notes[label] = value

    def hold_enter(self):
        """Enter a window and hold it until the test releases the holder."""
        with self._lock:
            self._inside += 1
            self.max_inside = max(self.max_inside, self._inside)
            self.arrivals.append("hold")
        self.hold_ready.set()
        self.hold_release.wait(self.hold_timeout)
        with self._lock:
            self._inside -= 1


class _WindowStartGate:
    """Hold every party at one Git call until all have arrived, then open."""

    def __init__(self, parties):
        self.arrived = threading.Event()
        self._open = threading.Event()
        self._barrier = threading.Barrier(parties, action=self.arrived.set)

    def arrive_and_wait(self, timeout=30.0):
        try:
            self._barrier.wait(timeout)
        except threading.BrokenBarrierError:
            pass
        self._open.wait(timeout)

    def open(self):
        self._open.set()


class _GatedRunner:
    """RecordingRunner that holds one armed, identified Git call at the gate."""

    def __init__(self, trigger, gate, armed=False):
        self._runner = RecordingRunner()
        self._trigger = trigger
        self._gate = gate
        self._armed = bool(armed)
        self._held = False

    @property
    def calls(self):
        return self._runner.calls

    def arm(self):
        self._armed = True

    def __call__(self, argv, **kwargs):
        result = self._runner(argv, **kwargs)
        if self._armed and not self._held and self._trigger(self._runner.calls[-1]["argv"]):
            self._held = True
            self._gate.arrive_and_wait()
        return result


_RACE_PROGRAMMES_PATH = "config/mastermind_programs.yml"


def _programmes_show_trigger(argv):
    # the last bounded read before the capture exec window opens
    return argv[5] == "show" and any(
        type(arg) is str and arg.endswith(_RACE_PROGRAMMES_PATH) for arg in argv[6:]
    )


def _programmes_ls_tree_trigger(argv):
    # the last bounded read of a wrapper requalification before the scope opens
    return argv[5] == "ls-tree" and any(
        type(arg) is str and arg == _RACE_PROGRAMMES_PATH for arg in argv[6:]
    )


@contextmanager
def _race_probe_module(probe):
    """Expose the probe to the exec'd race stand-in bytes as a plain module."""
    module = types.ModuleType("_ppc_race_probe")
    module.arrive = probe.arrive
    module.note = probe.note
    module.hold_enter = probe.hold_enter
    saved = sys.modules.get("_ppc_race_probe")
    sys.modules["_ppc_race_probe"] = module
    try:
        yield probe
    finally:
        if saved is None:
            sys.modules.pop("_ppc_race_probe", None)
        else:
            sys.modules["_ppc_race_probe"] = saved


def _race_owner_code(label, hold=False):
    """Race owner stand-in bytes: hook the capture window, record the sibling."""
    arrival = (
        "_probe.hold_enter()"
        if hold
        else "_probe.arrive(" + repr(label) + ", 'capture')"
    )
    return (
        '"""Test-only race owner stand-in (' + label + '); never production bytes."""\n'
        "import re\n"
        "import sys\n\n"
        "import yaml\n\n"
        "import _ppc_race_probe as _probe\n\n"
        "OWNER_SOURCE_MARKER = 'captured-owner-race-" + label + "'\n"
        "PROGRAMMES_SOURCE_PATH = 'config/mastermind_programs.yml'\n"
        "OWNER_ARRIVAL = " + arrival + "\n"
        "OWNER_SAW_CONTRACT_MODULE = sys.modules.get('scripts.agentos_project_plan_contract')\n"
        "_FRONT_MATTER = re.compile(r\"---\\n(.*?)\\n---[ \\t]*\\n?(.*)\", re.DOTALL)\n"
        "\n\n"
        "class _OwnerLawError(ValueError):\n"
        "    pass\n\n\n"
        "def _load_programs():\n"
        "    names = yaml.safe_load(_PROGRAMS.read_text(encoding='utf-8'))\n"
        "    if type(names) is not dict or not names:\n"
        "        raise _OwnerLawError('INVALID_PROGRAMMES')\n"
        "    return set(names)\n"
    )


def _race_contract_code(label):
    """Race contract stand-in bytes carrying a per-commit marker."""
    return (
        '"""Test-only race contract stand-in (' + label + '); never production bytes."""\n'
        "import copy\n"
        "import hashlib\n\n"
        "import _ppc_race_probe as _probe\n\n"
        "_probe.note('contract:" + label + "', True)\n"
        "CONTRACT_SOURCE_MARKER = 'captured-contract-race-" + label + "'\n"
        "_REF_KEYS = {'repository', 'path', 'commit', 'content_sha256'}\n"
    )


def _race_creation_code(label):
    """Race creation stand-in bytes: hook the compile window, live-resolve."""
    return (
        '"""Test-only race creation stand-in (' + label + '); never production bytes."""\n'
        "import hashlib\n"
        "import json\n\n"
        "import _ppc_race_probe as _probe\n\n"
        "from scripts.agentos import OWNER_SOURCE_MARKER, PROGRAMMES_SOURCE_PATH\n\n"
        "OUTPUT_SCHEMA = 'agentos.project_proposal.v1'\n"
        "DRAFT_STATE = 'DRAFT_ONLY'\n"
        "WORKSTREAM_DIR = 'agentos/workstreams'\n"
        "REQUEST_KEYS = frozenset({'request_id', 'record', 'expected_commit'})\n"
        "COMPILER_MARKER = 'captured-creation-race-" + label + "'\n\n\n"
        "def _canonical(value):\n"
        "    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,\n"
        "                      separators=(',', ':')).encode('utf-8')\n\n\n"
        "def compile_proposal(request, *, programs):\n"
        "    import scripts.agentos as _live_owner\n"
        "    _probe.arrive(" + repr(label) + ", 'compile')\n"
        "    _probe.note(" + repr(label) + ", _live_owner.OWNER_SOURCE_MARKER)\n"
        "    if (type(request) is not dict or set(request) != REQUEST_KEYS\n"
        "            or type(programs) not in (set, frozenset) or not programs\n"
        "            or OWNER_SOURCE_MARKER != 'captured-owner-race-" + label + "'):\n"
        "        raise ValueError('INVALID_COMPILER_REQUEST')\n"
        "    key = request['record']['key']\n"
        "    body = 'objective: ' + str(request['record'].get('objective', '')) + '\\n'\n"
        "    return {\n"
        "        'schema': OUTPUT_SCHEMA,\n"
        "        'state': DRAFT_STATE,\n"
        "        'request_id': request['request_id'],\n"
        "        'request_sha256': hashlib.sha256(_canonical(request)).hexdigest(),\n"
        "        'expected_commit': request['expected_commit'],\n"
        "        'work_ref': 'WS:' + key,\n"
        "        'path': WORKSTREAM_DIR + '/WS-' + key + '.md',\n"
        "        'content_utf8': body,\n"
        "        'content_sha256': hashlib.sha256(body.encode('utf-8')).hexdigest(),\n"
        "    }\n"
    )


def _race_files(label, *, hold_owner=False, broken_contract=False):
    payload = {
        "scripts/agentos.py": _race_owner_code(label, hold=hold_owner).encode("utf-8"),
        "scripts/agentos_project_plan_contract.py": (
            "import _ppc_race_probe as _probe\n_probe.arrive("
            + repr(label) + ", 'capture')\n"
            "raise RuntimeError('broken race contract module')\n"
        ).encode("utf-8") if broken_contract else _race_contract_code(label).encode("utf-8"),
        "scripts/agentos_project_proposal.py": _race_creation_code(label).encode("utf-8"),
        "config/mastermind_programs.yml": PROGRAMMES_YAML.encode("utf-8"),
    }
    payload.update(_fixture_bytes())
    return payload


def _race_repository(
    tmp_path, name="race-macro", *, labels=("first", "second"),
    hold_owner=False, broken_contract=False,
):
    """One repo, two qualified code commits with genuinely different modules."""
    root = tmp_path / name
    root.mkdir()
    _git(root, "init", "-q")
    (root / "README.md").write_bytes(b"race fixture base\n")
    _git(root, "add", "-A", "-f")
    _git(root, "commit", "-q", "-m", "Base")
    commits = []
    for label in labels:
        for path, raw in _race_files(
            label, hold_owner=hold_owner, broken_contract=broken_contract
        ).items():
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        _git(root, "add", "-A", "-f")
        _git(root, "commit", "-q", "-m", "Qualified code commit " + label)
        commits.append(_git(root, "rev-parse", "HEAD").decode().strip())
    # Advance current DATA without rewriting either code commit.
    (root / "agentos/data").mkdir(parents=True, exist_ok=True)
    (root / "agentos/data/ledger.txt").write_bytes(b"race data advance\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "Race DATA advance")
    head = _git(root, "rev-parse", "HEAD").decode().strip()
    assert len(set(commits + [head])) == len(commits) + 1
    return {"root": root, "codes": commits, "head": head}


def _race_capture(repo, code, runner, **overrides):
    args = {
        "macro_root": repo["root"],
        "expected_macro_sha": repo["head"],
        "code_commit": code,
        "runner": runner,
    }
    args.update(overrides)
    return capture_project_planning_compilers(**args)


def _race_creation_request(code):
    return {
        "request_id": "mmos-project-create-" + "a" * 40,
        "record": {"key": "PLAN-TEST", "objective": "Race the captured compile windows."},
        "expected_commit": code,
    }


def test_concurrent_captures_serialize_the_alias_window(tmp_path):
    repo = _race_repository(tmp_path)
    saved = {name: sys.modules.get(name) for name in _ALIAS_NAMES}
    gate = _WindowStartGate(2)
    probe = _WindowRaceProbe({
        ("first", "capture"): ("second", "capture"),
        ("second", "capture"): ("first", "capture"),
    })
    runner_first = _GatedRunner(_programmes_show_trigger, gate, armed=True)
    runner_second = _GatedRunner(_programmes_show_trigger, gate, armed=True)
    outcomes = {}

    def capture(label, code, runner):
        try:
            outcomes[label] = _race_capture(repo, code, runner)
        except BaseException as error:  # recorded, never silently dropped
            outcomes[label] = error

    with _race_probe_module(probe):
        threads = [
            threading.Thread(target=capture, args=("first", repo["codes"][0], runner_first)),
            threading.Thread(target=capture, args=("second", repo["codes"][1], runner_second)),
        ]
        for thread in threads:
            thread.start()
        try:
            assert gate.arrived.wait(30.0), "capturers never reached the alias window"
        finally:
            gate.open()
        for thread in threads:
            thread.join(60.0)
            assert not thread.is_alive()
    _assert_scope_clean(saved)
    first, second = outcomes["first"], outcomes["second"]
    assert type(first) is CapturedProjectPlanningCompilers
    assert type(second) is CapturedProjectPlanningCompilers
    # the two exec windows never overlapped
    assert probe.max_inside == 1
    # each capture's own window resolved its own captured sibling modules
    assert first.owner.OWNER_SAW_CONTRACT_MODULE is first.owner._project_plan_contract()
    assert second.owner.OWNER_SAW_CONTRACT_MODULE is second.owner._project_plan_contract()
    assert first.owner.OWNER_SOURCE_MARKER == "captured-owner-race-first"
    assert second.owner.OWNER_SOURCE_MARKER == "captured-owner-race-second"
    assert first.creation_compiler.OWNER_SOURCE_MARKER == "captured-owner-race-first"
    assert second.creation_compiler.OWNER_SOURCE_MARKER == "captured-owner-race-second"


def test_concurrent_compile_scopes_serialize_the_alias_window(tmp_path):
    repo = _race_repository(tmp_path)
    saved = {name: sys.modules.get(name) for name in _ALIAS_NAMES}
    gate = _WindowStartGate(2)
    probe = _WindowRaceProbe({
        # sequential preliminary captures rendezvous with themselves (no wait)
        ("first", "capture"): ("first", "capture"),
        ("second", "capture"): ("second", "capture"),
        ("first", "compile"): ("second", "compile"),
        ("second", "compile"): ("first", "compile"),
    })
    runner_first = _GatedRunner(_programmes_ls_tree_trigger, gate)
    runner_second = _GatedRunner(_programmes_ls_tree_trigger, gate)
    outcomes = {}

    def compile_creation(label, captured, code):
        try:
            outcomes[label] = captured.compile_creation(_race_creation_request(code))
        except BaseException as error:  # recorded, never silently dropped
            outcomes[label] = error

    with _race_probe_module(probe):
        # both captures complete first, so the race below is compile-scope only
        first = _race_capture(repo, repo["codes"][0], runner_first)
        second = _race_capture(repo, repo["codes"][1], runner_second)
        runner_first.arm()
        runner_second.arm()
        threads = [
            threading.Thread(target=compile_creation, args=("first", first, repo["codes"][0])),
            threading.Thread(target=compile_creation, args=("second", second, repo["codes"][1])),
        ]
        for thread in threads:
            thread.start()
        try:
            assert gate.arrived.wait(30.0), "compilers never reached the alias window"
        finally:
            gate.open()
        for thread in threads:
            thread.join(60.0)
            assert not thread.is_alive()
    _assert_scope_clean(saved)
    draft_first, draft_second = outcomes["first"], outcomes["second"]
    assert draft_first["state"] == "DRAFT_ONLY" and draft_second["state"] == "DRAFT_ONLY"
    # the two compiler scopes never overlapped
    assert probe.max_inside == 1
    # each in-call live import resolved its own capture's owner module
    assert probe.notes["first"] == "captured-owner-race-first"
    assert probe.notes["second"] == "captured-owner-race-second"


def test_concurrent_capture_and_compile_windows_stay_disjoint(tmp_path):
    repo = _race_repository(tmp_path)
    saved = {name: sys.modules.get(name) for name in _ALIAS_NAMES}
    gate = _WindowStartGate(2)
    # probe labels are the race stand-in labels: the fresh capture is "first",
    # while both the "second" capture window and the "second" compile window
    # rendezvous against "first"
    probe = _WindowRaceProbe({
        # the preliminary capture of "second" rendezvous with itself (no wait);
        # the fresh capture window rendezvous against the concurrent compile
        # window of the other commit, and vice versa
        ("second", "capture"): ("second", "capture"),
        ("first", "capture"): ("second", "compile"),
        ("second", "compile"): ("first", "capture"),
    })
    runner_capture = _GatedRunner(_programmes_show_trigger, gate, armed=True)
    runner_compile = _GatedRunner(_programmes_ls_tree_trigger, gate)
    outcomes = {}

    def capture_action():
        try:
            return _race_capture(repo, repo["codes"][0], runner_capture)
        except BaseException as error:  # recorded, never silently dropped
            return error

    def compile_action():
        try:
            return existing.compile_creation(_race_creation_request(repo["codes"][1]))
        except BaseException as error:  # recorded, never silently dropped
            return error

    with _race_probe_module(probe):
        # the compile side's capture completes first, so the race below mixes
        # one fresh capture window against one compiler-call window
        existing = _race_capture(repo, repo["codes"][1], runner_compile)
        runner_compile.arm()
        threads = [
            threading.Thread(target=lambda: outcomes.update(capture=capture_action())),
            threading.Thread(target=lambda: outcomes.update(compile=compile_action())),
        ]
        for thread in threads:
            thread.start()
        try:
            assert gate.arrived.wait(30.0), "windows never opened together"
        finally:
            gate.open()
        for thread in threads:
            thread.join(60.0)
            assert not thread.is_alive()
    _assert_scope_clean(saved)
    captured, draft = outcomes["capture"], outcomes["compile"]
    assert type(captured) is CapturedProjectPlanningCompilers
    assert draft["state"] == "DRAFT_ONLY"
    assert probe.max_inside == 1
    assert captured.owner.OWNER_SAW_CONTRACT_MODULE is captured.owner._project_plan_contract()
    assert probe.notes["second"] == "captured-owner-race-second"


def test_failed_capture_window_releases_and_leaves_the_peer_exact(tmp_path):
    good = _race_repository(tmp_path, name="good-macro", labels=("peer",))
    broken = _race_repository(
        tmp_path, name="broken-macro", labels=("broken",), broken_contract=True
    )
    saved = {name: sys.modules.get(name) for name in _ALIAS_NAMES}
    gate = _WindowStartGate(2)
    probe = _WindowRaceProbe({
        ("broken", "capture"): ("peer", "capture"),
        ("peer", "capture"): ("broken", "capture"),
    })
    runner_broken = _GatedRunner(_programmes_show_trigger, gate, armed=True)
    runner_peer = _GatedRunner(_programmes_show_trigger, gate, armed=True)
    outcomes = {}

    def capture(label, repo, code, runner):
        try:
            outcomes[label] = _race_capture(repo, code, runner)
        except BaseException as error:  # recorded, never silently dropped
            outcomes[label] = error

    with _race_probe_module(probe):
        threads = [
            threading.Thread(target=capture,
                             args=("broken", broken, broken["codes"][0], runner_broken)),
            threading.Thread(target=capture,
                             args=("peer", good, good["codes"][0], runner_peer)),
        ]
        for thread in threads:
            thread.start()
        try:
            assert gate.arrived.wait(30.0), "capturers never reached the alias window"
        finally:
            gate.open()
        for thread in threads:
            thread.join(60.0)
            assert not thread.is_alive()
    _assert_scope_clean(saved)
    # the failing capture surfaces its own untranslated failure ...
    assert type(outcomes["broken"]) is RuntimeError
    # ... while the peer still captured its own modules exactly, and the
    # failed window released the alias lock for it
    peer = outcomes["peer"]
    assert type(peer) is CapturedProjectPlanningCompilers
    assert probe.max_inside == 1
    assert peer.owner.OWNER_SAW_CONTRACT_MODULE is peer.owner._project_plan_contract()
    assert peer.owner.OWNER_SOURCE_MARKER == "captured-owner-race-peer"


def test_window_wait_is_bounded_by_the_capture_deadline(tmp_path):
    holder_repo = _race_repository(
        tmp_path, name="holder-macro", labels=("hold",), hold_owner=True
    )
    peer_repo = _race_repository(tmp_path, name="peer-macro")
    saved = {name: sys.modules.get(name) for name in _ALIAS_NAMES}
    probe = _WindowRaceProbe({
        ("first", "capture"): ("first", "capture"),
        ("second", "capture"): ("second", "capture"),
    })
    outcomes = {}

    with _race_probe_module(probe):
        holder_thread = threading.Thread(
            target=lambda: outcomes.update(
                hold=_race_capture(holder_repo, holder_repo["codes"][0], RecordingRunner())
            )
        )
        holder_thread.start()
        try:
            assert probe.hold_ready.wait(30.0), "holder never entered its alias window"
            # the window is held past this second capture's deadline: the wait
            # must refuse closed, never block unboundedly
            with pytest.raises(ProjectPlanningCompilerUnavailable):
                _race_capture(peer_repo, peer_repo["codes"][0], RecordingRunner(), timeout=1.0)
        finally:
            probe.hold_release.set()
        holder_thread.join(60.0)
        assert not holder_thread.is_alive()
    _assert_scope_clean(saved)
    holder = outcomes["hold"]
    assert type(holder) is CapturedProjectPlanningCompilers
    assert probe.max_inside == 1


def test_free_alias_lock_refuses_an_already_expired_deadline():
    from control_plane import project_planning_compiler_source as source
    with pytest.raises(ProjectPlanningCompilerUnavailable):
        source._acquire_scope_lock(time.monotonic()-1)
    assert source._SCOPE_LOCK.acquire(blocking=False)
    source._SCOPE_LOCK.release()

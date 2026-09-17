"""tests.test_fabric_job_view — the WB1-B1 truthful fabric view guard file.

D1-D6 acceptance for :mod:`control_plane.fabric_job_view` and
``scripts/fabric_job_view.py`` (frozen spec ``orch/fabric/WB0_FROZEN_SPEC.md``
§(d), lane WB1-B1 under ORCH-WB1 / Meta-CEO B).

Falsifier and so-what for each D row:

* D1 an absent runtime is a typed refusal, never "no work".  The whole value
  of this view today is that production renders an empty tree *with reasons*
  (census §1); a projector that silently reports zero jobs would erase the
  single fact the Chairman most needs.
* D2 a job that was admitted and never claimed is ``NOT_STARTED``, never
  ``RUNNING``/``FAILED``.  Admission creates a Job; only ``claim_job`` creates
  an Attempt.
* D3 an undecided review is ``NOT_YET`` and *named* as an unproduced fact.
  ``JobPayload.to_dict`` omits an empty ``verdict`` key entirely, so the
  absent-key case is the common case, not an edge case.
* D4 a job the view cannot join to a workstream is counted and named, never
  silently dropped (the ``chairman_control_room`` bare-``continue`` hazard).
* D5 fixture data can never wear production labels: ``runtime.root`` is the
  literal root given, and the capability state is derived only from observed
  facts.
* D6 the read surfaces are structurally read-only (AST), so a future edit
  cannot turn the viewer into a writer without a red test.

Guard-test law: this file is the guard for every production module in the
diff (``control_plane/fabric_job_view.py``, ``scripts/fabric_job_view.py``).
No marker is used anywhere in this file (nothing is gated to one platform).

Deviation recorded: the spec's second no-regression witness names
``tests/test_executive_runtime.py``, which does not exist at BASE
``19b61118``.  The real guard for ``control_plane/executive_runtime.py`` is
``tests/test_executive_os_sqlite.py``; both it and
``tests/test_chairman_control_room.py`` are run UNEDITED as the witness.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO_ROOT / "control_plane" / "fabric_job_view.py"
CLI_PATH = REPO_ROOT / "scripts" / "fabric_job_view.py"

SCHEMA_LITERAL = "mastermind.fabric_job_view.v1"

DOC_KEYS = frozenset(
    {
        "schema",
        "generated_at",
        "runtime",
        "armed",
        "root",
        "children",
        "unjoined_job_count",
        "unjoined_job_ids",
        "degraded",
        "missingness",
        "capability",
    }
)
RUNTIME_KEYS = frozenset({"root", "db_present", "identity"})
ARMED_KEYS = frozenset(
    {
        "ceo_submit_armed",
        "coo_autonomy_armed",
        "ceo_ingress_app_armed",
        "dialogue_bridge_armed",
        "terminal_return_armed",
        "source",
    }
)
CARD_KEYS = frozenset(
    {
        "job_id",
        "status",
        "parent_job_id",
        "root_job_id",
        "depth",
        "orchestration_role",
        "plan_step_id",
        "attempt_count",
        "attempt_limit",
        "current_attempt_id",
        "attempts",
        "latest_attempt",
        "review",
        "repair",
        "result",
    }
)
ATTEMPT_KEYS = frozenset(
    {
        "attempt_id",
        "attempt_number",
        "status",
        "started_at",
        "finished_at",
        "exit_code",
        "has_result",
        "error",
    }
)
REVIEW_KEYS = frozenset({"required", "reviews_job_id", "verdict"})
REPAIR_KEYS = frozenset({"repair_round", "supersedes_job_id"})
RESULT_KEYS = frozenset({"state", "summary", "artifacts", "errors", "next_actions"})
MISSINGNESS_FACT_KEYS = frozenset(
    {"missingness_class", "target_field", "producer_owner", "reason"}
)
CAPABILITY_KEYS = frozenset({"state", "installed", "version", "detail"})
CAPABILITY_STATES = ("PROVEN", "PARTIAL", "UNSUPPORTED", "NOT_INSTALLED")
MISSINGNESS_CLASSES = frozenset(
    {"MISSING_PRODUCER", "NULL_BY_DESIGN", "EXCLUDED", "OMITTED", "DEGRADED"}
)
RESULT_STATES = frozenset(
    {
        "ACCEPTED",
        "FAILED",
        "LOST",
        "RATE_LIMITED",
        "CANCELLED",
        "IN_PROGRESS",
        "NOT_STARTED",
    }
)

DB_RELATIVE_PATH = Path("data") / "control_plane" / "executive.sqlite3"


# ---------------------------------------------------------------------------
# helpers — the production module is imported LAZILY so that a baseline run
# (module absent) fails each discriminator without a collection error, which
# would also take D6's pin down with it.
# ---------------------------------------------------------------------------

def _mod():
    from control_plane import fabric_job_view

    return fabric_job_view


def _runtime_module():
    from control_plane import executive_runtime

    return executive_runtime


def _payload_module():
    from control_plane.executive_runtime import JobPayload

    return JobPayload


def _provenance(workstream: str) -> dict:
    return {"schema": "mastermind.ceo_intent.v1", "workstream": workstream}


def _control_config(tmp_path: Path, **overrides) -> Path:
    arms = {key: False for key in sorted(ARMED_KEYS - {"source"})}
    arms.update(overrides)
    path = tmp_path / "control.json"
    path.write_text(json.dumps({"schema_version": "mastermind.executive_control_config/v1", **arms}), encoding="utf-8")
    return path


def _new_runtime(tmp_path: Path, name: str):
    runtime_root = tmp_path / name
    runtime_root.mkdir()
    return runtime_root, _runtime_module().Runtime.at(runtime_root)


def _register_worker(runtime) -> None:
    runtime.workers.register_worker(
        "worker-01",
        provider="codex",
        account_label="primary",
        worker_type="mock",
        capabilities=["code", "research"],
    )


def _claim_and_complete(runtime, job_id: str, verdict: str) -> None:
    lease = runtime.attempts.claim_job(job_id)
    assert lease is not None
    runtime.jobs.complete_job(job_id, _payload_module()(verdict=verdict))


def _tree_snapshot(root: Path):
    rows = []
    for path in sorted(root.rglob("*")):
        rel = str(path.relative_to(root))
        if path.is_dir():
            rows.append((rel, -1, ""))
        else:
            rows.append(
                (rel, path.stat().st_size, hashlib.sha256(path.read_bytes()).hexdigest())
            )
    return tuple(rows)


def _cards(doc) -> dict:
    return {card["job_id"]: card for card in doc["children"]}


def _assert_doc_shape(doc) -> None:
    assert set(doc.keys()) == DOC_KEYS
    assert doc["schema"] == SCHEMA_LITERAL
    assert isinstance(doc["generated_at"], str) and doc["generated_at"]
    assert set(doc["runtime"].keys()) == RUNTIME_KEYS
    assert set(doc["armed"].keys()) == ARMED_KEYS
    assert doc["armed"]["source"] in {"control.json", "absent"}
    assert isinstance(doc["unjoined_job_count"], int)
    assert isinstance(doc["unjoined_job_ids"], list)
    assert len(doc["unjoined_job_ids"]) <= 50
    assert doc["degraded"] == sorted(doc["degraded"])
    assert set(doc["capability"].keys()) == CAPABILITY_KEYS
    assert doc["capability"]["state"] in CAPABILITY_STATES
    for fact in doc["missingness"]:
        assert set(fact.keys()) == MISSINGNESS_FACT_KEYS
        assert fact["missingness_class"] in MISSINGNESS_CLASSES
    for card in ([doc["root"]] if doc["root"] is not None else []) + list(doc["children"]):
        assert set(card.keys()) == CARD_KEYS
        assert set(card["review"].keys()) == REVIEW_KEYS
        assert card["review"]["verdict"] in {"approve", "reject", "NOT_YET"}
        assert set(card["repair"].keys()) == REPAIR_KEYS
        assert set(card["result"].keys()) == RESULT_KEYS
        assert card["result"]["state"] in RESULT_STATES
        for attempt in card["attempts"]:
            assert set(attempt.keys()) == ATTEMPT_KEYS
            assert "lease_token" not in attempt
    assert "lease_token" not in json.dumps(doc)


# ---------------------------------------------------------------------------
# D1 — an absent runtime never renders as "no work"
# ---------------------------------------------------------------------------

def test_d1_absent_runtime_refuses(tmp_path):
    mod = _mod()
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    control = _control_config(tmp_path)
    before = _tree_snapshot(runtime_root)

    doc = mod.read_fabric_view(runtime_root, "JOB-ABSENT", control_config_path=control)

    _assert_doc_shape(doc)
    assert doc["runtime"]["root"] == str(runtime_root)
    assert doc["runtime"]["db_present"] is False
    assert doc["capability"]["state"] == "NOT_INSTALLED"
    assert doc["root"] is None
    assert doc["children"] == []
    assert doc["unjoined_job_count"] == 0
    assert doc["unjoined_job_ids"] == []

    db_path = runtime_root / DB_RELATIVE_PATH
    matching = [
        entry
        for entry in doc["degraded"]
        if re.match(r"^executive_runtime: database missing at ", entry)
    ]
    assert len(matching) == 1
    assert matching[0] == f"executive_runtime: database missing at {db_path}"

    # the call performed NO SQLite write: the directory is byte-identical and
    # no file (not even a -wal/-journal) was created
    assert _tree_snapshot(runtime_root) == before


# ---------------------------------------------------------------------------
# D2 — an admitted-but-unclaimed Job is never shown as running or failed
# ---------------------------------------------------------------------------

def test_d2_no_attempt_is_not_started(tmp_path):
    mod = _mod()
    runtime_root, runtime = _new_runtime(tmp_path, "runtime")
    root = runtime.jobs.create_job("root", provenance=_provenance("WS:D2"))
    never = runtime.jobs.create_job(
        "admitted, never claimed",
        parent_job_id=root.job_id,
        provenance=_provenance("WS:D2"),
    )
    claimed = runtime.jobs.create_job(
        "claimed", parent_job_id=root.job_id, provenance=_provenance("WS:D2")
    )
    _register_worker(runtime)
    assert runtime.attempts.claim_job(claimed.job_id) is not None

    doc = mod.read_fabric_view(
        runtime_root, root.job_id, control_config_path=_control_config(tmp_path)
    )

    _assert_doc_shape(doc)
    cards = _cards(doc)
    assert set(cards) == {never.job_id, claimed.job_id}

    never_card = cards[never.job_id]
    assert never_card["current_attempt_id"] is None
    assert never_card["attempt_count"] == 0
    assert never_card["attempts"] == []
    assert never_card["latest_attempt"] is None
    assert never_card["result"]["state"] == "NOT_STARTED"

    claimed_card = cards[claimed.job_id]
    assert [attempt["status"] for attempt in claimed_card["attempts"]] in (
        ["CLAIMED"],
        ["RUNNING"],
    )
    assert claimed_card["latest_attempt"] is not None
    assert claimed_card["result"]["state"] == "IN_PROGRESS"

    # the two cases must produce DIFFERENT literals, never one default
    assert claimed_card["result"]["state"] != never_card["result"]["state"]


# ---------------------------------------------------------------------------
# D3 — a review that has not happened is never rendered as a verdict
# ---------------------------------------------------------------------------

def test_d3_empty_verdict_is_not_yet(tmp_path):
    mod = _mod()
    runtime_root, runtime = _new_runtime(tmp_path, "runtime")
    root = runtime.jobs.create_job("root", provenance=_provenance("WS:D3"))
    _register_worker(runtime)

    cases = {}
    for verdict in ("", "approve", "reject"):
        subject = runtime.jobs.create_job(
            f"subject verdict={verdict!r}",
            parent_job_id=root.job_id,
            provenance=_provenance("WS:D3"),
        )
        reviewer = runtime.jobs.create_job(
            f"review of {subject.job_id}",
            parent_job_id=root.job_id,
            reviews_job_id=subject.job_id,
        )
        _claim_and_complete(runtime, reviewer.job_id, verdict)
        cases[verdict] = (subject.job_id, reviewer.job_id)

    doc = mod.read_fabric_view(
        runtime_root, root.job_id, control_config_path=_control_config(tmp_path)
    )

    _assert_doc_shape(doc)
    cards = _cards(doc)

    empty_subject, empty_reviewer = cases[""]
    assert cards[empty_subject]["review"]["required"] is False
    assert cards[empty_subject]["review"]["reviews_job_id"] == empty_reviewer
    assert cards[empty_subject]["review"]["verdict"] == "NOT_YET"

    facts = [
        fact
        for fact in doc["missingness"]
        if fact["missingness_class"] == "MISSING_PRODUCER"
        and fact["target_field"] == "review.verdict"
    ]
    assert len(facts) == 1
    assert facts[0]["producer_owner"] == empty_reviewer
    assert facts[0]["reason"] == "no completed independent review"

    for verdict in ("approve", "reject"):
        subject, reviewer = cases[verdict]
        assert cards[subject]["review"]["reviews_job_id"] == reviewer
        assert cards[subject]["review"]["verdict"] == verdict


# ---------------------------------------------------------------------------
# D4 — a job the view cannot join is counted, never silently dropped
# ---------------------------------------------------------------------------

def test_d4_unjoined_jobs_are_counted(tmp_path):
    mod = _mod()
    runtime_root, runtime = _new_runtime(tmp_path, "runtime")
    root = runtime.jobs.create_job("root", provenance=_provenance("WS:D4"))
    joined = [
        runtime.jobs.create_job(
            f"joined {index}",
            parent_job_id=root.job_id,
            provenance=_provenance("WS:D4"),
        )
        for index in range(2)
    ]
    unjoined = [
        runtime.jobs.create_job(f"unjoined {index}", parent_job_id=root.job_id)
        for index in range(3)
    ]

    doc = mod.read_fabric_view(
        runtime_root, root.job_id, control_config_path=_control_config(tmp_path)
    )

    _assert_doc_shape(doc)
    assert len(doc["children"]) == 2
    assert {card["job_id"] for card in doc["children"]} == {job.job_id for job in joined}
    assert doc["unjoined_job_count"] == 3
    assert doc["unjoined_job_ids"] == sorted(job.job_id for job in unjoined)
    assert len(doc["children"]) + doc["unjoined_job_count"] == 5

    gap = [entry for entry in doc["degraded"] if "unjoined" in entry]
    assert len(gap) == 1


# ---------------------------------------------------------------------------
# D5 — fixture data can never wear production labels
# ---------------------------------------------------------------------------

def test_d5_capability_state_is_derived(tmp_path):
    mod = _mod()
    root_a, runtime_a = _new_runtime(tmp_path, "runtime-a")
    root_b, runtime_b = _new_runtime(tmp_path, "runtime-b")
    job_a = runtime_a.jobs.create_job("root a", provenance=_provenance("WS:D5A"))
    job_b = runtime_b.jobs.create_job("root b", provenance=_provenance("WS:D5B"))
    control = _control_config(tmp_path)

    doc_a = mod.read_fabric_view(root_a, job_a.job_id, control_config_path=control)
    doc_b = mod.read_fabric_view(root_b, job_b.job_id, control_config_path=control)

    _assert_doc_shape(doc_a)
    _assert_doc_shape(doc_b)
    assert doc_a["runtime"]["root"] == str(root_a)
    assert doc_b["runtime"]["root"] == str(root_b)
    assert doc_a["runtime"]["root"] != doc_b["runtime"]["root"]
    assert doc_a["capability"]["state"] == "PROVEN"

    # PROVEN is unreachable while db_present is false, property-asserted over
    # every combination of (db_present, read_failed, root_present)
    armed = {key: False for key in sorted(ARMED_KEYS - {"source"})}
    armed["source"] = "control.json"
    observed = set()
    for db_present in (False, True):
        for read_failed in (False, True):
            for root_present in (True, False):
                doc = mod.compose_fabric_view(
                    root_job_id=job_a.job_id,
                    root_job=job_a if root_present else None,
                    jobs=[job_a],
                    attempts_by_job={},
                    joined_job_ids={job_a.job_id},
                    runtime_identity={
                        "root": str(root_a),
                        "db_present": db_present,
                        "identity": None,
                    },
                    armed=armed,
                    degraded=[],
                    read_failed=read_failed,
                )
                _assert_doc_shape(doc)
                observed.add(doc["capability"]["state"])
                if doc["runtime"]["db_present"] is False:
                    assert doc["capability"]["state"] != "PROVEN"
                if doc["runtime"]["db_present"] is False and not read_failed:
                    assert doc["capability"]["state"] == "NOT_INSTALLED"
                if doc["runtime"]["db_present"] is True and read_failed:
                    assert doc["capability"]["state"] == "UNSUPPORTED"
                if doc["runtime"]["db_present"] is True and not read_failed and root_present:
                    assert doc["capability"]["state"] == "PROVEN"

    # the derivation is non-degenerate: it reaches three distinct literals
    assert {"NOT_INSTALLED", "UNSUPPORTED", "PROVEN"} <= observed


# ---------------------------------------------------------------------------
# D6 — the view is read-only, structurally (PIN — see the docstring)
# ---------------------------------------------------------------------------

_BANNED_CALLS = frozenset(
    {
        "complete_attempt",
        "fail_attempt",
        "mark_lost",
        "claim_job",
        "create_job",
        "create_cycle_review",
        "create_cycle_repair",
        "submit_intent",
        "reconcile_wakes",
        "apply_wake_reconciliation",
        "append",
        "transaction",
    }
)
_BANNED_OS_CALLS = frozenset({"os.write", "os.mkdir"})
_BANNED_IMPORTS = ("integrations.executive_mcp", "subprocess")


def _dotted(node: ast.AST) -> str:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.insert(0, node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.insert(0, node.id)
    return ".".join(parts)


def _read_only_problems(path: Path) -> list:
    problems = []
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for banned in _BANNED_IMPORTS:
                    if alias.name == banned or alias.name.startswith(banned + "."):
                        problems.append(f"{path.name}: imports {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for banned in _BANNED_IMPORTS:
                if module == banned or module.startswith(banned + "."):
                    problems.append(f"{path.name}: imports from {module}")
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                dotted = _dotted(func)
                if func.attr in _BANNED_CALLS:
                    problems.append(f"{path.name}: banned call .{func.attr}()")
                if dotted in _BANNED_OS_CALLS:
                    problems.append(f"{path.name}: banned call {dotted}()")
                if func.attr == "at":
                    for keyword in node.keywords:
                        if keyword.arg == "create" and not (
                            isinstance(keyword.value, ast.Constant)
                            and keyword.value.value is False
                        ):
                            problems.append(
                                f"{path.name}: Runtime.at(..., create=...) is not False"
                            )
            elif isinstance(func, ast.Name) and func.id in _BANNED_CALLS:
                problems.append(f"{path.name}: banned call {func.id}()")
    return problems


def test_d6_view_is_read_only():
    """PIN: vacuously green at BASELINE while both production modules are
    absent; the named mutant (one ``runtime.reconcile_wakes()`` call added to
    the gather layer) is what establishes this test's power.
    """
    problems = []
    for path in (MODULE_PATH, CLI_PATH):
        if path.is_file():
            problems += _read_only_problems(path)
    assert problems == []


# ---------------------------------------------------------------------------
# supporting coverage — R2 list-roots enumerator and the CLI surface
# ---------------------------------------------------------------------------

def test_list_roots_enumerates_self_rooted_jobs(tmp_path):
    mod = _mod()
    runtime_root, runtime = _new_runtime(tmp_path, "runtime")
    roots = [
        runtime.jobs.create_job(f"root {index}", provenance=_provenance("WS:ROOTS"))
        for index in range(3)
    ]
    child = runtime.jobs.create_job("child", parent_job_id=roots[0].job_id)

    doc = mod.list_roots(runtime_root, control_config_path=_control_config(tmp_path))

    assert doc["schema"] == "mastermind.fabric_job_root_list.v1"
    assert doc["runtime"]["root"] == str(runtime_root)
    assert doc["runtime"]["db_present"] is True
    ids = [row["job_id"] for row in doc["roots"]]
    assert sorted(ids) == sorted(job.job_id for job in roots)
    assert child.job_id not in ids
    assert doc["count"] == len(ids)
    assert doc["truncated"] is False
    assert doc["degraded"] == sorted(doc["degraded"])


def test_list_roots_is_bounded_and_refuses_absent_runtime(tmp_path):
    mod = _mod()
    runtime_root, runtime = _new_runtime(tmp_path, "runtime")
    for index in range(4):
        runtime.jobs.create_job(f"root {index}")
    control = _control_config(tmp_path)

    doc = mod.list_roots(runtime_root, limit=2, control_config_path=control)
    assert doc["count"] == 2
    assert doc["truncated"] is True

    absent = tmp_path / "absent"
    absent.mkdir()
    refused = mod.list_roots(absent, control_config_path=control)
    assert refused["runtime"]["db_present"] is False
    assert refused["roots"] == []
    assert refused["count"] == 0
    assert any(
        entry.startswith("executive_runtime: database missing at ")
        for entry in refused["degraded"]
    )


def test_cli_json_describe_and_list_roots(tmp_path):
    runtime_root, runtime = _new_runtime(tmp_path, "runtime")
    root = runtime.jobs.create_job("root", provenance=_provenance("WS:CLI"))
    control = _control_config(tmp_path)

    def _run(*argv):
        return subprocess.run(
            [sys.executable, str(CLI_PATH), *argv],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            check=False,
        )

    view = _run(
        "--runtime-root",
        str(runtime_root),
        "--root-job-id",
        root.job_id,
        "--control-config",
        str(control),
        "--json",
    )
    assert view.returncode == 0, view.stderr
    doc = json.loads(view.stdout)
    assert set(doc.keys()) == DOC_KEYS
    assert doc["runtime"]["root"] == str(runtime_root)
    assert doc["root"]["job_id"] == root.job_id

    described = _run("--describe", "--json")
    assert described.returncode == 0, described.stderr
    capability = json.loads(described.stdout)
    assert set(capability.keys()) == CAPABILITY_KEYS
    assert capability["installed"] is False
    assert capability["state"] in CAPABILITY_STATES

    listed = _run("--list-roots", "--runtime-root", str(runtime_root), "--json")
    assert listed.returncode == 0, listed.stderr
    roots_doc = json.loads(listed.stdout)
    assert [row["job_id"] for row in roots_doc["roots"]] == [root.job_id]

    human = _run(
        "--runtime-root", str(runtime_root), "--root-job-id", root.job_id
    )
    assert human.returncode == 0, human.stderr
    assert "schema:" in human.stdout
    assert "capability:" in human.stdout
    assert "degraded:" in human.stdout

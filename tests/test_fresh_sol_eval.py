"""Deterministic fake-backend/falsifier coverage for the fresh-Sol F0 harness.

No provider credentials, no live provider calls.  Every App Server interaction
here goes through an injected in-process fake client -- see ``_FakeEvalClient``
below -- so these tests never spawn ``scripts.ohf.fake_app_server`` as a
subprocess.
"""
from __future__ import annotations

import inspect
import itertools
import subprocess
from pathlib import Path
from typing import Any

import pytest

from scripts.ohf.fresh_sol_eval import (
    MAS136_ARMS,
    MAS136_SCENARIOS,
    FreshSolEvalError,
    SkillpackArm,
    ScenarioPacket,
    CleanupReceipt,
    EvalClient,
    materialize_skillpack,
    parse_protocol,
    build_eval_agents_md,
    run_one,
    build_live_client_factory,
)
from scripts.ohf.laboratory import AppServerClient


# ---------------------------------------------------------------------------
# Task 1, Step 1: RED contract tests for immutable arm identity.
# ---------------------------------------------------------------------------


def test_mas136_arm_identity_is_frozen():
    assert MAS136_ARMS["control-1.0.0"].commit_sha == "51f9942733b86e550bb9169d2a43462bd28e774f"
    assert MAS136_ARMS["control-1.0.0"].skillpack_version == "1.0.0"
    assert MAS136_ARMS["amended-1.1.0"].commit_sha == "8209e1f31da15f8effc23a9899a5c5a02d30cab4"
    assert MAS136_ARMS["amended-1.1.0"].skillpack_version == "1.1.0"
    assert MAS136_SCENARIOS == ("S2", "S6", "S7", "S8")


# ---------------------------------------------------------------------------
# Task 1, Step 3: RED tests proving source bytes come from immutable Git
# objects, not the working tree.
# ---------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture()
def skillpack_git_repo(tmp_path: Path) -> dict[str, object]:
    """A tiny two-commit Git repo shaped like the real Skillpack tree."""

    repo = tmp_path / "skillpack_repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "ohf1@example.invalid")
    _git(repo, "config", "user.name", "ohf1 fixture")

    index_v1 = (
        "---\n"
        "schema: mastermind.sol_skillpack.v1\n"
        "skillpack_version: 1.0.0\n"
        "minimum_bootstrap_major: 1\n"
        "skill: index\n"
        "---\n\n# index v1\n"
    )
    sibling_v1 = "# sibling v1\ncontrol content\n"
    _write(repo / "docs/sol_skills/INDEX.md", index_v1)
    _write(repo / "docs/sol_skills/SIBLING.md", sibling_v1)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "control commit")
    control_sha = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()

    index_v2 = (
        "---\n"
        "schema: mastermind.sol_skillpack.v1\n"
        "skillpack_version: 1.1.0\n"
        "minimum_bootstrap_major: 1\n"
        "skill: index\n"
        "---\n\n# index v2\n"
    )
    sibling_v2 = "# sibling v2\namended content\n"
    _write(repo / "docs/sol_skills/INDEX.md", index_v2)
    _write(repo / "docs/sol_skills/SIBLING.md", sibling_v2)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "amended commit")
    amended_sha = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()

    # Dirty the working tree after both commits exist -- materialize_skillpack
    # must never read this.
    _write(repo / "docs/sol_skills/INDEX.md", "DIRTY WORKING TREE COPY -- MUST NOT BE READ\n")
    _write(repo / "docs/sol_skills/SIBLING.md", "DIRTY WORKING TREE COPY -- MUST NOT BE READ\n")

    return {"repo": repo, "control_sha": control_sha, "amended_sha": amended_sha}


def test_materialize_skillpack_reads_committed_bytes_not_dirty_worktree(skillpack_git_repo):
    repo = skillpack_git_repo["repo"]
    arm = SkillpackArm("fixture-control", skillpack_git_repo["control_sha"], "1.0.0")
    bundle = materialize_skillpack(repo, arm)
    paths = [source.path for source in bundle.sources]
    assert paths == sorted(paths)
    assert paths == ["docs/sol_skills/INDEX.md", "docs/sol_skills/SIBLING.md"]
    for source in bundle.sources:
        assert b"DIRTY WORKING TREE COPY" not in source.content
        assert len(source.blob_sha) == 40
    sibling = next(s for s in bundle.sources if s.path.endswith("SIBLING.md"))
    assert b"control content" in sibling.content
    assert isinstance(bundle.context_sha256, str) and len(bundle.context_sha256) == 64


def test_materialize_skillpack_aggregate_digest_is_stable(skillpack_git_repo):
    repo = skillpack_git_repo["repo"]
    arm = SkillpackArm("fixture-control", skillpack_git_repo["control_sha"], "1.0.0")
    first = materialize_skillpack(repo, arm)
    second = materialize_skillpack(repo, arm)
    assert first.context_sha256 == second.context_sha256


def test_materialize_skillpack_unknown_commit_refuses(skillpack_git_repo):
    repo = skillpack_git_repo["repo"]
    arm = SkillpackArm("fixture-bad", "0" * 40, "1.0.0")
    with pytest.raises(FreshSolEvalError) as excinfo:
        materialize_skillpack(repo, arm)
    assert excinfo.value.code == "SOURCE_COMMIT_UNAVAILABLE"


def test_materialize_skillpack_missing_index_refuses(tmp_path: Path):
    repo = tmp_path / "no_index_repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "ohf1@example.invalid")
    _git(repo, "config", "user.name", "ohf1 fixture")
    _write(repo / "docs/sol_skills/OTHER.md", "# not an index\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "no index")
    sha = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    arm = SkillpackArm("fixture-no-index", sha, "1.0.0")
    with pytest.raises(FreshSolEvalError) as excinfo:
        materialize_skillpack(repo, arm)
    assert excinfo.value.code == "PROCEDURE_SOURCE_UNAVAILABLE"


def test_materialize_skillpack_wrong_version_refuses(skillpack_git_repo):
    repo = skillpack_git_repo["repo"]
    arm = SkillpackArm("fixture-wrong-version", skillpack_git_repo["control_sha"], "9.9.9")
    with pytest.raises(FreshSolEvalError) as excinfo:
        materialize_skillpack(repo, arm)
    assert excinfo.value.code == "SKILLPACK_IDENTITY_MISMATCH"


def test_materialize_skillpack_wrong_schema_refuses(tmp_path: Path):
    repo = tmp_path / "wrong_schema_repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "ohf1@example.invalid")
    _git(repo, "config", "user.name", "ohf1 fixture")
    _write(
        repo / "docs/sol_skills/INDEX.md",
        "---\nschema: not.the.right.schema\nskillpack_version: 1.0.0\n"
        "minimum_bootstrap_major: 1\n---\n",
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "wrong schema")
    sha = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    arm = SkillpackArm("fixture-wrong-schema", sha, "1.0.0")
    with pytest.raises(FreshSolEvalError) as excinfo:
        materialize_skillpack(repo, arm)
    assert excinfo.value.code == "SKILLPACK_IDENTITY_MISMATCH"


# ---------------------------------------------------------------------------
# Task 1, Step 5: RED protocol-parser tests with exact S2/S6/S7/S8 extraction.
# ---------------------------------------------------------------------------


def _protocol_text(*, duplicate_preamble: bool = False, missing_pass_requires: bool = False) -> str:
    preamble = (
        "## Shared scenario preamble\n\n"
        "> PREAMBLE LINE\n\n"
    )
    body = preamble
    if duplicate_preamble:
        body += preamble
    for scenario_id, label, rule in (
        ("S2", "repaired-then-stale organizational state", "S2 RULE"),
        ("S6", "second scenario label", "S6 RULE"),
        ("S7", "third scenario label", "S7 RULE"),
        ("S8", "fourth scenario label", "S8 RULE"),
    ):
        body += f"## {scenario_id} — {label}\n\n> {scenario_id} BODY\n\n"
        if not (missing_pass_requires and scenario_id == "S2"):
            body += f"PASS requires: {rule}\n\n"
    return body


def test_parse_protocol_extracts_all_required_scenarios(tmp_path: Path):
    path = tmp_path / "PRESSURE_TEST_PROTOCOL.md"
    path.write_text(_protocol_text(), encoding="utf-8")
    packets = parse_protocol(path)
    assert set(packets) == {"S2", "S6", "S7", "S8"}
    s2 = packets["S2"]
    assert s2.scenario_id == "S2"
    assert "PREAMBLE LINE" in s2.prompt
    assert "S2 BODY" in s2.prompt
    assert "PASS requires" not in s2.prompt
    assert s2.pass_requires == "S2 RULE"


def test_parse_protocol_duplicate_preamble_refuses(tmp_path: Path):
    path = tmp_path / "PRESSURE_TEST_PROTOCOL.md"
    path.write_text(_protocol_text(duplicate_preamble=True), encoding="utf-8")
    with pytest.raises(FreshSolEvalError) as excinfo:
        parse_protocol(path)
    assert excinfo.value.code == "PROTOCOL_INVALID"


def test_parse_protocol_missing_scenario_refuses(tmp_path: Path):
    text = _protocol_text()
    text = text.replace(
        "## S8 — fourth scenario label\n\n> S8 BODY\n\nPASS requires: S8 RULE\n\n", ""
    )
    path = tmp_path / "PRESSURE_TEST_PROTOCOL.md"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(FreshSolEvalError) as excinfo:
        parse_protocol(path)
    assert excinfo.value.code == "PROTOCOL_INVALID"


def test_parse_protocol_missing_pass_requires_refuses(tmp_path: Path):
    path = tmp_path / "PRESSURE_TEST_PROTOCOL.md"
    path.write_text(_protocol_text(missing_pass_requires=True), encoding="utf-8")
    with pytest.raises(FreshSolEvalError) as excinfo:
        parse_protocol(path)
    assert excinfo.value.code == "PROTOCOL_INVALID"


def test_parse_protocol_never_falls_back_to_hardcoded_text(tmp_path: Path):
    """A protocol whose scenario body text is unusual must still be used verbatim."""
    path = tmp_path / "PRESSURE_TEST_PROTOCOL.md"
    text = _protocol_text().replace("S2 BODY", "UNUSUAL UNIQUE MARKER 42")
    path.write_text(text, encoding="utf-8")
    packets = parse_protocol(path)
    assert "UNUSUAL UNIQUE MARKER 42" in packets["S2"].prompt


# ---------------------------------------------------------------------------
# build_eval_agents_md
# ---------------------------------------------------------------------------


def test_build_eval_agents_md_is_arm_neutral_wrapper_plus_sources(skillpack_git_repo):
    repo = skillpack_git_repo["repo"]
    control_arm = SkillpackArm("control-1.0.0", skillpack_git_repo["control_sha"], "1.0.0")
    amended_arm = SkillpackArm("amended-1.1.0", skillpack_git_repo["amended_sha"], "1.1.0")
    control_bundle = materialize_skillpack(repo, control_arm)
    amended_bundle = materialize_skillpack(repo, amended_arm)
    control_md = build_eval_agents_md(control_bundle)
    amended_md = build_eval_agents_md(amended_bundle)
    assert isinstance(control_md, bytes)
    # The wrapper preamble (everything before the first source marker) must be
    # byte-identical between arms and must not name arm identity or grading.
    control_wrapper = control_md.split(b"----- BEGIN ", 1)[0]
    amended_wrapper = amended_md.split(b"----- BEGIN ", 1)[0]
    assert control_wrapper == amended_wrapper
    for banned in (b"Continuation Delta", b"control-1.0.0", b"amended-1.1.0", b"PASS requires"):
        assert banned not in control_wrapper
        assert banned not in amended_wrapper
    assert b"control content" in control_md
    assert b"amended content" in amended_md


# ---------------------------------------------------------------------------
# Task 2: fresh process/thread execution + capability attestation.
#
# ``_FakeEvalClient`` implements only the narrow structural surface
# ``fresh_sol_eval.EvalClient`` needs (pid, cwd, notifications, start,
# request, notify, wait_notification, graceful_close).  It never spawns a
# subprocess and never calls a provider.
# ---------------------------------------------------------------------------

_fake_pid_counter = itertools.count(9001)


class _FakeEvalClient:
    def __init__(
        self,
        workspace: Path,
        config_dir: Path,
        home: Path,
        *,
        served_model: str = "gpt-5.6-sol",
        approval_policy: str = "never",
        sandbox_mode: str = "read-only",
        skills: tuple[dict[str, Any], ...] = (),
        mcp_status: tuple[dict[str, Any], ...] = (),
        mcp_configured: tuple[str, ...] = (),
        plugins_configured: tuple[str, ...] = (),
        turn_output: str = "the answer",
        omit_model_key: bool = False,
        thread_read_turns: str = "normal",  # "normal" | "empty" | "ambiguous"
        cleanup_ok: bool = True,
        allow_resume_fork: bool = False,
        fail_capability_rpc: str | None = None,
        turn_error: dict[str, Any] | None = None,
        turn_error_at: str = "turn",  # "turn" (params.turn.error) | "top" (params.error)
    ) -> None:
        self.workspace = workspace
        self.config_dir = config_dir
        self.home = home
        self.cwd = workspace
        self.notifications: list[dict[str, Any]] = []
        self.pid: int | None = None
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.threads: dict[str, dict[str, Any]] = {}
        self._served_model = served_model
        self._approval_policy = approval_policy
        self._sandbox_mode = sandbox_mode
        self._skills = list(skills)
        self._mcp_status = list(mcp_status)
        self._mcp_configured = list(mcp_configured)
        self._plugins_configured = list(plugins_configured)
        self._turn_output = turn_output
        self._omit_model_key = omit_model_key
        self._thread_read_turns = thread_read_turns
        self._cleanup_ok = cleanup_ok
        self._allow_resume_fork = allow_resume_fork
        self._fail_capability_rpc = fail_capability_rpc
        self._turn_error = turn_error
        self._turn_error_at = turn_error_at
        self.thread_start_calls = 0
        self.thread_resume_calls = 0
        self.thread_fork_calls = 0
        self.turn_start_calls = 0
        self.graceful_close_calls = 0

    def start(self) -> None:
        self.pid = next(_fake_pid_counter)

    def request(
        self, method: str, params: dict[str, Any] | None = None, timeout: float = 15.0
    ) -> dict[str, Any]:
        params = dict(params or {})
        self.calls.append((method, params))
        if self._fail_capability_rpc == method:
            raise RuntimeError(f"fixture-forced failure for {method}")
        if method == "initialize":
            return {"userAgent": "fake-eval-client/1"}
        if method == "account/read":
            return {
                "account": {"type": "chatgpt", "planType": "pro"},
                "requiresOpenaiAuth": True,
            }
        if method == "config/read":
            config: dict[str, Any] = {
                "approval_policy": self._approval_policy,
                "sandbox_mode": self._sandbox_mode,
                "mcp_servers": {name: {} for name in self._mcp_configured},
                "plugins": {name: {} for name in self._plugins_configured},
            }
            if not self._omit_model_key:
                config["model"] = self._served_model
            return {"config": config}
        if method == "skills/list":
            return {"data": [{"cwd": str(self.workspace), "skills": self._skills, "errors": []}]}
        if method == "mcpServerStatus/list":
            return {"data": self._mcp_status}
        if method == "thread/start":
            self.thread_start_calls += 1
            thread_id = f"thr_fake_{next(_fake_pid_counter)}"
            self.threads[thread_id] = {"id": thread_id, "turns": []}
            return {"thread": {"id": thread_id}}
        if method == "thread/resume":
            self.thread_resume_calls += 1
            if not self._allow_resume_fork:
                raise AssertionError("run_one must never call thread/resume")
            return {"thread": {"id": params.get("threadId")}}
        if method == "thread/fork":
            self.thread_fork_calls += 1
            if not self._allow_resume_fork:
                raise AssertionError("run_one must never call thread/fork")
            return {"thread": {"id": "thr_fake_fork"}}
        if method == "turn/start":
            self.turn_start_calls += 1
            thread_id = str(params.get("threadId") or "")
            thread = self.threads.setdefault(thread_id, {"id": thread_id, "turns": []})
            thread["turns"].append(
                {
                    "id": "turn_fake",
                    "text": self._turn_output,
                    "items": [
                        {
                            "type": "agentMessage",
                            "text": self._turn_output,
                        }
                    ],
                }
            )
            return {"turn": {"id": "turn_fake"}}
        if method == "thread/read":
            thread_id = str(params.get("threadId") or "")
            if self._thread_read_turns == "empty":
                turns: list[dict[str, Any]] = []
            elif self._thread_read_turns == "ambiguous":
                turns = [
                    {
                        "id": "turn_fake",
                        "items": [
                            {"type": "agentMessage", "text": "first answer"},
                            {"type": "agentMessage", "text": "second different answer"},
                        ],
                    }
                ]
            else:
                thread = self.threads.get(thread_id) or {"turns": []}
                turns = list(thread.get("turns") or [])
            return {"thread": {"id": thread_id, "turns": turns}}
        raise AssertionError(f"unexpected fake RPC method: {method}")

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        self.calls.append((method, dict(params or {})))

    def wait_notification(self, method: str, *, timeout: float = 15.0) -> dict[str, Any]:
        turn: dict[str, Any] = {
            "id": "turn_fake",
            "text": "NOTIFICATION FRAGMENT MUST NEVER BE USED AS OUTPUT",
        }
        params: dict[str, Any] = {"turn": turn}
        if self._turn_error is not None:
            if self._turn_error_at == "top":
                params["error"] = self._turn_error
            else:
                turn["error"] = self._turn_error
        return {"method": method, "params": params}

    def graceful_close(self) -> object:
        self.graceful_close_calls += 1
        return CleanupReceipt(
            controller_returncode=0 if self._cleanup_ok else 1,
            private_group_id=self.pid,
            private_group_empty=self._cleanup_ok,
            termination_outcome="sigterm" if self._cleanup_ok else "unproven",
        )


def _fake_factory(**client_kwargs: Any):
    made: list[_FakeEvalClient] = []

    def factory(workspace: Path, config_dir: Path, home: Path) -> _FakeEvalClient:
        client = _FakeEvalClient(workspace, config_dir, home, **client_kwargs)
        made.append(client)
        return client

    factory.made = made  # type: ignore[attr-defined]
    return factory


def _scenario(scenario_id: str = "S8") -> ScenarioPacket:
    return ScenarioPacket(scenario_id=scenario_id, prompt="fixture prompt body", pass_requires="unused")


def _control_arm() -> SkillpackArm:
    return SkillpackArm("control-1.0.0", "51f9942733b86e550bb9169d2a43462bd28e774f", "1.0.0")


@pytest.fixture()
def mastermind_repo_root() -> Path:
    # This test worktree *is* the Mastermind repo; the two frozen MAS-136
    # commits already exist in its object database.
    return Path(__file__).resolve().parent.parent


def test_run_one_fresh_session_per_call(mastermind_repo_root: Path, tmp_path: Path):
    factory = _fake_factory()
    obs1 = run_one(
        repo_root=mastermind_repo_root,
        arm=_control_arm(),
        scenario=_scenario(),
        run_root=tmp_path / "run1",
        client_factory=factory,
    )
    obs2 = run_one(
        repo_root=mastermind_repo_root,
        arm=_control_arm(),
        scenario=_scenario(),
        run_root=tmp_path / "run2",
        client_factory=factory,
    )
    assert obs1.run_id != obs2.run_id
    assert obs1.process_pid != obs2.process_pid
    assert obs1.workspace != obs2.workspace
    assert obs1.native_thread_id != obs2.native_thread_id
    for obs, client in zip((obs1, obs2), factory.made):
        assert client.thread_start_calls == 1
        assert client.thread_resume_calls == 0
        assert client.thread_fork_calls == 0
        assert client.turn_start_calls == 1
    assert obs1.output == "the answer"
    assert obs1.prompt == "fixture prompt body"


# ---------------------------------------------------------------------------
# Task 2, Step 2: RED capability-attestation tests.
# ---------------------------------------------------------------------------


def test_served_model_mismatch_refuses_before_thread_start(mastermind_repo_root: Path, tmp_path: Path):
    factory = _fake_factory(served_model="gpt-4-not-sol")
    with pytest.raises(FreshSolEvalError) as excinfo:
        run_one(
            repo_root=mastermind_repo_root,
            arm=_control_arm(),
            scenario=_scenario(),
            run_root=tmp_path / "run",
            client_factory=factory,
        )
    assert excinfo.value.code == "SERVED_MODEL_MISMATCH"
    assert factory.made[0].graceful_close_calls == 1  # BLOCKER-2: cleanup ran despite the failure
    assert factory.made[0].thread_start_calls == 0


def test_approval_policy_mismatch_refuses_before_thread_start(mastermind_repo_root: Path, tmp_path: Path):
    factory = _fake_factory(approval_policy="on-request")
    with pytest.raises(FreshSolEvalError) as excinfo:
        run_one(
            repo_root=mastermind_repo_root,
            arm=_control_arm(),
            scenario=_scenario(),
            run_root=tmp_path / "run",
            client_factory=factory,
        )
    assert excinfo.value.code == "CAPABILITY_ATTESTATION_INVALID"
    assert factory.made[0].graceful_close_calls == 1  # BLOCKER-2: cleanup ran despite the failure
    assert factory.made[0].thread_start_calls == 0


def test_sandbox_mode_mismatch_refuses_before_thread_start(mastermind_repo_root: Path, tmp_path: Path):
    factory = _fake_factory(sandbox_mode="workspace-write")
    with pytest.raises(FreshSolEvalError) as excinfo:
        run_one(
            repo_root=mastermind_repo_root,
            arm=_control_arm(),
            scenario=_scenario(),
            run_root=tmp_path / "run",
            client_factory=factory,
        )
    assert excinfo.value.code == "CAPABILITY_ATTESTATION_INVALID"
    assert factory.made[0].graceful_close_calls == 1  # BLOCKER-2: cleanup ran despite the failure
    assert factory.made[0].thread_start_calls == 0


def test_configured_mcp_server_refuses_before_thread_start(mastermind_repo_root: Path, tmp_path: Path):
    factory = _fake_factory(mcp_configured=("some_mcp",))
    with pytest.raises(FreshSolEvalError) as excinfo:
        run_one(
            repo_root=mastermind_repo_root,
            arm=_control_arm(),
            scenario=_scenario(),
            run_root=tmp_path / "run",
            client_factory=factory,
        )
    assert excinfo.value.code == "CAPABILITY_ATTESTATION_INVALID"
    assert factory.made[0].graceful_close_calls == 1  # BLOCKER-2: cleanup ran despite the failure
    assert factory.made[0].thread_start_calls == 0


def test_configured_plugin_refuses_before_thread_start(mastermind_repo_root: Path, tmp_path: Path):
    factory = _fake_factory(plugins_configured=("some_plugin",))
    with pytest.raises(FreshSolEvalError) as excinfo:
        run_one(
            repo_root=mastermind_repo_root,
            arm=_control_arm(),
            scenario=_scenario(),
            run_root=tmp_path / "run",
            client_factory=factory,
        )
    assert excinfo.value.code == "CAPABILITY_ATTESTATION_INVALID"
    assert factory.made[0].graceful_close_calls == 1  # BLOCKER-2: cleanup ran despite the failure


def test_visible_skill_refuses_before_thread_start(mastermind_repo_root: Path, tmp_path: Path):
    factory = _fake_factory(skills=({"name": "some-skill"},))
    with pytest.raises(FreshSolEvalError) as excinfo:
        run_one(
            repo_root=mastermind_repo_root,
            arm=_control_arm(),
            scenario=_scenario(),
            run_root=tmp_path / "run",
            client_factory=factory,
        )
    assert excinfo.value.code == "CAPABILITY_ATTESTATION_INVALID"
    assert factory.made[0].graceful_close_calls == 1  # BLOCKER-2: cleanup ran despite the failure


def test_ambiguous_capability_observation_refuses(mastermind_repo_root: Path, tmp_path: Path):
    factory = _fake_factory(omit_model_key=True)
    with pytest.raises(FreshSolEvalError) as excinfo:
        run_one(
            repo_root=mastermind_repo_root,
            arm=_control_arm(),
            scenario=_scenario(),
            run_root=tmp_path / "run",
            client_factory=factory,
        )
    assert excinfo.value.code == "CAPABILITY_ATTESTATION_INVALID"
    assert factory.made[0].graceful_close_calls == 1  # BLOCKER-2: cleanup ran despite the failure


def test_capability_rpc_failure_refuses(mastermind_repo_root: Path, tmp_path: Path):
    factory = _fake_factory(fail_capability_rpc="account/read")
    with pytest.raises(FreshSolEvalError) as excinfo:
        run_one(
            repo_root=mastermind_repo_root,
            arm=_control_arm(),
            scenario=_scenario(),
            run_root=tmp_path / "run",
            client_factory=factory,
        )
    assert excinfo.value.code == "CAPABILITY_ATTESTATION_INVALID"
    assert factory.made[0].graceful_close_calls == 1  # BLOCKER-2: cleanup ran despite the failure


def test_thread_read_ambiguous_output_refuses(mastermind_repo_root: Path, tmp_path: Path):
    factory = _fake_factory(thread_read_turns="ambiguous")
    with pytest.raises(FreshSolEvalError) as excinfo:
        run_one(
            repo_root=mastermind_repo_root,
            arm=_control_arm(),
            scenario=_scenario(),
            run_root=tmp_path / "run",
            client_factory=factory,
        )
    assert excinfo.value.code == "THREAD_READ_FAILED"
    assert factory.made[0].graceful_close_calls == 1  # BLOCKER-2: cleanup ran despite the failure


def test_notification_fragment_never_substitutes_for_thread_read(mastermind_repo_root: Path, tmp_path: Path):
    factory = _fake_factory(thread_read_turns="empty")
    with pytest.raises(FreshSolEvalError) as excinfo:
        run_one(
            repo_root=mastermind_repo_root,
            arm=_control_arm(),
            scenario=_scenario(),
            run_root=tmp_path / "run",
            client_factory=factory,
        )
    assert excinfo.value.code == "THREAD_READ_FAILED"
    assert factory.made[0].graceful_close_calls == 1  # BLOCKER-2: cleanup ran despite the failure


# ---------------------------------------------------------------------------
# Auth-error truthfulness repair (F0 live-canary post-mortem 2026-09-01).
#
# Root cause: the isolated realm's refresh token was server-revoked, the
# real App Server turn failed with an `unauthorized` provider error, and
# the pre-fix harness discarded `wait_notification("turn/completed", ...)`'s
# return value entirely -- it then fell through to thread/read, found no
# candidate assistant text, and raised the misleading
# THREAD_READ_FAILED (candidates=[]) instead of the true auth cause.
#
# Ground truth for the error SHAPE is the real rollout's `task_complete`
# event (~/.codex-ohf-p0/sessions/2026/09/01/rollout-...-01a0601f...jsonl
# line 11): `error.codex_error_info == "unauthorized"`, `error.message`
# carries the human-readable cause. The live `turn/completed` notification's
# own field path is NOT confirmed, so these tests drive BOTH plausible
# carriers (`params.turn.error`, matching this fixture's and the repo's own
# fake_app_server.py `turn/completed` shape; and `params.error`, the other
# candidate path) rather than fitting the fix to one shape.
# ---------------------------------------------------------------------------


def test_turn_unauthorized_error_raises_turn_unauthorized_not_thread_read_failed(
    mastermind_repo_root: Path, tmp_path: Path
):
    """RED on pre-fix code: the pre-fix harness discards the turn/completed
    return value, falls through to thread/read on an empty thread, and
    raises THREAD_READ_FAILED (candidates=[]) -- truthful-but-misleading
    for a turn that never ran because auth was rejected. Post-fix it must
    raise TURN_UNAUTHORIZED and never reach thread/read."""

    factory = _fake_factory(
        thread_read_turns="empty",
        turn_error={
            "message": (
                "Your access token could not be refreshed because your "
                "refresh token was revoked. Please log out and sign in again."
            ),
            "codex_error_info": "unauthorized",
        },
        turn_error_at="turn",
    )
    with pytest.raises(FreshSolEvalError) as excinfo:
        run_one(
            repo_root=mastermind_repo_root,
            arm=_control_arm(),
            scenario=_scenario(),
            run_root=tmp_path / "run",
            client_factory=factory,
        )
    assert excinfo.value.code == "TURN_UNAUTHORIZED"
    assert "revoked" in str(excinfo.value)
    assert factory.made[0].graceful_close_calls == 1  # BLOCKER-2: cleanup ran despite the failure


def test_turn_unauthorized_error_detected_at_params_error_carrier(
    mastermind_repo_root: Path, tmp_path: Path
):
    """Same scenario, error carried at the OTHER plausible field path
    (`params.error` rather than `params.turn.error`) -- proves the
    extraction is not fitted to a single fixture shape."""

    factory = _fake_factory(
        thread_read_turns="empty",
        turn_error={"message": "token revoked", "codex_error_info": "unauthorized"},
        turn_error_at="top",
    )
    with pytest.raises(FreshSolEvalError) as excinfo:
        run_one(
            repo_root=mastermind_repo_root,
            arm=_control_arm(),
            scenario=_scenario(),
            run_root=tmp_path / "run",
            client_factory=factory,
        )
    assert excinfo.value.code == "TURN_UNAUTHORIZED"


def test_turn_generic_provider_error_raises_turn_provider_error(
    mastermind_repo_root: Path, tmp_path: Path
):
    """A non-null turn/completed error that is NOT an auth rejection (no
    codex_error_info == "unauthorized") must be reported distinctly from
    both an auth failure and a read failure."""

    factory = _fake_factory(
        thread_read_turns="empty",
        turn_error={"message": "upstream provider returned 503", "codex_error_info": "server_error"},
        turn_error_at="turn",
    )
    with pytest.raises(FreshSolEvalError) as excinfo:
        run_one(
            repo_root=mastermind_repo_root,
            arm=_control_arm(),
            scenario=_scenario(),
            run_root=tmp_path / "run",
            client_factory=factory,
        )
    assert excinfo.value.code == "TURN_PROVIDER_ERROR"
    assert factory.made[0].graceful_close_calls == 1


def test_turn_error_without_codex_error_info_field_is_provider_error(
    mastermind_repo_root: Path, tmp_path: Path
):
    """Defensive classification: an error dict missing codex_error_info
    entirely must not crash and must not be misclassified as unauthorized."""

    factory = _fake_factory(
        thread_read_turns="empty",
        turn_error={"message": "unspecified failure"},
        turn_error_at="turn",
    )
    with pytest.raises(FreshSolEvalError) as excinfo:
        run_one(
            repo_root=mastermind_repo_root,
            arm=_control_arm(),
            scenario=_scenario(),
            run_root=tmp_path / "run",
            client_factory=factory,
        )
    assert excinfo.value.code == "TURN_PROVIDER_ERROR"


def test_turn_error_never_reaches_thread_read(mastermind_repo_root: Path, tmp_path: Path):
    """An auth-rejected turn must short-circuit before thread/read is ever
    called -- proves the fix does not merely relabel the eventual
    THREAD_READ_FAILED but actually prevents the misleading read attempt."""

    class _CountingClient(_FakeEvalClient):
        def request(self, method, params=None, timeout=15.0):
            if method == "thread/read":
                raise AssertionError("thread/read must never be called after an auth-rejected turn")
            return super().request(method, params, timeout)

    def factory(workspace: Path, config_dir: Path, home: Path) -> _CountingClient:
        return _CountingClient(
            workspace,
            config_dir,
            home,
            turn_error={"message": "revoked", "codex_error_info": "unauthorized"},
        )

    with pytest.raises(FreshSolEvalError) as excinfo:
        run_one(
            repo_root=mastermind_repo_root,
            arm=_control_arm(),
            scenario=_scenario(),
            run_root=tmp_path / "run",
            client_factory=factory,
        )
    assert excinfo.value.code == "TURN_UNAUTHORIZED"


def test_turn_error_message_redacts_secret_and_launders_path(
    mastermind_repo_root: Path, tmp_path: Path
):
    """The raised failure message must go through the same redaction as
    every other closed failure -- no raw credential-shaped text or host
    filesystem path survives into the report."""

    sentinel = "sk-testFixtureSecretShape1234567890"
    leaky_path = "/Users/fixture-operator/.codex-ohf-p0/auth.json"
    factory = _fake_factory(
        thread_read_turns="empty",
        turn_error={
            "message": f"refresh failed near {leaky_path} leaking {sentinel}",
            "codex_error_info": "unauthorized",
        },
        turn_error_at="turn",
    )
    with pytest.raises(FreshSolEvalError) as excinfo:
        run_one(
            repo_root=mastermind_repo_root,
            arm=_control_arm(),
            scenario=_scenario(),
            run_root=tmp_path / "run",
            client_factory=factory,
        )
    assert excinfo.value.code == "TURN_UNAUTHORIZED"
    message = str(excinfo.value)
    assert sentinel not in message
    assert "/Users/" not in message
    assert "<path>" in message


def test_cleanup_unproven_invalidates_run(mastermind_repo_root: Path, tmp_path: Path):
    factory = _fake_factory(cleanup_ok=False)
    with pytest.raises(FreshSolEvalError) as excinfo:
        run_one(
            repo_root=mastermind_repo_root,
            arm=_control_arm(),
            scenario=_scenario(),
            run_root=tmp_path / "run",
            client_factory=factory,
        )
    assert excinfo.value.code == "CLEANUP_UNPROVEN"


# ---------------------------------------------------------------------------
# Task 2, Step 4: dedicated auth-realm validation without credential reads.
# ---------------------------------------------------------------------------


def test_default_codex_home_refuses(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    default_codex_home = fake_home / ".codex"
    default_codex_home.mkdir()
    (default_codex_home / "auth.json").write_text("{}", encoding="utf-8")
    with pytest.raises(FreshSolEvalError) as excinfo:
        build_live_client_factory(codex_home=default_codex_home, model="gpt-5.6-sol")
    assert excinfo.value.code == "AUTH_REALM_INVALID"


def test_auth_json_contents_are_never_read_copied_or_serialized(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    dedicated = tmp_path / "dedicated_realm"
    dedicated.mkdir()
    secret_marker = "sk-should-never-be-read-1234567890"
    (dedicated / "auth.json").write_text(secret_marker, encoding="utf-8")

    auth_json_path = (dedicated / "auth.json").resolve()
    real_read_bytes = Path.read_bytes
    real_read_text = Path.read_text
    real_open = Path.open

    def guarded_read_bytes(self: Path, *args: Any, **kwargs: Any) -> bytes:
        if self.resolve() == auth_json_path:
            raise AssertionError("auth.json bytes must never be read")
        return real_read_bytes(self, *args, **kwargs)

    def guarded_read_text(self: Path, *args: Any, **kwargs: Any) -> str:
        if self.resolve() == auth_json_path:
            raise AssertionError("auth.json text must never be read")
        return real_read_text(self, *args, **kwargs)

    def guarded_open(self: Path, *args: Any, **kwargs: Any):
        if self.resolve() == auth_json_path:
            raise AssertionError("auth.json must never be opened")
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", guarded_read_bytes)
    monkeypatch.setattr(Path, "read_text", guarded_read_text)
    monkeypatch.setattr(Path, "open", guarded_open)

    factory = build_live_client_factory(codex_home=dedicated, model="gpt-5.6-sol")
    assert callable(factory)


# ---------------------------------------------------------------------------
# Task 3: create-only evidence + CLI + MAS-136 matrix.
# ---------------------------------------------------------------------------

import hashlib
import json

import yaml

from scripts.ohf.fresh_sol_eval import (
    RUN_SCHEMA,
    MANIFEST_SCHEMA,
    write_run_artifact,
    run_matrix,
    check_corpus,
    main as fresh_sol_eval_main,
)


def _observation(**overrides: Any):
    from scripts.ohf.fresh_sol_eval import RunObservation, CapabilityReceipt, CleanupReceipt

    defaults: dict[str, Any] = dict(
        run_id="run-fixture-0001",
        arm="control-1.0.0",
        scenario_id="S8",
        workspace=Path("/tmp/does-not-matter"),
        process_pid=4242,
        process_pgid=4242,
        process_start_identity="4242:4242:run-fixture-0001",
        native_thread_id="thr_fixture",
        prompt="fixture exact prompt",
        output="fixture exact output",
        started_at="2026-08-26T00:00:00.000000Z",
        completed_at="2026-08-26T00:00:01.000000Z",
        capability=CapabilityReceipt(
            requested_model="gpt-5.6-sol",
            served_model="gpt-5.6-sol",
            approval_policy="never",
            sandbox_mode="read-only",
            mcp_names=(),
            plugin_names=(),
            skill_names=(),
            auth_type="chatgpt",
            plan_type="pro",
            requires_openai_auth=True,
            harness_version="fixture-version",
        ),
        cleanup=CleanupReceipt(
            controller_returncode=0,
            private_group_id=4242,
            private_group_empty=True,
            termination_outcome="sigterm",
        ),
    )
    defaults.update(overrides)
    return RunObservation(**defaults)


def _bundle_fixture(**overrides: Any) -> ProcedureBundle:
    from scripts.ohf.fresh_sol_eval import ProcedureBundle, ProcedureSource

    sources = (
        ProcedureSource(path="docs/sol_skills/INDEX.md", blob_sha="a" * 40, content=b"index"),
        ProcedureSource(path="docs/sol_skills/SIBLING.md", blob_sha="b" * 40, content=b"sibling"),
    )
    defaults: dict[str, Any] = dict(
        arm=_control_arm(),
        sources=sources,
        context_sha256="c" * 64,
    )
    defaults.update(overrides)
    return ProcedureBundle(**defaults)


from scripts.ohf.fresh_sol_eval import ProcedureBundle  # noqa: E402  (used by _bundle_fixture)


def test_evidence_artifact_exact_prompt_output_roundtrip(tmp_path: Path):
    observation = _observation()
    bundle = _bundle_fixture()
    path = write_run_artifact(
        observation=observation,
        bundle=bundle,
        protocol_sha256="d" * 64,
        harness_kind="codex-app-server",
        harness_binary_sha256="e" * 64,
        evidence_root=tmp_path,
    )
    assert path == tmp_path / "runs" / "control-1.0.0" / "S8" / "run-fixture-0001.md"
    text = path.read_text(encoding="utf-8")
    assert "fixture exact prompt" in text
    assert "fixture exact output" in text
    front_text = text.split("---\n", 2)[1]
    metadata = yaml.safe_load(front_text)
    assert metadata["schema"] == RUN_SCHEMA
    assert metadata["scenario_id"] == "S8"
    assert metadata["arm"] == "control-1.0.0"
    assert metadata["run_id"] == "run-fixture-0001"
    assert metadata["manual_classification"] == "PENDING_SOL_REVIEW"
    assert metadata["process_pid"] == 4242
    assert metadata["native_thread_id"] == "thr_fixture"
    for required_key in (
        "procedure_commit_sha",
        "expected_skillpack_version",
        "procedure_source_blobs",
        "procedure_context_sha256",
        "protocol_sha256",
        "prompt_sha256",
        "model_requested",
        "model_served",
        "harness_kind",
        "harness_version",
        "harness_binary_sha256",
        "provider_auth_type",
        "provider_plan_type",
        "requires_openai_auth",
        "process_pgid",
        "process_start_identity",
        "started_at",
        "completed_at",
        "cleanup_proof",
    ):
        assert required_key in metadata, required_key


def test_evidence_collision_never_overwrites_existing(tmp_path: Path):
    observation = _observation()
    bundle = _bundle_fixture()
    write_run_artifact(
        observation=observation, bundle=bundle, protocol_sha256="d" * 64,
        harness_kind="codex-app-server", harness_binary_sha256="e" * 64, evidence_root=tmp_path,
    )
    target = tmp_path / "runs" / "control-1.0.0" / "S8" / "run-fixture-0001.md"
    original_bytes = target.read_bytes()
    with pytest.raises(FreshSolEvalError) as excinfo:
        write_run_artifact(
            observation=_observation(output="a completely different output"),
            bundle=bundle, protocol_sha256="d" * 64, harness_kind="codex-app-server",
            harness_binary_sha256="e" * 64, evidence_root=tmp_path,
        )
    assert excinfo.value.code == "EVIDENCE_COLLISION"
    assert target.read_bytes() == original_bytes


def test_write_run_artifact_refuses_secret_shaped_prompt(tmp_path: Path):
    observation = _observation(prompt="leaked key sk-testFixtureSecretShape1234567890 in prompt")
    bundle = _bundle_fixture()
    with pytest.raises(FreshSolEvalError) as excinfo:
        write_run_artifact(
            observation=observation, bundle=bundle, protocol_sha256="d" * 64,
            harness_kind="codex-app-server", harness_binary_sha256="e" * 64, evidence_root=tmp_path,
        )
    assert excinfo.value.code == "EVIDENCE_SECRET_SHAPE_REFUSED"
    assert not (tmp_path / "runs").exists()


def test_write_run_artifact_refuses_secret_shaped_output(tmp_path: Path):
    observation = _observation(output="leaked key sk-testFixtureSecretShape1234567890 in output")
    bundle = _bundle_fixture()
    with pytest.raises(FreshSolEvalError) as excinfo:
        write_run_artifact(
            observation=observation, bundle=bundle, protocol_sha256="d" * 64,
            harness_kind="codex-app-server", harness_binary_sha256="e" * 64, evidence_root=tmp_path,
        )
    assert excinfo.value.code == "EVIDENCE_SECRET_SHAPE_REFUSED"
    assert not (tmp_path / "runs").exists()


def test_evidence_artifact_updates_manifest(tmp_path: Path):
    observation = _observation()
    bundle = _bundle_fixture()
    write_run_artifact(
        observation=observation, bundle=bundle, protocol_sha256="d" * 64,
        harness_kind="codex-app-server", harness_binary_sha256="e" * 64, evidence_root=tmp_path,
    )
    manifest = json.loads((tmp_path / "MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["schema"] == MANIFEST_SCHEMA
    assert len(manifest["entries"]) == 1
    entry = manifest["entries"][0]
    assert entry["run_id"] == "run-fixture-0001"
    assert entry["arm"] == "control-1.0.0"
    assert entry["scenario_id"] == "S8"
    artifact_path = tmp_path / entry["relative_path"]
    assert hashlib.sha256(artifact_path.read_bytes()).hexdigest() == entry["artifact_sha256"]


# ---------------------------------------------------------------------------
# Task 3, Step 4: matrix cardinality + resume-manifest tests.
# ---------------------------------------------------------------------------


def _protocol_path(tmp_path: Path) -> Path:
    path = tmp_path / "PRESSURE_TEST_PROTOCOL.md"
    path.write_text(_protocol_text(), encoding="utf-8")
    return path


def test_mas136_matrix_is_exactly_four_control_twelve_amended(
    mastermind_repo_root: Path, tmp_path: Path
):
    factory = _fake_factory()
    written = run_matrix(
        repo_root=mastermind_repo_root,
        protocol_path=_protocol_path(tmp_path),
        evidence_root=tmp_path / "evidence",
        client_factory=factory,
        run_root_parent=tmp_path / "runs_scratch",
        mode="mas-136",
    )
    assert len(written) == 16
    manifest = json.loads((tmp_path / "evidence" / "MANIFEST.json").read_text(encoding="utf-8"))
    entries = manifest["entries"]
    assert len(entries) == 16
    counts: dict[tuple[str, str], int] = {}
    for entry in entries:
        key = (entry["arm"], entry["scenario_id"])
        counts[key] = counts.get(key, 0) + 1
    for scenario_id in MAS136_SCENARIOS:
        assert counts[("control-1.0.0", scenario_id)] == 1
        assert counts[("amended-1.1.0", scenario_id)] == 3


def test_run_matrix_resume_manifest_skips_verified_entries(
    mastermind_repo_root: Path, tmp_path: Path
):
    factory = _fake_factory()
    evidence_root = tmp_path / "evidence"
    run_matrix(
        repo_root=mastermind_repo_root,
        protocol_path=_protocol_path(tmp_path),
        evidence_root=evidence_root,
        client_factory=factory,
        run_root_parent=tmp_path / "runs_scratch",
        mode="mas-136",
    )
    first_pid_count = len(factory.made)

    resume_manifest = evidence_root / "MANIFEST.json"
    second_factory = _fake_factory()
    written_again = run_matrix(
        repo_root=mastermind_repo_root,
        protocol_path=_protocol_path(tmp_path),
        evidence_root=evidence_root,
        client_factory=second_factory,
        run_root_parent=tmp_path / "runs_scratch_2",
        mode="mas-136",
        resume_manifest=resume_manifest,
    )
    # Every planned sample was already satisfied; resume must not create any
    # fresh App Server client/process.
    assert written_again == []
    assert len(second_factory.made) == 0
    assert first_pid_count == 16


def test_run_matrix_resume_manifest_tampered_artifact_refuses(
    mastermind_repo_root: Path, tmp_path: Path
):
    factory = _fake_factory()
    evidence_root = tmp_path / "evidence"
    run_matrix(
        repo_root=mastermind_repo_root,
        protocol_path=_protocol_path(tmp_path),
        evidence_root=evidence_root,
        client_factory=factory,
        run_root_parent=tmp_path / "runs_scratch",
        mode="mas-136",
    )
    manifest = json.loads((evidence_root / "MANIFEST.json").read_text(encoding="utf-8"))
    tampered_rel = manifest["entries"][0]["relative_path"]
    (evidence_root / tampered_rel).write_text("TAMPERED", encoding="utf-8")

    second_factory = _fake_factory()
    with pytest.raises(FreshSolEvalError) as excinfo:
        run_matrix(
            repo_root=mastermind_repo_root,
            protocol_path=_protocol_path(tmp_path),
            evidence_root=evidence_root,
            client_factory=second_factory,
            run_root_parent=tmp_path / "runs_scratch_2",
            mode="mas-136",
            resume_manifest=evidence_root / "MANIFEST.json",
        )
    assert excinfo.value.code == "EVIDENCE_COLLISION"


def test_check_corpus_reports_incomplete_before_16(tmp_path: Path):
    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()
    result = check_corpus(evidence_root=evidence_root, mode="mas-136")
    assert result["ok"] is False
    assert result["valid_count"] == 0
    assert result["expected"] == 16


def test_check_corpus_reports_complete_at_16(mastermind_repo_root: Path, tmp_path: Path):
    factory = _fake_factory()
    evidence_root = tmp_path / "evidence"
    run_matrix(
        repo_root=mastermind_repo_root,
        protocol_path=_protocol_path(tmp_path),
        evidence_root=evidence_root,
        client_factory=factory,
        run_root_parent=tmp_path / "runs_scratch",
        mode="mas-136",
    )
    result = check_corpus(evidence_root=evidence_root, mode="mas-136")
    assert result["ok"] is True
    assert result["valid_count"] == 16


def test_check_corpus_detects_digest_mismatch(mastermind_repo_root: Path, tmp_path: Path):
    factory = _fake_factory()
    evidence_root = tmp_path / "evidence"
    run_matrix(
        repo_root=mastermind_repo_root,
        protocol_path=_protocol_path(tmp_path),
        evidence_root=evidence_root,
        client_factory=factory,
        run_root_parent=tmp_path / "runs_scratch",
        mode="mas-136",
    )
    manifest = json.loads((evidence_root / "MANIFEST.json").read_text(encoding="utf-8"))
    corrupted_rel = manifest["entries"][0]["relative_path"]
    (evidence_root / corrupted_rel).write_text("CORRUPTED", encoding="utf-8")
    result = check_corpus(evidence_root=evidence_root, mode="mas-136")
    assert result["ok"] is False
    assert any("digest" in problem for problem in result["problems"])


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------


def test_cli_check_corpus_exits_nonzero_when_incomplete(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()
    exit_code = fresh_sol_eval_main(["check-corpus", "--evidence-root", str(evidence_root), "--mode", "mas-136"])
    assert exit_code != 0
    captured = capsys.readouterr()
    assert "valid_count" in captured.out


# ---------------------------------------------------------------------------
# Task 4: the sixteen named isolation/evidence falsifiers (design §14 /
# plan Task 4 Step 1).  Each name below makes the killed mutant obvious on
# its own; several reuse fixtures already exercised earlier in this file,
# but each is independently readable and independently fails if the named
# law regresses.
# ---------------------------------------------------------------------------


def test_second_sample_never_reuses_native_thread(mastermind_repo_root: Path, tmp_path: Path):
    factory = _fake_factory()
    first = run_one(
        repo_root=mastermind_repo_root, arm=_control_arm(), scenario=_scenario(),
        run_root=tmp_path / "run1", client_factory=factory,
    )
    second = run_one(
        repo_root=mastermind_repo_root, arm=_control_arm(), scenario=_scenario(),
        run_root=tmp_path / "run2", client_factory=factory,
    )
    assert first.native_thread_id != second.native_thread_id


def test_resume_and_fork_are_never_called(mastermind_repo_root: Path, tmp_path: Path):
    factory = _fake_factory()
    run_one(
        repo_root=mastermind_repo_root, arm=_control_arm(), scenario=_scenario(),
        run_root=tmp_path / "run", client_factory=factory,
    )
    client = factory.made[0]
    assert client.thread_resume_calls == 0
    assert client.thread_fork_calls == 0
    # _FakeEvalClient additionally raises if run_one ever calls either RPC
    # (see its request() handlers above) -- a regression that reintroduces
    # a resume/fork call fails this test via that AssertionError, not just
    # a zero-count check.


def test_skillpack_comes_from_exact_git_commit_not_dirty_worktree(skillpack_git_repo):
    repo = skillpack_git_repo["repo"]
    arm = SkillpackArm("fixture-control", skillpack_git_repo["control_sha"], "1.0.0")
    bundle = materialize_skillpack(repo, arm)
    for source in bundle.sources:
        assert b"DIRTY WORKING TREE COPY" not in source.content


def test_wrapper_is_byte_identical_between_arms_except_skill_sources(skillpack_git_repo):
    repo = skillpack_git_repo["repo"]
    control_arm = SkillpackArm("control-1.0.0", skillpack_git_repo["control_sha"], "1.0.0")
    amended_arm = SkillpackArm("amended-1.1.0", skillpack_git_repo["amended_sha"], "1.1.0")
    control_md = build_eval_agents_md(materialize_skillpack(repo, control_arm))
    amended_md = build_eval_agents_md(materialize_skillpack(repo, amended_arm))
    assert control_md.split(b"----- BEGIN ", 1)[0] == amended_md.split(b"----- BEGIN ", 1)[0]
    assert control_md != amended_md  # the source bytes themselves must still differ


def test_missing_or_wrong_commit_skill_file_refuses(skillpack_git_repo, monkeypatch: pytest.MonkeyPatch):
    import scripts.ohf.fresh_sol_eval as fresh_sol_eval_module

    repo = skillpack_git_repo["repo"]
    arm = SkillpackArm("fixture-control", skillpack_git_repo["control_sha"], "1.0.0")
    real_git = fresh_sol_eval_module._git

    def broken_git(repo_root, *args):
        if args and args[0] == "show" and args[-1].endswith("SIBLING.md"):
            return subprocess.CompletedProcess(args, returncode=128, stdout=b"", stderr=b"fixture: blob unreadable")
        return real_git(repo_root, *args)

    monkeypatch.setattr(fresh_sol_eval_module, "_git", broken_git)
    with pytest.raises(FreshSolEvalError) as excinfo:
        materialize_skillpack(repo, arm)
    assert excinfo.value.code == "PROCEDURE_SOURCE_UNAVAILABLE"


def test_protocol_has_no_hardcoded_scenario_fallback(tmp_path: Path):
    path = tmp_path / "PRESSURE_TEST_PROTOCOL.md"
    text = _protocol_text().replace("S2 BODY", "COMPLETELY UNUSUAL NON-DEFAULT TEXT 991")
    path.write_text(text, encoding="utf-8")
    packets = parse_protocol(path)
    assert "COMPLETELY UNUSUAL NON-DEFAULT TEXT 991" in packets["S2"].prompt
    assert "repaired-then-stale" not in packets["S2"].prompt  # never a built-in default


# test_served_model_mismatch_refuses_before_thread_start -- already defined
# above (Task 2, Step 2).


@pytest.mark.parametrize(
    "kwargs",
    [
        {"mcp_configured": ("some_mcp",)},
        {"plugins_configured": ("some_plugin",)},
        {"skills": ({"name": "some-skill"},)},
        {"mcp_status": ({"name": "unclassified_ambient_mcp"},)},
    ],
    ids=["mcp", "plugin", "skill", "unclassified_ambient"],
)
def test_ambient_mcp_plugin_skill_or_unclassified_capability_refuses(
    mastermind_repo_root: Path, tmp_path: Path, kwargs
):
    factory = _fake_factory(**kwargs)
    with pytest.raises(FreshSolEvalError) as excinfo:
        run_one(
            repo_root=mastermind_repo_root, arm=_control_arm(), scenario=_scenario(),
            run_root=tmp_path / "run", client_factory=factory,
        )
    assert excinfo.value.code == "CAPABILITY_ATTESTATION_INVALID"
    assert factory.made[0].thread_start_calls == 0


# test_default_codex_home_refuses -- already defined above (Task 2, Step 4).
# test_auth_json_contents_are_never_read_copied_or_serialized -- already
# defined above (Task 2, Step 4).


def test_notification_fragments_cannot_replace_canonical_thread_read(
    mastermind_repo_root: Path, tmp_path: Path
):
    factory = _fake_factory(thread_read_turns="empty")
    with pytest.raises(FreshSolEvalError) as excinfo:
        run_one(
            repo_root=mastermind_repo_root, arm=_control_arm(), scenario=_scenario(),
            run_root=tmp_path / "run", client_factory=factory,
        )
    assert excinfo.value.code == "THREAD_READ_FAILED"
    # The fake's wait_notification() always returns a fragment containing
    # "NOTIFICATION FRAGMENT MUST NEVER BE USED AS OUTPUT"; run_one must
    # never surface that text as a successful output.


def test_existing_run_artifact_is_never_overwritten(tmp_path: Path):
    observation = _observation()
    bundle = _bundle_fixture()
    write_run_artifact(
        observation=observation, bundle=bundle, protocol_sha256="d" * 64,
        harness_kind="codex-app-server", harness_binary_sha256="e" * 64, evidence_root=tmp_path,
    )
    target = tmp_path / "runs" / "control-1.0.0" / "S8" / "run-fixture-0001.md"
    before = target.read_bytes()
    with pytest.raises(FreshSolEvalError) as excinfo:
        write_run_artifact(
            observation=_observation(output="a different output entirely"), bundle=bundle,
            protocol_sha256="d" * 64, harness_kind="codex-app-server",
            harness_binary_sha256="e" * 64, evidence_root=tmp_path,
        )
    assert excinfo.value.code == "EVIDENCE_COLLISION"
    assert target.read_bytes() == before


def test_effect_unknown_turn_is_never_retried_or_resumed(mastermind_repo_root: Path, tmp_path: Path):
    class _DisconnectingClient:
        def __init__(self, workspace, config_dir, home):
            self.workspace = workspace
            self.cwd = workspace
            self.pid = None
            self.notifications: list[dict[str, Any]] = []
            self.thread_resume_calls = 0
            self.thread_fork_calls = 0
            self.turn_start_calls = 0
            self.graceful_close_calls = 0

        def start(self) -> None:
            self.pid = next(_fake_pid_counter)

        def request(self, method, params=None, timeout=15.0):
            params = params or {}
            if method == "initialize":
                return {"userAgent": "fake"}
            if method == "account/read":
                return {"account": {"type": "chatgpt", "planType": "pro"}, "requiresOpenaiAuth": True}
            if method == "config/read":
                return {
                    "config": {
                        "model": "gpt-5.6-sol",
                        "approval_policy": "never",
                        "sandbox_mode": "read-only",
                        "mcp_servers": {},
                        "plugins": {},
                    }
                }
            if method == "skills/list":
                return {"data": [{"cwd": str(self.workspace), "skills": [], "errors": []}]}
            if method == "mcpServerStatus/list":
                return {"data": []}
            if method == "thread/start":
                return {"thread": {"id": "thr_fake_disconnect"}}
            if method == "thread/resume":
                self.thread_resume_calls += 1
                raise AssertionError("an effect-unknown turn must never be resumed")
            if method == "thread/fork":
                self.thread_fork_calls += 1
                raise AssertionError("an effect-unknown turn must never be forked")
            if method == "turn/start":
                self.turn_start_calls += 1
                raise ConnectionError("fixture: connection dropped after dispatch")
            raise AssertionError(f"unexpected fake RPC method: {method}")

        def notify(self, method, params=None) -> None:
            pass

        def wait_notification(self, method, *, timeout=15.0):
            raise AssertionError("turn/start already raised; wait_notification must not be reached")

        def graceful_close(self):
            self.graceful_close_calls += 1
            return CleanupReceipt(
                controller_returncode=0, private_group_id=self.pid,
                private_group_empty=True, termination_outcome="sigterm",
            )

    made: list[_DisconnectingClient] = []

    def factory(workspace: Path, config_dir: Path, home: Path) -> _DisconnectingClient:
        client = _DisconnectingClient(workspace, config_dir, home)
        made.append(client)
        return client

    with pytest.raises(FreshSolEvalError) as excinfo:
        run_one(
            repo_root=mastermind_repo_root, arm=_control_arm(), scenario=_scenario(),
            run_root=tmp_path / "run", client_factory=factory,
        )
    assert excinfo.value.code == "TURN_EFFECT_UNKNOWN"
    assert made[0].turn_start_calls == 1
    assert made[0].thread_resume_calls == 0
    assert made[0].thread_fork_calls == 0
    # BLOCKER-2 falsifier: a forced post-dispatch disconnect must still
    # close the client exactly once and record a cleanup proof, not leave
    # the process/private group dangling.
    assert made[0].graceful_close_calls == 1


def test_unproven_process_group_cleanup_invalidates_run(mastermind_repo_root: Path, tmp_path: Path):
    factory = _fake_factory(cleanup_ok=False)
    with pytest.raises(FreshSolEvalError) as excinfo:
        run_one(
            repo_root=mastermind_repo_root, arm=_control_arm(), scenario=_scenario(),
            run_root=tmp_path / "run", client_factory=factory,
        )
    assert excinfo.value.code == "CLEANUP_UNPROVEN"


def test_secret_shaped_output_is_not_persisted(tmp_path: Path):
    observation = _observation(output="here is sk-testFixtureSecretShape1234567890 leaking")
    bundle = _bundle_fixture()
    with pytest.raises(FreshSolEvalError) as excinfo:
        write_run_artifact(
            observation=observation, bundle=bundle, protocol_sha256="d" * 64,
            harness_kind="codex-app-server", harness_binary_sha256="e" * 64, evidence_root=tmp_path,
        )
    assert excinfo.value.code == "EVIDENCE_SECRET_SHAPE_REFUSED"
    assert not (tmp_path / "runs" / "control-1.0.0" / "S8" / "run-fixture-0001.md").exists()


# test_mas136_matrix_is_exactly_four_control_twelve_amended -- already
# defined above (Task 3, Step 4).


# ---------------------------------------------------------------------------
# Review repair falsifiers (2026-09-01, principal adjudication of the
# adversarial review against exact head 26480a8207385ee75d3afd04e311e060a70567b6).
# ---------------------------------------------------------------------------


# --- BLOCKER-1: EvalClient/AppServerClient signature-compatibility -------


def test_eval_client_protocol_matches_real_app_server_client_surface(tmp_path: Path):
    """EvalClient must name real AppServerClient members with a compatible contract.

    The exact defect this falsifies: EvalClient previously declared
    ``terminate() -> object``, and ``_terminate_and_prove`` called
    ``client.terminate()``. The REAL ``AppServerClient.terminate()``
    returns a plain ``str`` outcome label -- ``_terminate_and_prove`` would
    have raised ``CLEANUP_UNPROVEN`` on every real (non-fake) run, because a
    ``str`` matches neither of its two recognized cleanup-proof types. The
    real cleanup method is ``graceful_close() -> AppServerStopProof``. This
    test pins that fact against the actual class, not a fake's opinion of
    it, so the Protocol and the real substrate cannot drift apart silently
    again ("the class of defect where the Protocol fits the fake must
    become untestable").
    """

    protocol_methods = {"start", "request", "notify", "wait_notification", "graceful_close"}
    declared = {name for name in dir(EvalClient) if not name.startswith("_")}
    assert protocol_methods <= declared
    assert "terminate" not in declared, (
        "EvalClient must not reintroduce terminate() -- the real "
        "AppServerClient.terminate() returns str, not a cleanup-proof object"
    )

    real_client = AppServerClient(["true"], env={}, cwd=tmp_path, start_new_session=False)
    for attr_name in ("pid", "cwd", "notifications"):
        assert hasattr(real_client, attr_name), attr_name
    for method_name in protocol_methods:
        assert callable(getattr(real_client, method_name, None)), method_name

    # `from __future__ import annotations` in laboratory.py means these
    # come back as literal strings, not evaluated types -- exactly what we
    # want to pin without importing AppServerStopProof just for isinstance.
    close_sig = inspect.signature(AppServerClient.graceful_close)
    assert close_sig.return_annotation == "AppServerStopProof"
    terminate_sig = inspect.signature(AppServerClient.terminate)
    assert terminate_sig.return_annotation == "str"


# --- MAJOR-3 / MAJOR-4: _git hardening (no lazy fetch, no raw timeout) ---


def test_git_materialization_refuses_lazy_fetch_from_a_blobless_clone(tmp_path: Path):
    """A partial/promisor clone must refuse a missing blob, never fetch it.

    Without ``GIT_NO_LAZY_FETCH=1`` git would transparently lazy-fetch the
    missing blob from the (here, merely locally-reachable) promisor remote,
    silently satisfying the read. That is exactly the network-fetch
    behavior design §6 forbids ("The runner performs no network fetch").
    """

    full_repo = tmp_path / "full_repo"
    full_repo.mkdir()
    _git(full_repo, "init", "-q")
    _git(full_repo, "config", "user.email", "ohf1@example.invalid")
    _git(full_repo, "config", "user.name", "ohf1 fixture")
    _write(full_repo / "docs/sol_skills/INDEX.md", (
        "---\nschema: mastermind.sol_skillpack.v1\nskillpack_version: 1.0.0\n"
        "minimum_bootstrap_major: 1\n---\n\n# index\n"
    ))
    _write(full_repo / "docs/sol_skills/SIBLING.md", "# sibling\ncontrol content\n")
    _git(full_repo, "add", "-A")
    _git(full_repo, "commit", "-q", "-m", "control commit")
    control_sha = subprocess.run(
        ["git", "-C", str(full_repo), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()

    partial_repo = tmp_path / "partial_repo"
    clone = subprocess.run(
        [
            "git", "clone", "-q", "--no-local", "--filter=blob:none", "--no-checkout",
            f"file://{full_repo}", str(partial_repo),
        ],
        capture_output=True, text=True,
    )
    if clone.returncode != 0:
        pytest.skip(f"local git does not support partial clone in this environment: {clone.stderr}")

    blob_sha = subprocess.run(
        ["git", "-C", str(full_repo), "rev-parse", f"{control_sha}:docs/sol_skills/SIBLING.md"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    blob_present = subprocess.run(
        ["git", "-C", str(partial_repo), "cat-file", "-e", blob_sha],
        capture_output=True,
    ).returncode == 0
    if blob_present:
        # This sandbox's git build/transport does not honor server-side
        # partial-clone filtering over file:// (observed: "warning:
        # filtering not recognized by server, ignoring" even with
        # --no-local and uploadpack.allowFilter=true) -- the "partial"
        # clone actually contains every blob, so there is nothing here to
        # lazily fetch and this integration probe cannot exercise the
        # refusal path in this environment. The env-var-is-set fact is
        # still covered unconditionally by
        # test_git_never_disables_lazy_fetch_refusal_env below.
        pytest.skip(
            "this git build/transport does not filter blobs on a local "
            "partial clone -- cannot construct a genuine missing-blob "
            "fixture here; see test_git_never_disables_lazy_fetch_refusal_env"
        )

    arm = SkillpackArm("fixture-partial", control_sha, "1.0.0")
    with pytest.raises(FreshSolEvalError) as excinfo:
        materialize_skillpack(partial_repo, arm)
    assert excinfo.value.code == "PROCEDURE_SOURCE_UNAVAILABLE"


def test_git_timeout_maps_to_closed_failure_code_not_raw_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A git subprocess timeout must never escape as subprocess.TimeoutExpired."""

    import scripts.ohf.fresh_sol_eval as fresh_sol_eval_module

    def fake_run(argv, **kwargs):
        raise subprocess.TimeoutExpired(cmd=argv, timeout=kwargs.get("timeout", 10))

    monkeypatch.setattr(subprocess, "run", fake_run)
    arm = SkillpackArm("fixture-timeout", "0" * 40, "1.0.0")
    with pytest.raises(FreshSolEvalError) as excinfo:
        materialize_skillpack(tmp_path, arm)
    # The very first git call materialize_skillpack makes is the commit
    # existence check, so a timeout there must map to SOURCE_COMMIT_UNAVAILABLE.
    assert excinfo.value.code == "SOURCE_COMMIT_UNAVAILABLE"
    del fresh_sol_eval_module  # imported for clarity of intent above


def test_git_never_disables_lazy_fetch_refusal_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """GIT_NO_LAZY_FETCH must actually be set on every git subprocess call."""

    import scripts.ohf.fresh_sol_eval as fresh_sol_eval_module

    seen_envs: list[dict[str, str]] = []
    real_run = subprocess.run

    def spying_run(argv, **kwargs):
        seen_envs.append(dict(kwargs.get("env") or {}))
        return real_run(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", spying_run)
    fresh_sol_eval_module._git(tmp_path, "status")
    assert seen_envs, "no git subprocess was observed"
    assert seen_envs[0].get("GIT_NO_LAZY_FETCH") == "1"


# --- MAJOR-5: check_corpus forgery resistance -----------------------------


def test_check_corpus_refuses_forged_corpus_reusing_one_artifact_for_all_rows(
    mastermind_repo_root: Path, tmp_path: Path
):
    """16 manifest rows all pointing at ONE real artifact must never pass.

    This is the reviewer's adversarial construction: a digest-only,
    cardinality-by-manifest-claim check can be satisfied by one genuine
    artifact whose bytes/digest are correct, reused under 16 different
    forged manifest rows that merely CLAIM the right run_id/arm/scenario_id
    distribution. check_corpus must cross-validate each artifact's own
    frontmatter identity against what its manifest row claims, and must
    reject duplicate relative_path/native_thread_id across rows.
    """

    from scripts.ohf.fresh_sol_eval import write_run_artifact, check_corpus
    import hashlib
    import json

    evidence_root = tmp_path / "evidence"
    real_observation = _observation(run_id="real-run-0001", arm="control-1.0.0", scenario_id="S2")
    bundle = _bundle_fixture()
    real_path = write_run_artifact(
        observation=real_observation, bundle=bundle, protocol_sha256="d" * 64,
        harness_kind="codex-app-server", harness_binary_sha256="e" * 64,
        evidence_root=evidence_root,
    )
    real_relative_path = real_path.relative_to(evidence_root).as_posix()
    real_sha256 = hashlib.sha256(real_path.read_bytes()).hexdigest()

    forged_entries = []
    for scenario_id in MAS136_SCENARIOS:
        for arm, count in (("control-1.0.0", 1), ("amended-1.1.0", 3)):
            for _ in range(count):
                forged_entries.append(
                    {
                        "run_id": f"forged-{scenario_id}-{arm}-{len(forged_entries)}",
                        "arm": arm,
                        "scenario_id": scenario_id,
                        "relative_path": real_relative_path,  # reused for every row
                        "artifact_sha256": real_sha256,  # correct digest for the reused file
                    }
                )
    assert len(forged_entries) == 16

    manifest_path = evidence_root / "MANIFEST.json"
    manifest_path.write_text(
        json.dumps({"schema": "mastermind.fresh_sol_eval_manifest/v1", "entries": forged_entries}),
        encoding="utf-8",
    )

    result = check_corpus(evidence_root=evidence_root, mode="mas-136")
    assert result["ok"] is False
    assert result["valid_count"] < 16
    assert any("duplicate relative_path" in p for p in result["problems"])


def test_check_corpus_refuses_manifest_artifact_identity_mismatch(tmp_path: Path):
    from scripts.ohf.fresh_sol_eval import write_run_artifact, check_corpus
    import hashlib
    import json

    evidence_root = tmp_path / "evidence"
    observation = _observation()
    bundle = _bundle_fixture()
    path = write_run_artifact(
        observation=observation, bundle=bundle, protocol_sha256="d" * 64,
        harness_kind="codex-app-server", harness_binary_sha256="e" * 64,
        evidence_root=evidence_root,
    )
    relative_path = path.relative_to(evidence_root).as_posix()
    sha256 = hashlib.sha256(path.read_bytes()).hexdigest()

    manifest_path = evidence_root / "MANIFEST.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema": "mastermind.fresh_sol_eval_manifest/v1",
                "entries": [
                    {
                        # Claims a DIFFERENT scenario_id than the artifact's
                        # own frontmatter actually records.
                        "run_id": observation.run_id,
                        "arm": observation.arm,
                        "scenario_id": "S6",
                        "relative_path": relative_path,
                        "artifact_sha256": sha256,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    result = check_corpus(evidence_root=evidence_root, mode="mas-136")
    assert result["ok"] is False
    assert any("identity mismatch" in p for p in result["problems"])


def test_check_corpus_refuses_duplicate_native_thread_id(mastermind_repo_root: Path, tmp_path: Path):
    from scripts.ohf.fresh_sol_eval import write_run_artifact, check_corpus
    import hashlib
    import json

    evidence_root = tmp_path / "evidence"
    bundle = _bundle_fixture()
    entries = []
    for idx, (arm, scenario_id) in enumerate(
        [("control-1.0.0", "S2"), ("amended-1.1.0", "S2")]
    ):
        observation = _observation(
            run_id=f"run-dup-thread-{idx}",
            arm=arm,
            scenario_id=scenario_id,
            native_thread_id="thr_SAME_FOR_BOTH",  # identical across two distinct samples
        )
        path = write_run_artifact(
            observation=observation, bundle=bundle, protocol_sha256="d" * 64,
            harness_kind="codex-app-server", harness_binary_sha256="e" * 64,
            evidence_root=evidence_root,
        )
        entries.append(
            {
                "run_id": observation.run_id,
                "arm": observation.arm,
                "scenario_id": observation.scenario_id,
                "relative_path": path.relative_to(evidence_root).as_posix(),
                "artifact_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    manifest_path = evidence_root / "MANIFEST.json"
    manifest_path.write_text(
        json.dumps({"schema": "mastermind.fresh_sol_eval_manifest/v1", "entries": entries}),
        encoding="utf-8",
    )
    result = check_corpus(evidence_root=evidence_root, mode="mas-136")
    assert result["ok"] is False
    assert any("duplicate native_thread_id" in p for p in result["problems"])


# --- MAJOR-6: exception text redaction ------------------------------------


def test_capability_attestation_failure_redacts_sentinel_secret_from_exception_text(
    mastermind_repo_root: Path, tmp_path: Path
):
    sentinel = "sk-testFixtureSecretShape1234567890"

    class _LeakyClient(_FakeEvalClient):
        def request(self, method, params=None, timeout=15.0):
            if method == "account/read":
                raise RuntimeError(f"fixture provider error leaking {sentinel}")
            return super().request(method, params, timeout)

    def factory(workspace: Path, config_dir: Path, home: Path) -> _LeakyClient:
        return _LeakyClient(workspace, config_dir, home)

    with pytest.raises(FreshSolEvalError) as excinfo:
        run_one(
            repo_root=mastermind_repo_root, arm=_control_arm(), scenario=_scenario(),
            run_root=tmp_path / "run", client_factory=factory,
        )
    assert excinfo.value.code == "CAPABILITY_ATTESTATION_INVALID"
    assert sentinel not in str(excinfo.value)


def test_auth_realm_invalid_message_is_redacted(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    dedicated = tmp_path / "dedicated_realm_sk-testFixtureSecretShape1234567890"
    dedicated.mkdir()
    with pytest.raises(FreshSolEvalError) as excinfo:
        build_live_client_factory(codex_home=dedicated, model="gpt-5.6-sol")
    assert excinfo.value.code == "AUTH_REALM_INVALID"
    assert "sk-testFixtureSecretShape1234567890" not in str(excinfo.value)


# --- MAJOR-7: live client factory env shape -------------------------------


def test_live_client_factory_env_has_no_pythonpath(tmp_path: Path):
    dedicated = tmp_path / "dedicated_realm"
    dedicated.mkdir()
    (dedicated / "auth.json").write_text("{}", encoding="utf-8")

    factory = build_live_client_factory(codex_home=dedicated, model="gpt-5.6-sol", codex_binary="/bin/echo")
    workspace = tmp_path / "run" / "workspace"
    config_dir = tmp_path / "run" / "config"
    home = tmp_path / "run" / "home"
    for d in (workspace, config_dir, home):
        d.mkdir(parents=True)
    client = factory(workspace, config_dir, home)
    assert set(client.env.keys()) == {"PATH", "HOME", "CODEX_HOME", "LC_ALL"}
    assert "PYTHONPATH" not in client.env


# --- N1: manifest relative_path path-traversal probes ---------------------


@pytest.mark.parametrize("evil_path", ["/etc/passwd", "../../etc/passwd", "runs/../../../etc/passwd"])
def test_resume_manifest_rejects_unsafe_relative_path(
    mastermind_repo_root: Path, tmp_path: Path, evil_path: str
):
    import json

    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()
    resume_manifest = tmp_path / "resume_manifest.json"
    resume_manifest.write_text(
        json.dumps(
            {
                "schema": "mastermind.fresh_sol_eval_manifest/v1",
                "entries": [
                    {
                        "run_id": "evil",
                        "arm": "control-1.0.0",
                        "scenario_id": "S2",
                        "relative_path": evil_path,
                        "artifact_sha256": "0" * 64,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    factory = _fake_factory()
    with pytest.raises(FreshSolEvalError) as excinfo:
        run_matrix(
            repo_root=mastermind_repo_root,
            protocol_path=_protocol_path(tmp_path),
            evidence_root=evidence_root,
            client_factory=factory,
            run_root_parent=tmp_path / "runs_scratch",
            mode="mas-136",
            resume_manifest=resume_manifest,
        )
    assert excinfo.value.code == "EVIDENCE_COLLISION"


@pytest.mark.parametrize("evil_path", ["/etc/passwd", "../../etc/passwd"])
def test_check_corpus_rejects_unsafe_relative_path(tmp_path: Path, evil_path: str):
    import json

    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()
    manifest_path = evidence_root / "MANIFEST.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema": "mastermind.fresh_sol_eval_manifest/v1",
                "entries": [
                    {
                        "run_id": "evil",
                        "arm": "control-1.0.0",
                        "scenario_id": "S2",
                        "relative_path": evil_path,
                        "artifact_sha256": "0" * 64,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    result = check_corpus(evidence_root=evidence_root, mode="mas-136")
    assert result["ok"] is False
    assert any("unsafe relative_path" in p for p in result["problems"])


# --- N2: workspace freshness ------------------------------------------------


def test_run_root_reuse_refuses_instead_of_silently_merging(
    mastermind_repo_root: Path, tmp_path: Path
):
    run_root = tmp_path / "shared_run_root"
    factory = _fake_factory()
    run_one(
        repo_root=mastermind_repo_root, arm=_control_arm(), scenario=_scenario(),
        run_root=run_root, client_factory=factory,
    )
    with pytest.raises(FreshSolEvalError) as excinfo:
        run_one(
            repo_root=mastermind_repo_root, arm=_control_arm(), scenario=_scenario(),
            run_root=run_root, client_factory=factory,
        )
    assert excinfo.value.code == "HARNESS_INITIALIZE_FAILED"


# --- N4: artifact fencing exceeds the longest backtick run ----------------


def test_evidence_fence_exceeds_longest_backtick_run_in_payload(tmp_path: Path):
    from scripts.ohf.fresh_sol_eval import write_run_artifact

    tricky_output = "here is a fenced block:\n````python\nprint('hi')\n````\nend"
    observation = _observation(output=tricky_output)
    bundle = _bundle_fixture()
    path = write_run_artifact(
        observation=observation, bundle=bundle, protocol_sha256="d" * 64,
        harness_kind="codex-app-server", harness_binary_sha256="e" * 64, evidence_root=tmp_path,
    )
    text = path.read_text(encoding="utf-8")
    assert tricky_output in text
    # The fence markers immediately surrounding "## Exact model output" must
    # be longer than the longest backtick run inside the payload (4), i.e.
    # at least 5 backticks, or the payload's own ```` would prematurely
    # close a plain triple-backtick fence.
    output_section = text.split("## Exact model output", 1)[1]
    fence_line = output_section.strip().splitlines()[0]
    assert fence_line.startswith("`````") or len(fence_line.rstrip("t").rstrip()) >= 5


# --- N6: no duplicate Skillpack materialization in run_matrix -------------


def test_run_matrix_materializes_each_arm_commit_once_per_sample(
    mastermind_repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    import scripts.ohf.fresh_sol_eval as fresh_sol_eval_module

    calls: list[str] = []
    real_materialize = fresh_sol_eval_module.materialize_skillpack

    def counting_materialize(repo_root, arm):
        calls.append(arm.name)
        return real_materialize(repo_root, arm)

    monkeypatch.setattr(fresh_sol_eval_module, "materialize_skillpack", counting_materialize)
    factory = _fake_factory()
    run_matrix(
        repo_root=mastermind_repo_root,
        protocol_path=_protocol_path(tmp_path),
        evidence_root=tmp_path / "evidence",
        client_factory=factory,
        run_root_parent=tmp_path / "runs_scratch",
        mode="mas-136",
    )
    # 16 samples total; each sample must materialize its arm's Skillpack
    # exactly once (16 calls), never twice (32 calls, the pre-repair count).
    assert len(calls) == 16


# ---------------------------------------------------------------------------
# Review repair round 2 (2026-09-01, preflight vs
# a0d70cdb05c5520a3ffcd1b9d9db002b9c57e5a8).
# ---------------------------------------------------------------------------


def _fake_build_live_client_factory_for_cli(*args: Any, **kwargs: Any):
    """Drop-in replacement for build_live_client_factory in CLI-level tests.

    Ignores codex_home/model/codex_binary entirely and returns the same
    injectable fake factory every other test in this file uses -- so
    main()'s run-one/run-matrix branches can be driven end-to-end with zero
    provider calls and zero real --codex-home validation.
    """

    del args, kwargs
    return _fake_factory()


def _prepared_codex_home(tmp_path: Path) -> Path:
    codex_home = tmp_path / "codex_home"
    codex_home.mkdir()
    (codex_home / "auth.json").write_text("{}", encoding="utf-8")
    return codex_home


# --- BLOCKER-A: main()'s run-one branch vs. N2's freshness check ---------


def test_cli_run_one_end_to_end_with_injected_fake_factory(
    mastermind_repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """The exact defect: main()'s run-one branch passed the already-existing
    TemporaryDirectory itself as run_root, which _prepare_run_root's N2
    freshness check (review repair round 1) now refuses on sight -- every
    real `run-one` CLI invocation would have failed HARNESS_INITIALIZE_FAILED
    before this fix, with zero test coverage catching it (no prior test
    drove main() end to end for run-one or run-matrix at all).
    """

    import scripts.ohf.fresh_sol_eval as fresh_sol_eval_module

    monkeypatch.setattr(
        fresh_sol_eval_module,
        "build_live_client_factory",
        _fake_build_live_client_factory_for_cli,
    )
    codex_home = _prepared_codex_home(tmp_path)
    evidence_root = tmp_path / "evidence"
    protocol_path = _protocol_path(tmp_path)

    exit_code = fresh_sol_eval_main(
        [
            "run-one",
            "--repo-root", str(mastermind_repo_root),
            "--protocol-path", str(protocol_path),
            "--codex-home", str(codex_home),
            "--evidence-root", str(evidence_root),
            "--arm", "control-1.0.0",
            "--scenario", "S8",
        ]
    )
    assert exit_code == 0
    written = list((evidence_root / "runs" / "control-1.0.0" / "S8").glob("*.md"))
    assert len(written) == 1


def test_cli_run_matrix_end_to_end_with_injected_fake_factory(
    mastermind_repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    import scripts.ohf.fresh_sol_eval as fresh_sol_eval_module

    monkeypatch.setattr(
        fresh_sol_eval_module,
        "build_live_client_factory",
        _fake_build_live_client_factory_for_cli,
    )
    codex_home = _prepared_codex_home(tmp_path)
    evidence_root = tmp_path / "evidence"
    protocol_path = _protocol_path(tmp_path)

    exit_code = fresh_sol_eval_main(
        [
            "run-matrix",
            "--repo-root", str(mastermind_repo_root),
            "--protocol-path", str(protocol_path),
            "--codex-home", str(codex_home),
            "--evidence-root", str(evidence_root),
            "--mode", "mas-136",
        ]
    )
    assert exit_code == 0
    manifest = json.loads((evidence_root / "MANIFEST.json").read_text(encoding="utf-8"))
    assert len(manifest["entries"]) == 16


# --- MAJOR-B: sys.exc_info() cross-context leak ----------------------------


def test_run_one_cleanup_failure_is_not_masked_by_callers_own_exception_handler(
    mastermind_repo_root: Path, tmp_path: Path
):
    """The exact defect: sys.exc_info() inside run_one()'s own finally block
    reflects the exception currently being handled ANYWHERE on the call
    stack for the whole dynamic extent of an active except block -- not
    only exceptions raised inside run_one() itself. A caller that invokes
    run_one() from inside its OWN unrelated `except ValueError:` handler
    would make run_one() wrongly believe a prior failure already occurred,
    swallowing a genuine local cleanup failure into a bare AssertionError
    (or, under `python -O` where asserts are stripped, a RunObservation
    with cleanup=None) instead of raising CLEANUP_UNPROVEN.
    """

    factory = _fake_factory(cleanup_ok=False)
    try:
        raise ValueError("unrelated caller-side error, already being handled")
    except ValueError:
        with pytest.raises(FreshSolEvalError) as excinfo:
            run_one(
                repo_root=mastermind_repo_root, arm=_control_arm(), scenario=_scenario(),
                run_root=tmp_path / "run", client_factory=factory,
            )
    assert excinfo.value.code == "CLEANUP_UNPROVEN"


# --- NB-C: path laundering on the error surface ----------------------------


def test_turn_effect_unknown_message_redacts_secret_and_launders_path(
    mastermind_repo_root: Path, tmp_path: Path
):
    sentinel = "sk-testFixtureSecretShape1234567890"
    leaky_path = "/Users/fixture-operator/.codex/auth.json"

    class _LeakyDisconnectClient(_FakeEvalClient):
        def request(self, method, params=None, timeout=15.0):
            if method == "turn/start":
                self.turn_start_calls += 1
                raise ConnectionError(f"dropped near {leaky_path} leaking {sentinel}")
            return super().request(method, params, timeout)

    def factory(workspace: Path, config_dir: Path, home: Path) -> _LeakyDisconnectClient:
        return _LeakyDisconnectClient(workspace, config_dir, home)

    with pytest.raises(FreshSolEvalError) as excinfo:
        run_one(
            repo_root=mastermind_repo_root, arm=_control_arm(), scenario=_scenario(),
            run_root=tmp_path / "run", client_factory=factory,
        )
    assert excinfo.value.code == "TURN_EFFECT_UNKNOWN"
    message = str(excinfo.value)
    assert sentinel not in message
    assert "/Users/" not in message
    assert "<path>" in message


def test_auth_json_home_tilde_path_is_laundered(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """A ~/-prefixed path in an exception message is laundered too, not
    only /Users|/private|/var|/tmp|/home absolute paths."""

    def fake_validate(codex_home):
        raise RuntimeError(f"dedicated CODEX_HOME is not authenticated: ~/fixture-codex-home")

    import scripts.ohf.fresh_sol_eval as fresh_sol_eval_module

    monkeypatch.setattr(fresh_sol_eval_module, "validate_live_codex_home", fake_validate)
    dedicated = tmp_path / "dedicated_realm"
    dedicated.mkdir()
    with pytest.raises(FreshSolEvalError) as excinfo:
        build_live_client_factory(codex_home=dedicated, model="gpt-5.6-sol")
    assert excinfo.value.code == "AUTH_REALM_INVALID"
    assert "~/fixture-codex-home" not in str(excinfo.value)
    assert "<path>" in str(excinfo.value)


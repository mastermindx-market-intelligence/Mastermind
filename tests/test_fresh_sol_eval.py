"""Deterministic fake-backend/falsifier coverage for the fresh-Sol F0 harness.

No provider credentials, no live provider calls.  Every App Server interaction
here goes through an injected in-process fake client -- see ``_FakeEvalClient``
below -- so these tests never spawn ``scripts.ohf.fake_app_server`` as a
subprocess.
"""
from __future__ import annotations

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
    materialize_skillpack,
    parse_protocol,
    build_eval_agents_md,
    run_one,
    build_live_client_factory,
)


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
# request, notify, wait_notification, terminate).  It never spawns a
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
        self.thread_start_calls = 0
        self.thread_resume_calls = 0
        self.thread_fork_calls = 0
        self.turn_start_calls = 0
        self.terminate_calls = 0

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
        return {
            "method": method,
            "params": {
                "turn": {
                    "id": "turn_fake",
                    "text": "NOTIFICATION FRAGMENT MUST NEVER BE USED AS OUTPUT",
                }
            },
        }

    def terminate(self) -> object:
        self.terminate_calls += 1
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


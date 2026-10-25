"""Unit tests for the pinned Rakazo topology readiness launcher.

Synthetic daemon fixtures are labeled and are not topology proof. Compressed
upstream bytes at the bottom of this file are the pinned donor blobs; tests
check their SHA-256 before applying the reviewed patch.
"""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

import pytest

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "integrations"
    / "rakazo_reference_journey"
    / "run.py"
)


def load_module():
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("rakazo_reference_journey_run", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


journey = load_module()


def upstream_bytes():
    topology = zlib.decompress(base64.b64decode(TOPOLOGY_Z64))
    compose = zlib.decompress(base64.b64decode(COMPOSE_Z64))
    assert hashlib.sha256(topology).hexdigest() == journey.UPSTREAM_TOPOLOGY_SHA256
    assert hashlib.sha256(compose).hexdigest() == journey.UPSTREAM_COMPOSE_SHA256
    return topology, compose


def git_env(home: Path) -> dict[str, str]:
    return {
        "PATH": "/usr/bin:/bin",
        "HOME": str(home),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_COUNT": "0",
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    }


def make_unrelated_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    env = git_env(path)
    git = "/usr/bin/git"
    subprocess.check_call([git, "init"], cwd=path, env=env)
    (path / "a.txt").write_text("unrelated\n", encoding="utf-8")
    subprocess.check_call([git, "add", "a.txt"], cwd=path, env=env)
    subprocess.check_call([git, "commit", "-m", "unrelated"], cwd=path, env=env)
    git_dir = path / ".git"
    assert git_dir.is_dir() and not git_dir.is_symlink()
    return git_dir.resolve()


def test_import_does_not_arm_execution_or_admit_a_daemon():
    assert journey.EXECUTION_AUTHORIZED is False
    assert journey.ADMITTED_DAEMON_IDS == frozenset()
    assert journey.main is not None


def test_closed_env_rejects_caller_injection(tmp_path):
    owned = journey.create_owned_root()
    try:
        env = journey.build_closed_env(owned)
        assert env["PATH"] == "/usr/bin:/bin"
        assert "NODE_OPTIONS" not in env
        assert "DOCKER_HOST" not in env
        assert env["GIT_CONFIG_COUNT"] == "0"
        dirty = dict(env)
        dirty["NODE_OPTIONS"] = "--canary"
        with pytest.raises(journey.Refusal) as caught:
            journey.assert_closed_env(dirty)
        assert caught.value.reason == "environment_not_closed"
    finally:
        assert journey.remove_owned_root(owned) == "REMOVED"


def test_probe_first_child_drops_canaries():
    canaries = {
        "NODE_OPTIONS": "--canary-node-options",
        "NPM_CONFIG_USERCONFIG": "/tmp/canary-npmrc",
        "npm_config_globalconfig": "/tmp/canary-npm-global",
        "OPENAI_API_KEY": "canary-not-a-real-secret",
        "HTTP_PROXY": "http://127.0.0.1:9",
        "DOCKER_HOST": "tcp://127.0.0.1:9",
        "DOCKER_CONTEXT": "canary-context",
        "GIT_CONFIG_COUNT": "4",
        "GIT_CONFIG_KEY_0": "core.hooksPath",
        "GIT_CONFIG_VALUE_0": "/tmp/canary-hooks",
        "OIDC_CLIENT_SECRET": "canary-oidc",
        "ALL_PROXY": "http://127.0.0.1:9",
    }
    env = dict(os.environ)
    env.update(canaries)
    completed = subprocess.run(
        [sys.executable, "-B", str(MODULE_PATH), "probe-first-child"],
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    child = json.loads(completed.stdout)
    rendered = "".join(str(item) for item in child.values())
    for key, value in canaries.items():
        assert child.get(key) != value
        if len(value) >= 8:
            assert value not in rendered
    assert set(child) == set(journey.ALLOWED_ENV_KEYS)
    assert "NODE_OPTIONS" not in child
    assert "DOCKER_HOST" not in child
    assert child["PATH"] == "/usr/bin:/bin"
    assert child["GIT_CONFIG_COUNT"] == "0"


def test_wrong_pin_refuses_before_donor_execution(tmp_path):
    git_dir = make_unrelated_repo(tmp_path / "repo")
    calls = []
    sink = {
        "NODE_OPTIONS": "--canary-node-options",
        "DOCKER_HOST": "tcp://127.0.0.1:9",
        "OPENAI_API_KEY": "canary-not-a-real-secret",
    }

    def runner(argv, **kwargs):
        calls.append(tuple(argv))
        assert "NODE_OPTIONS" not in kwargs["env"]
        assert kwargs["env"]["PATH"] == "/usr/bin:/bin"
        return journey.default_spawn(argv, **kwargs)

    receipt = journey.run_readiness(object_store=git_dir, environ=sink, spawn=runner)
    assert receipt["status"] == "READINESS_BLOCKED"
    assert receipt["source"]["state"] == "REFUSED"
    assert receipt["source"]["reason"] == "pin_not_present"
    assert receipt["execution"]["spawned"] is False
    assert receipt["execution"]["state"] == "NOT_RUN"
    assert receipt["cleanup"]["resource_cleanup"] == "NOT_RUN"
    assert receipt["cleanup"]["owned_root"] == "REMOVED"
    assert journey.receipt_problems(receipt) == []
    flat = [item for argv in calls for item in argv]
    assert "pnpm" not in flat
    assert "compose" not in flat
    assert not any(item.endswith("topology.ts") for item in flat)
    assert any("--no-replace-objects" in argv for argv in calls)
    assert any("core.fsmonitor=false" in item for argv in calls for item in argv)
    assert any("core.hooksPath=/dev/null" in item for argv in calls for item in argv)
    assert "NODE_OPTIONS" not in sink
    assert sink["GIT_CONFIG_COUNT"] == "0"


def test_fsmonitor_and_hook_sentinels_do_not_run(tmp_path):
    repo = tmp_path / "repo"
    git_dir = make_unrelated_repo(repo)
    sentinel = tmp_path / "sentinel"
    script = tmp_path / "fsmonitor.sh"
    script.write_text(f"#!/bin/sh\ntouch {sentinel}\n", encoding="utf-8")
    script.chmod(0o755)
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    hook = hooks / "pre-commit"
    hook.write_text(f"#!/bin/sh\ntouch {sentinel}\n", encoding="utf-8")
    hook.chmod(0o755)
    env = git_env(repo)
    subprocess.check_call(
        ["/usr/bin/git", "config", "core.fsmonitor", str(script)], cwd=repo, env=env,
    )
    subprocess.check_call(
        ["/usr/bin/git", "config", "core.hooksPath", str(hooks)], cwd=repo, env=env,
    )
    receipt = journey.run_readiness(object_store=git_dir)
    assert receipt["source"]["state"] == "REFUSED"
    assert not sentinel.exists()
    joined = " ".join(" ".join(item["argv"]) for item in receipt["commands"])
    assert "--no-filters" in joined or "hash-object" not in joined
    assert "core.fsmonitor=false" in joined


def test_symlink_object_store_is_refused_and_target_kept(tmp_path):
    git_dir = make_unrelated_repo(tmp_path / "real")
    link = tmp_path / "alias.git"
    link.symlink_to(git_dir)
    marker = git_dir / "HEAD"
    before = marker.read_text(encoding="utf-8")
    receipt = journey.run_readiness(object_store=link)
    assert receipt["source"]["reason"] == "symlink_path_refused"
    assert marker.read_text(encoding="utf-8") == before
    assert git_dir.is_dir()


def test_unsafe_paths_refuse_without_deletion(tmp_path):
    sentinel = tmp_path / "stay.txt"
    sentinel.write_text("stay", encoding="utf-8")
    assert journey.remove_owned_root(journey.OwnedRoot(tmp_path, "not-our-token")) == "REFUSED"
    assert sentinel.read_text(encoding="utf-8") == "stay"
    with pytest.raises(journey.Refusal) as relative:
        journey.validate_git_dir(Path("relative.git"))
    assert relative.value.reason == "relative_object_store"
    with pytest.raises(journey.Refusal) as escaped:
        journey.validate_git_dir(Path("/tmp/../etc"))
    assert escaped.value.reason == "path_traversal"
    assert Path("/etc").is_dir()


def test_tampered_patch_and_anchor_refuse_before_apply():
    topology, compose = upstream_bytes()
    owned = journey.create_owned_root()
    try:
        env = journey.build_closed_env(owned)
        blobs = {journey.TOPOLOGY_REL: topology, journey.COMPOSE_REL: compose}

        def boom(*_args, **_kwargs):
            raise AssertionError("donor evaluation spawned")

        with pytest.raises(journey.Refusal) as patch:
            journey.derive_runner(
                blobs, owned=owned, env=env, spawn=boom, patch_bytes=b"not-the-reviewed-patch\n",
            )
        assert patch.value.reason == "patch_hash_mismatch"
        with pytest.raises(journey.Refusal) as override:
            journey.derive_runner(
                blobs, owned=owned, env=env, spawn=boom, override_bytes=b"services: {}\n",
            )
        assert override.value.reason == "override_hash_mismatch"
        bad = dict(blobs)
        bad[journey.TOPOLOGY_REL] = b"not the pinned topology\n"
        with pytest.raises(journey.Refusal) as anchor:
            journey.derive_runner(bad, owned=owned, env=env, spawn=boom)
        assert anchor.value.reason == "source_anchor_mismatch"
    finally:
        journey.remove_owned_root(owned)


def test_reviewed_patch_preserves_upstream_assertions():
    topology, compose = upstream_bytes()
    owned = journey.create_owned_root()
    try:
        env = journey.build_closed_env(owned)
        derived = journey.derive_runner(
            {journey.TOPOLOGY_REL: topology, journey.COMPOSE_REL: compose},
            owned=owned,
            env=env,
            spawn=journey.default_spawn,
        )
        text = (owned.path / "staging" / journey.TOPOLOGY_REL).read_text(encoding="utf-8")
        compose_text = (owned.path / "staging" / journey.COMPOSE_REL).read_text(encoding="utf-8")
        assert derived["derived_topology_sha256"] == journey.DERIVED_TOPOLOGY_SHA256
        assert hashlib.sha256(text.encode("utf-8")).hexdigest() == journey.DERIVED_TOPOLOGY_SHA256
        for marker in journey.UPSTREAM_ASSERTIONS:
            assert marker in text
        assert "process.env" not in text
        assert "--mmx-attempt" in text
        assert "overrideFile" in text
        assert "      - /var/run/docker.sock:/var/run/docker.sock\n" not in compose_text
        assert "MMX_ADMITTED_DOCKER_SOCKET" in compose_text
    finally:
        journey.remove_owned_root(owned)


def test_patch_does_not_delete_upstream_assertions():
    removed = []
    for line in (journey.PATCH_PATH).read_text(encoding="utf-8").splitlines():
        if line.startswith("-") and not line.startswith("---"):
            removed.append(line[1:])
    blob = "\n".join(removed)
    for marker in journey.UPSTREAM_ASSERTIONS:
        assert marker not in blob
    assert hashlib.sha256(journey.PATCH_PATH.read_bytes()).hexdigest() == journey.PATCH_SHA256
    assert hashlib.sha256(journey.OVERRIDE_PATH.read_bytes()).hexdigest() == journey.OVERRIDE_SHA256


def test_override_sets_catalog_off_inside_api_and_worker():
    text = journey.OVERRIDE_PATH.read_text(encoding="utf-8")
    api = text.split("\n  api:\n", 1)[1].split("\n  web:\n", 1)[0]
    worker = text.split("\n  worker:\n", 1)[1]
    for block in (api, worker):
        assert 'RAKAZO_LIVE_MODEL_CATALOG: "off"' in block
        assert "AGENT_RUNTIME: scripted" in block
        assert "WAKEUP_DRIVER: graphile" in block
        assert "SANDBOX_PROVIDER: docker" in block
    assert "rakazo/app:topology" not in text
    assert "rakazo/computer:topology" not in text
    assert "/var/run/docker.sock" not in text
    assert "0.0.0.0" not in text
    assert "POSTGRES_USER" not in text


def test_planned_identity_avoids_donor_tags():
    seen = set()
    for _ in range(5):
        identity = journey.new_identity()
        assert identity["docker_resources_created"] is False
        assert journey.PROJECT_RE.fullmatch(identity["project"])
        assert not identity["app_image"].startswith("rakazo/")
        assert not identity["computer_image"].endswith(":topology")
        seen.add(identity["project"])
    assert len(seen) == 5
    execution = journey.execute_journey()
    assert execution["spawned"] is False
    assert execution["planned_command"][:3] == ["pnpm", "test:topology", "--"]


def test_daemon_qualification_ignores_project_name_and_synthetic_claims():
    docker = journey.DOCKER
    shared_a = journey.DaemonObservation(
        "local-binary", False, docker, "unix:///var/run/docker.sock", "abc",
        True, True, "fixture", project_name="mmx-rakazo-journey-" + "a" * 32,
    )
    shared_b = journey.DaemonObservation(
        "local-binary", False, docker, "unix:///var/run/docker.sock", "abc",
        True, True, "fixture", project_name="other-project",
    )
    assert journey.qualify_observation(shared_a)["reason"] == "shared_default_socket"
    assert journey.qualify_observation(shared_a)["reason"] == journey.qualify_observation(shared_b)["reason"]
    assert journey.qualify_observation(shared_a)["project_name_qualifies_shared_daemon"] is False
    custom = journey.DaemonObservation(
        "local-binary", False, docker, "unix:///tmp/mmx-owned.sock", "deadbeef",
        True, True, "fixture", project_name="mmx-rakazo-journey-" + "b" * 32,
    )
    assert journey.qualify_observation(custom)["reason"] == "daemon_id_not_admitted"
    synthetic = journey.DaemonObservation(
        "local-binary", True, docker, "unix:///tmp/mmx-owned.sock", "admitted",
        True, True, "synthetic fixture",
    )
    verdict = journey.qualify_observation(synthetic)
    assert verdict["synthetic"] is True
    assert verdict["state"] == "UNQUALIFIED"
    assert verdict["reason"] == "synthetic_fixture_is_not_daemon_authority"
    assert verdict["admitted_daemon_ids"] == []


def test_cleanup_outside_owned_scope_and_exit_zero_uncertainty():
    project = "mmx-rakazo-journey-" + "ab" * 16
    images = (
        "mmx-rakazo-journey/app:" + "ab" * 16,
        "mmx-rakazo-journey/computer:" + "ab" * 16,
    )
    plan = journey.plan_owned_cleanup(project, images)
    flat = [item for argv in plan for item in argv]
    assert "prune" not in flat
    assert "system" not in flat
    with pytest.raises(journey.Refusal) as donor:
        journey.plan_owned_cleanup(project, ["rakazo/app:topology"])
    assert donor.value.reason == "donor_image_tag"
    with pytest.raises(journey.Refusal) as unowned:
        journey.plan_owned_cleanup("rakazo-topology-1", images)
    assert unowned.value.reason == "unowned_project"
    assert journey.classify_cleanup(
        exit_code=0, before=None, after=None, observation_present=False, owned_project_only=True,
    ) == "UNKNOWN"
    assert journey.classify_cleanup(
        exit_code=None, before=None, after=None, observation_present=False, owned_project_only=True,
    ) == "NOT_RUN"
    assert journey.classify_cleanup(
        exit_code=0, before=["owned"], after=[], observation_present=True, owned_project_only=False,
    ) == "REFUSED"
    with pytest.raises(journey.Refusal) as unrelated:
        journey.plan_owned_cleanup(project, ["ubuntu:24.04", images[1]])
    assert unrelated.value.reason == "unowned_image"
    with pytest.raises(journey.Refusal) as duplicate:
        journey.plan_owned_cleanup(project, [images[0], images[0]])
    assert duplicate.value.reason == "unowned_image"
    with pytest.raises(journey.Refusal) as mismatched:
        journey.plan_owned_cleanup(project, [
            "mmx-rakazo-journey/app:" + "cd" * 16,
            "mmx-rakazo-journey/computer:" + "cd" * 16,
        ])
    assert mismatched.value.reason == "unowned_image"
    with pytest.raises(journey.Refusal) as extra:
        journey.plan_owned_cleanup(project, [*images, images[0]])
    assert extra.value.reason == "unowned_image"
    flat_rm = [argv for argv in plan if "rm" in argv]
    assert flat_rm == [
        ("/usr/bin/docker", "image", "rm", images[0]),
        ("/usr/bin/docker", "image", "rm", images[1]),
    ]


def test_fixture_cannot_mint_journey_passed(tmp_path):
    git_dir = make_unrelated_repo(tmp_path / "repo")
    receipt = journey.run_readiness(object_store=git_dir)
    assert receipt["status"] == "READINESS_BLOCKED"
    assert receipt["source_phase"] == "REFUSED"
    forged = json.loads(json.dumps(receipt))
    forged["status"] = "JOURNEY_PASSED"
    assert journey.receipt_problems(forged)
    assert all(value > 0 for value in journey.DEADLINES_SECONDS.values())
    assert journey.DEADLINES_SECONDS["execution"] == 900
    assert receipt["limits"]["execution_armed"] is False
    assert receipt["limits"]["automatic_retry"] is False
    assert receipt["daemon"]["state"] == "UNQUALIFIED"


def test_process_group_timeout_is_bounded():
    owned = journey.create_owned_root()
    try:
        env = journey.build_closed_env(owned)
        record = journey.default_spawn(
            [sys.executable, "-I", "-c", "import time; time.sleep(30)"],
            env=env,
            cwd=owned.path / "tmp",
            timeout=0.4,
        )
        assert record.timed_out is True
        assert record.returncode != 0
    finally:
        journey.remove_owned_root(owned)


def test_hash_object_uses_no_filters_and_closed_git(tmp_path):
    sentinel = tmp_path / "filter-ran"
    trap = tmp_path / "trap"
    trap.mkdir()
    env = git_env(trap)
    subprocess.check_call(["/usr/bin/git", "init"], cwd=trap, env=env)
    script = tmp_path / "filter.sh"
    script.write_text(f"#!/bin/sh\ntouch {sentinel}\ncat\n", encoding="utf-8")
    script.chmod(0o755)
    subprocess.check_call(
        ["/usr/bin/git", "config", "filter.evil.clean", str(script)], cwd=trap, env=env,
    )
    (trap / ".gitattributes").write_text("* filter=evil\n", encoding="utf-8")
    owned = journey.create_owned_root()
    try:
        closed = journey.build_closed_env(owned)
        argv = journey.git_argv(None, "hash-object", "--no-filters", "--stdin")
        assert "--no-filters" in argv
        assert "--no-replace-objects" in argv
        assert "core.fsmonitor=false" in argv
        record = journey.default_spawn(
            argv, env=closed, cwd=trap, timeout=15, stdin_bytes=b"hello\n",
        )
        assert record.returncode == 0
        assert not sentinel.exists()
    finally:
        journey.remove_owned_root(owned)


def test_cli_readiness_on_wrong_pin_emits_blocked_receipt(tmp_path):
    git_dir = make_unrelated_repo(tmp_path / "repo")
    env = dict(os.environ)
    env["NODE_OPTIONS"] = "--canary-node-options"
    env["DOCKER_HOST"] = "tcp://127.0.0.1:9"
    completed = subprocess.run(
        [sys.executable, "-B", str(MODULE_PATH), "readiness", "--object-store", str(git_dir)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    receipt = json.loads(completed.stdout)
    assert receipt["status"] == "READINESS_BLOCKED"
    assert receipt["source"]["reason"] == "pin_not_present"
    assert journey.receipt_problems(receipt) == []
    for command in receipt["commands"]:
        assert "compose" not in command["argv"]
        assert "pnpm" not in command["argv"]
        assert not any(str(item).endswith("topology.ts") for item in command["argv"])


def test_redact_bounds_and_strips_donor_test_secrets():
    assert "secret-value" not in journey.redact("password=secret-value")
    assert "topology-only-password" not in journey.redact("see topology-only-password")
    bounded = journey.redact("a" * 9000)
    assert len(bounded.encode("utf-8")) <= journey.LOG_MAX_BYTES
    assert bounded.endswith("\n[truncated]")


def test_node_engine_range_matches_donor():
    assert journey.node_satisfies("v22.23.4") is True
    assert journey.node_satisfies("v22.22.1") is False
    assert journey.node_satisfies("v24.0.0") is True
    assert journey.node_satisfies("v25.1.0") is False
    assert journey.node_satisfies("v26.0.0") is True


def test_cumulative_deadline_is_not_reset_for_each_command():
    clock = {"now": 0.0}

    def now():
        return clock["now"]

    budget = journey.AttemptBudget(now=now)
    assert budget.take("fetch") == 90
    clock["now"] = 100
    assert budget.take("fetch") == 60
    clock["now"] = 160
    with pytest.raises(journey.Refusal) as exhausted:
        budget.take("admit")
    assert exhausted.value.reason == "deadline_exhausted"
    with pytest.raises(journey.Refusal) as again:
        budget.take("derive")
    assert again.value.reason == "deadline_exhausted"
    assert budget.elapsed() == 160
    assert budget.remaining() == 20
    assert budget.facts()["exhausted_phase"] == "admit"
    assert budget.take("owned_cleanup") == 20
    with pytest.raises(journey.Refusal) as armed:
        journey.AttemptBudget(now=now).take("execution")
    assert armed.value.reason == "execution_not_authorized_for_initial_placement"

    timeouts = []

    def spawn(argv, **kwargs):
        assert clock["now"] < 160
        timeouts.append(kwargs["timeout"])
        clock["now"] += 80
        code = 0 if len(timeouts) == 1 else 1
        return journey.CommandRecord(tuple(argv), code, "", "fetch-failed", False, False)

    clock["now"] = 0.0
    receipt = journey.run_readiness(now=now, spawn=spawn)
    assert timeouts == [90, 80]
    assert receipt["status"] == "READINESS_BLOCKED"
    assert receipt["limits"]["budget"]["exhausted_phase"] == "hash_manifest"
    assert receipt["limits"]["budget"]["elapsed_seconds"] == 160
    assert receipt["limits"]["budget"]["remaining_seconds"] == 20
    assert receipt["hashes"]["config_manifest_cause"] == "deadline_exhausted"
    assert receipt["source_phase"] != "SOURCE_PREPARED"
    assert "deadline_exhausted" in receipt["limits"]["notes"]
    assert journey.receipt_problems(receipt) == []


def test_streamed_captures_stop_at_the_ceiling(tmp_path):
    owned = journey.create_owned_root()
    try:
        env = journey.build_closed_env(owned)
        text = journey.default_spawn(
            [sys.executable, "-I", "-c", "import sys; sys.stdout.write('Z' * 2000000)"],
            env=env, cwd=owned.path / "tmp", timeout=5,
        )
        assert len(text.stdout.encode("utf-8")) <= journey.LOG_MAX_BYTES
        assert text.stdout.endswith("\n[truncated]")
        assert text.uncertain is False
        err = journey.default_spawn(
            [sys.executable, "-I", "-c", "import sys; sys.stderr.write('E' * 2000000)"],
            env=env, cwd=owned.path / "tmp", timeout=5,
        )
        assert len(err.stderr.encode("utf-8")) <= journey.LOG_MAX_BYTES
        assert err.stderr.endswith("\n[truncated]")
        exact = journey.default_spawn(
            [sys.executable, "-I", "-c", f"import sys; sys.stdout.buffer.write(b'B'*{journey.BINARY_OBJECT_CEILING})"],
            env=env, cwd=owned.path / "tmp", timeout=5, binary=True,
        )
        assert exact.capture_refusal is None
        assert exact.stdout_bytes is not None
        assert len(exact.stdout_bytes) == journey.BINARY_OBJECT_CEILING
        flooded = journey.default_spawn(
            [sys.executable, "-I", "-c", f"import sys; sys.stdout.buffer.write(b'B'*{journey.BINARY_OBJECT_CEILING + 32})"],
            env=env, cwd=owned.path / "tmp", timeout=5, binary=True,
        )
        assert flooded.capture_refusal == "binary_capture_exceeded"
        assert flooded.stdout_bytes is None
        assert flooded.uncertain is False
    finally:
        journey.remove_owned_root(owned)


def test_operational_failure_returns_a_receipt(tmp_path):
    def allocate():
        raise FileNotFoundError("missing-temp")

    def spawn(argv, **kwargs):
        raise AssertionError("spawned")

    receipt = journey.run_readiness(allocate_root=allocate, spawn=spawn)
    assert receipt["status"] == "READINESS_BLOCKED"
    assert receipt["source_phase"] != "SOURCE_PREPARED"
    assert receipt["source"]["reason"] == "operational_failure"
    assert receipt["cleanup"]["owned_root"] == "UNKNOWN"
    assert receipt["hashes"]["config_manifest_sha256"] is None
    assert receipt["hashes"]["config_manifest_cause"] == "FileNotFoundError"
    assert journey.EMPTY_SHA256 not in receipt["hashes"].values()
    assert journey.receipt_problems(receipt) == []

    git_dir = make_unrelated_repo(tmp_path / "repo")
    before = set(Path(tempfile.gettempdir()).glob("mmx-rakazo-journey-*"))

    def failing(argv, **kwargs):
        raise OSError("closed")

    receipt = journey.run_readiness(object_store=git_dir, spawn=failing)
    after = set(Path(tempfile.gettempdir()).glob("mmx-rakazo-journey-*"))
    assert after == before
    assert receipt["status"] == "READINESS_BLOCKED"
    assert receipt["source"]["reason"] == "operational_failure"
    assert receipt["cleanup"]["owned_root"] == "REMOVED"
    assert journey.receipt_problems(receipt) == []


def test_uncertain_child_does_not_continue_or_delete(tmp_path):
    git_dir = make_unrelated_repo(tmp_path / "repo")
    calls = []

    def spawn(argv, **kwargs):
        calls.append(tuple(argv))
        return journey.CommandRecord(tuple(argv), -1, "", "", True, True)

    before = set(Path(tempfile.gettempdir()).glob("mmx-rakazo-journey-*"))
    receipt = journey.run_readiness(object_store=git_dir, spawn=spawn)
    created = set(Path(tempfile.gettempdir()).glob("mmx-rakazo-journey-*")) - before
    try:
        assert len(calls) == 1
        assert receipt["status"] == "READINESS_BLOCKED"
        assert receipt["source"]["reason"] == "uncertain_child"
        assert receipt["cleanup"]["owned_root"] == "UNKNOWN"
        assert "uncertain_child" in receipt["limits"]["notes"]
        assert receipt["hashes"]["config_manifest_cause"] == "uncertain_child"
        assert receipt["source_phase"] != "SOURCE_PREPARED"
        assert len(created) == 1
        assert journey.receipt_problems(receipt) == []
    finally:
        for path in created:
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)


def test_manifest_failure_is_unavailable_not_an_empty_hash():
    owned = journey.create_owned_root()
    try:
        (owned.path / "config" / "link").symlink_to(owned.path / "config" / "gitconfig")
        hashes = journey._owned_hashes(owned, journey.AttemptBudget())
        assert hashes["config_manifest_sha256"] is None
        assert hashes["config_manifest_cause"] == "symlink_in_owned_root"
        for key in journey.MANIFEST_KEYS:
            if hashes[key] is None:
                assert hashes[journey._hash_cause(key)]
            elif hashes[key] == journey.EMPTY_SHA256:
                assert hashes[journey._hash_cause(key)] is None
        with pytest.raises(journey.Refusal) as bounded:
            journey.directory_manifest_sha256(
                owned.path / "config", journey.AttemptBudget(), max_files=1,
            )
        assert bounded.value.reason == "manifest_bound_exceeded"
        receipt = journey.build_receipt(
            source_state="ADMITTED",
            source_reason="",
            blobs={},
            derivation_state="PREPARED",
            derivation_reason="",
            assertions=True,
            derived={},
            identity=journey.new_identity(),
            daemon=journey.qualify_observation(journey.DaemonObservation(
                "absent", False, None, None, None, False, False, "not_probed",
            )),
            toolchain=journey._empty_toolchain(),
            env_keys=sorted(journey.ALLOWED_ENV_KEYS),
            owned_root="RETAINED",
            hashes=hashes,
            commands=(),
            notes=["symlink_in_owned_root"],
            budget=journey.AttemptBudget(),
        )
        assert receipt["source_phase"] == "NOT_PREPARED"
        assert receipt["status"] == "READINESS_BLOCKED"
        assert journey.receipt_problems(receipt) == []
    finally:
        journey.remove_owned_root(owned)


def test_phase_cap_bounds_a_real_child():
    owned = journey.create_owned_root()
    try:
        env = journey.build_closed_env(owned)
        budget = journey.AttemptBudget()
        budget.started = budget._now() - (journey.DEADLINES_SECONDS["overall"] - journey.DEADLINES_SECONDS["owned_cleanup"] - 0.3)
        allowance = budget.take("toolchain_probe")
        assert allowance <= 0.3
        record = journey.default_spawn(
            [sys.executable, "-I", "-c", "import time; time.sleep(30)"],
            env=env, cwd=owned.path / "tmp", timeout=allowance, budget=budget,
        )
        assert record.timed_out is True
        assert record.uncertain is False
        assert record.returncode != 0
    finally:
        journey.remove_owned_root(owned)

TOPOLOGY_Z64 = """
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
jnjgv/8BBjbwBw==
"""

COMPOSE_Z64 = """
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
"""

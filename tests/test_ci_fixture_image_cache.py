"""The two apt-built Linux fixture images are outage-hardened, not weakened.

Since 2026-11-11 GitHub-hosted runners intermittently cannot reach any Ubuntu
archive during docker build (``Ign … InRelease`` then
``E: Unable to locate package python3.12``), so the H1 no-ACL journey (shard
two) and the closed application transport journey (shard zero; also rebuilt by
the Hermes inference workflow) failed every run while the same archives
answered from outside GitHub.

The fix restores the exact built image bytes from the Actions cache, keyed by
the fixture Dockerfile's own hash (each Dockerfile pins its base by digest and
COPYs nothing, so the hash covers the complete image recipe). apt runs only on
a genuine cache miss. These tests pin the load-bearing parts:

- the cache key binds the Dockerfile hash and the pinned base digest;
- a pull request or merge group can never save the shared cache entry (only a
  protected master push may), and no ``restore-keys`` prefix can ever return a
  stale image after the Dockerfile changes;
- on a cache miss the original docker build still runs, and the container
  invocation (image ref, flags, mounts) is identical in both branches --
  executed here through the real workflow shell with a recording docker stub,
  not compared as strings only.
"""

from __future__ import annotations

import ast
import hashlib
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

from scripts import ci_parallel_shard as fan
from scripts import ci_pytest as cip

ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
HERMES_WORKFLOW = ROOT / ".github" / "workflows" / "hermes-application-inference.yml"

_JOURNEY_NAME = "H1 required real Linux no-ACL positive journey"
_TRANSPORT_NAME = "Verify closed application transport in isolated root fixtures"
_FROM_DIGEST_RE = re.compile(r"^FROM ubuntu:24\.04@sha256:([0-9a-f]{64})$", re.M)
_BASE_DIGEST = "68ee22004a9109b44973313b02ff7b1de250f1de0f5ecb628d73f579aaff33ac"
_SAVE_SUFFIX = " fixture image for protected runs"


@dataclass(frozen=True)
class Fixture:
    tag: str                # pytest id
    workflow: Path
    journey_name: str       # the released step name, kept byte-identical
    restore_id: str         # step id of the actions/cache/restore producer
    dockerfile: str         # path relative to the repository root
    tar_name: str           # tar filename inside runner.temp
    index: int | None       # owning shard matrix index, None outside a matrix
    image: str              # per-run image reference prefix (tag = github.sha)
    cache_tag: str          # stable tag used by docker save/load
    save_short: str         # short fixture name inside the save step name


FIXTURES = (
    Fixture("ci:h1", CI_WORKFLOW, _JOURNEY_NAME, "h1_fixture_image_cache",
            "tests/h1_ci_fixture/Dockerfile", "h1-fixture-image.tar", 2,
            "mastermind-h1-noacl", "mastermind-h1-noacl:fixture-cache", "H1"),
    Fixture("ci:application-transport", CI_WORKFLOW, _TRANSPORT_NAME,
            "application_transport_image_cache", "tests/application_tunnel_ci/Dockerfile",
            "application-transport-image.tar", 0,
            "mastermind-application-transport",
            "mastermind-application-transport:fixture-cache", "application transport"),
    Fixture("hermes:application-transport", HERMES_WORKFLOW,
            "Qualify original and successor in isolated Linux root fixture",
            "application_transport_image_cache", "tests/application_tunnel_ci/Dockerfile",
            "application-transport-image.tar", None,
            "hermes-transport", "mastermind-application-transport:fixture-cache",
            "application transport"),
)
CI_FIXTURES = FIXTURES[:2]


def _load(path: Path) -> dict:
    return yaml.load(path.read_text(encoding="utf-8"), Loader=cip._WorkflowYAMLLoader)


def _shard_steps() -> list:
    return _load(CI_WORKFLOW)["jobs"]["pytest_shards"]["steps"]


def _step(steps: list, **match) -> dict:
    found = [s for s in steps if all(s.get(k) == v for k, v in match.items())]
    assert len(found) == 1, match
    return found[0]


def _fixture_parts(fixture: Fixture, dockerfile_text: str | None = None) -> dict:
    workflow = _load(fixture.workflow)
    steps = next(
        job["steps"] for job in workflow["jobs"].values()
        if any(step.get("id") == fixture.restore_id for step in job["steps"])
    )
    dockerfile = ROOT / fixture.dockerfile
    return {
        "workflow": workflow,
        "steps": steps,
        "journey": _step(steps, name=fixture.journey_name),
        "restore": _step(steps, id=fixture.restore_id),
        "saves": _step(steps, name=f"Save {fixture.save_short}{_SAVE_SUFFIX}"),
        "dockerfile_rel": fixture.dockerfile,
        "dockerfile_text": (dockerfile_text if dockerfile_text is not None
                            else dockerfile.read_text(encoding="utf-8")),
        "tar": fixture.tar_name,
        "index": fixture.index,
        "image": fixture.image,
        "cache_tag": fixture.cache_tag,
    }


def _require_wired_cache(parts: dict) -> None:
    journey, restore, save = parts["journey"], parts["restore"], parts["saves"]
    assert restore["uses"] == "actions/cache/restore@v4"
    assert save["uses"] == "actions/cache/save@v4"
    assert "continue-on-error" not in journey and "continue-on-error" not in save
    assert parts["steps"].index(restore) < parts["steps"].index(journey)
    assert parts["steps"].index(journey) < parts["steps"].index(save)
    # The restore/save pair shares one exact key and one tar path; a prefix
    # fallback (restore-keys) could silently return an image built from an
    # older Dockerfile, so it is forbidden outright.
    tar_path = "${{ runner.temp }}/" + parts["tar"]
    for step in (restore, save):
        assert "restore-keys" not in step["with"]
        assert step["with"]["path"] == tar_path
    assert restore["with"]["key"] == save["with"]["key"]
    key = restore["with"]["key"]
    hash_expression = "${{ hashFiles('%s') }}" % parts["dockerfile_rel"]
    assert key.count(hash_expression) == 1
    # The key names the pinned base digest in plain text, and that fragment
    # must match the Dockerfile's actual FROM pin (which itself must stay
    # digest-pinned so the hashed bytes always cover the base identity).
    match = _FROM_DIGEST_RE.search(parts["dockerfile_text"])
    assert match, "fixture Dockerfile must pin its Ubuntu base by sha256 digest"
    assert f"ubuntu-24.04-{match.group(1)[:12]}-" in key
    # The journey step consumes exactly this restore step's hit output.
    assert len(journey["env"]) == 1
    (name, value), = journey["env"].items()
    assert name.endswith("_IMAGE_RESTORED")
    assert value == "${{ steps.%s.outputs.cache-hit }}" % restore["id"]


def _expression(source: str, github: dict, matrix: dict, steps: dict) -> bool:
    """Evaluate the logical subset the cache save conditions use."""
    source = source.strip()
    if source.startswith("$" + "{{"):
        source = source[3:-2].strip()
    values: dict = {}

    def bind(matched):
        path = matched[0].split(".")
        value: object = {"github": github, "matrix": matrix, "steps": steps}
        for part in path:
            value = value.get(part) if isinstance(value, dict) else None
        key = f"context_{len(values)}"
        values[key] = value
        return key

    source = re.sub(r"\b(?:github|matrix|steps)\.[a-zA-Z0-9_.-]+", bind, source)
    source = source.replace("&&", " and ").replace("||", " or ")
    source = re.sub(r"!(?!=)", " not ", source)
    try:
        parsed = ast.parse(source, mode="eval")
    except SyntaxError as error:
        raise AssertionError(f"unparseable condition: {source!r}") from error
    allowed = (ast.Expression, ast.BoolOp, ast.UnaryOp, ast.Compare, ast.Name,
               ast.Load, ast.Constant, ast.And, ast.Or, ast.Not, ast.Eq, ast.NotEq)
    assert all(isinstance(node, allowed) for node in ast.walk(parsed))
    return bool(eval(compile(parsed, "<cache-save-condition>", "eval"),
                     {"__builtins__": {}}, values))


def _require_only_master_push_saves(parts: dict) -> None:
    restore_id = parts["restore"]["id"]
    condition = parts["saves"]["if"]
    miss = {restore_id: {"outputs": {"cache-hit": "false"}}}
    hit = {restore_id: {"outputs": {"cache-hit": "true"}}}
    index = parts["index"] if parts["index"] is not None else 0
    cases = [
        # (github context, steps, expected)
        ({"event_name": "pull_request", "ref": "refs/pull/751/merge"}, miss, False),
        ({"event_name": "merge_group",
          "ref": "refs/heads/gh-readonly-queue/master/pr-751-verified"}, miss, False),
        ({"event_name": "workflow_dispatch", "ref": "refs/heads/master"}, miss, False),
        ({"event_name": "push", "ref": "refs/heads/feature/x"}, miss, False),
        # Only a protected master push that actually built the image saves it.
        ({"event_name": "push", "ref": "refs/heads/master"}, miss, True),
        ({"event_name": "push", "ref": "refs/heads/master"}, hit, False),
    ]
    for github, steps, expected in cases:
        assert _expression(condition, github, {"index": index}, steps) is expected, (
            github["event_name"], github["ref"], steps, expected)
    # And, inside a matrix, only on the shard that owns this fixture: the
    # shard term itself is required, not merely tolerated.
    if parts["index"] is not None:
        assert "matrix.index" in condition, "matrix save lost its shard scope"
        assert _expression(condition, {"event_name": "push", "ref": "refs/heads/master"},
                           {"index": (index + 1) % 6}, miss) is False


def _execute_journey(step: dict, *, restored: str, tmp_path: Path) -> list:
    """Run the real workflow shell body with a recording docker stub.

    Returns one record per docker invocation; each record is the argv with any
    argument containing newlines kept as raw multi-line text.
    """
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    (repo / "tracked.txt").write_text("public source\n", encoding="utf-8")
    author = ("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid")
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True, timeout=10)
    subprocess.run(["git", "-C", str(repo), *author, "add", "."], check=True, timeout=10)
    subprocess.run(["git", "-C", str(repo), *author, "commit", "-qm", "fixture"],
                   check=True, timeout=10)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "docker.log"
    stub = bin_dir / "docker"
    stub.write_text(
        "#!/bin/sh\n"
        "{\n"
        "  printf '%s\\n' docker\n"
        "  for argument in \"$@\"; do printf '%s\\n' \"$argument\"; done\n"
        "  printf '%s\\n' '---RECORD---'\n"
        "} >> \"$DOCKER_LOG\"\n"
        "exit 0\n", encoding="utf-8")
    stub.chmod(0o700)
    runner_temp = tmp_path / "runner-temp"
    runner_temp.mkdir()
    sha = "a" * 40
    env = {
        **{k: v for k, v in os.environ.items()
           if k not in {"GITHUB_ACTIONS", "CI"} and not k.startswith("GITHUB_")},
        "PATH": str(bin_dir) + os.pathsep + os.defpath,
        "RUNNER_TEMP": str(runner_temp),
        "DOCKER_LOG": str(log),
        "H1_FIXTURE_IMAGE_RESTORED": restored,
        "APPLICATION_TRANSPORT_IMAGE_RESTORED": restored,
    }
    script = step["run"].replace("${{ github.sha }}", sha)
    result = subprocess.run(
        ["/bin/bash", "-e", "-o", "pipefail", "-c", script],
        cwd=repo, env=env, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return [record.splitlines()
            for record in log.read_text(encoding="utf-8").split("---RECORD---\n")
            if record.strip()]


def _record(records: list, verb: str) -> list:
    found = [record for record in records
             if record[:2] == ["docker", verb]]
    assert len(found) == 1, (verb, [record[:2] for record in records])
    return found[0]


def _require_journey_invocations(parts: dict, tmp_path: Path) -> None:
    journey = parts["journey"]
    dockerfile_rel = parts["dockerfile_rel"]
    sha = "a" * 40
    image = f"{parts['image']}:{sha}"
    cache_tag = parts["cache_tag"]

    # Miss: the original build command (file, both tags, build context) runs
    # and the freshly built image is exported for the protected save gate.
    miss = _execute_journey(journey, restored="false", tmp_path=tmp_path / "miss")
    build = _record(miss, "build")
    assert "--file" in build and build[build.index("--file") + 1] == dockerfile_rel
    assert build.count("--tag") == 2 and image in build and cache_tag in build
    assert build[-1] == str(Path(dockerfile_rel).parent)
    save = _record(miss, "save")
    assert "--output" in save and save[save.index("--output") + 1].endswith(parts["tar"])
    assert save[-1] == cache_tag
    assert not [record for record in miss if record[:2] == ["docker", "load"]]

    # Hit: no build, no apt; the cached bytes are loaded and retagged.
    hit = _execute_journey(journey, restored="true", tmp_path=tmp_path / "hit")
    load = _record(hit, "load")
    assert "--input" in load and load[load.index("--input") + 1].endswith(parts["tar"])
    assert _record(hit, "tag") == ["docker", "tag", cache_tag, image]
    assert not [record for record in hit
                if record[:2][1] in {"build", "save"}]

    # The container invocation is identical in both branches apart from the
    # per-invocation mktemp source directory.
    def _normalized(record: list) -> list:
        return [re.sub(r"type=bind,src=[^,]+,", "type=bind,src=<mktemp>,", argument)
                for argument in record]

    runs = []
    for records in (miss, hit):
        run = _record(records, "run")
        assert run[2:7] == ["--rm", "--network=none", "--cap-drop=ALL",
                            "--security-opt=no-new-privileges", "--read-only"]
        assert image in run
        assert any(argument.startswith("type=bind,src=") for argument in run)
        runs.append(_normalized(run))
    assert runs[0] == runs[1]


def test_validator_still_accepts_ci_and_step_names_stay_required_shapes() -> None:
    fan.validate_parallel_workflow(CI_WORKFLOW.read_text(encoding="utf-8"))
    steps = _shard_steps()
    assert _step(steps, name=_JOURNEY_NAME)["if"] == "matrix.index == 2"
    assert _step(steps, name=_TRANSPORT_NAME)["if"] == "matrix.index == 0"
    assert not [s for s in steps if s.get("continue-on-error") is not None]


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda f: f.tag)
def test_cache_key_binds_dockerfile_hash_and_base_digest(fixture: Fixture) -> None:
    _require_wired_cache(_fixture_parts(fixture))


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda f: f.tag)
def test_only_a_protected_master_push_may_save_the_shared_entry(fixture: Fixture) -> None:
    _require_only_master_push_saves(_fixture_parts(fixture))


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda f: f.tag)
def test_dockerfile_change_always_changes_the_effective_key(fixture: Fixture) -> None:
    # GitHub's hashFiles is a sha256 over the matched file contents, so any
    # Dockerfile edit -- including a base digest bump -- necessarily produces
    # a different key and therefore a rebuild, never a stale restore.
    dockerfile = ROOT / fixture.dockerfile
    original = hashlib.sha256(dockerfile.read_bytes()).hexdigest()
    bumped = hashlib.sha256(
        dockerfile.read_bytes().replace(_BASE_DIGEST.encode(), b"0" * 64)
    ).hexdigest()
    assert re.fullmatch(r"[0-9a-f]{64}", original)
    assert bumped != original


@pytest.mark.parametrize("fixture", CI_FIXTURES, ids=lambda f: f.tag)
def test_cache_miss_builds_and_cache_hit_loads_the_same_bytes(
        fixture: Fixture, tmp_path: Path) -> None:
    _require_journey_invocations(_fixture_parts(fixture), tmp_path)


def test_hermes_tunnel_fixture_shares_the_same_hardening() -> None:
    parts = _fixture_parts(FIXTURES[2])
    _require_wired_cache(parts)
    _require_only_master_push_saves(parts)
    for fragment in (
        "docker run --rm --network=none --cap-drop=ALL --security-opt=no-new-privileges --read-only",
        "--tmpfs /tmp:rw,noexec,nosuid,nodev,mode=1777 --tmpfs /fixture:rw,exec,nosuid,nodev,mode=0755",
        '--mount "type=bind,src=${hermes_transport_source},dst=/repo,readonly"',
        "hermes-transport:${{ github.sha }}",
    ):
        assert fragment in parts["journey"]["run"]
    # It restores exactly the cache entry the main CI workflow saves.
    assert parts["restore"]["with"]["key"] == _fixture_parts(CI_FIXTURES[1])["restore"]["with"]["key"]


def test_playwright_gate_no_longer_hard_depends_on_the_ubuntu_archive() -> None:
    gate = _step(_shard_steps(),
                 name="Verify actual Brain Fabric and production inference composition")
    body = gate["run"]
    assert "python -m playwright install --with-deps chromium ||" in body
    # The fallback downloads only the browser from the Playwright CDN; the
    # browser proof itself stays with the unittest discovery below it, so a
    # genuinely missing library still fails the gate honestly.
    fallback = body.split("--with-deps chromium ||", 1)[1]
    assert "python -m playwright install chromium" in fallback
    assert "test_fabric_chat_browser.py" in body


@pytest.mark.parametrize("mutation", [
    "drop-hashfiles", "stale-digest-fragment", "restore-keys", "drop-path",
    "save-other-key", "save-before-journey", "restore-after-journey",
    "journey-env-unwired", "untagged-base",
])
@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda f: f.tag)
def test_cache_wiring_drift_is_refused(fixture: Fixture, mutation: str) -> None:
    import copy

    parts = _fixture_parts(fixture)
    workflow = copy.deepcopy(parts["workflow"])
    steps = next(
        job["steps"] for job in workflow["jobs"].values()
        if any(step.get("id") == fixture.restore_id for step in job["steps"]))
    journey, restore = _step(steps, name=fixture.journey_name), _step(steps, id=fixture.restore_id)
    save = _step(steps, name=parts["saves"]["name"])
    if mutation == "drop-hashfiles":
        for step in (restore, save):
            step["with"]["key"] = "docker-fixture-static"
    elif mutation == "stale-digest-fragment":
        for step in (restore, save):
            step["with"]["key"] = step["with"]["key"].replace(
                "ubuntu-24.04-68ee22004a91-", "ubuntu-24.04-000000000000-")
    elif mutation == "restore-keys":
        restore["with"]["restore-keys"] = "docker-fixture-"
    elif mutation == "drop-path":
        save["with"]["path"] = "${{ runner.temp }}/other.tar"
    elif mutation == "save-other-key":
        save["with"]["key"] = restore["with"]["key"] + "-x"
    elif mutation == "save-before-journey":
        steps.remove(save)
        steps.insert(steps.index(journey), save)
    elif mutation == "restore-after-journey":
        steps.remove(restore)
        steps.insert(steps.index(journey) + 1, restore)
    elif mutation == "journey-env-unwired":
        journey["env"] = {next(iter(journey["env"])): "${{ steps.other.outputs.cache-hit }}"}
    else:
        parts = _fixture_parts(
            fixture,
            dockerfile_text=parts["dockerfile_text"].replace("@sha256:" + _BASE_DIGEST, ""),
        )
    parts = {**parts, "workflow": workflow, "steps": steps,
             "journey": journey, "restore": restore, "saves": save}
    with pytest.raises(AssertionError):
        _require_wired_cache(parts)


@pytest.mark.parametrize("mutation", [
    "pr-saves", "any-push-saves", "dispatch-saves", "cache-hit-saves", "any-index-saves",
])
@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda f: f.tag)
def test_save_gate_drift_is_refused(fixture: Fixture, mutation: str) -> None:
    import copy

    if mutation == "any-index-saves" and fixture.index is None:
        pytest.skip("job is not a matrix job; no shard condition to drop")
    parts = _fixture_parts(fixture)
    workflow = copy.deepcopy(parts["workflow"])
    steps = next(
        job["steps"] for job in workflow["jobs"].values()
        if any(step.get("id") == fixture.restore_id for step in job["steps"]))
    save = _step(steps, name=parts["saves"]["name"])
    condition = save["if"]
    if mutation == "pr-saves":
        condition = condition.replace("github.event_name == 'push'", "")
    elif mutation == "any-push-saves":
        condition = condition.replace(" && github.ref == 'refs/heads/master'", "")
    elif mutation == "dispatch-saves":
        condition = condition.replace(
            "github.event_name == 'push'",
            "(github.event_name == 'push' || github.event_name == 'workflow_dispatch')")
    elif mutation == "cache-hit-saves":
        condition = condition.replace("!= 'true'", "== 'true'")
    else:
        condition = re.sub(r"matrix\.index == \d+ && ", "", condition)
    save["if"] = condition.strip() or "${{ true }}"
    parts = {**parts, "steps": steps, "saves": save}
    with pytest.raises(AssertionError):
        _require_only_master_push_saves(parts)


@pytest.mark.parametrize("mutation", ["no-build", "no-save", "load-ignores-input", "no-run"])
def test_journey_shell_drift_is_refused(tmp_path: Path, mutation: str) -> None:
    parts = _fixture_parts(CI_FIXTURES[1])  # the transport journey
    journey = dict(parts["journey"])
    if mutation == "no-build":
        journey["run"] = journey["run"].replace(
            "docker build --file tests/application_tunnel_ci/Dockerfile", "docker build")
    elif mutation == "no-save":
        journey["run"] = journey["run"].replace(
            'docker save --output "$RUNNER_TEMP/application-transport-image.tar"',
            'docker save --output "$RUNNER_TEMP/elsewhere.tar"')
    elif mutation == "load-ignores-input":
        journey["run"] = journey["run"].replace(
            'docker load --input "$RUNNER_TEMP/application-transport-image.tar"',
            "docker load")
    else:
        journey["run"] = journey["run"].replace("--network=none ", "")
    parts = {**parts, "journey": journey}
    with pytest.raises(AssertionError):
        _require_journey_invocations(parts, tmp_path)


def test_h1_and_transport_journeys_keep_their_original_container_bytes() -> None:
    transport = _step(_shard_steps(), name=_TRANSPORT_NAME)
    for fragment in (
        "--tmpfs /tmp:rw,noexec,nosuid,nodev,mode=1777",
        "--tmpfs /fixture:rw,exec,nosuid,nodev,mode=0755",
        '--mount "type=bind,src=${application_transport_source},dst=/repo,readonly"',
        "mastermind-application-transport:${{ github.sha }}",
        'trap \'rm -rf "$application_transport_source"\' EXIT',
        'chmod 0755 "$application_transport_source"',
    ):
        assert fragment in transport["run"]
    # The H1 journey's full pinned fragment set (flags, mounts, proofs) is
    # separately frozen by tests/test_paid_initializer.py; spot-check here
    # that image acquisition changes never touch the container invocation.
    h1 = _step(_shard_steps(), name=_JOURNEY_NAME)
    for fragment in (
        "--tmpfs /home/mmx-h1-fixture:rw,exec,nosuid,nodev,uid=1555,gid=1555,mode=0700",
        "--env MMX_H1_CONTROLLED_LINUX_FIXTURE=1",
        "mastermind-h1-noacl:${{ github.sha }}",
    ):
        assert fragment in h1["run"]

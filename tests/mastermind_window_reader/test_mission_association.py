"""Observed same-Mission association: actual Runtime, Mission producer, Reader."""
from __future__ import annotations

import asyncio
import contextlib
import copy
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from common.executive_workspace_contract import _check_attempt_id, _check_job_id
from control_plane.executive_content_observer import ExecutiveContentObserver
from control_plane.executive_worker_broker import WorkerBrokerClient
from control_plane.visible_turn_projection import TurnKey
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.executive_content_contract import ACCESS_SCHEMA, canonical
from integrations.mastermind_steward_app.installed import (
    construct_installed_live_window,
    build_installed_steward_app,
)
from test_executive_content_observer_reconcile import _terminal_run_absent
from test_mastermind_steward_app_live_window import (
    CONTENT_CLIENT,
    KID,
    ORIGIN,
    WINDOW_PATH,
    _Sink,
    _cache,
    _content_policy,
    _content_token,
    _headers,
    _invoke,
    _key,
    _steward_policy,
    _steward_verifier,
)
from test_steward_content_integration import fixture

V1 = "mastermind.workspace.window_read_candidate.v1"
V2 = "mastermind.workspace.window_read_candidate.v2"
ROOT_WORKSTREAM = "WS:FABRIC"
# Test-owned export of one actual producer run, consumed by the production TS
# decoder/consumer acceptance test (app/mastermind_os/src). The Python side
# re-proves the live chain every run and cross-checks this committed export.
PRODUCER_EXPORT = (
    Path(__file__).resolve().parents[2]
    / "app/mastermind_os/src/fixtures/window-mission-association-producer.json"
)
# Focused production TypeScript consumer (app/mastermind_os/src) driven by the
# actual-chain test below as a bounded subprocess. The fresh-path environment
# key is the cross-language contract: present means the consumer must consume
# exactly that real file, absent means the ordinary committed-export replay.
CONSUMER_APP_DIR = Path(__file__).resolve().parents[2] / "app" / "mastermind_os"
CONSUMER_TEST_PATH = "src/mission-window-producer.test.ts"
CONSUMER_FRESH_KEY = "WINDOW_MISSION_FIXTURE_PATH"
CONSUMER_CONSUMED_PREFIX = "FRESH_CONSUMED "
CONSUMER_TIMEOUT_SECONDS = 600


def _qualifies(mission, window, selection):
    if type(window) is not dict or window.get("schema") != V2:
        return False
    binding = window.get("observation_binding")
    if (
        type(binding) is not dict
        or set(binding) != {"job_id", "attempt_id"}
        or not _check_job_id(binding["job_id"])
        or not _check_attempt_id(binding["attempt_id"])
    ):
        return False
    view = window.get("view")
    if type(view) is not dict or view.get("terminal") is not False:
        return False
    if type(mission) is not dict or mission.get("schema") != "mastermind.mission_workspace.v3":
        return False
    if type(selection) is not dict:
        return False
    program = mission.get("program") or {}
    card = mission.get("mission") or {}
    read_state = mission.get("read_state") or {}
    source = mission.get("source") or {}
    observation = source.get("owner_observation") or {}
    runtime = observation.get("runtime") or {}
    children = mission.get("children") or {}
    if (
        program.get("work_ref") != selection.get("work_ref")
        or card.get("root_job_id") != selection.get("root_job_id")
        or read_state.get("state") != "CURRENT"
        or card.get("runtime_root_state") != "RESOLVED"
        or card.get("root_job_ambiguous") is not False
        or observation.get("state") != "SAME"
        or runtime.get("state") != "SAME"
        or children.get("state") != "AVAILABLE"
        or children.get("coverage") != "COMPLETE"
    ):
        return False
    items = children.get("items")
    if type(items) is not list:
        return False
    matches = [row for row in items if type(row) is dict and row.get("job_id") == binding["job_id"]]
    if len(matches) != 1:
        return False
    child = matches[0]
    latest = child.get("latest_attempt") or {}
    live = {"RUNNING", "CHECKPOINTED"}
    return (
        child.get("orchestration_role") == "plan"
        and child.get("parent_job_id") == selection.get("root_job_id")
        and child.get("depth") == 1
        and child.get("current_attempt_id") == binding["attempt_id"]
        and child.get("status") in live
        and type(latest) is dict
        and latest.get("attempt_id") == binding["attempt_id"]
        and latest.get("status") in live
    )


def _artifact_root(tmp_path):
    """Ordinary assertions land in pytest tmp_path.

    An external location is used only when TASK_ARTIFACTS is explicitly set in
    the environment; there is no hardcoded author-owned default path.
    """
    requested = os.environ.get("TASK_ARTIFACTS")
    root = Path(requested) if requested else tmp_path / "artifacts"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _write_artifact(tmp_path, name, value):
    path = _artifact_root(tmp_path) / name
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    return path


@contextlib.contextmanager
def _canonical_workstream_intent():
    """Serve the shared G1 seed its intent at canonical INPUT.

    The supervisor module's base intent carries no workstream; this fixture
    needs the root's Event-backed workstream provenance, so the dict handed to
    ``submit_intent`` is amended before any row exists. Persisted rows and
    events are never mutated to compensate for the input. The seed resolves
    ``_intent`` from whichever module object the test importer actually loaded
    (flat or ``tests.``-prefixed), so every loaded copy is patched.
    """
    import sys

    targets = {}
    for name in ("test_executive_operator_supervisor",
                 "tests.test_executive_operator_supervisor"):
        module = sys.modules.get(name)
        if module is not None and hasattr(module, "_intent"):
            targets[id(module)] = module
    assert targets, "supervisor seed module is not loaded"
    originals = {key: module._intent for key, module in targets.items()}
    original = next(iter(originals.values()))

    def intent():
        value = dict(original())
        value["workstream"] = ROOT_WORKSTREAM
        return value

    try:
        for module in targets.values():
            module._intent = intent
        yield
    finally:
        for key, module in targets.items():
            module._intent = originals[key]


async def _enrolled_reader(tmp_path, short_socket_root):
    with _canonical_workstream_intent():
        clock, runtime, profile, adapter, broker = fixture(tmp_path)
    broker_path = short_socket_root / "broker.sock"
    ingress_path = short_socket_root / "ingress.sock"

    async def serve_broker(reader, writer):
        frame = json.loads(await reader.readline())
        try:
            result = await broker._dispatch(frame["operation"], frame["payload"])
            reply = dict(
                schema_version="mastermind.executive_worker_broker_response/v1",
                request_id=frame["request_id"],
                operation=frame["operation"],
                ok=True,
                result=result,
            )
        except Exception:
            reply = dict(
                schema_version="mastermind.executive_worker_broker_response/v1",
                request_id=frame["request_id"],
                operation=frame["operation"],
                ok=False,
                error={"code": "state_conflict", "message": "refused"},
            )
        writer.write(canonical(reply) + b"\n")
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_unix_server(serve_broker, path=str(broker_path))
    observer = ExecutiveContentObserver(
        runtime=runtime,
        broker_client=WorkerBrokerClient(broker_path),
        profile_loader=lambda: profile,
        now=lambda: clock.value // 1000,
    )
    await server.__aenter__()
    try:
        enrollment = await observer.enroll()
        assert enrollment["status"] == "ACTIVE"
        key = TurnKey(**enrollment["turn_key"])
        adapter.visible_turn_projection.publish(
            key,
            method="item/updated",
            params={"item": {"type": "agentMessage", "id": "0", "sequence": 0, "text": "plan child visible"}},
            native_turn_id="NATIVE-G1",
        )

        async def serve_ingress(reader, writer):
            frame = json.loads(await reader.readline())
            reply = await observer.handle_frame(frame)
            writer.write(canonical(reply) + b"\n")
            await writer.drain()
            writer.close()
            await writer.wait_closed()

        ingress = await asyncio.start_unix_server(serve_ingress, path=str(ingress_path))
        await ingress.__aenter__()
        try:
            key_material = _key()
            content_policy = _content_policy()
            steward_policy = _steward_policy()
            app = build_installed_steward_app(
                profile=profile,
                steward_policy=steward_policy,
                steward_token_verifier=_steward_verifier(steward_policy, key_material),
                content_authenticator=JwtAuthenticator(
                    policy=content_policy, jwks_cache=_cache(content_policy, key_material)
                ),
                content_policy=content_policy,
                audit_sink=_Sink(),
                ceo_ingress_socket_path=ingress_path,
                now=lambda: clock.value // 1000,
                allowed_origin=ORIGIN,
            )
            token = _content_token(
                key_material,
                issued_at=clock.value // 1000 - 5,
                expires_at=clock.value // 1000 + 600,
            )
            status, _, raw, _ = await _invoke(app, path=WINDOW_PATH, headers=_headers(token=token))
            yield {
                "status": status,
                "body": json.loads(raw) if raw else None,
                "raw": raw,
                "profile": profile,
                "runtime": runtime,
                "clock": clock,
                "observer": observer,
                "adapter": adapter,
                "broker": broker,
                "app": app,
                "token": token,
                "key_material": key_material,
            }
        finally:
            await ingress.__aexit__(None, None, None)
    finally:
        await server.__aexit__(None, None, None)


def _compose_mission(runtime, profile):
    from control_plane import executive_runtime as er
    from control_plane.executive_runtime import Runtime
    from control_plane.fabric_job_view import read_fabric_view_v3_from_runtime
    from control_plane.mission_workspace import compose_mission_workspace_v3
    from tests.test_executive_runtime_bounded_read import ObservationNamespace
    from tests.test_fabric_job_view_bounded import _identity
    from tests.test_mission_workspace import _owner_observation_inputs, _refresh_observation_digests

    root_id = runtime.jobs.get_job(profile.job_id).root_job_id
    # Read the companion through the same qualified bounded-read binding the
    # trusted caller uses, so the observation receipt attains SAME generation
    # on the real store instead of an unbound UNKNOWN.
    keeper = er.sqlite3.connect(runtime.store.path, isolation_level=None)
    keeper.execute("SELECT 1 FROM jobs").fetchone()
    namespace = ObservationNamespace(runtime.store.path)
    binding = er.RuntimeReadBinding(namespace)
    reader = Runtime.at(runtime.store.root, create=False, read_binding=binding)
    try:
        companion = read_fabric_view_v3_from_runtime(
            reader, root_id, armed={}, runtime_identity=_identity()
        )
    finally:
        keeper.close()
        if binding._unclosed_connection is not None:
            er.sqlite3.Connection.close(binding._unclosed_connection)
        if binding._retained_namespace is not None:
            binding._retained_namespace.close()
    args = _owner_observation_inputs()
    # Align the CCR owner selection to the root's real canonical workstream so
    # the observed pair is the genuine same-Mission selection.
    work = args["control_room"]["work"][0]
    work["work_ref"] = ROOT_WORKSTREAM
    work.setdefault("agent_os", {})["workstream"] = ROOT_WORKSTREAM.split(":", 1)[1]
    responsibility = args["control_room"]["autonomy"]["responsibilities"][0]
    responsibility["responsibility_ref"] = ROOT_WORKSTREAM
    responsibility["root_job_id"] = root_id
    responsibility["root_job_candidates"] = [root_id]
    responsibility["root_job_ambiguous"] = False
    responsibility["runtime_root_state"] = "RESOLVED"
    args["work_ref"] = ROOT_WORKSTREAM
    args["root_job_id"] = root_id
    cards = args["source_validity"].get("cards") or []
    if cards:
        cards[0]["responsibility_ref"] = ROOT_WORKSTREAM
        cards[0]["root_job_id"] = root_id
    args["fabric_view"] = companion
    args["owner_observation"]["selection"] = {"work_ref": ROOT_WORKSTREAM, "root_job_id": root_id}
    generation = companion["fabric_view"]["runtime"]["acquisition"]["generation"]
    digest = companion["fabric_view"]["runtime"]["acquisition"]["snapshot_digest"]
    args["owner_observation"]["runtime"] = dict(generation, snapshot_digest=digest)
    _refresh_observation_digests(args)
    document = compose_mission_workspace_v3(
        control_room=args["control_room"],
        fabric_view=companion,
        work_ref=args["work_ref"],
        root_job_id=root_id,
        source_validity=args["source_validity"],
        cache_currentness=args["cache_currentness"],
        source_generation=args["source_generation"],
        owner_observation=args["owner_observation"],
    )
    return document, {"work_ref": args["work_ref"], "root_job_id": root_id}, companion


def _run_focused_consumer(fresh_path, present=True):
    """Run ONLY the focused TS consumer as a bounded argv subprocess.

    The child environment is a copy of this process's environment with only
    the fresh-path contract key added or removed, so the consumer sees the
    externally supplied path exactly as a real caller would. A missing Node
    executable or missing consumer dependencies is an integration-gate
    failure, never a skip and never a fallback to the committed export.
    """
    vitest_entry = CONSUMER_APP_DIR / "node_modules" / "vitest" / "vitest.mjs"
    assert vitest_entry.exists(), (
        f"focused consumer dependencies absent: {vitest_entry}"
    )
    node = shutil.which("node")
    assert node, "node executable is required by the focused consumer gate"
    env = dict(os.environ)
    env.pop(CONSUMER_FRESH_KEY, None)
    if present:
        env[CONSUMER_FRESH_KEY] = str(fresh_path)
    argv = [
        node,
        "node_modules/vitest/vitest.mjs",
        "run",
        CONSUMER_TEST_PATH,
        "--pool",
        "threads",
        "--maxWorkers",
        "1",
        "--no-file-parallelism",
        "--no-cache",
    ]
    try:
        return subprocess.run(
            argv,
            cwd=str(CONSUMER_APP_DIR),
            env=env,
            capture_output=True,
            text=True,
            timeout=CONSUMER_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        raise AssertionError(
            f"focused consumer exceeded {CONSUMER_TIMEOUT_SECONDS}s"
        ) from error


def _focused_consumer_gate(tmp_path, document, profile):
    """Required cross-language positive plus external-input discriminators.

    ``document`` is the actual producer DTO of this run (mission, window,
    selection), written untouched to tmp_path and consumed from there; the
    committed export is never substituted for it. The consumer must accept
    exactly that file — reported on its stdout as a consumed path/digest and
    association identity this run produced — and must fail its process for
    every explicitly supplied unusable input. With the key absent the
    ordinary committed-export replay must still pass.
    """
    fresh_path = tmp_path / "fresh-producer-fixture.json"
    fresh_path.write_text(json.dumps(document, sort_keys=True) + "\n")
    expected_digest = hashlib.sha256(fresh_path.read_bytes()).hexdigest()

    positive = _run_focused_consumer(fresh_path)
    assert positive.returncode == 0, (
        "focused consumer rejected the actual fresh producer DTO\n"
        f"{positive.stdout}\n{positive.stderr}"
    )
    reports = [
        json.loads(line[len(CONSUMER_CONSUMED_PREFIX):])
        for line in positive.stdout.splitlines()
        if line.startswith(CONSUMER_CONSUMED_PREFIX)
    ]
    assert len(reports) == 1, positive.stdout
    report = reports[0]
    assert report["path"] == str(fresh_path), report
    assert report["sha256"] == expected_digest, report
    assert report["selection"] == document["selection"], report
    assert report["association"]["job_id"] == profile["job_id"], report
    assert report["association"]["attempt_id"] == profile["attempt_id"], report
    assert report["mission_schema"] == "mastermind.mission_workspace.v3", report
    assert report["window_schema"] == V2, report

    unusable = {
        "missing_file": tmp_path / "definitely-absent-producer.json",
        "malformed_json": tmp_path / "malformed-producer.json",
        "nonconforming_document": tmp_path / "nonconforming-producer.json",
    }
    unusable["malformed_json"].write_text("{ this is not json\n")
    unusable["nonconforming_document"].write_text(
        json.dumps(
            {
                "mission": {"schema": "mastermind.mission_workspace.v2"},
                "window": document["window"],
                "selection": document["selection"],
            },
            sort_keys=True,
        )
        + "\n"
    )
    for label, path in unusable.items():
        outcome = _run_focused_consumer(path)
        assert outcome.returncode != 0, (
            f"focused consumer accepted {label}: an explicitly supplied "
            f"unusable fresh input must fail the process gate\n{outcome.stdout}"
        )
    empty = _run_focused_consumer("")
    assert empty.returncode != 0, (
        "focused consumer accepted an explicitly empty fresh path\n"
        f"{empty.stdout}"
    )
    replay = _run_focused_consumer(None, present=False)
    assert replay.returncode == 0, (
        "focused consumer failed the ordinary committed-export replay\n"
        f"{replay.stdout}\n{replay.stderr}"
    )
    return fresh_path


def test_installed_config_derives_canonical_binding_from_real_profile(tmp_path):
    from integrations.mastermind_window_reader.owner_read_resource import ObservationBinding

    with _canonical_workstream_intent():
        clock, runtime, profile, adapter, broker = fixture(tmp_path)
    assert _check_job_id(profile.job_id) and _check_attempt_id(profile.attempt_id)
    key_material = _key()
    policy = _content_policy()
    config = construct_installed_live_window(
        profile=profile,
        authenticator=JwtAuthenticator(policy=policy, jwks_cache=_cache(policy, key_material)),
        content_policy=policy,
        audit_sink=_Sink(),
        ceo_ingress_socket_path=tmp_path / "unused.sock",
        now=lambda: clock.value // 1000,
        allowed_origin=ORIGIN,
    )
    assert type(config.observation_binding) is ObservationBinding
    assert config.observation_binding.job_id == profile.job_id
    assert config.observation_binding.attempt_id == profile.attempt_id


def test_actual_canonical_plan_child_and_reader_join(tmp_path, short_socket_root):
    async def run():
        async for ctx in _enrolled_reader(tmp_path, short_socket_root):
            assert ctx["status"] == 200, ctx["raw"]
            window = ctx["body"]
            profile = ctx["profile"]
            runtime = ctx["runtime"]
            app = ctx["app"]
            assert window["schema"] == V2
            assert window["observation_binding"] == {
                "job_id": profile.job_id,
                "attempt_id": profile.attempt_id,
            }
            assert "NATIVE-G1" not in ctx["raw"].decode()
            mission, selection, companion = _compose_mission(runtime, profile)
            planner = runtime.jobs.get_job(profile.job_id)
            root = runtime.jobs.get_job(planner.root_job_id)
            from control_plane.executive_runtime import JobStatus
            assert planner.orchestration_role == "plan"
            assert planner.parent_job_id == root.job_id == selection["root_job_id"]
            assert planner.status is JobStatus.RUNNING
            assert planner.current_attempt_id == profile.attempt_id
            assert planner.orchestration_provenance["source_id"] == root.job_id
            assert planner.orchestration_provenance["source_digest"] == root.orchestration_provenance_digest
            # The Fabric companion actually joined the plan child on the same
            # bounded observation: root workstream COMPLETE, no unjoined facts.
            fabric = companion["fabric_view"]
            assert [row["job_id"] for row in fabric["children"]] == [planner.job_id]
            assert fabric["runtime"]["acquisition"]["provenance"]["state"] == "COMPLETE"
            assert fabric["runtime"]["acquisition"]["provenance"]["unjoined_job_ids"] == []
            # Unconditional required positive: the canonical Mission carries the
            # joined plan child and the observed pair qualifies.
            assert mission["schema"] == "mastermind.mission_workspace.v3"
            assert mission["children"]["state"] == "AVAILABLE"
            assert mission["children"]["coverage"] == "COMPLETE"
            assert mission["children"]["unjoined_job_ids"] == []
            children = [
                row
                for row in mission["children"]["items"]
                if row["job_id"] == profile.job_id
            ]
            assert len(children) == 1, mission["children"]
            child = children[0]
            assert child["orchestration_role"] == "plan"
            assert child["parent_job_id"] == selection["root_job_id"]
            assert child["depth"] == 1
            assert child["current_attempt_id"] == profile.attempt_id
            assert child["status"] == "RUNNING"
            assert child["latest_attempt"]["attempt_id"] == profile.attempt_id
            assert child["latest_attempt"]["status"] == "RUNNING"
            assert _qualifies(mission, window, selection) is True
            joined = {
                "selection": selection,
                "window": window,
                "mission": mission,
                "profile_job_id": profile.job_id,
                "profile_attempt_id": profile.attempt_id,
                "runtime_plan_child": {
                    "job_id": planner.job_id,
                    "parent_job_id": planner.parent_job_id,
                    "root_job_id": planner.root_job_id,
                    "orchestration_role": planner.orchestration_role,
                    "status": str(planner.status),
                    "current_attempt_id": planner.current_attempt_id,
                },
                "mission_children": mission["children"],
                "qualified": True,
            }
            _write_artifact(tmp_path, "joined-canonical-fixture.json", joined)
            # The committed test-owned export stays a qualifying producer DTO.
            assert PRODUCER_EXPORT.exists(), PRODUCER_EXPORT
            prior = json.loads(PRODUCER_EXPORT.read_text())
            assert _qualifies(prior["mission"], prior["window"], prior["selection"]) is True

            negatives = {}
            replaced = copy.deepcopy(window)
            other = "ATT-" + "cd" * 16
            assert other != profile.attempt_id
            replaced["observation_binding"]["attempt_id"] = other
            negatives["replaced_attempt_id"] = _qualifies(mission, replaced, selection)
            foreign_job = copy.deepcopy(window)
            foreign_job["observation_binding"]["job_id"] = "JOB-999"
            negatives["cross_root_binding"] = _qualifies(mission, foreign_job, selection)
            cross_root = copy.deepcopy(selection)
            cross_root["root_job_id"] = "JOB-999"
            negatives["cross_root_selection"] = _qualifies(mission, window, cross_root)
            cross_workstream = copy.deepcopy(selection)
            cross_workstream["work_ref"] = "WS:OTHER"
            negatives["foreign_workstream_selection"] = _qualifies(mission, window, cross_workstream)
            terminal = copy.deepcopy(mission)
            for row in terminal["children"]["items"]:
                if row["job_id"] == profile.job_id:
                    row["status"] = "COMPLETED"
                    row["latest_attempt"]["status"] = "COMPLETED"
            negatives["terminal_child"] = _qualifies(terminal, window, selection)
            non_plan = copy.deepcopy(mission)
            for row in non_plan["children"]["items"]:
                if row["job_id"] == profile.job_id:
                    row["orchestration_role"] = "work"
            negatives["non_plan_child"] = _qualifies(non_plan, window, selection)
            unjoined_mission = copy.deepcopy(mission)
            unjoined_mission["children"]["state"] = "PARTIAL"
            negatives["partial_children"] = _qualifies(unjoined_mission, window, selection)
            v1 = dict(window)
            v1.pop("observation_binding")
            v1["schema"] = V1
            negatives["v1_window"] = _qualifies(mission, v1, selection)
            _write_artifact(tmp_path, "negative-controls.json", {
                "selection": selection,
                "window": replaced,
                "mission": mission,
                "negatives": negatives,
            })
            assert set(negatives.values()) == {False}
            # An unauthenticated Reader call yields no window at all: without a
            # permitted content response there is nothing to associate.
            status, _, raw, _ = await _invoke(app, path=WINDOW_PATH, headers=_headers(token=None))
            assert status == 401, (status, raw)
            return joined, negatives

    joined, negatives = asyncio.run(run())
    assert negatives == {
        "replaced_attempt_id": False,
        "cross_root_binding": False,
        "cross_root_selection": False,
        "foreign_workstream_selection": False,
        "terminal_child": False,
        "non_plan_child": False,
        "partial_children": False,
        "v1_window": False,
    }
    assert joined["window"]["schema"] == V2
    # Unconditional required cross-language positive: the actual producer DTO
    # of THIS run is written untouched to tmp_path and consumed by the
    # production TypeScript decoder chain, which must accept it, while every
    # explicitly supplied unusable input must fail the consumer's process.
    _focused_consumer_gate(
        tmp_path,
        {
            "mission": joined["mission"],
            "window": joined["window"],
            "selection": joined["selection"],
        },
        {
            "job_id": joined["profile_job_id"],
            "attempt_id": joined["profile_attempt_id"],
        },
    )


def test_generic_recorded_constructor_stays_v1():
    from integrations.mastermind_window_reader.owner_read_resource import (
        NativeOutputReadResource,
        WIRE_SCHEMA,
    )
    from tests.mastermind_window_reader.test_read_resource import OwnerFixture, RESOURCE, app, call

    status, _, body = call(app())
    document = json.loads(body)
    assert status == 200
    assert document["schema"] == WIRE_SCHEMA
    assert document["schema"] != V2
    assert "observation_binding" not in document
    with pytest.raises((TypeError, ValueError)):
        NativeOutputReadResource(
            owner=OwnerFixture(),
            resource=RESOURCE,
            source_ref="native-lane:a15_7054_p0b_r2",
            allowed_origin="https://workspace.example",
            observation_binding={"job_id": "JOB-1", "attempt_id": "ATT-" + "a" * 32},
        )

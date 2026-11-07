"""Closed v3 startup observation on the original real native-process channel.

The Python probe is deliberately not an actual DSH Agent. It qualifies framing,
generation and pre-prompt refusal. The current-donor fixture supplies Agent proof.
"""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
from types import SimpleNamespace

import pytest

from integrations.acp_worker.native import AcpNativeProcessOwner
from integrations.acp_worker.tool_admission import AcpAdmissionChannel, AcpNativeToolGate, AcpObservedTool
from test_acp_native_startup import launch
from test_acp_tool_admission import _trusted_attempt_overlay


PROBE = r"""
import hashlib, json, os, socket, sys
sock = socket.socket(fileno=int(os.environ['MMX_ACP_ATTEST_FD']))
stream = sock.makefile('rwb', buffering=0)
seed = json.loads(stream.readline())
mode = sys.argv[1]
reply = dict(seed, ready=True)
if 'attempt_overlay' in seed:
    reply['attempt_overlay_sha256'] = hashlib.sha256(json.dumps(
        seed['attempt_overlay'], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
if mode != 'missing':
    reply['native_session_id'] = 'native-session:1'
invalid = {'null': None, 'boolean': True, 'integer': 1, 'array': [],
           'empty': '', 'overlong': 'a' * 129, 'control': 'native\nother',
           'foreign-grammar': 'native/session', 'unicode': 'native-é'}
if mode in invalid: reply['native_session_id'] = invalid[mode]
if mode == 'v2': reply['schema'] = 'mastermind.acp_tools_ready/v2'
if mode == 'unknown-schema': reply['schema'] = 'mastermind.acp_tools_ready/v4'
if mode == 'extra': reply['session_owner'] = 'browser'
raw = json.dumps(reply)
if mode == 'duplicate': raw = raw[:-1] + ',"native_session_id":"native-session:1"}'
stream.write(raw.encode() + b'\n')
ack = stream.readline()
if ack: print(ack.decode().strip(), flush=True)
stream.close()
sock.close()
sys.stdin.read()
"""


def native_owner(launch, tmp_path, *, mode="ok", native_required=True):
    profile, spec = launch
    probe = tmp_path / "native-session-probe.py"
    probe.write_text(PROBE)
    profile = dataclasses.replace(profile, argv=(profile.argv[0], str(probe), mode))
    digest = hashlib.sha256(probe.read_bytes()).hexdigest()
    gate = AcpNativeToolGate(
        "a" * 64, digest, (AcpObservedTool("mcp__granted__read_file", "b" * 64),),
        ((str(probe), digest),), native_session_required=native_required,
    )
    owner = AcpNativeProcessOwner(
        profile, environment_loader=lambda: {}, tool_gate=gate,
        launch_argv_builder=lambda *_: profile.argv,
        attempt_overlay_builder=lambda row, workspace, _run: _trusted_attempt_overlay(row, workspace),
    )
    return owner, spec, probe


def test_v3_observation_matches_original_session_and_is_consumed_once(launch, tmp_path):
    owner, spec, _ = native_owner(launch, tmp_path)

    async def run():
        resources = await owner.open_run(spec)
        try:
            admission = await asyncio.wait_for(
                resources.prepare_prompt("native-session:1", spec.model), 3)
            channel = owner._runs[spec.run_id].admission_channel
            assert channel.seed["schema"] == "mastermind.acp_tools_ready/v3"
            assert "native_session_id" not in channel.seed
            assert admission.native_session_id == channel.native_session_id == "native-session:1"
            assert admission.matches(spec, resources.process_ref, "native-session:1", spec.model)
            assert json.loads(await resources.reader.readline()) == {"accepted": True}
            assert channel.task.done() and channel.writer.is_closing()
            with pytest.raises(ValueError, match="already consumed"):
                await resources.prepare_prompt("native-session:1", spec.model)
            with pytest.raises(ValueError, match="differs from the admitted session"):
                dataclasses.replace(admission, native_session_id="different-session")
        finally:
            finished = await resources.finish(None)
        assert finished.settled and owner._active is None
        assert not owner._identity_matches(resources.process_ref)

    asyncio.run(run())


@pytest.mark.parametrize("mode", [
    "missing", "null", "boolean", "integer", "array", "empty", "overlong",
    "control", "foreign-grammar", "unicode", "v2", "unknown-schema", "extra", "duplicate",
])
def test_v3_closed_observation_refuses_before_ack(launch, tmp_path, mode):
    owner, spec, _ = native_owner(launch, tmp_path, mode=mode)

    async def run():
        resources = await owner.open_run(spec)
        try:
            with pytest.raises(ValueError):
                await asyncio.wait_for(resources.prepare_prompt("native-session:1", spec.model), 3)
        finally:
            finished = await resources.finish("native observation refused")
        assert finished.settled and owner._active is None
        assert await resources.reader.read() == b""

    asyncio.run(run())


def test_v2_never_silently_adopts_a_native_observation_field(launch, tmp_path):
    owner, spec, _ = native_owner(launch, tmp_path, native_required=False)

    async def run():
        resources = await owner.open_run(spec)
        try:
            with pytest.raises(ValueError, match="readiness identity refused"):
                await asyncio.wait_for(resources.prepare_prompt("native-session:1", spec.model), 3)
        finally:
            finished = await resources.finish("wrong readiness version")
        assert finished.settled and owner._active is None
        assert await resources.reader.read() == b""

    asyncio.run(run())


def test_v3_standard_acp_session_mismatch_refuses_before_prompt(launch, tmp_path):
    owner, spec, _ = native_owner(launch, tmp_path)

    async def run():
        resources = await owner.open_run(spec)
        try:
            assert json.loads(await asyncio.wait_for(resources.reader.readline(), 3)) == {"accepted": True}
            with pytest.raises(ValueError, match="does not address the observed native session"):
                await resources.prepare_prompt("different-acp-session", spec.model)
            assert owner._runs[spec.run_id].admission_channel.native_session_id == "native-session:1"
            with pytest.raises(ValueError, match="already consumed"):
                await resources.prepare_prompt("native-session:1", spec.model)
        finally:
            finished = await resources.finish("session mismatch")
        assert finished.settled and owner._active is None

    asyncio.run(run())


@pytest.mark.parametrize("changed", ["expired", "artifact", "process"])
def test_v3_rechecks_original_authority_at_prompt_boundary(launch, tmp_path, monkeypatch, changed):
    owner, spec, probe = native_owner(launch, tmp_path)

    async def run():
        resources = await owner.open_run(spec)
        try:
            assert json.loads(await asyncio.wait_for(resources.reader.readline(), 3)) == {"accepted": True}
            channel = owner._runs[spec.run_id].admission_channel
            if changed == "expired":
                from integrations.acp_worker import tool_admission
                expiry = int(channel.attempt_overlay["env"]["MMX_ACP_DEADLINE_MS"])
                monkeypatch.setattr(tool_admission, "time", SimpleNamespace(time=lambda: expiry / 1000 + 1))
            elif changed == "artifact":
                probe.write_text(PROBE + "\n# changed after readiness\n")
            else:
                channel.identity_matches = lambda _ref: False
            with pytest.raises(ValueError):
                await resources.prepare_prompt("native-session:1", spec.model)
        finally:
            finished = await resources.finish("original readiness no longer qualifies")
        assert finished.settled and owner._active is None

    asyncio.run(run())


def test_v3_gate_requires_exact_overlay_before_descriptor_or_process(launch, tmp_path, monkeypatch):
    owner, spec, _ = native_owner(launch, tmp_path)
    from integrations.acp_worker import tool_admission

    def forbidden():
        pytest.fail("missing original Attempt reached descriptor creation")

    monkeypatch.setattr(tool_admission.socket, "socketpair", forbidden)
    with pytest.raises(ValueError, match="requires the exact Attempt overlay"):
        AcpAdmissionChannel(owner.tool_gate)
    for value in (1, "true", None):
        with pytest.raises(ValueError, match="must be a boolean"):
            dataclasses.replace(owner.tool_gate, native_session_required=value)


def test_generic_v2_node_helper_refuses_v3_without_native_observer(launch, tmp_path):
    from test_acp_native_dsh_child import _build
    owner, spec = _build(launch, tmp_path, native_required=True)

    async def run():
        resources = await owner.open_run(spec)
        try:
            with pytest.raises(ValueError):
                await asyncio.wait_for(resources.prepare_prompt("native-session:1", spec.model), 5)
        finally:
            finished = await resources.finish("generic helper cannot attest native Agent")
        assert finished.settled and owner._active is None
        assert b"after-native-v2" not in await resources.reader.read()

    asyncio.run(run())

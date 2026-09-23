import contextlib
import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from control_plane.sol_ops_restart import RestartObservation, RestartRequest, RestartState
import scripts.mastermind_chatgpt_ops_restart as ops


class SequenceOwner:
    def __init__(self, observations, *, fail_after=None):
        self.observations = list(observations)
        self.actions = []
        self.fail_after = fail_after

    def observe(self, service_ref):
        if len(self.observations) > 1:
            return self.observations.pop(0)
        return self.observations[0]

    def action(self, account, action):
        self.actions.append((account, action))
        if self.fail_after == len(self.actions):
            raise subprocess.TimeoutExpired(["fixed-owner"], 1)
        return {"ok": True}


class DisposableProcessOwner:
    def __init__(self):
        self.proc = None
        self.build = "b" * 64
        self.actions = []
        self.start()

    def start(self):
        self.proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def close(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=2)

    def observe(self, service_ref):
        pid = self.proc.pid if self.proc and self.proc.poll() is None else None
        return RestartObservation(
            service_ref=service_ref,
            instance_identity=ops._digest({"disposable_pid": pid}),
            build_identity=self.build,
            ready=pid is not None,
            runtime_version="fixture",
            issues=(),
        )

    def action(self, account, action):
        self.actions.append((account, action))
        if action == "stop":
            self.close()
        elif action == "start":
            self.start()
        else:
            raise AssertionError(action)
        return {"ok": True}


class OpsRestartTests(unittest.TestCase):
    def observation(self, instance="1" * 64, build="2" * 64, ready=True, issues=()):
        return RestartObservation(
            service_ref="studio-direct.chatgpt1",
            instance_identity=instance,
            build_identity=build,
            ready=ready,
            runtime_version="0.1.5",
            issues=issues,
        )

    def request(self, instance="1" * 64, build="2" * 64):
        return RestartRequest(
            service_ref="studio-direct.chatgpt1",
            expected_instance_identity=instance,
            expected_build_identity=build,
            reason_code="health_recovery",
        )

    def restart(self, request, **kwargs):
        kwargs.setdefault("lock_fn", contextlib.nullcontext)
        return ops.restart_exact_service(request, **kwargs)

    def test_lock_contention_refuses_before_observation_or_owner_effect(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            root.chmod(0o700)
            owner = SequenceOwner([self.observation()])
            with patch.object(ops, "CONTROL_ROOT", root):
                with ops._restart_lock():
                    with self.assertRaisesRegex(RuntimeError, "restart already in progress"):
                        ops.restart_exact_service(
                            self.request(), observe_fn=owner.observe, action_fn=owner.action
                        )
            self.assertEqual(owner.actions, [])
            self.assertEqual(len(owner.observations), 1)

    def test_service_mapping_is_closed_to_isolated_studio_routes(self):
        self.assertEqual(
            ops.SERVICE_TO_ACCOUNT,
            {
                "studio-direct.chatgpt1": "chatgpt1",
                "studio-direct.chatgpt2-personal": "chatgpt2-personal",
                "studio-direct.chatgpt2-business": "chatgpt2-business",
                "studio-direct.admin-business": "admin-business",
                "studio-direct.chatgpt3-w570f6f34": "chatgpt3-w570f6f34",
                "studio-direct.chatgpt3-wa2a9e6f9": "chatgpt3-wa2a9e6f9",
                "studio-direct.chatgpt4": "chatgpt4",
            },
        )
        self.assertNotIn("studio-direct.chatgpt2", ops.SERVICE_TO_ACCOUNT)
        self.assertNotIn("studio-direct.chatgpt3", ops.SERVICE_TO_ACCOUNT)
        self.assertNotIn("studio-direct.all", ops.SERVICE_TO_ACCOUNT)

    def test_manifest_identity_is_secret_free_and_changes_on_build_change(self):
        base = {
            "version": 2,
            "account": "chatgpt1",
            "label": "com.mastermind.studio-direct-private.chatgpt1",
            "configHash": "a" * 64,
            "nodeHash": "b" * 64,
            "backendHash": "c" * 64,
            "dependencyTreeHash": "d" * 64,
            "plistHash": "e" * 64,
            "files": {"gateway.mjs": "f" * 64},
            "source": "/private/should-not-project",
            "backend": "/private/backend",
            "node": "/private/node",
        }
        one = ops._build_identity("chatgpt1", base)
        changed = dict(base, configHash="0" * 64)
        two = ops._build_identity("chatgpt1", changed)
        self.assertNotEqual(one, two)
        self.assertNotIn("/private/", one)

    def test_instance_identity_changes_when_generation_changes(self):
        status = {
            "gateway": {"pid": 11, "runtimeVersion": "0.1.5", "configurationDrift": False},
            "tunnel": {"pid": 22, "tunnelId": "tunnel_" + "a" * 32},
            "ready": True,
        }
        one = ops._instance_identity("chatgpt1", status)
        status["gateway"]["pid"] = 33
        two = ops._instance_identity("chatgpt1", status)
        self.assertNotEqual(one, two)

    def test_success_restarts_once_and_duplicate_old_identity_refuses(self):
        before = self.observation()
        after = self.observation(instance="3" * 64)
        owner = SequenceOwner([before, after])
        result = self.restart(
            self.request(), observe_fn=owner.observe, action_fn=owner.action
        )
        self.assertEqual(result.state, RestartState.APPLIED)
        self.assertTrue(result.ready)
        self.assertEqual(owner.actions, [("chatgpt1", "stop"), ("chatgpt1", "start")])

        duplicate = self.restart(
            self.request(), observe_fn=lambda _: after, action_fn=owner.action
        )
        self.assertEqual(duplicate.state, RestartState.NOT_APPLIED)
        self.assertEqual(duplicate.code, "STALE_INSTANCE_IDENTITY")
        self.assertEqual(owner.actions, [("chatgpt1", "stop"), ("chatgpt1", "start")])

    def test_lost_response_reconciles_applied_when_generation_changed(self):
        before = self.observation()
        after = self.observation(instance="4" * 64)
        owner = SequenceOwner([before, after], fail_after=1)
        result = self.restart(
            self.request(), observe_fn=owner.observe, action_fn=owner.action
        )
        self.assertEqual(result.state, RestartState.APPLIED)
        self.assertEqual(result.code, "APPLIED_RECONCILED_AFTER_OWNER_ERROR")
        self.assertFalse(result.retry_allowed)

    def test_lost_response_without_generation_change_is_effect_unknown(self):
        before = self.observation()
        owner = SequenceOwner([before, before], fail_after=1)
        result = self.restart(
            self.request(), observe_fn=owner.observe, action_fn=owner.action
        )
        self.assertEqual(result.state, RestartState.EFFECT_UNKNOWN)
        self.assertFalse(result.retry_allowed)

    def test_build_change_during_restart_is_applied_but_explicit(self):
        before = self.observation()
        after = self.observation(instance="5" * 64, build="6" * 64)
        owner = SequenceOwner([before, after])
        result = self.restart(
            self.request(), observe_fn=owner.observe, action_fn=owner.action
        )
        self.assertEqual(result.state, RestartState.APPLIED)
        self.assertEqual(result.code, "APPLIED_BUILD_CHANGED_DURING_RESTART")
        self.assertFalse(result.retry_allowed)

    def test_disposable_real_process_restart_changes_instance_and_duplicate_is_zero_effect(self):
        owner = DisposableProcessOwner()
        try:
            before = owner.observe("studio-direct.chatgpt1")
            request = RestartRequest(
                service_ref=before.service_ref,
                expected_instance_identity=before.instance_identity,
                expected_build_identity=before.build_identity,
                reason_code="release_canary",
            )
            result = self.restart(
                request, observe_fn=owner.observe, action_fn=owner.action
            )
            self.assertEqual(result.state, RestartState.APPLIED)
            self.assertNotEqual(result.instance_identity, before.instance_identity)
            calls = list(owner.actions)
            duplicate = self.restart(
                request, observe_fn=owner.observe, action_fn=owner.action
            )
            self.assertEqual(duplicate.state, RestartState.NOT_APPLIED)
            self.assertEqual(owner.actions, calls)
        finally:
            owner.close()

    def test_observe_projection_does_not_emit_raw_owner_details(self):
        manifest = {
            "version": 2,
            "account": "chatgpt1",
            "label": "com.mastermind.studio-direct-private.chatgpt1",
            "configHash": "a" * 64,
            "nodeHash": "b" * 64,
            "backendHash": "c" * 64,
            "dependencyTreeHash": "d" * 64,
            "plistHash": "e" * 64,
            "files": {"gateway.mjs": "f" * 64},
        }
        status = {
            "ready": True,
            "gateway": {"pid": 123, "runtimeVersion": "0.1.5", "configurationDrift": False},
            "tunnel": {"pid": 124, "tunnelId": "tunnel_" + "a" * 32},
        }
        row = ops.observe_exact_service(
            "studio-direct.chatgpt1",
            status_reader=lambda _: status,
            manifest_reader=lambda _: manifest,
        ).to_dict()
        encoded = json.dumps(row)
        self.assertNotIn("123", encoded)
        self.assertNotIn("124", encoded)
        self.assertNotIn("tunnel_", encoded)
        self.assertNotIn("/Users/", encoded)
        self.assertEqual(row["service_ref"], "studio-direct.chatgpt1")


if __name__ == "__main__":
    unittest.main()

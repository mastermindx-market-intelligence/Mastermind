"""Host lifecycle tests. Factory/host authorization here are explicit fixtures."""
from contextvars import Context
from types import SimpleNamespace as N
import unittest
from unittest.mock import patch

from integrations.hermes_application_fabric.attended_host import AttendedHost
from integrations.hermes_application_fabric.client import ApplicationBinding, NativeCall
from integrations.hermes_application_fabric.errors import HermesFabricError
from integrations.hermes_application_fabric.native import PROVIDER


class HostTests(unittest.TestCase):
    def setUp(self):
        self.callbacks, self.disposals, self.closes, self.factories = [], [], [], []
        self.allow = True
        def register(kind, callback):
            self.callbacks.append((kind, callback))
            return N(dispose=lambda: self.disposals.append(kind))
        self.host = AttendedHost(N(register_middleware=register))
        self.call = NativeCall("session-1", "task-1", "turn-1", "api-1")

    def turn(self, **overrides):
        options = dict(factory=object(), operation_id="owner-op-1", session_id="session-1",
            task_id="task-1", requested_model="host-model", strict_model="actual-model",
            authorized=lambda _: self.allow, prior_admission_possible=False)
        options.update(overrides)
        return self.host.admitted_turn(**options)

    def bind(self, factory, **kwargs):
        self.factories.append(kwargs)
        owner = N(_closed=False)
        def close():
            owner._closed = True
            receipt = {"closed": False, "effect_unknown": True, "original": kwargs["operation_id"]}
            self.closes.append(receipt)
            return receipt
        owner.close = close
        binding = object.__new__(ApplicationBinding)
        binding._owner, binding._authorized = owner, kwargs["authorized"]
        binding.operation_id, binding.session_id, binding.turn_id = (
            kwargs["operation_id"], kwargs["session_id"], kwargs["turn_id"])
        binding.model, binding.requested_model = "actual-model", kwargs["requested_model"]
        return binding

    def test_scope_registers_once_and_retains_original_binding_and_close(self):
        turn = self.turn()
        with patch.object(ApplicationBinding, "from_factory", side_effect=self.bind):
            with self.host.activate(turn):
                first = self.host._resolve(self.call)
                rebuilt = self.host._resolve(NativeCall("session-1", "task-1", "turn-1", "api-2"))
                self.assertIs(first, rebuilt)
                self.assertEqual(len(self.factories), 1)
                self.assertEqual(self.factories[0]["profile_id"], "attended")
                self.assertEqual(self.factories[0]["strict_model"], "actual-model")
            self.assertIsNone(self.host._resolve(self.call))
            self.assertIs(turn.close(), self.closes[0])
            self.assertIs(turn.close_result, self.closes[0])
        self.assertEqual(len(self.closes), 1)
        self.assertEqual(len(self.callbacks), 1)

    def test_auto_selection_retains_one_binding_and_original_output_bound(self):
        turn = self.turn(requested_model=f"{PROVIDER}/auto", strict_model=None,
                         automatic=True, strict_pool="go", max_output_tokens=512)
        with patch.object(ApplicationBinding, "from_factory", side_effect=self.bind):
            with self.host.activate(turn):
                first = self.host._resolve(self.call)
                self.assertIs(first, self.host._resolve(
                    NativeCall("session-1", "task-1", "turn-1", "api-2")))
        self.assertEqual(len(self.factories), 1)
        self.assertEqual((self.factories[0]["automatic"], self.factories[0]["strict_model"],
                          self.factories[0]["strict_pool"], self.factories[0]["max_output_tokens"]),
                         (True, None, "go", 512))

    def test_invalid_host_selection_never_constructs_a_binding(self):
        with patch.object(ApplicationBinding, "from_factory") as bind:
            for values in ({"automatic": 1}, {"strict_model": None},
                           {"strict_pool": "go"}, {"automatic": True, "strict_pool": ""},
                           {"max_output_tokens": True}, {"max_output_tokens": 0},
                           {"max_output_tokens": 32769}):
                with self.subTest(values=values), self.assertRaises(HermesFabricError):
                    self.turn(**values)
            bind.assert_not_called()

    def test_unknown_prior_admission_is_not_rebound(self):
        for prior in (True, None, 0, ""):
            with self.subTest(prior=prior), self.assertRaises(HermesFabricError):
                self.turn(prior_admission_possible=prior)

    def test_wrong_session_task_and_revoked_host_never_bind(self):
        turn = self.turn()
        with patch.object(ApplicationBinding, "from_factory") as factory, self.host.activate(turn):
            for call in (NativeCall("other", "task-1", "turn-1", "api-1"),
                         NativeCall("session-1", "other", "turn-1", "api-1")):
                with self.assertRaises(HermesFabricError):
                    self.host._resolve(call)
            self.allow = False
            with self.assertRaises(HermesFabricError):
                self.host._resolve(self.call)
            factory.assert_not_called()

    def test_failed_binding_is_terminal_without_replay(self):
        turn = self.turn()
        with patch.object(ApplicationBinding, "from_factory",
                side_effect=HermesFabricError("hermes_fabric_role_unqualified")) as factory:
            with self.host.activate(turn):
                for _ in range(2):
                    with self.assertRaises(HermesFabricError):
                        self.host._resolve(self.call)
            self.assertEqual(factory.call_count, 1)
            self.assertEqual(turn.refusal, ("hermes_fabric_role_unqualified", False))

    def test_unexpected_binding_failure_retains_uncertainty_without_raw_error(self):
        turn = self.turn()
        with patch.object(ApplicationBinding, "from_factory",
                side_effect=RuntimeError("private owner detail")) as factory:
            with self.host.activate(turn):
                for _ in range(2):
                    with self.assertRaises(HermesFabricError) as raised:
                        self.host._resolve(self.call)
                    self.assertTrue(raised.exception.effect_unknown)
                    self.assertNotIn("private", str(raised.exception))
                    self.assertIsNone(raised.exception.__context__)
            self.assertEqual(factory.call_count, 1)

    def test_turn_identity_cannot_change_on_rebuilt_facade(self):
        turn = self.turn()
        with patch.object(ApplicationBinding, "from_factory", side_effect=self.bind):
            with self.host.activate(turn):
                self.host._resolve(self.call)
                with self.assertRaises(HermesFabricError):
                    self.host._resolve(NativeCall("session-1", "task-1", "other-turn", "api-2"))
        self.assertEqual(len(self.factories), 1)

    def test_independent_native_contexts_do_not_share_bindings(self):
        one, two = self.turn(), self.turn(operation_id="owner-op-2", session_id="session-2", task_id="task-2")
        second_call = NativeCall("session-2", "task-2", "turn-2", "api-2")
        def second():
            with self.host.activate(two):
                return self.host._resolve(second_call)
        with patch.object(ApplicationBinding, "from_factory", side_effect=self.bind):
            with self.host.activate(one):
                first = self.host._resolve(self.call)
                other = Context().run(second)
                self.assertIs(self.host._resolve(self.call), first)
                self.assertIsNot(first, other)
        self.assertEqual(len(self.factories), 2)
        self.assertEqual(len(self.closes), 2)

    def test_dispose_revokes_current_host_before_late_result(self):
        turn = self.turn()
        with patch.object(ApplicationBinding, "from_factory", side_effect=self.bind):
            with self.host.activate(turn):
                binding = self.host._resolve(self.call)
                self.host.dispose()
                with self.assertRaises(HermesFabricError):
                    binding.check(self.call)
                self.assertIsNone(self.host._resolve(self.call))
        self.assertEqual(len(self.closes), 1)

    def test_scope_reentry_and_foreign_turn_refuse(self):
        turn = self.turn()
        with self.host.activate(turn):
            with self.assertRaises(HermesFabricError):
                with self.host.activate(turn):
                    pass
        with self.assertRaises(HermesFabricError):
            with self.host.activate(turn):
                pass

    def test_gateway_route_cannot_smuggle_credentials_or_fallback(self):
        turn = self.turn()
        route = dict(model="host-model", session_id="session-1", provider=PROVIDER,
            requested_provider=PROVIDER, api_mode="chat_completions")
        with self.host.activate(turn), patch(
                "integrations.hermes_application_fabric.attended_host.create_primary_agent") as create:
            for change in ({"provider": "zai"}, {"api_key": "secret"}, {"base_url": "https://example.com"},
                           {"fallback_model": [{"provider": "zai"}]}, {"credential_pool": object()},
                           {"session_id": "other"}, {"model": "other"}):
                with self.subTest(change=list(change)), self.assertRaises(HermesFabricError):
                    turn.create_gateway_agent(**(route | change))
            create.assert_not_called()
            turn.create_gateway_agent(**route, api_key=None, base_url="", fallback_model=[],
                                      enabled_toolsets=["terminal"])
            self.assertEqual(create.call_args.kwargs,
                {"model": "host-model", "session_id": "session-1", "enabled_toolsets": ["terminal"]})

    def test_agent_construction_outside_original_scope_refuses(self):
        turn = self.turn()
        with self.assertRaises(HermesFabricError):
            turn.create_agent(model="host-model", session_id="session-1")

    def test_exception_exit_closes_the_same_owner(self):
        turn = self.turn()
        with patch.object(ApplicationBinding, "from_factory", side_effect=self.bind):
            with self.assertRaisesRegex(RuntimeError, "fixture stop"):
                with self.host.activate(turn):
                    self.host._resolve(self.call)
                    raise RuntimeError("fixture stop")
        self.assertEqual(len(self.closes), 1)
        self.assertTrue(turn.close_result["effect_unknown"])


if __name__ == "__main__":
    unittest.main()

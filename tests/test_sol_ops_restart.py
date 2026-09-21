import unittest

from control_plane.sol_ops_restart import (
    RestartObservation,
    RestartRequest,
    RestartState,
    preflight_restart,
)

D1 = "1" * 64
D2 = "2" * 64


class SolOpsRestartContractTests(unittest.TestCase):
    def observation(self, **overrides):
        values = dict(
            service_ref="studio-direct.chatgpt1",
            instance_identity=D1,
            build_identity=D2,
            ready=True,
            runtime_version="0.1.5",
            issues=(),
        )
        values.update(overrides)
        return RestartObservation(**values)

    def request(self, **overrides):
        values = dict(
            service_ref="studio-direct.chatgpt1",
            expected_instance_identity=D1,
            expected_build_identity=D2,
            reason_code="health_recovery",
        )
        values.update(overrides)
        return RestartRequest(**values)

    def test_exact_current_identity_is_eligible(self):
        self.assertIsNone(preflight_restart(self.request(), self.observation()))

    def test_stale_instance_refuses_without_effect(self):
        result = preflight_restart(
            self.request(expected_instance_identity="3" * 64), self.observation()
        )
        self.assertEqual(result.state, RestartState.NOT_APPLIED)
        self.assertEqual(result.code, "STALE_INSTANCE_IDENTITY")

    def test_stale_build_refuses_without_effect(self):
        result = preflight_restart(
            self.request(expected_build_identity="4" * 64), self.observation()
        )
        self.assertEqual(result.state, RestartState.NOT_APPLIED)
        self.assertEqual(result.code, "STALE_BUILD_IDENTITY")

    def test_configuration_drift_refuses_before_restart(self):
        result = preflight_restart(
            self.request(), self.observation(issues=("CONFIGURATION_DRIFT",))
        )
        self.assertEqual(result.state, RestartState.NOT_APPLIED)
        self.assertEqual(result.code, "CONFIGURATION_DRIFT")

    def test_unknown_service_reason_and_bad_digest_refuse(self):
        for request in (
            self.request(service_ref="studio-direct.all"),
            self.request(reason_code="restart_everything"),
            self.request(expected_instance_identity="not-a-digest"),
        ):
            with self.subTest(request=request):
                with self.assertRaises(ValueError):
                    preflight_restart(request, self.observation())


if __name__ == "__main__":
    unittest.main()

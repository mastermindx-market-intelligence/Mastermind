import json
import unittest

from control_plane.sol_ops_health import (
    OpsHealthError,
    OpsState,
    ServiceFact,
    TunnelFact,
    project_ops_health,
)


def service(name="studio-direct.chatgpt1", *, live=True, ready=True, issues=()):
    return ServiceFact(
        service_ref=name,
        service_kind="studio_direct_gateway",
        scope="personal_account",
        owner_ref="studio-direct",
        observed_at="2026-09-20T05:30:00Z",
        live=live,
        ready=ready,
        runtime_version="0.1.6",
        deployment_ref="gateway-0.1.6",
        source_refs=("studio-direct:chatgpt1",),
        issues=issues,
    )


def tunnel(name="tunnel_0123456789abcdef0123456789abcdef", *, live=True, ready=True, issues=()):
    return TunnelFact(
        tunnel_ref=name,
        service_ref="studio-direct.chatgpt1",
        owner_ref="studio-direct",
        observed_at="2026-09-20T05:30:00Z",
        live=live,
        ready=ready,
        source_refs=("studio-direct:chatgpt1",),
        issues=issues,
    )


class OpsHealthProjectionTests(unittest.TestCase):
    def test_ready_owner_facts_project_ready(self):
        out = project_ops_health(
            (service(),),
            (tunnel(),),
            observed_at="2026-09-20T05:30:01Z",
            generation="scf-ops1",
        )
        self.assertEqual(out.overall_state, OpsState.READY)
        self.assertEqual(out.services[0].state, OpsState.READY)
        self.assertEqual(out.tunnels[0].state, OpsState.READY)

    def test_live_but_not_ready_is_degraded(self):
        out = project_ops_health(
            (service(ready=False),),
            (tunnel(ready=False),),
            observed_at="2026-09-20T05:30:01Z",
            generation="scf-ops1",
        )
        self.assertEqual(out.overall_state, OpsState.DEGRADED)

    def test_explicit_not_live_is_unavailable(self):
        out = project_ops_health(
            (service(live=False, ready=False),),
            (tunnel(live=False, ready=False),),
            observed_at="2026-09-20T05:30:01Z",
            generation="scf-ops1",
        )
        self.assertEqual(out.overall_state, OpsState.UNAVAILABLE)

    def test_missing_owner_signal_is_unknown_not_green(self):
        out = project_ops_health(
            (service(live=None, ready=None),),
            (tunnel(live=None, ready=None),),
            observed_at="2026-09-20T05:30:01Z",
            generation="scf-ops1",
        )
        self.assertEqual(out.overall_state, OpsState.UNKNOWN)

    def test_issues_make_otherwise_ready_row_degraded(self):
        out = project_ops_health(
            (service(issues=("CONFIGURATION_DRIFT",)),),
            (tunnel(),),
            observed_at="2026-09-20T05:30:01Z",
            generation="scf-ops1",
        )
        self.assertEqual(out.services[0].state, OpsState.DEGRADED)

    def test_duplicate_service_refs_refuse(self):
        with self.assertRaisesRegex(OpsHealthError, "duplicate service_ref"):
            project_ops_health(
                (service(), service()),
                (tunnel(),),
                observed_at="2026-09-20T05:30:01Z",
                generation="scf-ops1",
            )

    def test_tunnel_must_reference_projected_service(self):
        with self.assertRaisesRegex(OpsHealthError, "unknown service_ref"):
            project_ops_health(
                (service("studio-direct.chatgpt2"),),
                (tunnel(),),
                observed_at="2026-09-20T05:30:01Z",
                generation="scf-ops1",
            )

    def test_secret_shaped_source_ref_refuses(self):
        bad = ServiceFact(
            service_ref="studio-direct.chatgpt1",
            service_kind="studio_direct_gateway",
            scope="personal_account",
            owner_ref="studio-direct",
            observed_at="2026-09-20T05:30:00Z",
            live=True,
            ready=True,
            runtime_version=None,
            deployment_ref=None,
            source_refs=("authorization=Bearer abc",),
            issues=(),
        )
        with self.assertRaisesRegex(OpsHealthError, "secret-shaped"):
            project_ops_health(
                (bad,),
                (),
                observed_at="2026-09-20T05:30:01Z",
                generation="scf-ops1",
            )

    def test_digest_is_stable_across_input_order(self):
        services = (service("studio-direct.chatgpt2"), service("studio-direct.chatgpt1"))
        tunnels = (
            TunnelFact(
                tunnel_ref="tunnel_1123456789abcdef0123456789abcdef",
                service_ref="studio-direct.chatgpt2",
                owner_ref="studio-direct",
                observed_at="2026-09-20T05:30:00Z",
                live=True,
                ready=True,
                source_refs=("studio-direct:chatgpt2",),
            ),
            tunnel(),
        )
        a = project_ops_health(services, tunnels, observed_at="2026-09-20T05:30:01Z", generation="scf-ops1")
        b = project_ops_health(tuple(reversed(services)), tuple(reversed(tunnels)), observed_at="2026-09-20T05:30:01Z", generation="scf-ops1")
        self.assertEqual(a.canonical_digest, b.canonical_digest)
        json.dumps(a.to_dict(), sort_keys=True)


if __name__ == "__main__":
    unittest.main()

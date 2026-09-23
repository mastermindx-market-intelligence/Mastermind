import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.mastermind_chatgpt_ops_health as ops
from control_plane.sol_ops_health import OpsState


class ChatGptOpsHealthTests(unittest.TestCase):
    def test_direct_entrypoint_bootstraps_repo_root_before_mastermind_import(self):
        source = Path(ops.__file__).read_text()
        root_line = source.index("_REPO_ROOT = Path(__file__).resolve().parents[1]")
        insert_line = source.index("sys.path.insert(0, str(_REPO_ROOT))")
        import_line = source.index("from control_plane.sol_ops_health import")
        self.assertLess(root_line, insert_line)
        self.assertLess(insert_line, import_line)

    def test_studio_accounts_are_closed_to_isolated_routes(self):
        self.assertEqual(
            ops.STUDIO_ACCOUNTS,
            (
                "chatgpt1",
                "chatgpt2-personal",
                "chatgpt2-business",
                "chatgpt3-w570f6f34",
                "chatgpt3-wa2a9e6f9",
                "chatgpt4",
            ),
        )
        self.assertNotIn("chatgpt2", ops.STUDIO_ACCOUNTS)
        self.assertNotIn("chatgpt3", ops.STUDIO_ACCOUNTS)

    def test_personal_fact_preserves_owner_status_without_paths_or_args(self):
        status = {
            "account": "chatgpt1",
            "ready": True,
            "gateway": {
                "running": True,
                "runtimeReady": True,
                "runtimeVersion": "0.1.5",
                "configurationDrift": False,
            },
            "tunnel": {
                "healthy": True,
                "ready": True,
                "tunnelId": "tunnel_0123456789abcdef0123456789abcdef",
            },
        }
        service, tunnel = ops.personal_facts("chatgpt1", status, "2026-09-20T05:30:00Z")
        self.assertTrue(service.live)
        self.assertTrue(service.ready)
        self.assertEqual(service.runtime_version, "0.1.5")
        self.assertEqual(tunnel.tunnel_ref, status["tunnel"]["tunnelId"])
        self.assertNotIn("/Users/", json.dumps({"service": service.source_refs, "tunnel": tunnel.source_refs}))

    def test_personal_fact_falls_back_to_owner_end_to_end_ready(self):
        status = {
            "account": "chatgpt2-personal",
            "ready": True,
            "gateway": {
                "running": True,
                "configurationDrift": False,
            },
            "tunnel": {
                "healthy": True,
                "ready": True,
                "tunnelId": "tunnel_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            },
        }
        service, _ = ops.personal_facts(
            "chatgpt2-personal", status, "2026-09-20T05:30:00Z"
        )
        self.assertTrue(service.live)
        self.assertTrue(service.ready)

    def test_personal_configuration_drift_is_explicit_issue(self):
        status = {
            "account": "chatgpt2-personal",
            "gateway": {
                "running": True,
                "runtimeReady": True,
                "runtimeVersion": "0.1.5",
                "configurationDrift": True,
            },
            "tunnel": {
                "healthy": True,
                "ready": True,
                "tunnelId": "tunnel_1123456789abcdef0123456789abcdef",
            },
        }
        service, _ = ops.personal_facts("chatgpt2-personal", status, "2026-09-20T05:30:00Z")
        self.assertIn("CONFIGURATION_DRIFT", service.issues)

    def test_business_profile_extracts_only_tunnel_identity(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "profile.json"
            p.write_text(json.dumps({
                "control_plane": {
                    "tunnel_id": "tunnel_2123456789abcdef0123456789abcdef",
                    "api_key": "super-secret",
                },
                "mcp": {"url": "http://127.0.0.1:9999/mcp"},
            }))
            self.assertEqual(
                ops.read_tunnel_id(p),
                "tunnel_2123456789abcdef0123456789abcdef",
            )

    def test_business_profile_refuses_symlink_and_oversize(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / "profile-target.json"
            target.write_text(json.dumps({
                "control_plane": {
                    "tunnel_id": "tunnel_2123456789abcdef0123456789abcdef",
                },
            }))
            link = root / "profile-link.json"
            link.symlink_to(target)
            with self.assertRaisesRegex(ValueError, "regular bounded file"):
                ops.read_tunnel_id(link)

            oversized = root / "oversized.json"
            oversized.write_text("x" * (ops.MAX_PROFILE_BYTES + 1))
            with self.assertRaisesRegex(ValueError, "regular bounded file"):
                ops.read_tunnel_id(oversized)

    def test_health_ref_refuses_symlink_before_http(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / "health-target.url"
            target.write_text("http://127.0.0.1:9999")
            link = root / "health-link.url"
            link.symlink_to(target)
            called = []
            live, ready, issues = ops.probe_health_ref(
                link, lambda url: called.append(url) or 200
            )
            self.assertIsNone(live)
            self.assertIsNone(ready)
            self.assertEqual(issues, ("HEALTH_REF_UNAVAILABLE",))
            self.assertEqual(called, [])

    def test_health_ref_rejects_non_loopback_before_http(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "health.url"
            p.write_text("https://example.com:443")
            called = []
            live, ready, issues = ops.probe_health_ref(
                p, lambda url: called.append(url) or 200
            )
            self.assertIsNone(live)
            self.assertIsNone(ready)
            self.assertIn("HEALTH_REF_NOT_LOOPBACK", issues)
            self.assertEqual(called, [])

    def test_health_ref_probes_only_healthz_and_readyz(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "health.url"
            p.write_text("http://127.0.0.1:9999")
            called = []
            def get(url):
                called.append(url)
                return 200
            live, ready, issues = ops.probe_health_ref(p, get)
            self.assertTrue(live)
            self.assertTrue(ready)
            self.assertEqual(issues, ())
            self.assertEqual(
                called,
                [
                    "http://127.0.0.1:9999/healthz",
                    "http://127.0.0.1:9999/readyz",
                ],
            )

    def test_build_snapshot_composes_six_isolated_studio_and_two_business_services(self):
        tunnel_ids = {
            account: f"tunnel_{index:032x}"
            for index, account in enumerate(ops.STUDIO_ACCOUNTS, start=1)
        }

        def personal_reader(account):
            return {
                "account": account,
                "gateway": {
                    "running": True,
                    "runtimeReady": True,
                    "runtimeVersion": "0.1.6",
                    "configurationDrift": False,
                },
                "tunnel": {
                    "healthy": True,
                    "ready": True,
                    "tunnelId": tunnel_ids[account],
                },
            }

        with patch.object(ops, "read_personal_status", side_effect=personal_reader), \
             patch.object(ops, "business_facts") as business:
            business.side_effect = [
                ops.BusinessFacts(
                    service=ops.ServiceFact(
                        service_ref="mastermind-executive.business",
                        service_kind="executive_mcp",
                        scope="business_workspace",
                        owner_ref="executive-mcp",
                        observed_at="2026-09-20T05:30:00Z",
                        live=True,
                        ready=True,
                        runtime_version="1.0.0",
                        deployment_ref="app-1.0.0",
                        source_refs=("business-service:executive",),
                    ),
                    tunnel=ops.TunnelFact(
                        tunnel_ref="tunnel_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                        service_ref="mastermind-executive.business",
                        owner_ref="executive-mcp",
                        observed_at="2026-09-20T05:30:00Z",
                        live=True,
                        ready=True,
                        source_refs=("business-service:executive",),
                    ),
                ),
                ops.BusinessFacts(
                    service=ops.ServiceFact(
                        service_ref="mastermind-workbench.business",
                        service_kind="workbench",
                        scope="business_workspace",
                        owner_ref="workbench",
                        observed_at="2026-09-20T05:30:00Z",
                        live=True,
                        ready=True,
                        runtime_version=None,
                        deployment_ref=None,
                        source_refs=("business-service:workbench",),
                    ),
                    tunnel=ops.TunnelFact(
                        tunnel_ref="tunnel_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                        service_ref="mastermind-workbench.business",
                        owner_ref="workbench",
                        observed_at="2026-09-20T05:30:00Z",
                        live=True,
                        ready=True,
                        source_refs=("business-service:workbench",),
                    ),
                ),
            ]
            out = ops.build_snapshot(observed_at="2026-09-20T05:30:00Z")

        self.assertEqual(len(out.services), 8)
        self.assertEqual(len(out.tunnels), 8)
        self.assertEqual(out.overall_state, OpsState.READY)
        scopes = {row.scope for row in out.services}
        self.assertEqual(
            scopes,
            {"personal_account", "business_workspace", "workspace_account"},
        )


if __name__ == "__main__":
    unittest.main()

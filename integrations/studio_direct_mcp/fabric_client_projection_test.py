import json
import unittest

from integrations.studio_direct_mcp.fabric_client_projection import (
    DESIGN_PATH,
    READ_PATH,
    SERVER_NAME,
    FabricClientProjectionError,
    project_fabric_client,
    select_route,
)


READ = "https://mac-studio.example-tailnet.ts.net/studio-fabric"
DESIGN = "https://mac-studio.example-tailnet.ts.net/studio-design"


class TestRouteSelection(unittest.TestCase):
    def test_only_exact_design_class_receives_design_route(self):
        self.assertEqual(select_route("design"), "design")
        for task_class in ("review", "fix_build", "audit", "build", "high_level"):
            with self.subTest(task_class=task_class):
                self.assertEqual(select_route(task_class), "read")

    def test_invalid_task_class_refuses(self):
        for value in ("", "Design Work", "../design", "x" * 100):
            with self.subTest(value=value):
                with self.assertRaises(FabricClientProjectionError):
                    select_route(value)


class TestProviderProjection(unittest.TestCase):
    def test_every_provider_uses_read_route_for_non_design(self):
        for provider in ("claude", "codex", "grok", "cursor", "opencode"):
            with self.subTest(provider=provider):
                p = project_fabric_client(
                    provider, "review", read_url=READ, design_url=DESIGN
                )
                self.assertEqual(p.route, "read")
                self.assertEqual(p.url, READ)
                self.assertIn(READ, p.config_text)
                self.assertNotIn(DESIGN, p.config_text)
                self.assertEqual(
                    p.as_dict()["authority"]["gateway_tool_ceiling_authoritative"],
                    True,
                )
                self.assertEqual(
                    p.as_dict()["authority"]["client_config_is_authority"], False
                )

    def test_design_selects_only_design_route(self):
        for provider in ("claude", "codex", "grok", "cursor", "opencode"):
            with self.subTest(provider=provider):
                p = project_fabric_client(
                    provider, "design", read_url=READ, design_url=DESIGN
                )
                self.assertEqual(p.route, "design")
                self.assertEqual(p.url, DESIGN)
                self.assertIn(DESIGN, p.config_text)

    def test_client_shapes_match_current_native_contracts(self):
        claude = project_fabric_client(
            "claude", "review", read_url=READ, design_url=DESIGN
        )
        self.assertEqual(
            json.loads(claude.config_text),
            {"mcpServers": {SERVER_NAME: {"type": "http", "url": READ}}},
        )
        self.assertEqual(
            claude.cli_args,
            ("--strict-mcp-config", "--mcp-config", claude.config_text),
        )

        codex = project_fabric_client(
            "codex", "review", read_url=READ, design_url=DESIGN
        )
        self.assertEqual(
            codex.config_text,
            f'[mcp_servers.{SERVER_NAME}]\nurl = "{READ}"\n',
        )

        grok = project_fabric_client(
            "grok", "review", read_url=READ, design_url=DESIGN
        )
        self.assertEqual(
            grok.config_text,
            f'[mcp_servers.{SERVER_NAME}]\nurl = "{READ}"\nenabled = true\n',
        )

        cursor = project_fabric_client(
            "cursor", "review", read_url=READ, design_url=DESIGN
        )
        self.assertEqual(
            json.loads(cursor.config_text),
            {"mcpServers": {SERVER_NAME: {"url": READ}}},
        )
        self.assertEqual(cursor.cli_args, ("--approve-mcps",))

        opencode = project_fabric_client(
            "opencode", "review", read_url=READ, design_url=DESIGN
        )
        self.assertEqual(
            json.loads(opencode.config_text),
            {"mcp": {SERVER_NAME: {"type": "remote", "url": READ}}},
        )

    def test_only_exact_tailnet_routes_are_admitted(self):
        bad = (
            "http://mac-studio.example-tailnet.ts.net/studio-fabric",
            "https://example.com/studio-fabric",
            "https://mac-studio.example-tailnet.ts.net/wrong",
            "https://user:pass@mac-studio.example-tailnet.ts.net/studio-fabric",
            "https://mac-studio.example-tailnet.ts.net/studio-fabric?x=1",
            "https://mac-studio.example-tailnet.ts.net:8443/studio-fabric",
        )
        for read_url in bad:
            with self.subTest(read_url=read_url):
                with self.assertRaises(FabricClientProjectionError):
                    project_fabric_client(
                        "claude", "review", read_url=read_url, design_url=DESIGN
                    )

        for design_url in (
            READ,
            "https://example.com/studio-design",
            "https://mac-studio.example-tailnet.ts.net/studio-design#x",
        ):
            with self.subTest(design_url=design_url):
                with self.assertRaises(FabricClientProjectionError):
                    project_fabric_client(
                        "claude", "design", read_url=READ, design_url=design_url
                    )

    def test_projection_contains_no_credentials_or_host_execution_authority(self):
        p = project_fabric_client(
            "claude", "design", read_url=READ, design_url=DESIGN
        )
        rendered = json.dumps(p.as_dict(), sort_keys=True)
        client_surface = p.config_text + " " + " ".join(p.cli_args)
        for forbidden in (
            "Bearer ",
            "access_token",
            "refresh_token",
            "ssh_alias",
            "deviceId",
        ):
            self.assertNotIn(forbidden, rendered)
        for forbidden_tool in (
            "start_process",
            "interact_with_process",
            "studio_git_push_current_branch",
        ):
            self.assertNotIn(forbidden_tool, client_surface)
        self.assertIs(p.as_dict()["authority"]["may_start_process"], False)
        self.assertEqual(READ_PATH, "/studio-fabric")
        self.assertEqual(DESIGN_PATH, "/studio-design")


if __name__ == "__main__":
    unittest.main()

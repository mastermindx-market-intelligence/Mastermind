"""Pure projection tests; synthetic grants are never Runtime admission."""
from __future__ import annotations
import copy
import dataclasses
import importlib
import importlib.util
import json
import unittest
from pathlib import Path
from control_plane.executive_agent_capabilities import (
    ExecutionCapabilityRegistry, observed_mcp_tool_schema_digest,
)
MODULE = 'control_plane.dsh_mcp_client_projection'
ROOT = Path(__file__).resolve().parents[1]


def fixture():
    registry = ExecutionCapabilityRegistry.load(
        ROOT / 'scripts/ohf/fixtures/executive_agent_capabilities_v4_mastermind_operator.json',
        source_root=ROOT)
    base = registry.resolve('operator.browser.local-review.v1')
    catalog = {'tools': [
        {'name': 'read_file', 'description': 'Read a synthetic memo',
         'inputSchema': {'type': 'object', 'properties': {'file': {'type': 'string'}}},
         'outputSchema': {'type': 'object'}, 'annotations': {'readOnlyHint': True}},
        {'name': 'write_file', 'inputSchema': {'type': 'object'},
         'annotations': {'readOnlyHint': True}},
    ]}
    source = next(g for g in base.mcp_server_grants if g.transport == 'stdio')
    digest = observed_mcp_tool_schema_digest({'tools': {'read_file': catalog['tools'][0]}})
    grant = dataclasses.replace(source, config_name='fixture', command='/fixture/node',
        args=('/fixture/server.mjs',), enabled_tools=('read_file',),
        server_identity='mmx-stdio-fixture', server_version='1', tool_schema_digest=digest)
    return dataclasses.replace(base, mcp_server_grants=(grant,)), catalog


class DshProjectionTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec(MODULE), 'DSH projection is missing')
        self.api = importlib.import_module(MODULE)
        self.profile, self.catalog = fixture()

    def project(self, profile=None, catalog=None):
        return self.api.project_dsh_mcp_tools(profile or self.profile,
            capability_id=self.profile.mcp_server_grants[0].capability_id,
            observed_tool_catalog=self.catalog if catalog is None else catalog)

    def test_preserves_existing_owner_identity_and_exact_target(self):
        value = self.project().configuration()
        grant = self.profile.mcp_server_grants[0]
        self.assertEqual(value['source']['profile_digest'], self.profile.profile_digest)
        self.assertEqual(value['source']['grant_digest'], grant.grant_digest)
        self.assertEqual(value['source']['tool_schema_digest'], grant.tool_schema_digest)
        self.assertEqual(value['source']['execution_surface'], 'codex-app-server')
        self.assertFalse(value['production_armed'])
        self.assertEqual(value['target'], {'serverName': 'fixture', 'transport': 'stdio',
            'command': '/fixture/node', 'args': ['/fixture/server.mjs']})
        self.assertEqual([t['name'] for t in value['tools']], ['read_file'])
        self.assertEqual(value['serverInfo'], {'name': 'mmx-stdio-fixture', 'version': '1'})

    def test_detached_output_and_deterministic_order(self):
        projection = self.project(); original = projection.configuration()
        value = projection.configuration(); value['tools'][0]['inputSchema']['type'] = 'null'
        self.catalog['tools'].reverse()
        self.assertEqual(projection.configuration(), original)
        self.assertEqual(self.project().configuration(), original)

    def test_canonical_schema_drift_refused(self):
        for field in ['inputSchema', 'outputSchema', 'annotations']:
            with self.subTest(field=field):
                changed = copy.deepcopy(self.catalog)
                changed['tools'][0][field] = {'changed': True}
                with self.assertRaises(self.api.DshMcpProjectionError): self.project(catalog=changed)

    def test_missing_or_duplicate_catalog_tool_refused(self):
        for tools in [[], [self.catalog['tools'][1]], self.catalog['tools'] * 2]:
            with self.subTest(tools=len(tools)):
                with self.assertRaises(self.api.DshMcpProjectionError): self.project(catalog={'tools': tools})

    def test_incomplete_catalog_refused(self):
        with self.assertRaises(self.api.DshMcpProjectionError):
            self.project(catalog={**self.catalog, 'nextCursor': 'remaining-page'})

    def test_disabled_profile_and_unknown_grant_refused(self):
        with self.assertRaises(self.api.DshMcpProjectionError):
            self.project(profile=dataclasses.replace(self.profile, enabled=False))
        with self.assertRaises(self.api.DshMcpProjectionError):
            self.api.project_dsh_mcp_tools(self.profile, capability_id='missing', observed_tool_catalog=self.catalog)

    def test_prompt_approval_is_not_auto_approval(self):
        grant = dataclasses.replace(self.profile.mcp_server_grants[0], default_tools_approval_mode='prompt')
        with self.assertRaises(self.api.DshMcpProjectionError):
            self.project(profile=dataclasses.replace(self.profile, mcp_server_grants=(grant,)))

    def test_unrepresentable_or_nonrequired_target_refused(self):
        grant = self.profile.mcp_server_grants[0]
        for changes in [{'required': False}, {'config_name': 'x' * 33},
                        {'command': 'relative'}, {'enabled_tools': ()},
                        {'enabled_tools': ('read_file', 'read_file')}]:
            with self.subTest(changes=changes):
                value = dataclasses.replace(grant, **changes)
                with self.assertRaises(self.api.DshMcpProjectionError):
                    self.project(profile=dataclasses.replace(self.profile, mcp_server_grants=(value,)))

    def test_transport_projection_is_secret_free(self):
        source = self.profile.mcp_server_grants[0]
        grant = dataclasses.replace(source, transport='streamable-http',
            url='https://docs.example.test/mcp', command=None, args=())
        value = self.project(profile=dataclasses.replace(self.profile, mcp_server_grants=(grant,))).configuration()
        self.assertEqual(value['target'], {'serverName': 'fixture', 'transport': 'streamable-http',
            'url': 'https://docs.example.test/mcp'})
        for url in ['http://docs.example.test/mcp', 'https://user:password@docs.example.test/mcp',
                    'https://docs.example.test/mcp?token=x', 'https://docs.example.test/mcp#x']:
            with self.subTest(url=url):
                invalid = dataclasses.replace(grant, url=url)
                with self.assertRaises(self.api.DshMcpProjectionError):
                    self.project(profile=dataclasses.replace(self.profile, mcp_server_grants=(invalid,)))

    def test_non_json_and_unsafe_numeric_schema_refused(self):
        for value in [float('nan'), 9007199254740993, {1: 'non-string-key'}, object()]:
            with self.subTest(kind=type(value).__name__):
                changed = copy.deepcopy(self.catalog); changed['tools'][0]['inputSchema']['default'] = value
                with self.assertRaises(self.api.DshMcpProjectionError): self.project(catalog=changed)

    def test_top_level_prose_does_not_change_authority(self):
        changed = copy.deepcopy(self.catalog); changed['tools'][0]['description'] = 'new description'
        changed['tools'][0]['title'] = 'new title'
        self.assertEqual(self.project(catalog=changed).configuration(), self.project().configuration())


if __name__ == '__main__': unittest.main()

"""Test-only typed grant producer: stdin is a synthetic local MCP observation.

No live policy is modified. The synthetic profile/digests are not Runtime
admission; the real registry types and schema-digest function are exercised.
"""
from __future__ import annotations
import dataclasses
import hashlib
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from control_plane.executive_agent_capabilities import (  # noqa: E402
    ExecutionCapabilityRegistry, observed_mcp_tool_schema_digest,
)
from control_plane.dsh_mcp_client_projection import project_dsh_mcp_tools  # noqa: E402

value = json.loads(sys.stdin.read(262145))
if value.get('fixture') != 'synthetic-dsh-grant-canary':
    raise ValueError('Synthetic fixture identity required')
config, snapshot = value['config'], value['snapshot']
registry = ExecutionCapabilityRegistry.load(
    ROOT / 'scripts/ohf/fixtures/executive_agent_capabilities_v4_mastermind_operator.json',
    source_root=ROOT)
base = registry.resolve('operator.browser.local-review.v1')
source = next(g for g in base.mcp_server_grants if g.transport == 'stdio')
selected = {t['name']: t for t in snapshot['tools'] if t['name'] in ('read_file', 'search_files')}
grant = dataclasses.replace(source, capability_id='fixture.dsh.read', config_name=config['serverName'],
    command=config['command'], args=tuple(config['args']),
    server_identity=snapshot['serverInfo']['name'], server_version=snapshot['serverInfo']['version'],
    enabled_tools=('read_file', 'search_files'),
    tool_schema_digest=observed_mcp_tool_schema_digest({'tools': selected}),
    grant_digest=hashlib.sha256(b'SYNTHETIC_DSH_CANARY_GRANT_NOT_AUTHORITY').hexdigest())
profile = dataclasses.replace(base, profile_id='fixture.dsh.projection', mcp_server_grants=(grant,),
    profile_digest=hashlib.sha256(b'SYNTHETIC_DSH_CANARY_PROFILE_NOT_AUTHORITY').hexdigest())
projection = project_dsh_mcp_tools(profile, capability_id=grant.capability_id,
    observed_tool_catalog={'tools': snapshot['tools']})
print(json.dumps(projection.configuration(), sort_keys=True, separators=(',', ':')))

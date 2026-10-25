# Hermes Steward read bridge (WP3)

Offline consumer that lets a pinned Hermes profile see company state only
through the existing six read-only Steward MCP tools. Scope is
`mastermind.steward.read`. There is no write method, no second Steward, and
no credential in git.

Upstream pin inspected for the `mcp_servers` shape:
`NousResearch/hermes-agent@1c0cd667746d3395fe9e1b6c74f8f85952486f18`.

`hermes.mcp.yaml` is a Hermes config:

- native toolsets stay `clarify` only, with the qualification denylist intact
- one server, `mastermind_steward`
- `tools.include` is exactly `list_responsibilities`, `get_responsibility`,
  `get_attention`, `get_current_runtime`, `explain_blocker`, `resolve_surface`
- resources and prompts are off
- the URL and bearer token are `${ENV}` references

`StewardReadClient` checks the bearer token against the existing Business MCP
claims policy, then forwards one allowlisted read to an injected transport.
`DEGRADED` and `UNKNOWN` payloads are copied through. Missing facts are not
filled in. A disappeared source becomes `UPSTREAM_UNAVAILABLE` with `data: null`.

This package does not start Hermes, open a socket, or admit an Executive
write. `PASS_OFFLINE_STEWARD_READ_CONFIG` is a static config result.

```sh
python3 -m unittest discover -s integrations/hermes_steward/tests -p 'test_*.py' -v
python3 -m compileall -q integrations/hermes_steward
python3 integrations/hermes_steward/config_guard.py \
  --config integrations/hermes_steward/hermes.mcp.yaml
```

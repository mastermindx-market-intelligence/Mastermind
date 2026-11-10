# Subagent Fabric plugin source

The MCP server and deployment profile live in `integrations/studio_direct_mcp`; the companion operating skill is `skills/use-subagent-fabric/SKILL.md`.

This source directory is not yet a registered ChatGPT plugin. Do not manufacture an app ID, put an OpenAI-hosted private tunnel into a public `server_url`, or publish a placeholder MCP configuration. The actual private app must first be registered through ChatGPT's supported Tunnel connection and required consent. Its verified app ID can then be bound into the private package using the installed Plugin Creator's supported format.

The intended app exposes only the Fabric tools plus the gateway's existing liveness/output paging. It must not inherit the general Studio Git/Paper/shell catalog. Current Studio Direct access remains a separate already-authorized attended adapter path, not proof that the dedicated app is installed.

See `../FABRIC.md` for ownership, trust boundaries, exact tool behavior and qualification steps. See `../../../docs/superpowers/plans/2026-10-11-subagent-fabric-mcp.md` for this candidate's evidence and unreconciled obligations. Creation, connection, installation and native invocation are verified separately for each intended account.

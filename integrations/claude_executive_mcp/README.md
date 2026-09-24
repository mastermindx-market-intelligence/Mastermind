# Claude Code -> Mastermind Executive MCP localhost adapter

This is a stateless, loopback-only OAuth/resource translation edge for the existing production Mastermind Executive HTTP MCP. It does not create an Executive app, auth server, queue, credential store, lifecycle, retry, capacity, or identity plane.

The adapter exists because the production Executive MCP resource identity is the existing secure tunnel resource while Claude Code must reach the production process from the Mac Studio over loopback. It translates only the local resource URL to the canonical configured Executive resource at the OAuth and MCP boundaries.

Runtime contract:

- local listener: `http://127.0.0.1:8444`
- production Executive MCP upstream: `http://127.0.0.1:8443`
- installed Executive policy source: `/Library/Application Support/MastermindExecutive/config/executive-mcp.json`
- Claude MCP URL: `http://127.0.0.1:8444/mcp`
- Claude OAuth callback for this vertical: `http://localhost:8774/callback`
- authentication: a distinct pre-registered **public** Auth0 client, PKCE S256, no client secret
- requested authorization: `mastermind.executive.read`, `mastermind.executive.intent.submit`, plus `offline_access` as a non-authorizing session capability

Never place a JWT, refresh token, cookie, provider token, ChatGPT tunnel credential, or client secret in this directory or in Claude configuration.

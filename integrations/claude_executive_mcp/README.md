# Claude Code -> Mastermind Executive MCP localhost adapter

Status: **TRANSPORT BUILT / ENROLLMENT HELD / NO COO MUTATION AUTHORITY**

This is a stateless, loopback-only OAuth/resource translation edge for the existing production Mastermind Executive HTTP MCP. It does not create an Executive app, auth server, queue, credential store, lifecycle, retry, capacity, or identity plane.

The adapter exists because the production Executive MCP resource identity is the existing secure tunnel resource while Claude Code must reach the production process from the Mac Studio over loopback. It translates only the local resource URL to the canonical configured Executive resource at the OAuth and MCP boundaries.

Runtime contract:

- local listener: `http://127.0.0.1:8444`
- production Executive MCP upstream: `http://127.0.0.1:8443`
- installed Executive policy source: `/Library/Application Support/MastermindExecutive/config/executive-mcp.json`
- Claude MCP URL: `http://127.0.0.1:8444/mcp`
- Claude OAuth callback for this vertical: `http://localhost:8774/callback`
- future authentication shape: distinct public/native Auth0 client, PKCE S256, no client secret

## Authority boundary

The transport can reach the currently installed Executive profile, but that does not make its CEO submit permission appropriate for Fable.

**Do not enroll Fable with `mastermind.executive.intent.submit`.**

Fable's production client is held until the accepted COO principal implementation supplies a distinct role-correct action policy/profile. The proposed `mastermind.executive.coo.act` scope is SPEC_ONLY until that source is accepted and must not be provisioned merely from this README.

Until then:
- harmless reads may be used only after the authenticated client ceremony itself is authorized;
- CEO-specific mutation remains outside the Fable/COO seat;
- no alternate client, token cache, proxy, or public Executive endpoint should be created to bypass the hold.

Never place a JWT, refresh token, cookie, provider token, ChatGPT tunnel credential, or client secret in this directory or in Claude configuration.

See `docs/runbooks/claude-executive-mcp-client.md` for the current gated enrollment and acceptance sequence.

## Source-only COO route repair

The local endpoint now has exactly one upstream tool target: `/mcp/coo` on the existing8443 listener. No missing-route fallback to the CEO profile exists. The adapter refuses missing or divergent COO policy, confines its protected-resource scopes, rejects foreign-role authorization requests/challenges and preserves uncertainty on a lost response. Literal path/method, local Host/Origin and duplicate-Authorization checks precede forwarding.

`createAdapter(installed, dependencies)` is an in-process construction seam for isolated transport tests. It does not read the live installation or open a listener when imported. Only the executable entry reads the fixed existing configuration and listens on127.0.0.1:8444. No wire or environment option chooses another upstream; tests inject local fixtures without real issuer traffic, installed services or credentials.

The executable contract lives in `tests/claude_executive_mcp_adapter.test.mjs` and runs through the repository's pytest discovery using `tests/test_claude_executive_mcp_adapter_runtime.py`. Real Claude OAuth, issuer-response interoperability, source acceptance and the reviewed managed-session capability profile remain separate gates. Keep ENROLLMENT HELD until those applicable gates pass.

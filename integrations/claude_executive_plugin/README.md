# Mastermind Executive Claude plugin

Status: **P1 SOURCE PACKAGE / PRODUCTION INERT / EXECUTIVE MUTATION UNAVAILABLE**

This directory is the first private Claude plugin package for the Mastermind Executive OS / Fable COO integration.

It packages provider-side workflow and UX around the **existing** Executive client/runtime owners. It does not create another Executive backend, OAuth client, MCP server, Runtime, queue, scheduler, session registry, retry plane, identity store, token store, or source-release controller.

## Current composition

```text
Claude Code / Claude Desktop Code
        |
        v
Mastermind Executive plugin
  - COO orchestration Skill
  - /executive-context command
        |
        v
existing user-scope MCP registration: mastermind-executive
        |
        v
#955 loopback OAuth/resource adapter
        |
        v
existing installed Executive MCP / CeoIngress / Runtime / Workspace / Fabric
```

The plugin deliberately ships **without** a plugin-owned `.mcp.json` and without hooks in P1.

### Why the MCP connector is not bundled yet

The incumbent #955 path already qualifies a distinct user-scope Claude MCP registration at the local Executive edge and owns its OAuth/PKCE enrollment.

Bundling another HTTP MCP declaration here would create a second client carrier before the COO scope/admission contract is accepted. It would also depend on provider behavior that must be requalified for the exact installed Claude versions: plugin-bundled OAuth MCPs have had version-specific authentication/client-ID defects even when the equivalent manually registered server works.

Until the role-correct COO profile exists, keep connector ownership with #955.

The future package may gain an exact `.mcp.json` only after all of these are true:

1. the static COO Executive MCP profile exists inside the existing installed Executive process;
2. its OAuth policy uses the accepted COO action scope rather than the CEO submit scope;
3. a public/native OAuth client is enrolled through the authorized IdP ceremony;
4. bundled-plugin OAuth works on the exact deployed Claude Code CLI and macOS Desktop Code surfaces;
5. tool-schema attestation proves that no CEO or ambient modifying surface leaked into the plugin.

## Development loading

Claude Code's current plugin structure expects:

```text
.claude-plugin/plugin.json
commands/
skills/
hooks/        # optional; absent in P1
.mcp.json     # optional; absent in P1
```

For source development, load this directory with Claude Code's supported local plugin mechanism (for example `--plugin-dir`) and use it only with the separately enrolled `mastermind-executive` user-scope MCP connector.

The plugin manifest contains no credential, endpoint secret, client ID, OAuth token, provider account, host identity, or mission authority.

## Surface parity boundary

The plugin package is intended for both Claude Code CLI and Claude Desktop's Code/plugin surface, but the current connector proof is narrower.

#955 has qualified the `mastermind-executive` **Claude Code user-scope registration path**. P1 does not assume that this local registration automatically appears inside Claude Desktop.

Therefore:

- Claude Code plugin/package loading is a source-level target in P1;
- Claude Desktop plugin loading remains a separate exact-version proof;
- Claude Desktop Executive connector availability remains **UNPROVEN** until the real macOS app exposes the expected connector and exact read tool schema;
- if Desktop does not consume the incumbent user-scope registration, do not add an ad-hoc second connector. Qualify the accepted bundled-MCP/Desktop-extension route after the COO OAuth profile exists.

The eventual parity test must prove the same principal policy, tool schema, and authority ceiling on both surfaces; one surface's success is not inherited by the other.

## Current capability

P1 adds:
- a reusable Fable/COO orchestration Skill;
- a read-only `/executive-context` workflow;
- explicit broad-mission / narrow-reserved-boundary behavior;
- explicit distinction between organizational authority and technical tool capability;
- a packaging location that can later receive the reviewed static COO MCP profile and optional session-binding hooks.

P1 does **not** add:
- Executive mutation;
- a COO OAuth scope;
- Auth0 enrollment;
- exact Claude session binding;
- a provider/session attestor;
- source release;
- service installation;
- production acceptance.

## Relationship to current carriers

- #957: COO Principal Mandate source contract.
- #960: pure Mission Workspace v3 mandate projection.
- #961: pure high-level COO request/identity law.
- #955: existing authenticated Claude transport / localhost adapter.
- #676: accepted SPEC_ONLY rich-principal vs sealed-worker and portable COO architecture.
- #804: incumbent unresolved non-CEO canonical sink experiment; must be reconciled before P2-C edits `ceo_intent.py`.

Do not use this package to bypass any of those owners.

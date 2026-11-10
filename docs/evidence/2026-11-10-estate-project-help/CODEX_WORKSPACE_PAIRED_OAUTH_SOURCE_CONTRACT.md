# Executable native paired-resource contract

Base: official Codex `086ccc833bc9cf01024ad2dd6af7dbd421b6bf9a` (rust-v0.167.0). Reference semantics: Mastermind `95762fc3700598a7be1a12b8c6c1995753071eed`, `integrations/hermes_qualification/workspace_oauth_privacy/guard.patch` blob `db2234d36549fa774d5eaf76c47bcb90b8aae92a`. This source phase is authorized; native/fork publication, credential enrollment and activation are not part of it.

## Fixed opt-in

The native config will accept the exact existing `oauth.workspace` descriptor:

```json
{
  "schema": "mastermind.hermes_workspace_oauth.v1",
  "resource": "https://mcp.mastermind-x.com/workspace/read",
  "identity_url": "https://mcp.mastermind-x.com/workspace/native-draft-identity/current",
  "scope": "mastermind.workspace.read",
  "principal_scope": "<64 lower-case hexadecimal characters from the enrolled publication>"
}
```

It is valid only for the existing local `mastermind_coo` server at `https://mcp.mastermind-x.com/mcp/coo`, with the explicit public OAuth client and exact Executive scopes/resource from the reference. Static/env bearer overrides, generic header helpers, other auth modes, remote execution routing and arbitrary companion resources are refused. Absence preserves the existing single-resource path.

The companion uses the existing OAuth credential-store machinery and fixed `mastermind_coo_workspace` identity. No second registry, credential service, helper/relay or new storage format is added. Store and profile custody stay bound to the original client lifecycle. Independent resource tokens are never exported to T3 config, model arguments, argv or a helper.

## Reached lifecycle

1. The original explicit browser-login owner performs two separate authorization-code/PKCE consents with exact scopes/resources. The second consent is not inferred from the first. Partial login does not claim paired readiness. Background startup never starts login. The existing app-server single-URL and unsupported manual flows refuse the opt-in before any partial login effect.
2. The original native MCP factory validates the selected full server configuration, then reaches the existing rmcp-client constructor.
3. Each original protected request uses the existing pinned stores and coordinated refresh transaction. The fixed Workspace protected identity GET must return a bounded, closed `mastermind.native_draft_identity.v1` response with the expected `principal_scope` and future expiry.
4. The same original HTTP capability carries the proof GET and final MCP request. The companion header is attached only to the exact Executive endpoint; metadata/token endpoints and redirects never receive it. The original primary OAuth authorization remains independently owned and checked.
5. Before and after network work, recheck the retained home/config/client/store identity and exact current credential evidence. Missing initial grants, failed refresh/proof and current connection drift remain distinguishable closed errors. No new retry or replay is introduced. Lost response remains an original-operation uncertainty.
6. Cancellation joins/uses existing refresh-persistence ownership and drops the original HTTP future; this feature adds no detached work, queue or watcher.

## Exact source owners and expected edits

- `codex-rs/config/src/mcp_types.rs` and its existing type exports/tests: optional closed descriptor and full local/server/auth/scope validation.
- `codex-rs/codex-mcp/src/rmcp_client.rs`: reached full-configuration guard before constructing the native connection.
- `codex-rs/rmcp-client/src/rmcp_client.rs`: reusable existing OAuth-manager preparation and original transport composition; legacy branch unchanged.
- `codex-rs/rmcp-client/src/oauth/runtime.rs` / existing credential-store seams only where necessary for retained currentness and refresh. No new store.
- A focused `codex-rs/rmcp-client/src/workspace_oauth.rs` module under that owner, plus actual owner tests.
- `codex-rs/rmcp-client/src/perform_oauth_login.rs` and existing callback/login boundary as required for explicit paired consent and early unsupported-flow refusal.
- Existing CLI login/factory caller only where needed to select the executable paired route without changing unrelated login behavior; app-server must receive early refusal from the original login owner.
- Deterministically regenerated existing config schema after typed changes; necessary direct struct-literal compatibility edits only.

## Qualification route

The exact checkout is isolated at `estate-t3-paired-oauth-qualification/source`. Official rustup-init was checksum verified; Rust 1.95.0 is installed only under that task directory. No system PATH or native runtime changed. `cargo metadata --no-deps --locked --format-version 1` passes. Baseline `cargo test -p codex-rmcp-client --lib --no-run --locked --profile dev-small` is resolving the original pinned workspace dependencies.

Use the original Cargo packages and lockfile for meaningful tests. New cases must execute the actual config parser, OAuth storage/refresh/PKCE and HTTP transport bodies with disposable credentials and an inert HTTP/UI boundary. Cover legacy omission, closed descriptor and endpoint/resource/client/scope checks, two explicit consents, unsupported flow before effects, cold/expired independent grants, revocation, store/profile/config drift, concurrent refresh, identity mismatch/body bound/expiry, redirects, cancellation, redaction, streaming preservation and no additional send after a lost response. Finish with affected package tests, scoped formatting and schema generation/readback. Native installed-provider proof and real account consent remain explicitly separate.

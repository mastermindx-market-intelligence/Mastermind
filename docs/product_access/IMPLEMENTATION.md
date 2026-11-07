# Product public-observation implementation plan

Goal: deliver a reviewable authenticated Product MCP read vertical without changing domain owners or bypassing production/browser gates.
Architecture: `ARCHITECTURE.md`; fixed existing public API projections plus existing Business MCP auth. Factory is inert; deployment is separate. Stack: Python, existing httpx, JSON schema and pinned MCP 1.28.1 / PyJWT 2.13.0. Execute inline with TDD under the current commission.

## Constraints and review focus

Only `integrations/product_access_mcp/`, `tests/product_access_mcp/` and `docs/product_access/` are owned by this operation. Do not edit incumbent Browser, Context, Executive, auth, deployment, Macro or Terminal sources. Do not invoke the previously blocked production probe through this implementation. No user session/token/cookie extraction, no ambient credentials, no redirects, no retries, no private reads/actions. Errors and observations are distinct; source timestamps are never transport timestamps.

Review focus: unknown/malformed/future timestamps; partial and omitted data; redirects/oversized/non-JSON/secret-bearing upstream failures; wrong issuer/audience/subject/scope and revocation during await; mismatched schema/quote owner/view and unexpected extended-session fields. Invalid and revoked authorizations must not enter a backend read.

## Task 1 — bounded application observations

Files: create `contracts.py`, `transport.py`, `reader.py` in `integrations/product_access_mcp/`; tests `test_observations.py` and `test_transport.py`.
Interfaces: `PublicTransport.read(endpoint, symbols=()) -> HttpObservation`; `ProductReader.diagnostics()` and `.market_pulse(symbols)` return immutable-by-copy JSON observations; caller supplies neither transport URL nor credentials. `HttpObservation` holds status, bounded raw bytes, content type and an opaque error code.

- [x] Add failing projection tests for process/checkout drift, missing data, zero counts, explicit source age, unknown/future timestamps, partial coverage, quote revisions, unexpected secrets and malformed owner output.
- [x] Add failing actual local HTTP fixture tests for fixed destination/request, no cookies or auth, redirect refusal, deadlines, size/content-type/JSON errors and no retries.
- [x] Implement reviewed fixed endpoints and field projections. Disallow NaN/Infinity and duplicate JSON object keys. Preserve raw-body digest without returning raw failure content.
- [x] Run both suites; require correct RED→GREEN evidence. No production HTTP.

## Task 2 — authenticated MCP boundary

Files: create `app.py`, `__init__.py`; test `test_app.py`.
Interface: `create_product_server(authenticator, policy, now, audit_sink, reader, allowed_hosts, allowed_origins=()) -> FastMCP`. Reuse the existing verifier; require dedicated `product.observe` policy. Expose only two closed-schema read tools. Never send access tokens to reader. Reverify the same credential after awaited read.

- [x] Add failing real SDK/ASGI tests using ephemeral RSA fixture keys and signed JWTs, actual MCP initialize/list/call requests, actual projection code and a fixture upstream transport.
- [x] Prove missing/wrong/expired/revoked identities, absence of any private-user selector in this public-only profile (private tenant isolation remains a later gate), invalid arguments, unknown tools, host/origin refusal, secret-safe errors and auth drift after read.
- [x] Implement inert factory, catalog/input validation, bounded structured return and existing auth audit integration.
- [x] Run new and adjacent auth/Workbench suites with exact pinned SDK. Record full-suite limitations independently.

## Task 3 — qualification and recovery

Files: update `ACCEPTANCE.md`, `CHECKPOINT.md`; no automatic install/registration.

- [x] Adversarially inspect changed files and add regression tests for concrete findings. The incumbent Browser image-integrity expected failure remains explicitly unresolved.
- [ ] Run `git diff --check`, compile, targeted integration, adjacent Browser/auth tests, and repository pytest command. Preserve any unrelated failure by name; do not claim a full pass from targeted tests.
- [ ] Commit and publish the exact own branch; open draft PR; inspect exact head/checks and request independent review when supported. Required CI/review remain release gates.
- [x] Document existing-owner deployment composition and exact negative/live acceptance checklist. No generic proxy or new auth service.
- [ ] Reassess remaining commission. Continue independent safe work; retain private OAuth, Browser permission/install, artifact return, live preview, release and real-account acceptance as distinct unresolved requirements.

## Initial evidence

Operation `product-access-browser-20261009-astra-001`, branch `sol/web-product-access-browser-20261009-astra-001`, acquired through canonical mmx-workspace at protected SHA `326c8469a21d7f50fc9ecb1848196bf1c6e66685`. Source namespace did not displace any incumbent browser/context writer. Repository push permission observed true; this grants no merge or deployment approval.

A fresh isolated test venv was created at `/tmp/mmx-product-access-20261009-astra-001-venv`, preserving global packages; MCP upgraded there only from 1.28.0 to pinned 1.28.1. PyJWT 2.13.0 is available. Baseline actual auth/Workbench tests passed (60 cases, no production calls). No worker, listener, plugin, browser or live action was started.

## Task 4 — exact deployment composition without a new service

The active Product MCP source now adds `integrations/product_access_mcp/deployment.py` plus `tests/product_access_mcp/test_deployment.py`. This is a source-ready, **inert** factory. It borrows the existing `ResourcePolicy`/`JwtAuthenticator`/`AuthAuditSink`, host-approved clocks and exact ingress host/origin authority; it selects only `PublicTransport()` and returns an ASGI app wrapped with the inherited `PreAuthMcpBodyApp`. No identity exchange, private product data, listener, plug-in registration, session, scheduler, or production action is created.

- [x] Create exact source-only deployment factory and owner-binding refusal cases.
- [x] Add constructor and local ASGI/JWT fixture tests for read-only authenticated diagnostics and invalid subject/action refusal. Fake public responses are injected into `PublicTransport.read` only inside tests.
- [ ] Complete independent qualification of **this exact head** through required CI and source review. The previous Studio process attempt to run host pytest was refused before dispatch; do not replay or switch carriers to obtain that action.
- [ ] Deployment authority selects the live resource policy/issuer, subject allowlist, actual process/Host/TLS/tunnel, and authenticates a real Web CEO account. All these remain separate gates and are unproven.

Do not mistake a constructor or CI result for an installed or production-proven capability. The relevant remaining work is the first *real* authorized Web account → Product MCP read, followed by BrowserResource approval and actual protected-page visual evidence.

## 2026-10-10 follow-on: inert Product MCP loopback process entrypoint

The reviewed public-only Product MCP source is now accompanied by `scripts/mastermind_product_access_app.py`. This file is an explicit **existing-owner process composition**, not a launch daemon, installer, IdP, new token/session store or authorization grant.

`--describe` returns the fixed Product MCP catalog/version/hash without loading a policy, touching an audit directory, connecting to a backend, or opening a socket. A real invocation requires ALL owner-selected coordinates: `--policy-file` (a canonical absolute, regular 0600 owner-only JSON policy, exact `product.observe` resource), `--audit-directory` (pre-existing private owner-owned directory), and `--port` (1–65535). `--host` is fixed to loopback IPv4 by default and supports IPv6 loopback; public binds refuse. The ingress Host is derived from the policy's exact HTTPS `/mcp` resource, never taken from a model argument or arbitrary CLI URL. Optional repeated `--allowed-origin` accepts only exact vetted origins.

When an admitted operator *explicitly starts it*, it borrows `BoundedJwksCache` / `HttpxJwksFetcher`, the existing `JwtAuthenticator`, `DurableAuthAuditSink`, Product `create_deployment`, and the existing Uvicorn HTTP owner. It sets `proxy_headers=False`, `access_log=False`, a 16-client concurrency limit, and loopback-only listener binding. The durable audit owner is opened through its existing descriptor-fenced code and closed during shutdown. Source-only launcher and unit tests do not prove service installation or public account access.

This source should reach separate *new-head* CI + security review **before** a release owner binds it. The prior host `pytest` attempt and production HTTPS probe were explicitly refused and are not retried. The correct operator install sequence remains: (1) approved Business OAuth issuer/resource/subject allowlist and JWK rotation, (2) actual existing host audit directory and isolated runtime, (3) loopback process launch and readiness, (4) existing TLS edge host/resource/metadata path routing and upstream denial tests, (5) ChatGPT plugin registration and each account's explicit OAuth consent, selection and real endpoint canary. Do not infer acceptance from code compilation, mock-Uvicorn tests, metadata discovery, or installation alone.

Example *source-only* inspection:
```bash
python scripts/mastermind_product_access_app.py --describe
```

The host-side production invocation cannot be constructed by this source: its actual policy path, exact audience/issuer, allowed ChatGPT Origins, process identity, TLS route, audit directory, and explicit reviewer/operations approval are not yet established. Never replace those with `product.example` fixtures.

## Launcher owner-file trust hardening (source only, 2026-10-11)

The explicit Product launcher opens its policy and audit directories through a descriptor-relative `O_DIRECTORY|O_NOFOLLOW` chain. Every ancestor is checked for exact opened entry identity, root/current-principal custody, unsafe write bits, and extended macOS ACLs using the pre-existing first-party `control_plane.fs_security` checker. The only shared writable ancestors admitted are known root-owned mode-01777 sticky temporary directories. All other writable or symlinked ancestors fail closed. The regular policy file must be owned by the current service principal, mode 0600, single-link, ACL-free, nonempty and at most 64 KiB; the bounded read must retain its named/open inode, size, mode, ownership and modification/change-time identity. These checks operate before parsing the closed Business `ResourcePolicy`.

The audit directory is separately proven through the same ancestor chain before the existing `DurableAuthAuditSink` opens it. This source does **not** implement a second audit sink, file-event journal or model-controlled policy path. The shared Business audit file's macOS ACL qualification remains a distinct original-owner security/release decision: a safe Product policy read is not sufficient evidence that all audit-file permissions are safe.

Fixture-only negative tests verify invalid ACLs, writable ancestors, symlink ancestry changes, in-place equal-length policy rewrites, named-file replacement and guaranteed audit owner close after a simulated Uvicorn failure. They do not prove a real macOS ACL, server startup, live OAuth, real HTTPS route, ChatGPT installation, or user account consent. Preserve all earlier no-network/no-credential and source/release constraints.

## OAuth tool-level linking readiness, v1.2.0 candidate

The first Product release retains exactly `product_diagnostics` and `product_market_pulse` under the single `product.observe` Business MCP resource policy. ChatGPT linking requires per-tool **top-level** `securitySchemes: [{type: "oauth2", scopes: ["product.observe"]}]` and an `_meta["mcp/www_authenticate"]` resource-metadata Bearer challenge on missing/expired credentials. A nested `_meta.securitySchemes` field is not equivalent to the SDK's public Tool model. Pure signed-JWT fixtures verify the relink challenge on expired in-flight bearer, while current policy revocation and audit-system failures are held without relink; no private user grant, token or upstream secret crosses MCP.

RFC9728 protected-resource metadata and bare HTTP `401 WWW-Authenticate` remain owned by the existing pinned MCP SDK and Business authentication. This source adds no custom auth server, DCR handler, cookie store, session cache, plugin install or live process and does not change domain observation/scope semantics. Re-pin immutable catalog digest and version together. A green compilation or SDK fixture is not an installed OAuth client or consent; the real deployed audience/issuer, TLS resource and ChatGPT tool call still require owner-approved live admission.

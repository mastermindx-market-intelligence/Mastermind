# Product public-observation implementation plan

Goal: deliver a reviewable authenticated Product MCP read vertical without changing domain owners or bypassing production/browser gates.
Architecture: `ARCHITECTURE.md`; fixed existing public API projections plus existing Business MCP auth. Factory is inert; deployment is separate. Stack: Python, existing httpx, JSON schema and pinned MCP 1.28.1 / PyJWT 2.13.0. Execute inline with TDD under the current commission.

## Constraints and review focus

Only `integrations/product_access_mcp/`, `tests/product_access_mcp/` and `docs/product_access/` are owned by this operation. Do not edit incumbent Browser, Context, Executive, auth, deployment, Macro or Terminal sources. Do not invoke the previously blocked production probe through this implementation. No user session/token/cookie extraction, no ambient credentials, no redirects, no retries, no private reads/actions. Errors and observations are distinct; source timestamps are never transport timestamps.

Review focus: unknown/malformed/future timestamps; partial and omitted data; redirects/oversized/non-JSON/secret-bearing upstream failures; wrong issuer/audience/subject/scope and revocation during await; mismatched schema/quote owner/view and unexpected extended-session fields. Invalid and revoked authorizations must not enter a backend read.

## Task 1 — bounded application observations

Files: create `contracts.py`, `transport.py`, `reader.py` in `integrations/product_access_mcp/`; tests `test_observations.py` and `test_transport.py`.
Interfaces: `PublicTransport.read(endpoint, symbols=()) -> HttpObservation`; `ProductReader.diagnostics()` and `.market_pulse(symbols)` return immutable-by-copy JSON observations; caller supplies neither transport URL nor credentials. `HttpObservation` holds status, bounded raw bytes, content type and an opaque error code.

- [ ] Add failing projection tests for process/checkout drift, missing data, zero counts, explicit source age, unknown/future timestamps, partial coverage, quote revisions, unexpected secrets and malformed owner output.
- [ ] Add failing actual local HTTP fixture tests for fixed destination/request, no cookies or auth, redirect refusal, deadlines, size/content-type/JSON errors and no retries.
- [ ] Implement reviewed fixed endpoints and field projections. Disallow NaN/Infinity and duplicate JSON object keys. Preserve raw-body digest without returning raw failure content.
- [ ] Run both suites; require correct RED→GREEN evidence. No production HTTP.

## Task 2 — authenticated MCP boundary

Files: create `app.py`, `__init__.py`; test `test_app.py`.
Interface: `create_product_server(authenticator, policy, now, audit_sink, reader, allowed_hosts, allowed_origins=()) -> FastMCP`. Reuse the existing verifier; require dedicated `product.observe` policy. Expose only two closed-schema read tools. Never send access tokens to reader. Reverify the same credential after awaited read.

- [ ] Add failing real SDK/ASGI tests using ephemeral RSA fixture keys and signed JWTs, actual MCP initialize/list/call requests, actual projection code and a fixture upstream transport.
- [ ] Prove missing/wrong/expired/revoked identities, cross-user isolation from private state, invalid arguments, unknown tools, host/origin refusal, secret-safe errors and auth drift after read.
- [ ] Implement inert factory, catalog/input validation, bounded structured return and existing auth audit integration.
- [ ] Run new and adjacent auth/Workbench suites with exact pinned SDK. Record full-suite limitations independently.

## Task 3 — qualification and recovery

Files: update `ACCEPTANCE.md`, `CHECKPOINT.md`; no automatic install/registration.

- [ ] Adversarially inspect changed files and add regression tests for concrete findings.
- [ ] Run `git diff --check`, compile, targeted integration, adjacent Browser/auth tests, and repository pytest command. Preserve any unrelated failure by name; do not claim a full pass from targeted tests.
- [ ] Commit and publish the exact own branch; open draft PR; inspect exact head/checks and request independent review when supported. Required CI/review remain release gates.
- [ ] Document existing-owner deployment composition and exact negative/live acceptance checklist. No generic proxy or new auth service.
- [ ] Reassess remaining commission. Continue independent safe work; retain private OAuth, Browser permission/install, artifact return, live preview, release and real-account acceptance as distinct unresolved requirements.

## Initial evidence

Operation `product-access-browser-20261009-astra-001`, branch `sol/web-product-access-browser-20261009-astra-001`, acquired through canonical mmx-workspace at protected SHA `326c8469a21d7f50fc9ecb1848196bf1c6e66685`. Source namespace did not displace any incumbent browser/context writer. Repository push permission observed true; this grants no merge or deployment approval.

A fresh isolated test venv was created at `/tmp/mmx-product-access-20261009-astra-001-venv`, preserving global packages; MCP upgraded there only from 1.28.0 to pinned 1.28.1. PyJWT 2.13.0 is available. Baseline actual auth/Workbench tests passed (60 cases, no production calls). No worker, listener, plugin, browser or live action was started.

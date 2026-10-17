# Astra External Fabric Delegation — Codex Client Auth Amendment

Date: 2026-09-14
Status: **CHAIRMAN-CONTINUATION AUTHORIZED / ARCHITECTURE AMENDMENT / SOURCE CANDIDATE**
Parent freeze: `docs/superpowers/specs/2026-09-14-astra-external-fabric-delegation-design.md`
Operation: `codex-astra-fabric-delegation-impl-20260914-sol-001`

## 1. Why this amendment exists

Protected #618 correctly froze the server boundary: Astra must reuse the existing authenticated five-tool Executive MCP. Implementation proved one client assumption false without invalidating that architecture.

The installed Executive MCP is locally reachable at a loopback Streamable HTTP URL, but its OAuth resource is intentionally the existing ChatGPT Secure MCP Tunnel resource. Codex 0.154 refuses native `mcp login` because protected-resource metadata names that tunnel resource rather than the loopback transport URL. `--oauth-resource` does not change this resource-identity check, and the tunnel URL is not reachable from the Mac host.

Therefore native Codex OAuth is `DARK_OR_DISCONNECTED` for the local transport. This is not permission to change the Executive resource identity, weaken scope/subject checks, copy ChatGPT credentials, or add a second Executive ingress.

## 2. Frozen correction

Keep the Executive server, Auth0 issuer, resource/audience, required scopes, subject allowlist, JWT verifier, audit sink, CeoIngress and five MCP tools unchanged.

Add one **Codex-client credential adapter** only. It owns no Executive authority and no provider routing. Its job is to obtain and safely retain a user-delegated Auth0 credential for the same existing Executive resource, then supply an `Authorization` header to Codex through Codex 0.154's supported `http_headers_helper` boundary.

## 3. Client credential lifecycle

When no prior Codex Executive client exists, enrollment may dynamically register exactly one public/native Auth0 client using the tenant's advertised DCR endpoint. The client uses authorization-code + PKCE, no client secret, a loopback callback, the existing Executive API as `audience`, the exact read+intent-submit scopes, and `offline_access`.

DCR is never repeated merely because login or token refresh fails. The returned `client_id` is retained with the credential bundle and reused for later reauthorization. If the tenant/API has not granted dynamically registered third-party clients the required Executive scopes, enrollment stops as `BLOCKED_AUTH0_CLIENT_GRANT`; it does not request broader scopes or create another client.

The one-time browser authorization remains a user-delegated Auth0 ceremony. A later machine-to-machine service principal may supersede it only through a separately reviewed Auth0 client grant and Executive subject-policy update.

## 4. Credential custody

Access and refresh tokens are stored only in one fixed macOS Keychain generic-password item owned by this client adapter. No token, authorization code, refresh token, cookie, client secret, or bearer value may appear in Git, `.codex/config.toml`, argv, ambient environment, Agent OS, Slack, logs, receipts, or ChatGPT conversation content.

The Keychain item stores one closed credential document containing only the public `client_id`, current access token, current refresh token, access-token expiry, and a digest of the exact installed Executive auth policy. A policy digest change fails closed and requires explicit reauthorization rather than silently reusing stale authority.

Keychain is credential custody, not a new authorization authority or Executive state store. The existing Executive JWT verifier remains authoritative.

## 5. Runtime header helper

Codex starts a short-lived `http_headers_helper` process. The helper reads the fixed Keychain item, re-reads the installed non-secret Executive MCP policy, and validates policy continuity. If the access token is near expiry it performs at most one refresh-token exchange with the same Auth0 issuer/client/resource scope set, under one transient local process lock to prevent concurrent refresh races.

Before emitting a header, the helper parses the JWT only as a client-side safety check and requires exact issuer, exact Executive audience, allowed subject digest, the required Executive scopes, and a future expiry. Cryptographic JWT verification remains exclusively server-side.

The helper writes exactly one JSON object to stdout: `{"Authorization":"Bearer <access-token>"}`. This stdout is the supported private Codex helper pipe, not a durable receipt or terminal log. All refusals go to a fixed non-secret exit path with no token echo.

Codex may retry the same MCP request after a 401 only according to its built-in helper contract and only when helper-provided headers changed. The adapter itself contains no hidden MCP retry loop.

## 6. Codex wiring

The first canary uses a non-persistent Codex config override on the already-registered `mastermind-executive` server to set `http_headers_helper`. This proves the credential path without directly rewriting the user's Codex config file.

After the client path is production-proven, the same helper command belongs in the existing Executive-owned Astra/Codex launch profile or another current canonical Codex configuration owner. Do not create a separate launcher/scheduler merely to persist the setting.

## 7. Failure law

- Native Codex OAuth resource mismatch: expected blocker; do not weaken server metadata.
- DCR unavailable or refused: `BLOCKED_AUTH0_DCR`; no repeated registration.
- Required third-party API grant absent: `BLOCKED_AUTH0_CLIENT_GRANT`; no scope widening.
- Browser authorization denied/times out: no Keychain credential mutation.
- Keychain unavailable/corrupt: no header output.
- Installed Executive policy moved: no token reuse; reauthorization required.
- Refresh response lost/invalid: fail closed; do not mint another DCR client or switch auth carrier.
- 401/403 after unchanged helper credential: preserve the server challenge; no credential-loop retry.

## 8. Acceptance

This amendment is proven only when Codex 0.154+ can initialize the installed five-tool Executive MCP through the helper, list the exact five tools, execute a real authenticated read, and separately make one authorized harmless `submit_ceo_intent` admission with no secret material in repo/config/argv/environment/logs. Exact Astra RuntimeBinding and external-provider completion remain separate downstream gates from the parent freeze.

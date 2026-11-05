# Business Sol OAuth Resource Server — Current Contract and Security Amendment

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement the parent BSC-A1 plan task-by-task. This amendment has narrow precedence over the parent plan where explicitly stated.

**Parent plan:** `docs/superpowers/plans/2026-08-29-business-sol-oauth-resource-server.md`

**Parent architecture/program:** Mastermind #234 / #236

**Current protected source during review:** `Mastermind@7b8f3ca580f9872ca8ddf60f90c6022ce4a18e6b`, `mastermind.sol_skillpack.v1` v1.0.1 / bootstrap-major 1

**Verification date:** 2026-08-29

**Purpose:** Close current MCP SDK security, ChatGPT OAuth-linking, authorization-server metadata, scope-normalization, client-identity, and JWKS-refresh amplification defects found during Sol’s adversarial review of the existing BSC-A1 plan. All non-conflicting parent-plan architecture, file topology, TDD ordering, no-rebuild boundaries, redaction law, capability state, and stop conditions remain controlling.

**Capability state:** `SPEC_ONLY / PLAN_ONLY`. This amendment creates no OAuth resource server, authorization server, token verifier, app, MCP edge, tunnel, credential, Business workspace effect, or Mastermind runtime effect.

---

## A1. Dependency security floor — MCP Python SDK 1.28.1, not 1.28.0

The parent plan pins `mcp==1.28.0`. Current official MCP Python SDK release/security evidence makes that pin unacceptable:

- `v1.28.1` is the supported security-fix release on the v1 line;
- it adds transport security support that repairs the v1.28.0 WebSocket origin-validation vulnerability;
- the SDK security policy supports only current 2.x and the newest 1.x maintenance release;
- BSC-A1 should not jump to 2.x inside this bounded wave because the existing Mastermind MCP packages are built and tested on the 1.x API.

Replace every BSC-A1 `mcp==1.28.0` instruction with:

```toml
mcp==1.28.1
```

Task 1 must update the existing repository dev pin from `1.28.0` to `1.28.1`, not add two conflicting pins. The `business-mcp` optional dependency group also pins `1.28.1` exactly.

Add or amend the dependency-pin test:

```python
def test_business_auth_dependencies_are_security_pinned() -> None:
    root = Path(__file__).resolve().parents[1]
    text = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert 'mcp==1.28.1' in text
    assert 'mcp==1.28.0' not in text
    assert 'PyJWT[crypto]==2.13.0' in text
```

Run all existing Executive, Secretary, Company Dialogue, and Company MCP gateway suites against `mcp==1.28.1`. A patch-version bump is not accepted by assumption; current hosted regression evidence is required.

The exact MCP v1.28.1 `AccessToken` fields remain:

```text
token
client_id
scopes
expires_at
resource
subject
claims
```

Do not silently implement against MCP 2.x types under this operation.

---

## A2. Separate HTTP discovery challenges from tool-level ChatGPT linking challenges

The parent plan’s `mcp_auth_error_result()` reuses a challenge containing only `resource_metadata` and optional `scope`. Current official OpenAI plugin authentication documentation requires tool-level `_meta["mcp/www_authenticate"]` challenges to include both an OAuth `error` and `error_description` before ChatGPT will surface the linking UI.

Replace the challenge interface with:

```python
from typing import Literal

OAuthChallengeError = Literal["invalid_token", "insufficient_scope"]


def www_authenticate(
    policy: ResourcePolicy,
    required_scopes: tuple[str, ...] = (),
    *,
    error: OAuthChallengeError | None = None,
    error_description: str | None = None,
) -> str:
    ...
```

Closed behavior:

1. The base challenge always contains:

```text
Bearer resource_metadata="<exact metadata URL>"
```

2. `scope="..."` is included only when `required_scopes` is non-empty, after exact closed-policy validation and deterministic sorting.
3. `error` and `error_description` are either both absent or both present.
4. `error_description` is selected from gateway-authored constant text only; no exception, token, claim, subject, issuer payload, provider response, or model text may enter it.
5. Quote, backslash, control-character, CR/LF, and length validation is enforced before formatting.

Use this exact public mapping for MCP error results:

```python
MCP_CHALLENGE_BY_CODE = {
    AuthErrorCode.MISSING_TOKEN: (
        "invalid_token",
        "Authentication required: no valid access token was provided.",
    ),
    AuthErrorCode.INVALID_TOKEN: (
        "invalid_token",
        "Authentication required: the access token is invalid or no longer usable.",
    ),
    AuthErrorCode.MISSING_SCOPE: (
        "insufficient_scope",
        "Authentication required: the access token does not include the required scope.",
    ),
}
```

`mcp_auth_error_result()` produces exactly:

```python
{
    "isError": True,
    "content": [{"type": "text", "text": "Authentication required."}],
    "_meta": {
        "mcp/www_authenticate": [
            www_authenticate(
                policy,
                required_scopes,
                error=oauth_error,
                error_description=description,
            )
        ]
    },
}
```

The HTTP `401` helper may use the base challenge without `error` when the request is simply unauthenticated, or use the same constant error mapping when the caller supplied an invalid token. Both forms remain deterministic and secret-free.

Required tests:

```python
def test_tool_level_challenge_contains_required_oauth_error_fields(policy):
    result = mcp_auth_error_result(
        policy,
        AuthError(AuthErrorCode.MISSING_SCOPE),
        required_scopes=("mastermind.executive.intent.submit",),
    )
    challenge = result["_meta"]["mcp/www_authenticate"][0]
    assert 'error="insufficient_scope"' in challenge
    assert 'error_description="Authentication required: the access token does not include the required scope."' in challenge
    assert 'scope="mastermind.executive.intent.submit"' in challenge


def test_challenge_refuses_unpaired_or_untrusted_error_description(policy):
    with pytest.raises(AuthError):
        www_authenticate(policy, error="invalid_token")
    with pytest.raises(AuthError):
        www_authenticate(
            policy,
            error="invalid_token",
            error_description='bad"\r\nInjected: yes',
        )
```

---

## A3. Authorization-server metadata describes capabilities; it does not choose U1 deployment strategy

The parent plan forces:

```text
CIMD when supported, otherwise DCR
```

and requires an intersection with only `none` / `private_key_jwt`. Current official OpenAI documentation supports three client-registration paths:

```text
CIMD
DCR
predefined OAuth client
```

For DCR and predefined clients, supported token endpoint methods may also include:

```text
client_secret_post
client_secret_basic
```

BSC-A1 is a resource-server library. It must validate metadata capabilities without choosing the BSC-U1 enrollment strategy.

Replace the parent `ValidatedAuthorizationServerMetadata.client_registration` field with:

```python
@dataclass(frozen=True)
class ValidatedAuthorizationServerMetadata:
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    authorization_response_iss_parameter_supported: bool
    client_id_metadata_document_supported: bool
    registration_endpoint: str | None
    token_endpoint_auth_methods_supported: tuple[str, ...]
    code_challenge_methods_supported: tuple[str, ...]
    scopes_supported: tuple[str, ...]
```

Use the closed supported token endpoint method set:

```python
OPENAI_SUPPORTED_TOKEN_ENDPOINT_AUTH_METHODS = frozenset(
    {
        "none",
        "private_key_jwt",
        "client_secret_post",
        "client_secret_basic",
    }
)
```

Validation law:

1. `issuer`, authorization endpoint, token endpoint, and `jwks_uri` retain the parent plan’s exact canonical HTTPS and same-origin policy.
2. `code_challenge_methods_supported` must include `S256`.
3. `token_endpoint_auth_methods_supported` must be a unique bounded string list and have a non-empty intersection with the closed set above.
4. `client_id_metadata_document_supported` is a real bool, defaulting to `False` only when absent.
5. `registration_endpoint` is optional. When present, validate it canonically; absence is not a refusal because a predefined client is allowed.
6. Do not require CIMD or DCR to exist merely to validate the authorization server.
7. Do not select or persist a registration mode in A1.
8. BSC-U1 chooses one exact mode after inspecting these validated capabilities and then-current ChatGPT workspace behavior.

Required tests:

```python
def test_metadata_accepts_dcr_client_secret_basic_without_cimd(base_metadata):
    value = dict(base_metadata)
    value["client_id_metadata_document_supported"] = False
    value["registration_endpoint"] = "https://auth.example.com/register"
    value["token_endpoint_auth_methods_supported"] = ["client_secret_basic"]
    result = validate_authorization_server_metadata(policy, value)
    assert result.client_id_metadata_document_supported is False
    assert result.registration_endpoint == "https://auth.example.com/register"
    assert result.token_endpoint_auth_methods_supported == ("client_secret_basic",)


def test_metadata_accepts_predefined_client_capability_without_cimd_or_dcr(base_metadata):
    value = dict(base_metadata)
    value.pop("registration_endpoint", None)
    value["client_id_metadata_document_supported"] = False
    value["token_endpoint_auth_methods_supported"] = ["client_secret_post"]
    result = validate_authorization_server_metadata(policy, value)
    assert result.registration_endpoint is None
    assert result.token_endpoint_auth_methods_supported == ("client_secret_post",)
```

Update every test or output that currently expects `client_registration == "cimd"` or `"dcr"`.

---

## A4. Scope order is not authority and must not invalidate a legal token

The parent plan rejects “unsorted ambiguity” in the JWT `scope` claim. OAuth scope order is not semantically significant. A legal token containing:

```text
mastermind.executive.intent.submit mastermind.executive.read
```

must not fail only because the issuer emitted the scopes in that order.

Replace the scope parser law with:

1. `scope` must be a bounded string.
2. Reject leading/trailing space, repeated spaces that create empty tokens, control characters, invalid scope-token characters, duplicate tokens, and an excessive token count.
3. Accept any legal token order.
4. Normalize the verified principal’s `scopes` to a deterministic sorted tuple.
5. Required-scope enforcement remains set containment.

Required tests:

```python
def test_scope_order_is_normalized_not_rejected(verifier, signed_token):
    token = signed_token(
        scope="mastermind.executive.intent.submit mastermind.executive.read"
    )
    principal = verifier.verify(token, required_scopes=("mastermind.executive.read",))
    assert principal.scopes == (
        "mastermind.executive.intent.submit",
        "mastermind.executive.read",
    )

@pytest.mark.parametrize("scope", (" read", "read ", "read  write", "read read"))
def test_noncanonical_or_duplicate_scope_wire_is_refused(verifier, signed_token, scope):
    with pytest.raises(AuthError):
        verifier.verify(signed_token(scope=scope))
```

---

## A5. Bound unknown-kid and failed-refresh amplification across requests

The parent custom JWKS cache permits one forced refresh per verify call for every attacker-controlled unknown `kid`. Across many calls, random kids can still create an unbounded outbound JWKS request stream—the same vulnerability family PyJWT 2.13.0 repaired in `PyJWKClient`.

Extend `ResourcePolicy` with bounded process-memory refresh controls:

```python
unknown_kid_refresh_cooldown_seconds: int = 30
fetch_failure_backoff_seconds: int = 5
```

Closed bounds:

```text
unknown_kid_refresh_cooldown_seconds: 1..300
fetch_failure_backoff_seconds: 1..300
```

Extend `BoundedJwksCache` with process-memory only:

```python
last_unknown_kid_refresh_at: float | None
fetch_retry_not_before: float | None
```

Required behavior under the existing lock:

### Fresh cache + unknown kid

```text
if now - last_unknown_kid_refresh_at < cooldown:
    refuse UNKNOWN_KID with zero fetch
else:
    record this unknown-kid refresh attempt
    fetch once
    if kid still absent: refuse UNKNOWN_KID
```

### Stale/empty cache

```text
if fetch_retry_not_before is not None and now < fetch_retry_not_before:
    refuse JWKS_UNAVAILABLE with zero fetch
else:
    fetch once
    on failure set fetch_retry_not_before = now + backoff
    on success clear backoff and replace cache atomically
```

A failed refresh never makes stale keys acceptable. The cache may retain old bytes for diagnostics but verification still fails closed until a successful current refresh.

Required tests:

```python
def test_random_unknown_kids_trigger_one_refresh_per_cooldown(cache, fake_clock, fetcher):
    cache.get_key("unknown-1")
    for index in range(2, 100):
        with pytest.raises(AuthError):
            cache.get_key(f"unknown-{index}")
    assert fetcher.calls == 1
    fake_clock.advance(30)
    with pytest.raises(AuthError):
        cache.get_key("unknown-100")
    assert fetcher.calls == 2


def test_jwks_outage_uses_bounded_retry_backoff(cache, fake_clock, failing_fetcher):
    with pytest.raises(AuthError):
        cache.get_key("kid-1")
    with pytest.raises(AuthError):
        cache.get_key("kid-1")
    assert failing_fetcher.calls == 1
    fake_clock.advance(5)
    with pytest.raises(AuthError):
        cache.get_key("kid-1")
    assert failing_fetcher.calls == 2
```

Do not add a durable rate-limit table, negative-kid database, replay database, or distributed cache.

---

## A6. Do not fabricate OAuth client identity in the MCP AccessToken adapter

The parent plan maps:

```python
client_id=f"mastermind-business:{policy.policy_id}"
```

That value is a policy label, not a verified OAuth client identity. Do not place it in an SDK field named `client_id`.

Extend the verified principal with:

```python
client_ref: str
```

After signature verification:

1. Read optional `client_id` and `azp` claims.
2. If both are present and differ, refuse `INVALID_TOKEN`.
3. If one is present, require bounded canonical text and derive:

```python
client_ref = hashlib.sha256(
    (issuer + "\nclient\n" + client_id_or_azp).encode("utf-8")
).hexdigest()
```

4. If neither is present, set:

```text
client_ref = oauth-client-unavailable
```

5. `client_ref` is pseudonymous context, not authorization. Tool authorization still comes from verified resource, subject policy, and scopes.
6. Do not log or return the raw client identifier.

The MCP adapter maps:

```python
AccessToken(
    token=raw_token,
    client_id=principal.client_ref,
    scopes=list(principal.scopes),
    expires_at=principal.expires_at,
    resource=principal.resource,
    subject=principal.subject_digest,
    claims={
        "issuer_digest": principal.issuer_digest,
        "client_ref": principal.client_ref,
        "jti_digest": principal.jti_digest,
    },
)
```

Required tests:

```python
def test_client_claim_is_pseudonymized(verifier, signed_token):
    principal = verifier.verify(signed_token(client_id="chatgpt-client"))
    assert principal.client_ref != "chatgpt-client"
    assert len(principal.client_ref) == 64


def test_conflicting_client_id_and_azp_are_refused(verifier, signed_token):
    with pytest.raises(AuthError):
        verifier.verify(signed_token(client_id="one", azp="two"))
```

A1 still does not prove that the network client is ChatGPT. BSC-U1/S1/E1 own the supported OpenAI client-authentication and optional mTLS deployment gate. OAuth authenticates/authorizes the end user; it is not a substitute for the separate MCP-client boundary.

---

## A7. Current official contract receipts

The implementation PR must cite and re-verify these current sources before START:

- OpenAI Plugin Authentication: authenticated MCP servers use OAuth 2.1; resource metadata, authorization-server metadata, exact `resource` propagation, PKCE S256, token verification, and per-tool `securitySchemes` are required.
- OpenAI tool-level linking: `_meta["mcp/www_authenticate"]` must contain a challenge with both `error` and `error_description`.
- OpenAI client registration: CIMD, DCR, and predefined clients are supported; token endpoint auth methods depend on the chosen mode.
- OpenAI mTLS: the OpenAI-managed client certificate authenticates ChatGPT as the MCP client; OAuth remains the end-user authorization boundary. A1 does not implement this deployment layer.
- MCP Python SDK v1.28.1: current supported v1 security floor and unchanged `AccessToken` field shape used by this plan.
- PyJWT 2.13.0: current security release, including algorithm/JWK hardening and unknown-kid/JWKS request-amplification repair.

A material change returns `PLATFORM_CONTRACT_CHANGED`. Do not improvise a new auth architecture in the implementation carrier.

---

## A8. Updated implementation precedence and start gate

The current BSC-A1 planning set is:

1. `docs/superpowers/plans/2026-08-29-business-sol-oauth-resource-server.md`
2. `docs/superpowers/plans/2026-08-29-business-sol-oauth-resource-server-current-contract-amendment.md`

Where they conflict:

```text
current-contract amendment
→ parent BSC-A1 plan
```

The implementation PR must cite both files and implement all amendment tests before claiming GREEN.

No A1 implementation START occurs until:

1. current protected Mastermind and same-commit Skillpack are re-pinned;
2. #234/#236/#237 current state is reconciled;
3. the current release owner permits an independent BSC-A1 branch/CI carrier;
4. current OpenAI/MCP/PyJWT contracts are re-verified;
5. `integrations/business_mcp_auth/**`, tests, and `pyproject.toml` have no active colliding implementation carrier;
6. a fresh isolated worktree/branch is created from then-current protected `master`;
7. the implementation operator reads both the parent plan and this amendment.

The plan remains `SPEC_ONLY / PLAN_ONLY`. A later green implementation remains `BUILT_NOT_PROVEN / PRODUCTION_INERT` until a real Business account, real IdP, real app resource, real Secure MCP Tunnel, and app-specific canaries pass.
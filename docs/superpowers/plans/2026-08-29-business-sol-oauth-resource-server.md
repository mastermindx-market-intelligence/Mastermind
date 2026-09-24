# Business Sol OAuth Resource Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one issuer-agnostic, least-privilege OAuth 2.1 resource-server library that authenticates ChatGPT Business users for the separate Mastermind Steward, Executive, and Dialogue MCP apps without creating an authorization server, identity database, credential store, or second organizational authority plane.

**Architecture:** Pure stdlib contracts own closed policy, canonical resource identity, subject-digest authorization, claims validation, metadata, challenges, and redacted decisions. Edge-only modules isolate PyJWT, HTTPX, and MCP SDK imports; they verify RS256 access tokens against one configured JWKS endpoint, adapt accepted principals to the existing MCP `TokenVerifier` protocol, and expose per-tool OAuth metadata. All runtime configuration and real IdP/client enrollment remain in BSC-U1; this wave is production-inert and uses only hermetic keys, tokens, and fetchers.

**Tech Stack:** Python 3.11+, `mcp==1.28.0`, `PyJWT[crypto]==2.13.0`, existing `httpx>=0.27`, pytest, stdlib dataclasses/enum/hashlib/json/urllib parsing, `cryptography` through the PyJWT crypto extra for hermetic RSA fixtures.

**Spec:** `docs/superpowers/specs/2026-08-29-business-sol-surface-convergence-design.md`

**Program plan:** `docs/superpowers/plans/2026-08-29-business-sol-surface-convergence-program.md`

## Global Constraints

- Implementation START is forbidden until BSC-F0 architecture PR #234 is protected on then-current Mastermind `master`, the current release owner permits the independent BSC carrier, and a fresh A1 path/authority collision census is clean.
- At START and before every modifying boundary, fetch protected `master`, record its exact SHA, load `docs/sol_skills/INDEX.md` and required procedures from that same SHA, and verify `mastermind.sol_skillpack.v1` compatibility. Planning SHAs are advisory after protected source moves.
- Create one fresh isolated worktree and one uniquely named branch from then-current protected `master`. Do not implement on architecture PR #234, planning PR #236, or this stacked planning branch.
- Current official OpenAI authentication, MCP, Secure MCP Tunnel, and Business custom-app contracts must be re-read at START. A material platform change returns `PLATFORM_CONTRACT_CHANGED` before implementation rather than being improvised inside this operation.
- A1 is a resource-server library only. It does not implement an authorization server, OAuth login UI, consent screen, dynamic client registration endpoint, token endpoint, refresh-token store, user directory, app registry, or Business workspace setup.
- Use an established external IdP in BSC-U1. Do not implement authentication from scratch. A1 validates tokens issued by the configured IdP and never possesses the IdP’s signing private key or client secret.
- OAuth authenticates the end user and authorizes an app resource. `ceo-sol` remains reasoning provenance, not authentication. Business workspace role, plugin installation, ChatGPT confirmation, Slack principal, chat title, and model-authored identity never grant Mastermind authority.
- Initial JWT signature algorithm is exactly `RS256`. Do not accept HMAC algorithms, mixed key families, algorithm inference from a JWK, `none`, or caller-supplied algorithm lists. A future algorithm is a separately reviewed app/library generation.
- Pin `PyJWT[crypto]==2.13.0`. Earlier versions are not accepted for this wave because current 2026 security fixes include critical-header and algorithm/key-family verification repairs. Do not float the security dependency.
- The pure package modules must remain importable when `mcp`, `jwt`, and `httpx` are absent. Only edge modules may import those packages. No `control_plane` module imports `integrations.business_mcp_auth`.
- Token, authorization code, refresh token, client secret, raw `sub`, email, name, bearer header, private key, JWKS response body, and app identifier never appear in logs, exception strings, receipts, fixtures committed to Git, Slack, argv, environment dumps, or tool output.
- Subject authorization uses a deterministic SHA-256 digest of exact issuer plus exact subject. The digest is a comparison key, not an authenticity mechanism; signature/issuer/audience/time/scope verification remains mandatory.
- Exact canonical resource identity is configured, never derived from Host headers, request URLs, forwarded headers, tool arguments, model text, or path normalization. Resource and protected-resource metadata URLs are separate explicit fields.
- Runtime JWKS retrieval uses one exact configured HTTPS URL. The token may not choose `jku`, `x5u`, `jwk`, `x5c`, issuer, or discovery endpoints. Redirects, environment proxies, and arbitrary URLs are refused.
- No durable JWKS cache, token cache, login state, nonce database, replay database, user database, scheduler, queue, lease, retry ledger, or auth session store is created. The bounded in-memory key cache disappears on process restart.
- One unknown `kid` may trigger one bounded read-only JWKS refresh. There is no blind retry loop. A stale cache whose refresh fails refuses authentication.
- The resource server verifies every request. A prior accepted token, ChatGPT link state, tunnel connection, or UI session never bypasses verification.
- Per-tool `securitySchemes` and runtime `_meta["mcp/www_authenticate"]` challenges are required. Client-visible metadata is advisory; server-side verification remains authoritative.
- OpenAI-managed mTLS may authenticate ChatGPT at a direct TLS edge, but Secure MCP Tunnel may terminate that evidence outside the local app process. A1 does not accept a request header claiming mTLS. U1 owns the exact transport-evidence proof and policy.
- A valid Steward token cannot call Executive or Dialogue because resource and scope are exact per app. A valid Executive token cannot call Steward or Dialogue. Cross-resource reuse is a refusal.
- Repository CI proves only the library and hermetic resource-server contract. Real OAuth linking, IdP configuration, ChatGPT client registration, app publication, tunnel transport, and Business-account behavior belong to BSC-U1/BSC-C1/BSC-C2.
- Completion state for this wave is at most `BUILT_NOT_PROVEN / PRODUCTION_INERT`.

## Current Official OpenAI Contract to Re-Verify at START

Re-read only official current sources:

- `https://developers.openai.com/plugins/build/auth`
- `https://developers.openai.com/api/docs/guides/secure-mcp-tunnels`
- `https://help.openai.com/en/articles/12584461-developer-mode-apps-and-full-mcp-connectors-in-chatgpt-beta`

The current verified contract requires:

```text
customer-specific reads and writes authenticate users
OAuth 2.1 MCP authorization
RFC 9728 protected-resource metadata
exact resource parameter through authorization and token exchange
OAuth/OIDC authorization-server discovery metadata
PKCE S256
CIMD preferred, with DCR/predefined client alternatives
issuer-identification validation where advertised
access-token verification on every request
issuer + audience/resource + exp/nbf + scope + app policy checks
401 + WWW-Authenticate on HTTP authentication failure
per-tool securitySchemes
runtime _meta["mcp/www_authenticate"] for ChatGPT linking UI
OAuth for end-user identity even when OpenAI mTLS identifies the client
```

If the current official contract materially differs, record the exact delta and stop this operation before implementation.

---

## File Structure

```text
integrations/
  business_mcp_auth/
    __init__.py
    contracts.py
    metadata.py
    claims.py
    jwks.py
    jwt_verifier.py
    mcp_adapter.py

pyproject.toml

tests/
  test_business_mcp_auth_contracts.py
  test_business_mcp_auth_metadata.py
  test_business_mcp_auth_claims.py
  test_business_mcp_auth_jwks.py
  test_business_mcp_auth_jwt_verifier.py
  test_business_mcp_auth_mcp_adapter.py
  test_business_mcp_auth_integration.py
  test_business_mcp_auth_static_fences.py
```

### File Responsibilities

- `__init__.py` — re-export pure contracts only; importing the package must not require MCP, PyJWT, HTTPX, cryptography, network, filesystem, or configuration.
- `contracts.py` — closed policy wire, typed error vocabulary, canonical URL/scope/digest validation, verified-principal and redacted-audit contracts.
- `metadata.py` — deterministic RFC 9728 document, bounded OAuth/OIDC authorization-server metadata validation, HTTP `WWW-Authenticate`, per-tool `securitySchemes`, and MCP runtime challenge metadata.
- `claims.py` — post-signature JWT header and claims validation, exact subject authorization, exact audience/resource and scope enforcement, clock behavior, no raw identity projection.
- `jwks.py` — exact-URL bounded HTTPS fetcher protocol, process-memory single-flight cache, closed RSA JWK selection, one unknown-`kid` refresh, no persistent state.
- `jwt_verifier.py` — the only PyJWT importer; bounded bearer parsing, unverified header extraction for `kid`, exact RSA signature verification, and composition of key cache plus pure claim validation.
- `mcp_adapter.py` — the only MCP SDK importer; adapts accepted principals to `mcp.server.auth.provider.AccessToken` / `TokenVerifier` without changing policy or exposing raw identity.
- tests — RED-first contract, adversarial, concurrency, deterministic-output, dependency-isolation, and end-to-end hermetic proof.

## Public Interfaces Frozen by This Plan

```python
# integrations.business_mcp_auth.contracts
AUTH_POLICY_SCHEMA = "mastermind.business_mcp_auth_policy.v1"
AUTH_AUDIT_SCHEMA = "mastermind.business_mcp_auth_audit.v1"

class AuthErrorCode(str, Enum): ...
class AuthError(RuntimeError): ...

@dataclass(frozen=True)
class ResourcePolicy:
    policy_id: str
    resource: str
    resource_metadata_url: str
    issuer: str
    authorization_servers: tuple[str, ...]
    jwks_uri: str
    required_scopes: tuple[str, ...]
    allowed_subject_digests: tuple[str, ...]
    allowed_algorithms: tuple[str, ...]
    clock_skew_seconds: int
    max_token_lifetime_seconds: int
    jwks_cache_ttl_seconds: int
    schema: str = AUTH_POLICY_SCHEMA

@dataclass(frozen=True)
class VerifiedPrincipal:
    policy_id: str
    issuer: str
    resource: str
    subject_digest: str
    scopes: tuple[str, ...]
    issued_at: int
    expires_at: int
    token_id_digest: str | None

@dataclass(frozen=True)
class AuthAuditEvent:
    schema: str
    policy_id: str
    code: str
    accepted: bool

class AuthAuditSink(Protocol):
    def emit(self, event: AuthAuditEvent) -> None: ...

def load_resource_policy(value: object) -> ResourcePolicy: ...
def subject_digest(*, issuer: str, subject: str) -> str: ...

# integrations.business_mcp_auth.metadata
def protected_resource_metadata(policy: ResourcePolicy) -> dict[str, object]: ...
def validate_authorization_server_metadata(
    value: Mapping[str, object],
    policy: ResourcePolicy,
) -> dict[str, object]: ...
def www_authenticate(policy: ResourcePolicy, *, scopes: Sequence[str] | None = None) -> str: ...
def oauth_security_schemes(scopes: Sequence[str]) -> list[dict[str, object]]: ...
def mcp_auth_error_result(policy: ResourcePolicy, *, code: AuthErrorCode) -> dict[str, object]: ...

# integrations.business_mcp_auth.claims
def validate_jwt_header(header: Mapping[str, object], policy: ResourcePolicy) -> str: ...
def validate_verified_claims(
    claims: Mapping[str, object],
    policy: ResourcePolicy,
    *,
    now: int,
) -> VerifiedPrincipal: ...

# integrations.business_mcp_auth.jwks
class JwksFetcher(Protocol):
    async def fetch(self, *, url: str, timeout_seconds: float, max_bytes: int) -> bytes: ...

class HttpxJwksFetcher: ...
class BoundedJwksCache:
    async def key_for(self, kid: str) -> Mapping[str, object]: ...

# integrations.business_mcp_auth.jwt_verifier
class JwtAuthenticator:
    async def verify_authorization_header(self, header: str, *, now: int) -> VerifiedPrincipal: ...
    async def verify_token(self, token: str, *, now: int) -> VerifiedPrincipal: ...

# integrations.business_mcp_auth.mcp_adapter
class MastermindTokenVerifier(TokenVerifier):
    async def verify_token(self, token: str) -> AccessToken | None: ...
```

---

### Task 1: Add the isolated dependency profile and pure policy contracts

**Files:**
- Modify: `pyproject.toml`
- Create: `integrations/business_mcp_auth/__init__.py`
- Create: `integrations/business_mcp_auth/contracts.py`
- Create: `tests/test_business_mcp_auth_contracts.py`
- Create: `tests/test_business_mcp_auth_static_fences.py`

**Interfaces:**
- Produces `AuthErrorCode`, `AuthError`, `ResourcePolicy`, `VerifiedPrincipal`, `AuthAuditEvent`, `AuthAuditSink`, `load_resource_policy`, and `subject_digest`.
- Produces optional dependency group `business-mcp` and pins PyJWT in `dev` for tests.
- Consumed by every later A1 task.

- [ ] **Step 1: Add RED tests for the exact policy wire and subject digest**

Create `tests/test_business_mcp_auth_contracts.py` with:

```python
from __future__ import annotations

import hashlib

import pytest

from integrations.business_mcp_auth.contracts import (
    AUTH_POLICY_SCHEMA,
    AuthError,
    AuthErrorCode,
    load_resource_policy,
    subject_digest,
)


def _policy() -> dict[str, object]:
    issuer = "https://identity.example.test/"
    return {
        "schema": AUTH_POLICY_SCHEMA,
        "policy_id": "mastermind-steward-v1",
        "resource": "https://mcp.example.test/mcp/steward/v1",
        "resource_metadata_url": (
            "https://mcp.example.test/.well-known/"
            "oauth-protected-resource/mcp/steward/v1"
        ),
        "issuer": issuer,
        "authorization_servers": [issuer],
        "jwks_uri": "https://identity.example.test/.well-known/jwks.json",
        "required_scopes": ["mastermind.steward.read"],
        "allowed_subject_digests": [subject_digest(issuer=issuer, subject="chairman-opaque")],
        "allowed_algorithms": ["RS256"],
        "clock_skew_seconds": 30,
        "max_token_lifetime_seconds": 900,
        "jwks_cache_ttl_seconds": 300,
    }


def test_subject_digest_is_exact_issuer_subject_sha256() -> None:
    issuer = "https://identity.example.test/"
    subject = "chairman-opaque"
    expected = hashlib.sha256(f"{issuer}\n{subject}".encode("utf-8")).hexdigest()
    assert subject_digest(issuer=issuer, subject=subject) == expected


def test_exact_policy_wire_is_accepted() -> None:
    policy = load_resource_policy(_policy())
    assert policy.policy_id == "mastermind-steward-v1"
    assert policy.allowed_algorithms == ("RS256",)
    assert policy.required_scopes == ("mastermind.steward.read",)
    assert policy.authorization_servers == (policy.issuer,)


@pytest.mark.parametrize(
    ("mutator", "code"),
    [
        (lambda value: value.update(extra="x"), AuthErrorCode.INVALID_POLICY),
        (lambda value: value.update(resource="http://mcp.example.test/mcp/steward/v1"), AuthErrorCode.INVALID_POLICY),
        (lambda value: value.update(resource="https://user@mcp.example.test/mcp/steward/v1"), AuthErrorCode.INVALID_POLICY),
        (lambda value: value.update(allowed_algorithms=["HS256"]), AuthErrorCode.INVALID_POLICY),
        (lambda value: value.update(allowed_algorithms=["RS256", "HS256"]), AuthErrorCode.INVALID_POLICY),
        (lambda value: value.update(required_scopes=[]), AuthErrorCode.INVALID_POLICY),
        (lambda value: value.update(allowed_subject_digests=[]), AuthErrorCode.INVALID_POLICY),
        (lambda value: value.update(clock_skew_seconds=121), AuthErrorCode.INVALID_POLICY),
        (lambda value: value.update(max_token_lifetime_seconds=0), AuthErrorCode.INVALID_POLICY),
    ],
)
def test_policy_refuses_unknown_or_unsafe_values(mutator, code: AuthErrorCode) -> None:
    value = _policy()
    mutator(value)
    with pytest.raises(AuthError) as caught:
        load_resource_policy(value)
    assert caught.value.code is code
    assert caught.value.public_message == "authentication policy refused"
```

- [ ] **Step 2: Add RED tests for dependency isolation and forbidden cross-plane imports**

Start `tests/test_business_mcp_auth_static_fences.py` with:

```python
from __future__ import annotations

import ast
from pathlib import Path


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_pure_auth_modules_do_not_import_edge_or_control_plane_packages() -> None:
    root = Path(__file__).resolve().parents[1]
    for relative in (
        "integrations/business_mcp_auth/__init__.py",
        "integrations/business_mcp_auth/contracts.py",
    ):
        imports = _imports(root / relative)
        assert not any(name == "jwt" or name.startswith("jwt.") for name in imports)
        assert not any(name == "mcp" or name.startswith("mcp.") for name in imports)
        assert not any(name == "httpx" or name.startswith("httpx.") for name in imports)
        assert not any(name == "control_plane" or name.startswith("control_plane.") for name in imports)


def test_control_plane_does_not_import_business_auth() -> None:
    root = Path(__file__).resolve().parents[1]
    offenders: list[str] = []
    for path in sorted((root / "control_plane").glob("*.py")):
        if "business_mcp_auth" in path.read_text(encoding="utf-8"):
            offenders.append(path.relative_to(root).as_posix())
    assert offenders == []
```

- [ ] **Step 3: Run RED and record the expected import failure**

Run:

```bash
python3 -m pytest -q \
  tests/test_business_mcp_auth_contracts.py \
  tests/test_business_mcp_auth_static_fences.py
```

Expected: collection fails because `integrations.business_mcp_auth` does not exist. Preserve the output in the PR evidence; do not create production code before observing RED.

- [ ] **Step 4: Add the isolated optional dependency pins**

Modify `pyproject.toml` so the existing `dev` list also contains:

```toml
"PyJWT[crypto]==2.13.0",
```

and add:

```toml
business-mcp = [
    "mcp==1.28.0",
    "PyJWT[crypto]==2.13.0",
]
```

Do not add PyJWT or MCP to the base runtime dependency list. The sealed Executive control-plane runtime must remain independent of both packages.

- [ ] **Step 5: Implement the closed pure contracts**

Create `integrations/business_mcp_auth/contracts.py` with exact keys:

```python
POLICY_KEYS = frozenset(
    {
        "schema",
        "policy_id",
        "resource",
        "resource_metadata_url",
        "issuer",
        "authorization_servers",
        "jwks_uri",
        "required_scopes",
        "allowed_subject_digests",
        "allowed_algorithms",
        "clock_skew_seconds",
        "max_token_lifetime_seconds",
        "jwks_cache_ttl_seconds",
    }
)
```

Use one closed error vocabulary:

```python
class AuthErrorCode(str, enum.Enum):
    INVALID_POLICY = "invalid_policy"
    AUTHORIZATION_MISSING = "authorization_missing"
    AUTHORIZATION_MALFORMED = "authorization_malformed"
    TOKEN_TOO_LARGE = "token_too_large"
    TOKEN_HEADER_REFUSED = "token_header_refused"
    TOKEN_SIGNATURE_REFUSED = "token_signature_refused"
    TOKEN_CLAIMS_REFUSED = "token_claims_refused"
    TOKEN_EXPIRED = "token_expired"
    TOKEN_NOT_YET_VALID = "token_not_yet_valid"
    TOKEN_LIFETIME_REFUSED = "token_lifetime_refused"
    ISSUER_REFUSED = "issuer_refused"
    RESOURCE_REFUSED = "resource_refused"
    SCOPE_REFUSED = "scope_refused"
    SUBJECT_REFUSED = "subject_refused"
    JWKS_UNAVAILABLE = "jwks_unavailable"
    JWKS_REFUSED = "jwks_refused"
    KEY_NOT_FOUND = "key_not_found"
    INTERNAL_ERROR = "internal_error"
```

`AuthError` exposes only `code` and one fixed `public_message`; it never embeds exception text, URL query, token, subject, key, or claims:

```python
_PUBLIC_MESSAGES = {
    AuthErrorCode.INVALID_POLICY: "authentication policy refused",
    AuthErrorCode.AUTHORIZATION_MISSING: "authentication required",
    AuthErrorCode.AUTHORIZATION_MALFORMED: "authentication required",
    AuthErrorCode.TOKEN_TOO_LARGE: "authentication refused",
    AuthErrorCode.JWKS_UNAVAILABLE: "authentication temporarily unavailable",
}

class AuthError(RuntimeError):
    def __init__(self, code: AuthErrorCode) -> None:
        super().__init__(_PUBLIC_MESSAGES.get(code, "authentication refused"))
        self.code = code
        self.public_message = str(self)
```

`load_resource_policy()` must:

- require a mapping with exactly `POLICY_KEYS`;
- require `schema == AUTH_POLICY_SCHEMA`;
- validate canonical nonempty `policy_id` against `^[a-z0-9][a-z0-9._-]{2,95}$`;
- require HTTPS URLs with no userinfo, query, fragment, control characters, or non-default port;
- preserve exact trailing-slash spelling and reject duplicate URL normalization rather than silently repairing it;
- require `authorization_servers == [issuer]` in A1;
- require `jwks_uri` to share exact scheme + host + port with the issuer;
- require sorted unique scopes matching `^[a-z][a-z0-9._:-]{2,95}$`;
- require sorted unique 64-lowercase-hex subject digests;
- require `allowed_algorithms == ["RS256"]`;
- require actual integers, never bools, with `0 <= clock_skew_seconds <= 120`, `60 <= max_token_lifetime_seconds <= 3600`, and `60 <= jwks_cache_ttl_seconds <= 3600`.

`subject_digest()` strips nothing and hashes exact canonical issuer plus newline plus exact nonempty subject. It rejects controls, surrounding whitespace, and values over 1024 characters.

Create `__init__.py` that re-exports only symbols from `contracts.py`. Do not import future edge modules.

- [ ] **Step 6: Run focused GREEN and dependency-isolation proof**

Run:

```bash
python3 -m pytest -q \
  tests/test_business_mcp_auth_contracts.py \
  tests/test_business_mcp_auth_static_fences.py
python3 -m compileall -q integrations/business_mcp_auth/contracts.py
```

Expected: all focused tests pass and pure modules compile without importing MCP/PyJWT/HTTPX.

- [ ] **Step 7: Commit Task 1**

```bash
git add \
  pyproject.toml \
  integrations/business_mcp_auth/__init__.py \
  integrations/business_mcp_auth/contracts.py \
  tests/test_business_mcp_auth_contracts.py \
  tests/test_business_mcp_auth_static_fences.py
git commit -m "feat(auth): add Business MCP resource policy contracts"
```

---

### Task 2: Build protected-resource metadata, OAuth challenges, and per-tool schemes

**Files:**
- Create: `integrations/business_mcp_auth/metadata.py`
- Create: `tests/test_business_mcp_auth_metadata.py`
- Modify: `tests/test_business_mcp_auth_static_fences.py`

**Interfaces:**
- Consumes `ResourcePolicy` and `AuthErrorCode`.
- Produces `protected_resource_metadata`, `validate_authorization_server_metadata`, `www_authenticate`, `oauth_security_schemes`, and `mcp_auth_error_result`.
- Later S1/E1 server adapters use these helpers without reimplementing OAuth metadata.

- [ ] **Step 1: Write RED tests for exact RFC 9728 metadata**

Create `tests/test_business_mcp_auth_metadata.py`:

```python
from __future__ import annotations

from integrations.business_mcp_auth.contracts import AuthErrorCode, load_resource_policy, subject_digest
from integrations.business_mcp_auth.metadata import (
    mcp_auth_error_result,
    oauth_security_schemes,
    protected_resource_metadata,
    validate_authorization_server_metadata,
    www_authenticate,
)


def _policy():
    issuer = "https://identity.example.test/"
    return load_resource_policy(
        {
            "schema": "mastermind.business_mcp_auth_policy.v1",
            "policy_id": "mastermind-executive-v1",
            "resource": "https://mcp.example.test/mcp/executive/v1",
            "resource_metadata_url": (
                "https://mcp.example.test/.well-known/"
                "oauth-protected-resource/mcp/executive/v1"
            ),
            "issuer": issuer,
            "authorization_servers": [issuer],
            "jwks_uri": "https://identity.example.test/.well-known/jwks.json",
            "required_scopes": [
                "mastermind.executive.intent.submit",
                "mastermind.executive.read",
            ],
            "allowed_subject_digests": [subject_digest(issuer=issuer, subject="chairman-opaque")],
            "allowed_algorithms": ["RS256"],
            "clock_skew_seconds": 30,
            "max_token_lifetime_seconds": 900,
            "jwks_cache_ttl_seconds": 300,
        }
    )


def test_protected_resource_metadata_is_exact_and_deterministic() -> None:
    policy = _policy()
    assert protected_resource_metadata(policy) == {
        "resource": policy.resource,
        "authorization_servers": [policy.issuer],
        "scopes_supported": list(policy.required_scopes),
    }
    assert protected_resource_metadata(policy) == protected_resource_metadata(policy)


def test_authorization_server_metadata_is_validated_and_reduced() -> None:
    policy = _policy()
    value = {
        "issuer": policy.issuer,
        "authorization_endpoint": "https://identity.example.test/authorize",
        "token_endpoint": "https://identity.example.test/oauth/token",
        "jwks_uri": policy.jwks_uri,
        "authorization_response_iss_parameter_supported": True,
        "client_id_metadata_document_supported": True,
        "token_endpoint_auth_methods_supported": ["none", "private_key_jwt"],
        "code_challenge_methods_supported": ["S256"],
        "scopes_supported": list(policy.required_scopes),
        "unrelated_provider_field": "ignored",
    }
    assert validate_authorization_server_metadata(value, policy) == {
        "issuer": policy.issuer,
        "authorization_endpoint": "https://identity.example.test/authorize",
        "token_endpoint": "https://identity.example.test/oauth/token",
        "jwks_uri": policy.jwks_uri,
        "authorization_response_iss_parameter_supported": True,
        "client_registration": "cimd",
        "token_endpoint_auth_methods_supported": ["none", "private_key_jwt"],
        "code_challenge_methods_supported": ["S256"],
        "scopes_supported": list(policy.required_scopes),
    }


def test_www_authenticate_names_exact_metadata_and_scope() -> None:
    policy = _policy()
    assert www_authenticate(policy) == (
        'Bearer resource_metadata="https://mcp.example.test/.well-known/'
        'oauth-protected-resource/mcp/executive/v1", '
        'scope="mastermind.executive.intent.submit mastermind.executive.read"'
    )


def test_per_tool_security_scheme_is_closed() -> None:
    assert oauth_security_schemes(["mastermind.executive.read"]) == [
        {"type": "oauth2", "scopes": ["mastermind.executive.read"]}
    ]


def test_runtime_mcp_challenge_contains_no_identity_or_token() -> None:
    policy = _policy()
    result = mcp_auth_error_result(policy, code=AuthErrorCode.SUBJECT_REFUSED)
    assert result == {
        "content": [{"type": "text", "text": "authentication refused"}],
        "isError": True,
        "_meta": {"mcp/www_authenticate": [www_authenticate(policy)]},
    }
```

- [ ] **Step 2: Run RED**

```bash
python3 -m pytest -q tests/test_business_mcp_auth_metadata.py
```

Expected: import failure for `metadata.py`.

- [ ] **Step 3: Implement deterministic metadata helpers**

`protected_resource_metadata()` returns only:

```python
{
    "resource": policy.resource,
    "authorization_servers": list(policy.authorization_servers),
    "scopes_supported": list(policy.required_scopes),
}
```

Do not add issuer discovery results, app IDs, subject policy, JWKS URI, token details, workspace identifiers, or local host paths to public resource metadata.

`validate_authorization_server_metadata()` accepts a provider metadata mapping with additional provider fields but returns one closed reduced document. It must:

- require exact `issuer == policy.issuer`;
- require HTTPS `authorization_endpoint`, `token_endpoint`, and `jwks_uri`, with `jwks_uri == policy.jwks_uri`;
- require `code_challenge_methods_supported` contains `S256`;
- require `token_endpoint_auth_methods_supported` has a nonempty intersection with `{"none", "private_key_jwt"}` and return the supported intersection in deterministic order;
- require every policy scope appears in `scopes_supported`;
- select `client_registration="cimd"` when `client_id_metadata_document_supported is True`; otherwise require a canonical HTTPS `registration_endpoint` and return `client_registration="dcr"`;
- require `authorization_response_iss_parameter_supported` is an actual bool and preserve it so U1 can choose the exact stable or callback-ID-specific redirect URI;
- ignore unrelated provider metadata in the input but never return it;
- reject mismatches as `INVALID_POLICY` without provider response text.

A1 validates metadata; it does not host an authorization server, register a client, or persist discovery output.

`www_authenticate()`:

- accepts no caller-provided URL;
- uses `policy.resource_metadata_url` exactly;
- uses either the supplied scopes or the policy scopes;
- validates scopes through the same closed scope validator;
- returns one canonical string with quoted values and no newline;
- never includes internal failure code, subject, issuer error, token, or exception text.

`oauth_security_schemes()` returns exactly one `oauth2` scheme with sorted unique scopes.

`mcp_auth_error_result()` returns one fixed text selected from the typed error’s public message plus `_meta["mcp/www_authenticate"]`. It never returns the internal error code to the model; redacted code belongs only to an audit sink.

- [ ] **Step 4: Extend pure-module static fences**

Add `metadata.py` to the pure import census and assert it imports no MCP SDK. The plain dictionary output is later wrapped by app-specific server code.

- [ ] **Step 5: Run GREEN and canonical-JSON determinism check**

```bash
python3 -m pytest -q \
  tests/test_business_mcp_auth_metadata.py \
  tests/test_business_mcp_auth_contracts.py \
  tests/test_business_mcp_auth_static_fences.py
python3 - <<'PY'
import json
from tests.test_business_mcp_auth_metadata import _policy
from integrations.business_mcp_auth.metadata import protected_resource_metadata
value = protected_resource_metadata(_policy())
a = json.dumps(value, sort_keys=True, separators=(",", ":"))
b = json.dumps(value, sort_keys=True, separators=(",", ":"))
assert a == b
print(a)
PY
```

Expected: tests pass and byte-identical JSON is printed twice conceptually/compared once.

- [ ] **Step 6: Commit Task 2**

```bash
git add \
  integrations/business_mcp_auth/metadata.py \
  tests/test_business_mcp_auth_metadata.py \
  tests/test_business_mcp_auth_static_fences.py
git commit -m "feat(auth): add MCP OAuth metadata and challenges"
```

---

### Task 3: Implement strict post-signature JWT header and claims validation

**Files:**
- Create: `integrations/business_mcp_auth/claims.py`
- Create: `tests/test_business_mcp_auth_claims.py`
- Modify: `tests/test_business_mcp_auth_static_fences.py`

**Interfaces:**
- Consumes `ResourcePolicy`, `VerifiedPrincipal`, `AuthError`, `AuthErrorCode`, and `subject_digest`.
- Produces `validate_jwt_header()` and `validate_verified_claims()`.
- Does not parse or verify JWT signatures; Task 5 supplies already signature-verified header/claims.

- [ ] **Step 1: Write RED header-validation tests**

Use this exact positive header:

```python
GOOD_HEADER = {"alg": "RS256", "kid": "key-2026-01", "typ": "at+jwt"}
```

Add parameterized refusal for:

```python
{"alg": "none", "kid": "key-2026-01", "typ": "at+jwt"}
{"alg": "HS256", "kid": "key-2026-01", "typ": "at+jwt"}
{"alg": "RS256", "typ": "at+jwt"}
{"alg": "RS256", "kid": "", "typ": "at+jwt"}
{"alg": "RS256", "kid": "key-2026-01", "typ": "other"}
{"alg": "RS256", "kid": "key-2026-01", "crit": ["custom"]}
{"alg": "RS256", "kid": "key-2026-01", "jku": "https://attacker.test/jwks"}
{"alg": "RS256", "kid": "key-2026-01", "x5u": "https://attacker.test/cert"}
{"alg": "RS256", "kid": "key-2026-01", "jwk": {"kty": "RSA"}}
```

Expected code: `TOKEN_HEADER_REFUSED`.

- [ ] **Step 2: Write RED claims-validation tests**

Create one valid claims document:

```python
{
    "iss": policy.issuer,
    "sub": "chairman-opaque",
    "aud": policy.resource,
    "iat": 1_788_000_000,
    "nbf": 1_788_000_000,
    "exp": 1_788_000_600,
    "scope": "mastermind.executive.intent.submit mastermind.executive.read",
    "jti": "token-id-opaque",
}
```

At `now=1_788_000_100`, require accepted `VerifiedPrincipal` with:

```text
subject_digest = SHA256(issuer + newline + sub)
scopes = sorted tuple
issued_at = iat
expires_at = exp
token_id_digest = SHA256(jti)
```

Add exact refusal tests for:

- missing required claim: `iss`, `sub`, `aud`, `iat`, `exp`, or `scope`;
- wrong issuer;
- `aud` absent, wrong, wildcard, or a multi-audience list containing another resource;
- expired beyond skew;
- `nbf` or `iat` in the future beyond skew;
- `exp <= iat`;
- `exp - iat > max_token_lifetime_seconds`;
- scope as a list instead of canonical space-delimited string;
- missing required scope;
- duplicate scope token;
- unauthorized subject;
- bool where an integer timestamp is required;
- raw subject/email not appearing in `VerifiedPrincipal`, error string, or audit code.

- [ ] **Step 3: Run RED**

```bash
python3 -m pytest -q tests/test_business_mcp_auth_claims.py
```

Expected: import failure for `claims.py`.

- [ ] **Step 4: Implement exact header validation**

`validate_jwt_header()` must:

- require a mapping;
- require `alg == "RS256"` and membership in `policy.allowed_algorithms`;
- require `kid` matching `^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$`;
- accept absent `typ`, `JWT`, or `at+jwt`; reject every other value;
- reject any nonempty `crit` and reject presence of `jku`, `x5u`, `x5c`, or `jwk`;
- return the validated `kid` only.

Do not let a JWK’s `alg` override the policy algorithm.

- [ ] **Step 5: Implement exact claims validation**

`validate_verified_claims()` must:

- treat all token claims as untrusted input even after signature verification;
- require exact `iss`, one exact audience equal to `policy.resource`, nonempty canonical `sub`, integer `iat` and `exp`, optional integer `nbf`, and canonical scope string;
- refuse a multi-audience token in A1 even if one item matches;
- apply inclusive skew consistently:
  - expired when `now > exp + skew`;
  - not-yet-valid when `now + skew < nbf`;
  - future-issued when `now + skew < iat`;
- require `0 < exp - iat <= max_token_lifetime_seconds`;
- split scope on single spaces, reject empty/duplicate/unsorted ambiguity, sort for the principal, and require policy scopes as a subset;
- compare only the digest of exact issuer+subject against `allowed_subject_digests`;
- hash a canonical nonempty `jti` when present; reject malformed `jti`; never return it raw;
- return no email, name, role, workspace, app ID, claims map, token, or raw subject.

- [ ] **Step 6: Run GREEN and pure-module fences**

```bash
python3 -m pytest -q \
  tests/test_business_mcp_auth_claims.py \
  tests/test_business_mcp_auth_contracts.py \
  tests/test_business_mcp_auth_static_fences.py
python3 -m compileall -q integrations/business_mcp_auth/claims.py
```

- [ ] **Step 7: Commit Task 3**

```bash
git add \
  integrations/business_mcp_auth/claims.py \
  tests/test_business_mcp_auth_claims.py \
  tests/test_business_mcp_auth_static_fences.py
git commit -m "feat(auth): validate Business JWT claims strictly"
```

---

### Task 4: Build the exact-URL bounded JWKS fetcher and in-memory cache

**Files:**
- Create: `integrations/business_mcp_auth/jwks.py`
- Create: `tests/test_business_mcp_auth_jwks.py`
- Modify: `tests/test_business_mcp_auth_static_fences.py`

**Interfaces:**
- Consumes `ResourcePolicy`, `AuthError`, and `AuthErrorCode`.
- Produces `JwksFetcher`, `HttpxJwksFetcher`, and `BoundedJwksCache`.
- `BoundedJwksCache.key_for(kid)` returns one validated public RSA JWK mapping; it does not construct an executable crypto key.

- [ ] **Step 1: Write RED fixtures for exact JWKS and bounded fetch behavior**

Use a fake async fetcher:

```python
class FakeFetcher:
    def __init__(self, payloads: list[bytes | Exception]) -> None:
        self.payloads = list(payloads)
        self.calls: list[tuple[str, float, int]] = []

    async def fetch(self, *, url: str, timeout_seconds: float, max_bytes: int) -> bytes:
        self.calls.append((url, timeout_seconds, max_bytes))
        value = self.payloads.pop(0)
        if isinstance(value, Exception):
            raise value
        return value
```

Generate small public RSA JWK mappings in tests with fixed fake `n`/`e` strings for cache-shape tests; cryptographic validity is Task 5/7.

Require:

- first `key_for("kid-a")` fetches once and returns the matching key;
- repeated request before TTL uses cache with zero additional fetch;
- unknown `kid` forces exactly one refresh and then returns/refuses;
- stale cache forces one refresh;
- stale cache + fetch failure returns `JWKS_UNAVAILABLE`, never stale acceptance;
- malformed JSON, non-object, missing `keys`, oversized key list, duplicate `kid`, non-RSA key, `use != sig`, `alg != RS256`, missing `n/e`, or unknown fields that choose a remote key returns `JWKS_REFUSED`;
- 17 keys exceed the A1 limit of 16;
- concurrent first requests share one in-flight fetch;
- no file is written and a new cache instance begins empty.

- [ ] **Step 2: Run RED**

```bash
python3 -m pytest -q tests/test_business_mcp_auth_jwks.py
```

Expected: import failure for `jwks.py`.

- [ ] **Step 3: Implement the fetch protocol and constants**

Use:

```python
MAX_JWKS_BYTES = 256 * 1024
MAX_JWKS_KEYS = 16
JWKS_TIMEOUT_SECONDS = 5.0
```

`JwksFetcher` is a structural async protocol. `BoundedJwksCache` receives:

```python
policy: ResourcePolicy
fetcher: JwksFetcher
monotonic: Callable[[], float]
```

It owns only process memory:

```python
_keys_by_kid: dict[str, Mapping[str, object]]
_loaded_at: float | None
_lock: asyncio.Lock
```

No background refresh task, disk cache, timer, scheduler, retry counter, or database.

- [ ] **Step 4: Implement closed RSA JWK validation**

For each key require:

```text
kid: canonical opaque string
kty: RSA
use: sig or absent
alg: RS256 or absent
n: nonempty base64url text
e: nonempty base64url text
```

Allow these non-authoritative extras because established IdPs commonly publish them:

```text
x5c
x5t
x5t#S256
```

Never use extras for key selection. Reject `jku`, `x5u`, private RSA fields (`d`, `p`, `q`, `dp`, `dq`, `qi`), symmetric `k`, or embedded nested `jwk`.

A JWK without `alg` is accepted only because the resource policy and JWT header independently require `RS256`; the constructed crypto verifier still receives an explicit algorithm allowlist.

- [ ] **Step 5: Implement single-flight cache semantics**

`key_for(kid)`:

1. validates canonical `kid`;
2. returns a matching key from a fresh cache;
3. otherwise enters one async lock and rechecks cache;
4. performs one exact-URL fetch;
5. parses/validates/replaces the entire key map atomically;
6. returns the requested key or raises `KEY_NOT_FOUND`;
7. performs no second fetch in the same invocation.

A refresh exception is mapped to `JWKS_UNAVAILABLE` without exception text. A malformed response is `JWKS_REFUSED`.

- [ ] **Step 6: Implement the HTTPX edge fetcher safely**

`HttpxJwksFetcher` is the only `httpx` importer. It receives the exact `ResourcePolicy` and constructs:

```python
httpx.AsyncClient(
    follow_redirects=False,
    trust_env=False,
    timeout=JWKS_TIMEOUT_SECONDS,
)
```

It:

- accepts only `url == policy.jwks_uri`;
- sends `Accept: application/json`;
- refuses redirects and every non-200 status;
- streams bytes and aborts once `max_bytes` is exceeded;
- accepts `application/json` or `application/jwk-set+json` media types when supplied;
- maps all errors to `JWKS_UNAVAILABLE` without URL/body/exception text;
- closes its client through an async context manager or explicit `aclose()` contract.

No environment proxy, cookies, auth header, caller header, redirect, discovery, or token-derived URL.

- [ ] **Step 7: Extend static fences**

Require:

- `jwks.py` may import `httpx` but not MCP, PyJWT, `control_plane`, `subprocess`, `sqlite3`, `keyring`, or provider clients;
- source contains no `open(`, `write_text`, `write_bytes`, `sqlite`, `pickle`, or cache path constant;
- exact URI comparison is present; no `iss`-derived URL join.

- [ ] **Step 8: Run GREEN**

```bash
python3 -m pytest -q \
  tests/test_business_mcp_auth_jwks.py \
  tests/test_business_mcp_auth_contracts.py \
  tests/test_business_mcp_auth_static_fences.py
python3 -m compileall -q integrations/business_mcp_auth/jwks.py
```

- [ ] **Step 9: Commit Task 4**

```bash
git add \
  integrations/business_mcp_auth/jwks.py \
  tests/test_business_mcp_auth_jwks.py \
  tests/test_business_mcp_auth_static_fences.py
git commit -m "feat(auth): add bounded exact-URL JWKS cache"
```

---

### Task 5: Verify bounded RS256 bearer tokens with PyJWT 2.13.0

**Files:**
- Create: `integrations/business_mcp_auth/jwt_verifier.py`
- Create: `tests/test_business_mcp_auth_jwt_verifier.py`
- Modify: `tests/test_business_mcp_auth_static_fences.py`

**Interfaces:**
- Consumes `BoundedJwksCache`, `ResourcePolicy`, `validate_jwt_header`, and `validate_verified_claims`.
- Produces `JwtAuthenticator.verify_authorization_header()` and `JwtAuthenticator.verify_token()`.
- This is the only PyJWT importer.

- [ ] **Step 1: Write RED RSA token fixtures**

In the test file, generate an ephemeral 2048-bit RSA key using `cryptography.hazmat.primitives.asymmetric.rsa.generate_private_key(public_exponent=65537, key_size=2048)`. Convert its public numbers to a JWK with base64url-no-padding helpers and sign tokens with `jwt.encode(..., algorithm="RS256", headers={"kid": "kid-a", "typ": "at+jwt"})`.

Do not commit any static private key. Test keys exist only in process memory.

- [ ] **Step 2: Add RED positive and authorization-header tests**

Require:

- `Bearer <token>` verifies and returns the exact redacted principal;
- header name matching is case-insensitive only for the `Bearer` scheme, with exactly one ASCII space;
- missing header -> `AUTHORIZATION_MISSING`;
- Basic, multiple spaces, comma-separated values, control characters, empty token, or surrounding whitespace -> `AUTHORIZATION_MALFORMED`;
- token over `MAX_TOKEN_BYTES = 16 * 1024` -> `TOKEN_TOO_LARGE` before PyJWT or JWKS access.

- [ ] **Step 3: Add RED cryptographic refusal tests**

Require refusal for:

- signature from a different RSA key using same `kid`;
- tampered payload;
- `alg=none`;
- HS256 token using public-key material as an HMAC secret;
- ES256 token;
- unknown `kid` after exactly one cache refresh;
- malformed compact token segments;
- non-JSON header/payload;
- token with `crit`, `jku`, `x5u`, or embedded JWK;
- correct signature but wrong issuer/resource/scope/subject/time.

The cryptographic/malformed paths return typed codes without including PyJWT exception text.

- [ ] **Step 4: Run RED**

```bash
python3 -m pytest -q tests/test_business_mcp_auth_jwt_verifier.py
```

Expected: import failure for `jwt_verifier.py`.

- [ ] **Step 5: Implement strict bearer parsing**

Use a byte-size limit before decoding:

```python
MAX_TOKEN_BYTES = 16 * 1024
```

`verify_authorization_header()` accepts a Python string only, rejects controls, requires one exact scheme/token split, and forwards only the compact token to `verify_token()`.

- [ ] **Step 6: Implement exact header-first key selection**

`verify_token()`:

1. rejects oversized/noncanonical compact input;
2. calls `jwt.get_unverified_header(token)` only to obtain untrusted header fields;
3. validates the header and obtains `kid` through `validate_jwt_header()`;
4. obtains the configured key mapping from `BoundedJwksCache.key_for(kid)`;
5. builds the RSA public key with `jwt.PyJWK.from_dict(dict(key_mapping), algorithm="RS256").key`, then requires the resulting `PyJWK.algorithm_name == "RS256"`;
6. calls `jwt.decode_complete()` with exact `algorithms=["RS256"]` and signature verification enabled;
7. disables PyJWT’s issuer/audience/time policy checks only because `validate_verified_claims()` performs the frozen exact checks immediately afterward;
8. verifies the returned header again and requires the same `kid`;
9. passes only the signature-verified payload to `validate_verified_claims()`.

Do not use `PyJWKClient`; it performs its own URL/key-fetch behavior and would duplicate the exact-URL cache owner. Do not infer allowed algorithms from `PyJWK.algorithm_name`.

The decode call must include:

```python
jwt.decode_complete(
    token,
    key=public_key,
    algorithms=["RS256"],
    options={
        "verify_signature": True,
        "verify_exp": False,
        "verify_nbf": False,
        "verify_iat": False,
        "verify_aud": False,
        "verify_iss": False,
        "require": [],
    },
)
```

Pure claim validation remains the sole time/resource/subject/scope policy implementation.

- [ ] **Step 7: Map exceptions without leakage**

Map:

```text
PyJWT decode/signature/key errors -> TOKEN_SIGNATURE_REFUSED
header/shape errors               -> TOKEN_HEADER_REFUSED
JWKS typed errors                 -> preserve JWKS/KEY code
pure claim errors                 -> preserve exact typed code
unexpected defects                -> INTERNAL_ERROR
```

Never place the underlying exception string in `AuthError`, audit, stdout, logger arguments, or test snapshots.

- [ ] **Step 8: Run GREEN and prove algorithm confusion is refused**

```bash
python3 -m pytest -q \
  tests/test_business_mcp_auth_jwt_verifier.py \
  tests/test_business_mcp_auth_claims.py \
  tests/test_business_mcp_auth_jwks.py
```

Require explicit passing test names for the HS256-public-key and alternate-algorithm cases.

- [ ] **Step 9: Extend static fences and commit**

Static test requires `jwt_verifier.py` is the only production file under `integrations/business_mcp_auth` importing `jwt`.

```bash
git add \
  integrations/business_mcp_auth/jwt_verifier.py \
  tests/test_business_mcp_auth_jwt_verifier.py \
  tests/test_business_mcp_auth_static_fences.py
git commit -m "feat(auth): verify exact RS256 Business tokens"
```

---

### Task 6: Adapt accepted principals to the MCP SDK without widening authority

**Files:**
- Create: `integrations/business_mcp_auth/mcp_adapter.py`
- Create: `tests/test_business_mcp_auth_mcp_adapter.py`
- Modify: `tests/test_business_mcp_auth_static_fences.py`

**Interfaces:**
- Consumes `JwtAuthenticator`, `ResourcePolicy`, `AuthAuditSink`, `AuthAuditEvent`.
- Produces `MastermindTokenVerifier` implementing MCP 1.28.0 `TokenVerifier`.
- Produces no server, tool, route, app, or production mode.

- [ ] **Step 1: Write RED adapter tests against the pinned MCP protocol**

Use a fake authenticator returning a `VerifiedPrincipal`. Require `verify_token()` returns MCP `AccessToken` with:

```python
AccessToken(
    token=raw_token,
    client_id="mastermind-business:mastermind-steward-v1",
    scopes=["mastermind.steward.read"],
    expires_at=principal.expires_at,
    resource=principal.resource,
    subject=principal.subject_digest,
    claims={
        "iss": principal.issuer,
        "policy_id": principal.policy_id,
        "subject_digest": principal.subject_digest,
    },
)
```

The claims map is closed and contains no raw `sub`, email, name, role, token ID, app ID, workspace ID, Slack principal, or chat/session identifier.

Require a typed auth refusal returns `None` and emits one redacted `AuthAuditEvent`. Unexpected exceptions also return `None` with `internal_error`; they are not propagated across the MCP auth boundary.

- [ ] **Step 2: Add RED audit-sink tests**

Create a list-backed test sink. Require events contain exactly:

```text
schema
policy_id
code
accepted
```

No timestamp is minted inside the library, because A1 has no clock/audit-store ownership. The edge logger may timestamp its own log envelope later.

Assert raw token and raw subject do not occur in `repr(event)`, JSON serialization of event fields, or exception text.

- [ ] **Step 3: Run RED**

```bash
python3 -m pytest -q tests/test_business_mcp_auth_mcp_adapter.py
```

Expected: import failure for `mcp_adapter.py`.

- [ ] **Step 4: Implement the pinned MCP adapter**

Import only:

```python
from mcp.server.auth.provider import AccessToken, TokenVerifier
```

`MastermindTokenVerifier` receives:

```python
authenticator: JwtAuthenticator
policy: ResourcePolicy
now: Callable[[], int]
audit_sink: AuthAuditSink
```

It calls `authenticator.verify_token(token, now=now())` once. It does not retry, refresh independently, mutate policy, choose a resource, or call a backend.

On acceptance, emit `accepted=True, code="accepted"`. On refusal, emit only the typed code. Return `None` for all refusal paths so the MCP SDK enforces its normal unauthenticated response.

- [ ] **Step 5: Prove adapter isolation**

Extend static tests:

- `mcp_adapter.py` is the only `mcp` importer in the package;
- it imports no `control_plane`, GitHub, Linear, Slack, Agent OS, Executive service, filesystem, subprocess, socket, or HTTP client;
- no server or tool registration occurs at import time;
- `integrations.business_mcp_auth` root import succeeds when the MCP SDK import is blocked.

- [ ] **Step 6: Run GREEN and commit**

```bash
python3 -m pytest -q \
  tests/test_business_mcp_auth_mcp_adapter.py \
  tests/test_business_mcp_auth_metadata.py \
  tests/test_business_mcp_auth_static_fences.py
python3 -m compileall -q integrations/business_mcp_auth/mcp_adapter.py

git add \
  integrations/business_mcp_auth/mcp_adapter.py \
  tests/test_business_mcp_auth_mcp_adapter.py \
  tests/test_business_mcp_auth_static_fences.py
git commit -m "feat(auth): adapt Business principals to MCP verifier"
```

---

### Task 7: Prove the complete hermetic resource-server authorization chain

**Files:**
- Create: `tests/test_business_mcp_auth_integration.py`
- Modify: `tests/test_business_mcp_auth_static_fences.py`

**Interfaces:**
- Consumes all A1 production modules.
- Produces no additional production interface.
- Proves one signed token can traverse policy -> JWKS -> signature -> claims -> MCP `AccessToken`, and hostile/cross-resource tokens fail closed.

- [ ] **Step 1: Build three exact app policies in the test**

Create policies for:

```text
mastermind-steward-v1
  resource = https://mcp.example.test/mcp/steward/v1
  scopes   = mastermind.steward.read

mastermind-executive-v1
  resource = https://mcp.example.test/mcp/executive/v1
  scopes   = mastermind.executive.read, mastermind.executive.intent.submit

mastermind-dialogue-v1
  resource = https://mcp.example.test/mcp/dialogue/v1
  scopes   = mastermind.dialogue.read, mastermind.dialogue.write
```

All use the same fixture issuer but independent `ResourcePolicy` objects and exact resource metadata URLs.

- [ ] **Step 2: Prove the positive Steward chain**

Generate one ephemeral RSA key/JWKS and one signed Steward token. Compose:

```python
cache = BoundedJwksCache(policy=steward, fetcher=fake, monotonic=clock.monotonic)
authenticator = JwtAuthenticator(policy=steward, jwks=cache)
verifier = MastermindTokenVerifier(
    authenticator=authenticator,
    policy=steward,
    now=clock.now,
    audit_sink=sink,
)
access = await verifier.verify_token(token)
```

Require exact accepted `AccessToken`, one JWKS fetch, one accepted audit event, and no raw subject/token in audit material.

- [ ] **Step 3: Prove cross-resource isolation**

Pass the valid Steward token to Executive and Dialogue verifiers. Both return `None`, each emits `resource_refused`, and neither calls any Executive/Dialogue backend because no backend exists in A1.

Sign an Executive token lacking `mastermind.executive.intent.submit`; require `scope_refused`.

- [ ] **Step 4: Prove subject isolation and account rollover behavior**

A correctly signed token for another subject returns `None`. Changing the installed allowed subject digest in a new policy permits the new subject only in a newly constructed verifier; no mutable user database or live in-process grant update exists.

- [ ] **Step 5: Prove key rotation behavior**

Use JWKS generation 1 with `kid-a`, then generation 2 with `kid-b`:

- existing `kid-a` token verifies while cache is fresh;
- first `kid-b` token triggers one refresh and verifies;
- removed `kid-a` is refused after TTL/refresh;
- a fetch failure after TTL refuses both rather than silently extending stale trust.

- [ ] **Step 6: Prove process restart behavior**

Construct a new cache/verifier object. Require it fetches JWKS anew and has no remembered token, subject, session, or prior audit state.

- [ ] **Step 7: Prove ChatGPT linking metadata completeness**

For every app policy require:

```text
protected resource metadata has exact resource/issuer/scopes
HTTP challenge points to exact metadata URL
per-tool oauth2 securitySchemes name exact scopes
MCP auth error has _meta["mcp/www_authenticate"]
```

No test claims the actual ChatGPT linking UI appeared; that belongs to C1/C2.

- [ ] **Step 8: Run full A1 GREEN**

```bash
python3 -m pytest -q \
  tests/test_business_mcp_auth_contracts.py \
  tests/test_business_mcp_auth_metadata.py \
  tests/test_business_mcp_auth_claims.py \
  tests/test_business_mcp_auth_jwks.py \
  tests/test_business_mcp_auth_jwt_verifier.py \
  tests/test_business_mcp_auth_mcp_adapter.py \
  tests/test_business_mcp_auth_integration.py \
  tests/test_business_mcp_auth_static_fences.py
```

Expected: zero failures. Record exact test count and elapsed time from the real run; do not write an expected count into source.

- [ ] **Step 9: Commit Task 7**

```bash
git add \
  tests/test_business_mcp_auth_integration.py \
  tests/test_business_mcp_auth_static_fences.py
git commit -m "test(auth): prove isolated Business OAuth chain"
```

---

### Task 8: Adversarial review, hosted proof, and production-inert release carrier

**Files:**
- Modify only defects found in the exact A1 files above.
- No new product/runtime/config path is permitted during closeout.

**Interfaces:**
- Consumes exact implementation head and all A1 tests.
- Produces one draft/hold PR with immutable head, hosted proof, security review, and continuation handoff to S1/E1/U1.

- [ ] **Step 1: Run the exact changed-path census**

```bash
git fetch origin master
BASE=$(git merge-base origin/master HEAD)
printf 'merge_base=%s\n' "$BASE"
git diff --name-only "$BASE"...HEAD
```

Expected changed paths are only:

```text
pyproject.toml
integrations/business_mcp_auth/**
tests/test_business_mcp_auth_*.py
```

If protected `master` moved after pickup, history-preservingly reconcile the same branch, rerun every affected test, and recompute the census. Do not reset, rebase, force-push, or reuse stale green proof.

- [ ] **Step 2: Run static secret and authority scans**

```bash
python3 - <<'PY'
from pathlib import Path
roots = [Path('integrations/business_mcp_auth'), Path('tests')]
text = '\n'.join(
    p.read_text(encoding='utf-8')
    for root in roots
    for p in root.rglob('test_business_mcp_auth_*.py' if root.name == 'tests' else '*.py')
)
for marker in (
    'BEGIN PRIVATE KEY',
    'xoxb-',
    'ghp_',
    'sk-',
    'client_secret=',
    'access_token=',
    'refresh_token=',
):
    assert marker not in text, marker
print('AUTH_SECRET_SCAN_PASS')
PY
```

Test-only key generation code is allowed; serialized private-key material is not.

- [ ] **Step 3: Run full focused and adjacent MCP regressions**

```bash
python3 -m pytest -q tests/test_business_mcp_auth_*.py
python3 -m pytest -q \
  tests/test_executive_mcp.py \
  tests/test_mastermind_secretary_mcp.py \
  tests/test_mastermind_company_mcp.py
python3 -m compileall -q integrations/business_mcp_auth
python3 -m pytest -q tests/test_check_script_import_pinning.py

git diff --check
```

If an adjacent file name changed on current protected source, use the exact current test files owning Executive, Secretary, and Company MCP contracts; record the replacement names in the PR body.

- [ ] **Step 4: Perform independent security review on the immutable head**

Reviewer checklist:

```text
no token-selected URL
no mixed algorithms
no raw identity/log leakage
no stale-key acceptance after TTL
one unknown-kid refresh only
exact resource and scope isolation
subject digest does not replace signature verification
per-tool auth metadata present
pure/edge dependency split intact
no auth server or user/session database
no control-plane import
no backend action in A1
no production config or credential
```

Any material defect returns to the same branch for repair and fresh proof. Review text alone does not authorize merge.

- [ ] **Step 5: Push one canonical branch and open one DRAFT/HOLD PR**

PR body includes:

```text
operation key
protected pickup SHA and current reconciliation SHA
exact plan/spec paths
exact dependency pins
exact changed-file census
RED receipt
focused GREEN receipt
adjacent regression receipt
CodeQL/security check state
known platform assumptions
capability = BUILT_NOT_PROVEN / PRODUCTION_INERT
```

Do not label the PR “production auth,” “connected,” “installed,” or “live.”

- [ ] **Step 6: Obtain fresh hosted exact-head proof**

Require repository `test` and all configured security analyses on the exact immutable head. Cancelled/skipped/older checks are not proof. If a hosted infrastructure failure occurs, classify it before rerun; do not alter implementation merely to make an unrelated runner problem disappear.

- [ ] **Step 7: Stop before production enrollment**

A1 completion means:

```text
one reviewed resource-server library can validate hermetic RS256 tokens
three separate app policies are representable and cross-resource reuse is refused
MCP 1.28 TokenVerifier adaptation is proven
resource metadata / challenge / securitySchemes are generated exactly
no auth server, IdP tenant, app, tunnel, host principal, secret, or Business connection exists
```

BSC-S1 and BSC-E1 may consume the library only after A1 is protected and their own dependencies/collision gates clear. BSC-U1 owns real IdP/client/app/tunnel enrollment.

## Stop Condition

BSC-A1 stops at `BUILT_NOT_PROVEN / PRODUCTION_INERT` when the exact A1 code and tests are protected, the resource-server contract passes the full adversarial matrix, the pure/edge dependency boundary is proven, and no production identity or app effect exists. A real ChatGPT Business OAuth link remains `NOT_BUILT` until BSC-U1/C1/C2.

# GBL-3 lane note — the MCP edge and admission

Branch `t3/mmos-v4-gbl`, lane GBL-3 (BUILD_PLAN row GBL-3; ADDENDUM §4b).
Files owned here, as sole writer: `integrations/gbl/mcp_server.py`,
`integrations/gbl/admission.py`, `tests/test_gbl_mcp_server.py`,
`tests/test_gbl_admission.py`, this note.

The two required answers, copied from the prep evidence (not re-researched):

## (a) The token flow — pre-registered client, PKCE unknown

Source: `~/.mastermind/mmos_evidence/gbl-20261111/gbl3-prep.md` §(a) and
§(a-cont) (read-only research, 2026-11-11; mirrored in the deputy brief
`~/.mastermind/mmos_evidence/deputy/briefs/gbl3-inputs.md`).

- Grok's connector uses a **pre-registered OAuth client**: the connector form
  takes a manually entered OAuth Client ID, and a Client Secret field appears
  once one is entered; tokens are held on the vendor's connector backend and
  the bot never receives them. No dynamic client registration (RFC 7591) is
  performed by the connector.
- **PKCE: unknown**; discovery behavior: unknown (vendor docs silent on both).
  The MCP spec says clients MUST implement PKCE, but whether Grok's connector
  backend follows it is undocumented. Therefore our side must serve RFC 9728
  protected-resource metadata and the `WWW-Authenticate` challenge (the
  discovery entry points), and must work **with or without PKCE** — PKCE is
  the external authorization server's concern, never ours (we host no
  authorize/token endpoints; `business_mcp_auth` requires exactly one AS
  equal to the issuer).
- **Our sign-in check: serves-with-config.** The verifier, audience law
  (`claims.py:167-169`), scope law and JWKS are reused as they are; what is
  missing is wiring (the HTTP edge serving the metadata endpoints — this
  lane's `mcp_server.py`), plus configuration (the OAuth client at the
  external AS, and the principal's `sub` digest enrolled in the policy's
  `allowed_subject_digests` and this lane's admission table).
- The **API-key / static-header connector variant is NOT served**: a non-JWT
  static token has no 3-segment compact form (`jwt_verifier.py:159-164`);
  the edge refuses it with a typed error. Tested here.

## (b) Tunnel census (names only)

Source: `gbl3-prep.md` §(b). Nothing was started or contacted by this lane.

- **cloudflared** — present (2026.9.1, `/opt/homebrew/bin/cloudflared`).
- **tailscale** — present (1.102.4, plus Tailscale.app and its 2 launchd
  jobs, not ours).
- **ngrok** — absent.

No tunnel, hostname or OAuth client is created by this lane.

## How "audience `mastermind.gbl.bridge`" is realized

`business_mcp_auth` is imported as it is, never edited. Its audience law
requires `aud == policy.resource` EXACTLY (`claims.py:167-169`) and
`policy.resource` must be an HTTPS URL (RFC 9728 resource; `contracts.py`
`load_resource_policy`). ARCHITECTURE.md §3 says "exact scope
`mastermind.gbl.bridge`" — so the edge configures:

- `required_scopes = ("mastermind.gbl.bridge",)` — the token MUST carry
  exactly this scope (no extra grants beyond `offline_access`);
- `aud = policy.resource` — the edge's HTTPS resource URL (in production the
  tunnel-facing URL; in tests a fixture `.invalid` URL).

A wrong scope refuses with `scope_refused` (403 + `insufficient_scope`
challenge); a wrong audience refuses with `resource_refused` (401). Both
before any dispatch. This is the package's own law applied, not a
workaround; the flow serves as configured (`auth=serves-with-config`).

## The edge (mcp_server.py)

- Static census of EXACTLY five tools — `team.delegate`, `team.result`,
  `team.question`, `team.answer`, `team.message` — from a frozen ToolSpec
  table; `tool_schema_digest()` over the canonical snapshot, pinned by the
  literal `TOOL_SCHEMA_DIGEST` (any schema change must update the literal and
  is visible in review — the incumbent company-MCP digest law). No dynamic
  registration: the lowlevel Server exposes only `list_tools`/`call_tool`,
  and dispatch refuses any name outside the census (`TOOL_NOT_AVAILABLE`).
- Admission is by token only: the ASGI gate extracts the single
  Authorization header, `JwtAuthenticator.verify_authorization_header`
  enforces the whole imported law (RS256, canonical segments, header, life,
  issuer, audience, scope, subject digests), and a typed refusal answers
  401/403 with the `WWW-Authenticate: Bearer resource_metadata="..."`
  challenge built by `metadata.py`'s public helpers (`www_authenticate` via
  `mcp_auth_error_result`). Source address, headers other than the bearer
  Authorization, and API keys are never admission.
- Tool mapping onto the GBL-2 bridge (Unix socket, `mastermind.gbl.request.v1`
  frames via the GBL-1 codec):
  - `team.delegate {target,title,body,idempotency_key}` → op `ask`
    (kind `delegate`);
  - `team.question {ask_id}` → op `question`;
  - `team.answer {ask_id,text,idempotency_key}` → op `answer`;
  - `team.result {ask_id}` → op `result`;
  - `team.message {environment_id,thread_ref,body,idempotency_key}` →
    `message_send.MessageSender` (edge-side; GBL-2's bridge has no message
    op) after the per-thread allowlist gate.
- The verified principal's `subject_digest` is the ONLY identity input; the
  admission row supplies the bridge-side `principal` label. Tool arguments
  carry no identity/admission fields (closed key sets — a smuggled
  `principal`/`targets`/ceiling/allowlist argument is `INVALID_ARGUMENTS`,
  and the bridge never receives caller-chosen identity).
- Oversized payloads: canonical tool arguments are capped at the GBL frame
  cap (`gbl_contract.MAX_FRAME_BYTES`, 32 KiB) before any bridge/send call —
  typed `FRAME_TOO_LARGE`.

## admission.py

Fixed order (the lane law): **principal → targets → kinds → rates →
per-thread allowlist**, as pure typed functions over an immutable table:

- `PrincipalAdmission(subject_digest, principal, targets, kinds,
  max_asks_per_hour, message_allowlist=())` — `subject_digest` is the
  verified principal's digest; `principal` is the bridge-side label.
- `admit_principal` (`ADMISSION_EMPTY` / `PRINCIPAL_NOT_ADMITTED`),
  `admit_target` (`TARGET_NOT_ALLOWED`), `admit_kind` (`KIND_NOT_ALLOWED`,
  kinds ⊆ the contract's v1 kinds), `admit_rate` (`RATE_LIMITED`, ceiling ≤
  `MAX_ASKS_PER_HOUR_PER_PRINCIPAL`), `admit_message_thread`
  (`ALLOWLIST_EMPTY` / `THREAD_NOT_ALLOWED`, via the GBL-1
  `check_thread_allowlist`).
- The table **ships EMPTY** — every caller is refused until the principal's
  act adds a row. Rate counting is the bridge's (it owns the store); the
  edge calls `admit_rate` with a count provider (default 0) so the table's
  ceiling is enforced at the door and the bridge re-enforces it
  authoritatively on every create.

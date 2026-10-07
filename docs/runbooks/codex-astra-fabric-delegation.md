# Codex Astra → Executive Fabric delegation runbook

**Capability:** Astra external Fabric delegation, first closed vertical  
**Current source law:** protected PR #618 plus current protected Mastermind source  
**Authority:** client composition only; Executive Runtime/COO/Capacity remain lifecycle and placement owners

## Outcome

Use an Executive-owned Astra/Codex parent as the scarce reasoning principal while bounded research,
implementation, tests, repair, and independent review flow through the existing five-tool Executive
MCP and existing Executive/COO/Capacity worker fabric. The path must not create another dispatcher,
auth authority, provider selector, result bus, retry journal, or transcript store.

A successful connection is not end-to-end acceptance. Completion still requires one qualified external
worker, canonical review/result evidence, return to the exact parent, final Astra acceptance, and the
frozen token-economics comparison.

## 1. Fresh source and client preflight

1. Pin protected Mastermind `master`, load the compatible Sol Skillpack from that same SHA, and compare
   any protected movement against this client surface and its Executive/auth dependencies.
2. Require **Codex CLI 0.154.0 or newer** for this installed path. This host was qualified on 0.154.0.
   Install the reviewed `ops/codex_fabric/mastermind-astra.config.toml` as
   `$CODEX_HOME/mastermind-astra.config.toml` and launch attended project-delivery parents with
   `codex -p mastermind-astra`. The profile selects `gpt-6-astra`, keeps native agents disabled by
   default, and leaves the repository worker-attested `.codex/config.toml` unchanged.
3. Read the installed non-secret Executive MCP installation coordinate. The current qualified client
   registration name is `mastermind-executive`, using the installed loopback `/mcp` endpoint.
4. Run the repository registration helper and require an enabled Streamable HTTP registration with the
   exact installed URL. A conflicting existing registration is a refusal, not permission to overwrite.
5. Start a fresh Astra/Codex process after any registration/auth change before claiming its live MCP
   tool census changed.

## 2. Authentication: current installed-path law

The installed Executive resource server is still the canonical Auth0 verifier. Its issuer, resource,
required scopes, subject allowlist, JWT verification, and audit path are not changed by this client.
Client credentials live in **macOS Keychain** and are supplied at connection time by Codex's
`http_headers_helper`; access/refresh tokens must not be written to repository source, Codex TOML,
argv, ambient environment, prompts, Agent OS, or logs.

For the current reviewed canary, the Codex override key is
`mcp_servers.mastermind-executive.http_headers_helper`. The qualified host interpreter is
`/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/bin/python3.14`.
Run the helper module from the reviewed repository/worktree **working directory** (or through the
canonical launcher that pins that working directory) so `ops.codex_fabric.executive_mcp_auth` resolves
from the reviewed source. These are host-specific canary coordinates, not permission to copy a helper
command into an unrelated checkout or silently rewrite the user's global Codex configuration.

Do **not** use `codex mcp login mastermind-executive` as the login path for this installation. It was
serviceability-tested against Codex 0.154.0 and refused with a **resource identity mismatch**: the
transport is loopback while the Executive OAuth resource identity is the existing Secure MCP Tunnel
resource. `--oauth-resource` did not remove that protected-resource identity check. Do not weaken the
server resource policy or copy ChatGPT's user credential to make native login pass.

The client-side enrollment path uses the same Auth0 issuer/resource with a public DCR client and
authorization-code + PKCE. The authorization request uses the exact Executive audience, the exact
`mastermind.executive.intent.submit` + `mastermind.executive.read` authority scopes, and
`offline_access` for refresh continuity. It **must not request `openid`**. The DCR client identity is
stored and reused; do not create a new Auth0 application on each login.

## 3. DCR effect-unknown law — current live blocker

The first live DCR attempt for the pre-fingerprint client name **Mastermind Codex Astra** reached the DCR
HTTP effect boundary but returned no usable response to the client. The same Keychain registration item
contains the legacy pending marker. Current state is **DCR_EFFECT_UNKNOWN**.

While `DCR_EFFECT_UNKNOWN` is present:

- the client **must not retry** `/oidc/register`;
- it **must not delete the pending registration marker** merely to make another attempt possible;
- it must not create a differently named client or use another carrier as failover;
- user OAuth/PKCE cannot proceed because a verified client id is not yet available.

Read the local non-secret reconciliation coordinates before using an authorized tenant-admin surface:

```bash
python3 -m ops.codex_fabric.enroll_executive_mcp --pending-status
```

The status receipt contains only the pending `attempt_ref`, exact client name when one was precommitted,
callback, installed-policy digest, `state=effect_unknown`, and whether the marker is reconcilable. It does
not make a DCR call, exchange a token, or expose a credential. A legacy **pre-fingerprint** marker reports
`reconcilable=false` and `client_name=null`; it remains blocked until authoritative tenant evidence
resolves the original effect. Do not guess a name, clear the marker, or issue a replacement attempt.
The reviewed absence path requires the same stored `attempt_ref`, callback and policy digest, the
marker creation time, a bounded local-outcome upper bound, a fully paginated authoritative tenant audit
whose retained window covers that whole interval, and zero current-client, Create-a-client and DCR
matches. Only then may the same Keychain item be advanced with:

```bash
python3 -m ops.codex_fabric.enroll_executive_mcp \
  --legacy-absence-reconcile \
  --reconcile-attempt-ref "$PENDING_ATTEMPT_REF" \
  --reconcile-redirect-uri "$PENDING_CALLBACK" \
  --reconcile-policy-digest "$PENDING_POLICY_DIGEST" \
  --absence-marker-created-at-epoch "$MARKER_CREATED_AT" \
  --absence-attempt-outcome-by-epoch "$LOCAL_OUTCOME_BY" \
  --absence-audit-start-epoch "$AUDIT_START" \
  --absence-audit-end-epoch "$AUDIT_END" \
  --absence-audit-events-total "$AUDIT_EVENTS" \
  --absence-audit-pages-total "$AUDIT_PAGES" \
  --absence-audit-pagination-complete \
  --absence-audit-retention-complete \
  --absence-marker-metadata-digest "$MARKER_METADATA_SHA256" \
  --absence-audit-receipt-digest "$AUDIT_RECEIPT_SHA256" \
  --absence-inventory-receipt-digest "$INVENTORY_RECEIPT_SHA256" \
  --absence-local-outcome-evidence-digest "$LOCAL_OUTCOME_EVIDENCE_SHA256" \
  --absence-current-client-match-count 0 \
  --absence-create-client-match-count 0 \
  --absence-dcr-match-count 0 \
  --absence-deleted-tpc-match-count 0 \
  --reconcile-observed-at-epoch "$OBSERVED_AT"
```

This performs no Auth0 request. It preserves the same `attempt_ref`, derives the fingerprinted client
name from that identity, requires immutable SHA-256 evidence digests for the Keychain metadata, tenant
audit, current application inventory, and local-outcome bound, records only the aggregate absence digest
in the existing Keychain item, and makes `--pending-status` report `state=absence_reconciled`.

For a newly admitted attempt, source precommits the exact client name as
`Mastermind Codex Astra <first-16-attempt-ref-characters>`. Only when `--pending-status` reports
`reconcilable=true` may an authorized tenant administrator inspect Applications for that exact
fingerprinted name and callback `http://127.0.0.1:8769/oauth/callback`. If one exact matching client
exists, recover its public `tpc_` client id and reconcile all three operation-bound values together:

```bash
python3 -m ops.codex_fabric.enroll_executive_mcp \
  --reconcile-client-id "$PUBLIC_TPC_CLIENT_ID" \
  --reconcile-attempt-ref "$PENDING_ATTEMPT_REF" \
  --reconcile-client-name "$PENDING_CLIENT_NAME"
```

The client id and pending coordinates are public metadata; the command stores only the exact reconciled
public client identity and prints a digest-only receipt. It performs no DCR call and no token exchange.
A duplicate, stale, differently named, differently callback-bound, or otherwise ambiguous tenant
observation stays blocked.

When the separately reviewed authoritative tenant audit instead proves absence and `--pending-status`
reports `state=absence_reconciled`, one explicit same-operation resume is available:

```bash
python3 -m ops.codex_fabric.enroll_executive_mcp --resume-legacy-after-absence
```

The resume writes the fingerprinted v2 pending marker with the same `attempt_ref` **before the retry POST**,
then performs one same-operation DCR request. A lost/invalid response therefore returns to
`effect_unknown` with a reconcilable exact name and cannot be posted twice by another resume call. A
successful response replaces the same Keychain item with the completed public client registration.
A definitive Auth0 registration refusal writes `state=definitive_refusal` into that same Keychain item
and consumes the resume opportunity; another `--resume-legacy-after-absence` is refused rather than
issuing another POST.

For the historical legacy operation, later read-only tenant-admin evidence established a fully paginated
retained audit window spanning 2026-09-13T19:28:09.807Z through 2026-09-17T23:20:36.881Z (236
events / 5 pages), with seven `Create a client` events and zero exact `Mastermind Codex Astra` or DCR
matches. The current Applications census also had zero exact matching client. The same Keychain item was
created and last modified at 2026-09-14T18:26:28Z, and Git commit
`33e94cb567188604a914d27bb58af38f7345bad4` (`feat: reconcile ambiguous Executive DCR client`)
at 2026-09-14T18:47:45Z provides a source-side upper bound showing the ambiguous local attempt had
already returned by then. These are non-secret reconciliation coordinates; the stored tenant receipts
remain the evidence owner. No token or secret belongs in this runbook or chat.

## 4. Connection proof after enrollment

After the DCR state is reconciled and PKCE enrollment succeeds:

1. verify the Keychain-backed helper returns an Authorization header to Codex without emitting the
   refresh token or credential document;
2. start a fresh Codex/Astra process with the reviewed `http_headers_helper` override/profile;
3. require exactly the existing Executive tool surface: `executive_state`, `executive_inbox`,
   `executive_job`, `ceo_intent_status`, and `submit_ceo_intent`;
4. prove a read traverses the authenticated installed MCP before any modifying canary;
5. preserve server-side authorization as authoritative even if client-side JWT continuity checks pass.

A saved registration, `auth_status`, or helper configuration alone is not proof of an authenticated
MCP call.

## 5. Exact Astra parent qualification

A **manually opened arbitrary Codex tab** may prove connectivity but is not accepted parent-return
proof. End-to-end completion requires the Astra orchestrator to be the **exact current RuntimeBinding**
for the current Executive-owned Codex operator, including its exact **process generation** and exact
**provider-native handle**.

Wake/return must refuse a stale, neighboring, newest, or human-title-matched Codex session. If the
exact parent cannot be resolved, keep the result durable/unconsumed and classify the journey partial;
do not invent latest-tab routing or make the model poll for completion.

### Current Executive-parent compatibility hold

The named `mastermind-astra` profile above is an attended/manual client profile; it is not evidence
that the current Executive-owned operator is already an Astra generation. On the 2026-09-24 Studio
observation, the exact installed Executive provider binary remained Codex **0.147.0** and its
`debug models` catalog did **not** expose `gpt-6-astra`. The separately installed attended Codex
0.154.0/0.156.1 clients did expose that slug.

Therefore this PR must not rewrite the existing Executive `frontier.orchestrator` alias to Astra or
claim exact-parent Astra proof from profile presence. Production cutover requires the existing
provider/binary-attestation owner to install and attest one reviewed Astra-capable Codex generation,
prove `gpt-6-astra` with a real served-model canary under that exact generation, and only then move
the existing routing/profile authority through its normal reviewed path.

## 6. External worker lane

Astra never chooses the provider, account, provider home, endpoint, host, or worker identity.
**Capacity owns provider/account/host placement** and the subscription provider-realm owner supplies
its own enrollment receipt.

The first preferred external canary binding is
`alibaba-token-plan-personal.codex-responses`. Protected source currently labels this lane
**BUILT_NOT_PROVEN** with `autonomous_allowed=false`; that is intentional. The interactive canary path
requires owner-minted provider-realm enrollment and Capacity-available facts. Its activation gates are
not replaced by prompt text, and a merged implementation does not make the lane autonomous.

The current binding's canary gates remain: adapter implemented, provider realm enrolled, capacity
known, usage policy satisfied, and real canary passed. The first canary is how the final gate becomes
evidence; do not set `autonomous_allowed=true` to skip it.

Current live-host observation is more conservative than protected source: the Executive config directory
still exposes only the existing `worker-codex[-pro-*].json` generation and no installed subscription/v5
worker config carrying `harness_binding_id`. The source enrollment CLI requires exactly that reviewed v5
config before it can verify or enroll a subscription credential. Therefore the Alibaba lane is currently
**protected-source-ready but not installed/enrolled/production-ready** on this host. Installing/admitting
that lane is a separate host ceremony; do not infer it from #583 being merged.

## 7. Submission and effect semantics

Once authenticated MCP, exact parent binding, and one external interactive-canary lane are all
qualified, Astra authors only the bounded business objective/profile and acceptance constraints and
calls `submit_ceo_intent`. A normal accepted receipt keeps `dispatched=false`; later COO/Runtime
delivery is a separate transition.

One modifying operation keeps one `operation_key` and derived `request_ref`. If submission or any
worker effect is `effect_unknown`, reconcile the **same request_ref** / same canonical effect identity.
Do not mint a new operation, switch provider, switch to an internal agent, or re-submit because a client
request timed out.

The reviewed `mastermind-astra` client profile keeps native Codex agents disabled by default.
If current Fabric serviceability/capability cannot meet the job **before any effect begins** and a native
fallback is explicitly admitted, enable it only for that bounded invocation, with a ceiling of one
Sol/high child and a recorded fallback reason. Luna and Terra are not normal project-delivery
sub-orchestrators. The repository `.codex/config.toml` remains the independently audited
worker/portfolio configuration; it is not the attended Astra parent profile.

## 8. Production-proof sequence

The first accepted vertical requires all of the following, separately evidenced:

1. authenticated five-tool MCP read from a fresh Astra process;
2. exact Executive-owned Astra RuntimeBinding/process-generation/native-handle proof from an
   attested Astra-capable Codex generation with a real `gpt-6-astra` served-model canary;
3. sealed external subscription-canary admission from current provider-realm + Capacity facts;
4. one substantive external worker execution;
5. independent review and any bounded repair/re-review through existing owners;
6. compact canonical result returned to the exact Astra parent;
7. final Astra acceptance;
8. a comparable Codex-heavy baseline and external-Fabric run showing at least 50% lower Astra +
   internal-Codex usage using one common measured unit/proxy;
9. zero routine Chairman account selection or message shuttling between admission and returned result;
10. negative duplicate/restart/effect-unknown proofs creating no duplicate Job or provider attempt.

Until those are all true, report the precise state (`BUILT_NOT_PROVEN`, `PARTIAL`, blocker, or other
canonical vocabulary) rather than calling the program production-proven.

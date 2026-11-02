# Mastermind OS public launch composition

This is installation guidance for the existing OS → Executive command path.
Source tests do not establish an installed launch or permission to widen a grant.
Keep the existing Workspace, Content, Executive, Studio, Git and Runtime owners.

## Publication before admission

An OS launch key is the SHA-256-derived "mmos-launch-<40hex>" of the authenticated
principal namespace and the exact form. Backend normalization adds defaults, so
publication validates the form under the canonical five-tool law but preserves
its original semantic fields for the key. The inner submit uses normalized
arguments and the same key.

The App forwards the original bearer and original arguments to one installed
loopback Studio port, fixed route /os-internal/commission/prepare. Studio
independently authenticates through JwtAuthenticator and the audited
MastermindTokenVerifier, then matches a separately root-installed principal/form
grant. The OS bearer is never admitted to generic Studio MCP tools.

For a fresh operation the incumbent mmx-workspace owner acquires the fixed
sol/web-<operation_key> workspace. A descriptor-bound writer exclusively creates
research/executive_commissions/COMMISSION.md; the incumbent Git publisher commits
only that file and pushes once. It qualifies exact local/remote head and committed
content hash before returning "prepared". Existing/partial operations are
read-only reconciliation; uncertain effects never trigger another write or push.
Executive then re-verifies the bearer and performs the existing submit once.
GitHubWebCommissionSourceProvider re-observes the published source before Job
admission. No publication registry or alternate command/lifecycle queue is added.

The browser reserves its principal-scoped persistent pointer before the HTTP
effect. Reopen reads original intent status. It does not publish or submit again.
Unknown publication/admission retains the original pointer for reconciliation.

## Root-sealed Studio opt-in

Use the existing private Studio lifecycle and an existing qualified account/port.
The fixed root-owned, non-writable configuration is:

/Library/Application Support/MastermindExecutive/config/os-commission-publication.json

Its exact fields are:

- schema: mastermind.os_commission_publication.v1.
- release_sha: exact installed reviewed Mastermind source, 40 lowercase hex.
- studio_uid, studio_account, studio_port: actual bound Studio service identity.
- base_sha: reviewed source commit for canonical workspace acquisition.
- policy: complete canonical serialized ResourcePolicy, including defaults,
  for resource https://mcp.mastermind-x.com/os/executive, RS256, and exactly the
  sorted scopes mastermind.executive.intent.submit, mastermind.executive.read.
  Preserve actual verified subject grants; never invent client/subject receipts.
- grants: 1–16 objects containing exactly principal_scope and template.
  principal_scope comes from verified OS context for the intended client and
  subject. template contains exact workstream, department, priority,
  execution_profile and any actually emitted optional allowed_write_paths,
  validation, attempt_limit. Objective and operation key are not template fields.
- audit_directory:
  /Library/Application Support/MastermindExecutive/audit/os-commission-publication.
  Provision its existing durable auth sink access for the actual Studio identity.
- auth_helper_sha256, file_helper_sha256: hashes of the installed release's
  ops/executive_os/os_commission_auth_entry.py and
  integrations/studio_direct_mcp/commission_file.py.

Serialize policy from dataclasses.asdict(load_resource_policy(value)), preserving
all fields. The service compares its canonical policy digest with the verified
helper projection. The helper uses the incumbent Executive gateway's sealed network
runtime, not a system Python without JWT dependencies.

With the private service stopped, use its existing stage/upgrade operation with
--enable-repository-workspaces --os-commission-config-sha256 <exact-file-sha256>
and established account/source/node/backend/port arguments. No model-selected
config path is accepted. Seal dependencies and start through the same lifecycle.
Legacy installs remain off; an enabled prior setting is preserved only when its
manifest/config hashes still match. All staged modules are included in the manifest.

In the existing Executive MCP config, enable only web_ceo_v3 with
os_executive_transport: true, os_executive_resource equal to the exact resource
above, and os_commission_port equal to the opted-in private Studio port.
Existing connector resource variants remain intact. Do not enable OS transport
without its publication owner or bypass source custody with App-side Git.

## Public edge

Use the incumbent VPS Caddy and Chisel server, currently reached through
https://146-190-142-17.sslip.io. The candidate os_tunnel_entry.py consumes only:

- fixed config .../config/os-public-tunnel.json, with schema
  mastermind.os_public_tunnel.v1, exact binary_sha256, independently verified
  server_fingerprint, and one integer relay_port in 49152–50200;
- fixed root-private credential .../config/os-public-tunnel.auth, dedicated
  mastermind-os:<secret> from the authorized server-side exact-port grant;
- root-sealed binary .../transports/chisel/<binary_sha256>/chisel.

The transport owner must grant only the selected reverse listener on the existing
server. Do not copy an existing broad travel credential. Run the immutable wrapper
with the existing qualified Python and -I -B under a root-owned launchd transport
definition; credentials never belong in its plist/argv. It supplies Chisel's supported
AUTH environment variable and exact reverse argument
R:127.0.0.1:<relay_port>:127.0.0.1:8443. TLS verification and the independently
observed Chisel fingerprint remain enabled. The wrapper neither generates a
credential nor installs/reloads a service.

Build the actual OS assets with real public client/config values. Stage Caddy using
"python -m ops.executive_os.os_public_edge --source <build-dir> --relay-port <port>
--out <new-candidate-file>". The renderer verifies the asset manifest against actual
files. Its fixed template allows only OS assets, callback, canonical Workspace GETs
and the exact three incumbent Executive POSTs plus three session READ-only
POSTs (session/context, session/reply, session/references); session/send remains
closed at the public edge under the held F2 pre-network authorization review.
The existing transition planner accepts only the previously sealed three-path
POST set or the exact six-path read-expanded set, and stages the latter without
loading Caddy. It bounds request bodies, removes spoofable forwarding
headers and fixes the upstream authority. Validate and qualify routing before the
existing Caddy owner loads the candidate.

The intended DNS A record is mcp.mastermind-x.com → 146.190.142.17.
Do not claim DNS/certificate/routing readiness from rendered configuration.

## Auth0, view providers and installed acceptance

Use distinct verified SPA/native public clients in the existing tenant
dev-eo0jf8us5mup7wd5.us.auth0.com, PKCE S256 and the exact OS audience.
The web callback is https://mcp.mastermind-x.com/os/auth/callback;
the native callback is com.mastermind.os://oauth/callback. Reconcile existing
registrations before creating clients; unknown prior registration effects are
not permission to recreate/delete one. No offline refresh scope is needed.

Supply actual immutable VITE_MM_LAUNCH_CONFIG matching installed publication
templates. The UI's project ref maps to department, profile ref to execution_profile;
optional fields must match what the form emits. Workspace and Content views retain
their own existing auth/policy/binding owners. Use workspace_owner_enrollment.py
with real client, subject and permission receipts; a working Executive token is
not automatically Workspace authority.

Installed acceptance is separate from source tests:

1. Verify exact release/config/runtime hashes, live authenticated OS context and
   real Workspace/Content view providers.
2. Capture the original persisted pointer for one authorized LAUNCH.
3. Prove exact remote commission head/hash, one strict-v2 Job, original work_ref
   and accepted result through existing Runtime.
4. Lose the launch response, reopen the app, and resolve that same original
   pointer with status only. Prove no second publication, submit or Job.
5. Save exact source head, nonsecret receipts, test/build results and remaining
   installed gates on the same product PR. JOB-013 is unrelated acceptance
   evidence and must not become an app pointer.

## R2 historical original-answer installed-browser qualification (held until release)

This is the acceptance path for the existing #1473 Runtime original-reference
producer and #1542 Web Office historical-answer consumer. It is **not** a source
test, a fixture-created Job, native-parent consumption, or permission to install.
Run it only against an exact independently reviewed, protected, actually
installed source after the F2 READ-only-token pre-network effectful-SEND review
has been resolved and the original issuer's EFFECT_UNKNOWN operation remains
fenced. Do not repair F2 through an alternate carrier or grant.

### Preconditions that must be proved, not assumed

1. Retain the immutable installed Runtime/Office source SHA(s), release manifest
   digest, active Executive process path/configuration revision, and actual edge
   Caddy readback. A CI-green or mergeable PR is insufficient. The installed
   Runtime must contain `integrations/session_bridge/reference_tools.py`,
   the authenticated private `session_reply_references` tool, and the
   `POST /os/executive/session/references` leaf. The public edge admits the
   exact three incumbent Executive endpoints plus the three new READ-only
   `session/context`, `session/reply` and `session/references` paths.
   Its `session/send` route remains excluded until separately authorized.
2. Use the **existing** signed-in Web Office principal, configured Executive
   OAuth resource and verified browser selection. Retain only nonsecret policy,
   subject/client digest and auth-generation attestations; never copy, print,
   record to HAR, or paste bearer tokens, Auth0 codes, cookies or JWT bodies.
   A credential-less app build, mock transport or native Tauri test is not
   the installed Web Office journey.
3. Identify two already authorized, distinct **original** operations A and B
   under the same verified selection and principal. A has a canonical native
   committed reply; B is independently pending. Do not manufacture another
   SEND, ACK, worker/attempt or replacement operation just to satisfy the
   scenario. Especially do not reproduce the held CODEX EFFECT_UNKNOWN issuer.
   If this real safe precondition is unavailable, record `NOT_PROVEN` and stop
   that proof lane.

### Browser proof: reload A while B stays pending

1. Before reload, capture the browser's selected work/root, principal-scope
   **digest**, installed source/build identity and the existing pending
   B pointer's `operationKey`, `kind=message`, `targetKey`. Its canonical
   storage is the incumbent IndexedDB
   `mastermind-os-session-pending-v1` / `pointers` store, keyed by the verified
   64-hex principal scope. Inspect the record **read-only**; do not write,
   clear, migrate or export other scopes. The Launch pointer database is not
   this one.
2. Record a redacted request count baseline for
   `/os/executive/session/send` and `/os/executive/submit` **before** the
   recovery journey; also record original B's Runtime command/event ids and
   relevant published/queued count from the canonical owner where available.
   The read journey itself must cause **zero new effectful outbound requests**.
3. Reload the actual signed-in Office Web page and choose the same selected
   work/root. The history viewer must call only authenticated
   `session/references` (bounded, possibly multiple signed-cursor READ pages)
   and, after choosing A, the original `session/reply` with exactly A's
   original `operation_key`. For every reference, the public projection must
   preserve `REFERENCE_ONLY`, the original `read_ref` and
   `request_ref` derived from that operation, fixed high-water, same root,
   principal isolation and no duplicate history row. Cursor replay, drift,
   loss of authorization and malformed/oversized content must refuse closed.
4. Only when the verified `session/reply` returns the **native committed**
   original A, matching its canonical request/read refs, may the bounded
   answer text/next step appear. Treat `parent_consumed=false` as
   **not consumed**, never as ACK. Confirm active answer A is not rendered a
   second time as a historical card.
5. After opening A, verify the IndexedDB B record is byte-/field-identical
   to the pre-reload B pointer and remains pending in the UI/Runtime. Compare
   outbound effectful network counters to the baseline: no repeat SEND,
   publication, submit or new Job/Attempt, and no parent ACK. Capture one
   sanitized screenshot or browser proof reference with the restored A and
   pending B together. Do not include private message body unless the
   authorized test's evidence sink is approved for it.
6. As negative cases, switch to another work/root and back (A→B→A),
   revoke/expire the current browser auth, or force a bounded READ failure
   with an authorized test fixture. Any old A must disappear synchronously;
   a late reply must not republish it or clear pending B. Without a real
   installed signed-in negative-path fixture, label that case `NOT_PROVEN`.

### Distinct terminal evidence

Log the final observed release/route revision, exact selection, original
operation/ref digests, browser evidence identifiers, pre/post pending B
comparison, observed network counts and separately the native
`reply_committed` versus parent-consumed state, with actual source citations.
Never promote `REFERENCE_ONLY`, OAuth success, reply COMMIT, CI pass,
screenshots, or a static pointer-store fixture into parent consumption,
installation acceptance or PROVEN_LIVE by themselves. Native Tauri requires its
own lawful READ transport admission and signed-app callback journey. Final
`PROVEN_LIVE` requires the real signed-in path and outstanding security/release
gates, not this runbook.

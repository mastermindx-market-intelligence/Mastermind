# GitHub independent review — executable integration & production release

**State:** BUILT_NOT_PROVEN. Source-only, draft stack #1741 → #1748 →
#1763. No production webhook listener, GitHub App enrollment, autonomous
worker START, or real GitHub PR review is claimed.

Tracking: Mastermind #1740. Protected procedure pinned separately by the CEO
at its verified compatible Mastermind `master` SHA. This runbook is
implementation evidence, not admission law.

## Machine job and the one canonical execution plane

1. GitHub emits an explicit authorized review intent: `pull_request:labeled`
   using `independent-review`, a configured `review_requested`, or an
   authorized `issue_comment:created` with `/independent-review`.
2. The **installed Executive control host** (not the dedicated-UID
   `executive_mcp_entry.py`) mounts the exact
   `/internal/github/review-intent/delivery` route with
   `GitHubReviewASGIMount`. All other routes remain on the existing ASGI app.
3. `GitHubReviewReceiver` enforces exact method/path/raw path, TLS/host,
   bounded header/body/time, HMAC-SHA256 over raw bytes, event/action policy,
   current GitHub author permission and current PR head.
4. `GitHubReviewAPI` uses a configured GitHub App installation, short-lived
   repo-scoped token and fixed GitHub REST routes only. The token issuer is
   `GitHubAppInstallationTokens`; its private-key source is injected from
   the **existing approved host secret custodian**, not environment strings,
   Repo Actions secrets, GitHub comments, Slack, or model text.
5. `ExecutiveReviewJobAdmission` writes a single canonical **read-only**
   root Job with `events.command_id UNIQUE` (one PR+SHA, regardless of intent
   channel), under an *explicit existing Executive admission guard*. This
   is only QUEUED, not START. No watcher, subprocess, internal worker claim,
   provider selection, retry or separate run registry is created here.
6. Existing Executive/Fabric worker owner MUST perform real admission,
   START, terminal receipt and resource accounting. The current installed
   `ceo_submit_armed=false` posture is a release HOLD, not a bypass.
7. `ExecutiveVerifiedReviewResults` recognizes a genuine completed,
   read-only legacy Runtime Job with exactly one terminal Attempt, its
   `JOB_COMPLETED` event, a verdict in the existing JobPayload vocabulary,
   and a **separately source-verified distinct completed builder Job**. When
   that original builder provenance is unavailable, automatic publication
   refuses (it does not invent a builder). The native strict orchestration
   sibling-review validator remains separately owned; this adapter does
   not impersonate or replace it.
8. `GitHubReviewReturn` rebinds the terminal Job to its exact original
   `JOB_CREATED` repo, PR, actor and frozen head before calling
   `publish_verified_review`. The PR is fetched **again** at the effect
   boundary; changed SHA refuses. PASS publishes `COMMENT`, not APPROVE;
   REQUEST_CHANGES publishes `REQUEST_CHANGES`. No merge path exists.
9. `ExecutiveReviewPublicationRecord` reserves one publication via
   the incumbent Executive **events** table/UNIQUE command id before a
   GitHub POST; confirms the exact GitHub review ID afterward. Ambiguous
   POSTs reconcile against authenticated GitHub review readback (exact
   publisher, SHA, event and body). A claim without proof remains
   EFFECT_UNKNOWN: **never** blindly retry. The event log is a receipt,
   not a replacement for GitHub's publication authority.
10. `SlackReviewVisibility` uses the existing Mastermind Executive Relay
    bot, newly bound to exact channel `C0CAUK8P8S3` *without changing* its
    A2 `#agent-dispatch` client. `ExecutiveSlackReviewThreads` records
    parent timestamp on the existing Executive event ledger.
    `SlackReviewResultNotifier` posts one sanitized reply in that exact
    thread after confirmed GitHub publication. Missing/uncertain Slack
    receipts never become PR review acceptance and are never blindly
    reposted. The default public channel message does not reveal private
    repo names, PR titles, patch text or findings.

## Source files and hermetic proof

- Admission/decision: `control_plane/github_review_intent.py`,
  `control_plane/github_review_intent_ingress.py`,
  `control_plane/github_review_runtime_adapter.py`.
- HTTP/App: `control_plane/github_review_host_config.py`,
  `integrations/github_review_ingress_asgi.py`,
  `integrations/github_review_asgi_mount.py`,
  `integrations/github_review_app_token.py`,
  `integrations/github_review_api.py`,
  `integrations/github_review_host_composition.py`.
- Return: `control_plane/github_review_result_reader.py`,
  `control_plane/github_review_publication_record.py`,
  `integrations/github_review_return.py`,
  `integrations/github_review_slack_visibility.py`,
  `integrations/github_review_slack_thread.py`.
- Tests `tests/test_github_review_*.py`: signed ASGI → GitHub mock
  (including real ephemeral RSA/JWT) → **real SQLite Executive Runtime**
  → queued Job → real terminal worker fixture → GitHub formal review
  POST/readback → Slack thread reply; invalid signature, actor permission,
  duplicate intent, switched PR, moved SHA, uncertain POST, unknown builder
  and lost Slack ACK. **Hermetic tests are not a production reviewer.**

## Actual release/administration gates (unmet)

1. GitHub administrator must confirm whether existing organization installation
   `152874959` is the **right App**; do not repurpose it merely because
   installed. If not, register a separate narrowly scoped GitHub App. Needed:
   repository `contents:read`, `pull_requests:write`, metadata read;
   subscribed pull_request and issue_comment events. Configure exact webhook
   receiver URL and signing secret. GitHub REST review POST requires
   `pull_requests:write` and `commit_id`.
2. Enroll the app ID, installation ID, repo allowlist, *approved sealed* App
   private-key reader and webhook-secret reader on the actual Executive
   control host. No plaintext secret in git, Slack, test fixtures, environment
   exports or this runbook.
3. Qualify a separate, **exact-path** public Caddy route and ASGI mount for
   the Runtime-owning control service. Existing
   `ops/executive_os/os_public_edge.caddy.template` only exposes the current
   fixed Executive POST routes. The existing MCP launcher explicitly
   `never opens Runtime`: DO NOT mount a live Runtime-owning receiver
   into the dedicated-UID MCP process to work around this separation.
4. Prove authorized Executive runtime admission guard, real worker broker
   START/terminal evidence, and builder Job provenance resolution for the
   actual PR. GitHub PRs with no canonical Executive builder mapping remain
   refused for *automatic formal publication* until a separately accepted
   external-source independence binding is designed. Never fabricate a
   builder Job or self-approve.
5. Qualify source with an independent security reviewer **who actually
   returns readable findings**, repair blockers, protected PR/CI, and
   installed source SHA. A Fabric run rc=0 by itself is not read or accepted
   independent review evidence.
6. Live acceptance needs an actual signed GitHub delivery → one admitted
   Job → worker START → terminal verified independent result → one exact-SHA
   formal GitHub review ID read back → one matching Slack thread reply,
   plus negative signature, actor, duplicate, stale-SHA and lost-POST tests.
   No green CI / source push alone qualifies that chain.

## Explicitly prohibited shortcuts

Never auto-approve/merge, execute untrusted PR head code with app credentials,
reuse the A2 Slack conversation binding as a different channel, infer worker
START from QUEUED, bypass the installed CEO/Executive arm, manufacture
a builder worker ID, configure a GitHub App from an unrelated installation,
or retry an uncertain GitHub/Slack write. No new queue, watcher, database,
worker lease, token vault, or autonomous daemon is authorized by this source.

## Unix-socket bridge source slice — staged, never autonomously armed

PR #1763 adds `control_plane/github_review_socket_contract.py`,
`control_plane/github_review_socket_owner.py` and
`integrations/github_review_socket_client.py`.
`compose_github_review_host(..., socket_client=ExecutiveReviewSocketClient(...))`
is the **public-process composition**: it accepts the existing Executive CEO
Unix-socket path as a host-injected capability and refuses simultaneous direct
Runtime/database access. The legacy in-process Runtime admission mode remains
for the Executive owner and hermetic tests. The receiver and publication gates
default disabled; assembling an object is not starting a listener.

The socket client exposes exact review-command status, bounded review
admission, and one source-bound Slack parent-receipt capture frame over the
**same existing authenticated socket**. It does not enumerate Executive jobs,
run a worker, retry a lost POST, hold a credential, or select a model. The
`ExecutiveGitHubReviewSocketOwner` can apply those frames to the incumbent
JobRegistry/EventStore **only when an authorized control host invokes it**.
Its source_guard remains an explicitly injected trusted source-authorization
dependency, not satisfied production proof. Only the trusted Executive host
may supply the existing `eligible_quota_classes` worker route; the public
webhook host rejects worker constraints entirely. An unbound/default route
cannot be treated as actual worker-START eligibility.

**Critical missing production binding:** The existing
`ExecutiveControlService` authenticated CEO socket handler has NOT gained
an authorized `mastermind.github_review_socket_admission.v1` dispatch
branch. An attempted source-handler edit was explicitly blocked by platform
safety checks and was not replayed through another carrier. Dormant binding
fields in the original Ubuntu 0 workspace do not activate this capability.
No public Caddy route, GitHub App installation binding, Executive admission
arm, genuine Fabric START or GitHub review publication has been demonstrated.
The tests prove only a hermetic Unix socket server exercising the same protocol,
the real Executive ledger and source-owner adapter.

Before rollout, the authorized incumbent control-service maintainer must bind
this typed frame on the existing peer-authenticated Unix listener, without
altering existing C1/CEO/Session Bridge semantics. Both the peer UID and
separate disabled-by-default review arm must be checked before parsing or
committing. The host source_guard must reverify current PR identity/head and
actor authority **at the mutation boundary**. If disconnected after submit,
the caller performs read-only exact command reconciliation and never blindly
re-submits an uncertain effect. Qualify with the real existing Executive socket
service test fixture, not a substitute server; only then compose and enroll the
production App listener, secret custodian, Caddy route and runtime worker
consumer under normal protected release custody.


## Leaf bridge hardening — 2026-10-22

The socket-owner adapter now binds both the original authenticated Executive
admission guard and the exact immutable request's source guard into the existing
JobRegistry **commit-time** authorization callback. Authority revoked between
webhook preflight and the SQLite commit refuses admission. The owner also
refuses over-bound serialized frames before any host guard or ledger read.
These checks do not enroll or override the real socket listener.

The socket client treats even a partially sent Unix-socket command as
`REVIEW_SOCKET_EFFECT_UNKNOWN`; it never mistakes a failed `sendall`
response for proof that a submit did not execute. Any reconciliation must
read the original exact command from the existing canonical Executive ledger.
The real host must supply a trusted, bounded source guard and keep slow GitHub
network reads outside long-held database locks when integrating its endpoint.

`tests/test_github_review_socket_http_integration.py` now covers one signed
GitHub webhook through public socket-backed composition into an actual
test Runtime/JobRegistry, with redelivery dedupe and an explicit no-false-START
assertion. After the test worker's genuine fixture Attempt completes, the
existing return owner publishes exactly one mock GitHub advisory `COMMENT`
at the frozen head and sends exactly one sanitized result to the **same Slack
thread captured through the socket**. Negative tests reject wrong Job/Relay
bot/channel/timestamp, repeated conflicting thread capture, unbound worker
route authority and uncertain partial socket writes. All work occurs in
hermetic mocked GitHub/Slack transports and a test socket; this is **not**
evidence that installed `ExecutiveControlService` accepts the new frame,
that a production worker STARTed, or that a real GitHub/Slack write occurred.
The legacy 21-line dormant Executive binding worktree diff remains excluded
from this PR because the production handler modification was platform-denied.


## Source provenance modes for external pull requests

The earlier independent review identified that an ordinary GitHub PR can have
**no Executive builder Job**. The original two-worker contract deliberately
refused formal publication rather than inventing that Job. That stricter
contract **remains intact** for `EXECUTIVE_BUILDER` source.

The trusted return-owner factory selects `ReviewReturnSourceMode.EXTERNAL_GITHUB_ADVISORY`
(the verified source receipt uses `EXTERNAL_GITHUB_SUBMITTER`). This allows a
bounded **advisory COMMENT**, including on an authorized draft PR, only after:
1. A real terminal, read-only Executive reviewer Job and immutable original
   `JOB_CREATED` source receipt are verified.
2. The host explicitly provides its installation-scoped
   `GitHubReviewAPI.read_external_source` port and configured publisher login.
   Mixed external/native builder sources are refused.
3. An authenticated GitHub GET verifies the exact open PR/head SHA,
   same-repository source, exact boolean draft state, and stable GitHub
   submitter login/account ID. Draft PRs must already have passed signed,
   explicit label/comment admission with fresh requester permission;
   draft `review_requested` remains refused. Submitter matching the publisher
   bot is refused.
4. The source ID/login are freshly **re-read** at the publication boundary
   and checked against the result and frozen head. A changed submitter or
   head refuses without a review POST.
5. All external-origin verdicts publish only GitHub `COMMENT`, never
   `REQUEST_CHANGES` or `APPROVE`. The body explicitly warns that the
   submitter is not an attested code-builder and native two-worker
   independence has not been proven. It cannot become a release approval,
   automatic merge, or an independently verified builder-worker completion.

This produces useful external PR analysis without masquerading as an internal
builder worker. It is **not** a substitute for a production builder-attestation
writer if strict two-worker review is required. External provenance is
default-off because `ExecutiveVerifiedReviewResults` must be explicitly
constructed with `external_source` and `publisher_login`; the current
installed Executive service has no delivery/return binding for it.
Hermetic tests do not prove the GitHub App, source owner, or production
authentication is installed.

## Independent review security07 reconciliation (exact 0ad2ca189)

The independent reviewer returned PASS FOR SOURCE SLICE ONLY, independently
running 267 review tests and 14 adversarial publication/source checks.
Post-review fixes export both external-source contract names in
`github_review_intent_ingress.__all__` and add direct reader tests for
self-publisher identity, incorrect PR/head, malformed identity and GitHub
source read failure. These are source/coverage fixes, not live deployment.

The reviewer also flagged possible concurrent duplicate GitHub advisory
comments. That concern was checked against the *existing*
`ExecutiveReviewPublicationRecord._reserve`: its EventStore transaction and
unique `events.command_id` reservation ensure at most one caller owns the
right to POST. A concurrent caller observing the same reservation can only
reconcile using GitHub readback, never POST a second comment. The new
concurrent-publisher regression deliberately holds the first POST after
reservation and proves the competing caller returns `EFFECT_UNKNOWN`
without submitting. The original first publisher later confirms exactly one
review; a subsequent retry reads the confirmation without POST.

Production remains default-off: source/security test evidence is not a
substitute for authorized incumbent Executive socket dispatch, a real
worker's terminal receipt, external source binding, or actual GitHub App
review/Slack thread return.

## External PR review return — explicit existing Executive-host binding

The opt-in external GitHub submitter path is no longer just a standalone
source-reader constructor. The incumbent `GitHubReviewReturn` now provides
`for_authorized_source(...)`, a **pure and default-off host-side composition
step** for the canonical Executive Runtime owner. The host must pass its
existing `Runtime`, authenticated installation-scoped `GitHubReviewAPI`,
and callable publication authorization guard, then choose one closed
`ReviewReturnSourceMode`:

- `EXECUTIVE_BUILDER`: requires a supplied, source-verified
  `builder_job_id_for_review`. The result reader still enforces a genuinely
  completed **distinct** builder Job with immutable matching repo/PR/head
  provenance. Missing/unrelated builder evidence refuses.
- `EXTERNAL_GITHUB_ADVISORY`: prohibits any builder-Job resolver, binds
  the authenticated `GitHubReviewAPI` itself as the fresh submitter reader,
  and derives the publisher account from that *same validated App port*.
  A reviewed external PR may produce only a clearly labeled advisory
  GitHub `COMMENT`; it never claims an attested builder, never uses
  `APPROVE`, `REQUEST_CHANGES` as a GitHub event, or merges.

Strings, omitted source mode, mixed source modes, missing native builder
resolver and unbound publisher guard are refused **before a network write**.
The existing return consumer remains one-shot, invoked only after the
Executive owner's real Job/Attempt completion; this factory neither starts a
worker nor creates a watcher, queue, token store or separate database. Tests
exercise both modes through the real in-memory SQLite Executive Runtime,
including external `REQUEST_CHANGES` verdict downgrade to COMMENT, exact
submitter-account readback, native builder checks, invalid selection and
moved-SHA refusal.

This is **source wiring only**. The installed Executive service's
authenticated CEO Unix socket review-frame dispatch has **not** been
installed, the original explicit platform safety denial has **not** been
cleared, and its 21-line dormant local source diff remains excluded from
the PR. The public webhook cannot access Executive Runtime SQLite directly,
nor select the return source mode. No GitHub App enrollment, actual worker
START, webhook delivery, GitHub formal review or Slack thread production
receipt is proven.

## Latest exact-head reviewer return — security09 (2026-10-22)

Fabric `mmx-gh-review-20261022-security09` inspected the pushed
`a5528a560801d1b38d59fb167f080ff3fec3c50e` in an independent detached
checkout and reported PASS SOURCE SLICE, 283 review tests passing and additional
stale-head/self-publisher/source-drift probes. **This is not accepted security
review evidence:** although the text had no blocking findings, the Fabric
controller ended `rc=1` / `PROVIDER_TERMINAL kind=permission` with
`claude-code:unrecognized_model` for `MiniMax-M3`. Its status remains
`acceptance_state=UNVERIFIED`. Do not equate the source narrative with a
successfully accepted reviewer receipt or launch a duplicate worker through
another provider/account to evade that denial. A legitimately repaired
provider configuration and an explicitly authorized fresh exact-head review
are prerequisites to crossing the independent-review gate.

Follow-up local hardening, **not installed and not covered by security09**:
- The Executive-owned `for_authorized_source` factory requires the
  **exact** enrolled `GitHubReviewAPI` implementation rather than trusting
  a subclass override of the identity-bearing `publisher_login` property.
- Regression tests assert exact refusal codes for omitted/string/mixed modes
  and unarmed source, reject an overriding API subclass, malformed owners,
  self-publisher PRs and a changed submitter between source read and effect
  preflight. A denied input causes no review POST.

This is source hardening only. The incumbent authenticated Executive socket
service handler remains previously platform safety-denied and **unmodified**;
its original dormant local worktree diff remains excluded. Neither advisory
GitHub submitter identity nor a PASS narrative attests a real builder worker,
live GitHub App/webhook deployment, formal review acceptance, or Slack return.


## Security03/05 REQUEST_CHANGES final source reconciliation (2026-10-23)

The historic security03/security05 REQUEST_CHANGES findings were assessed
against current PR source, not replayed by accepting an old head:

- **Native builder proof:** `ExecutiveVerifiedReviewResults` demands a
  genuinely distinct, terminal builder Job. Its original immutable
  `JOB_CREATED.provenance` MUST match the review Job's same repository,
  same pull number and exact frozen commit SHA. Tests now independently
  vary pull number while keeping repo/SHA fixed and vary SHA on the same PR;
  neither is an independently verified native review. An ordinary external
  PR is not assigned a fictitious builder Job: it remains expressly
  `EXTERNAL_GITHUB_SUBMITTER`, advisory COMMENT only.
- **Permission floor:** the enrolled host already requires a fresh GitHub
  permission on all supported channels with a minimum `write` policy and
  preserves GitHub's exact `maintain`/`triage` role semantics. The pure
  policy now additionally refuses all current-unverified
  admissions whose requested minimum exceeds GitHub's triage baseline,
  even for signed GitHub-enforced events or an optional static-actor
  fallback. A stale allowlist alone cannot grant `write`/`maintain`/
  `admin` authority. Explicit elevated-floor tests cover both
  `labeled` and `review_requested`.
- **Ingress and publication:** signed HMAC exact-repository PR identity,
  frozen head, closed source/actor policy, and the default-off ASGI
  receiver remain intact. Existing tests exercise malformed/forged
  deliveries and duplicate events. The Executive EventStore reservation
  arbitrates only one GitHub review POST; a lost ACK or unavailable
  authoritative readback is `EFFECT_UNKNOWN`, never a second POST.
  Adversarial readback-outage and concurrent publisher regression tests
  are retained, not replaced with another queue/ledger.

This slice has no `ExecutiveControlService` frame-handler edits. The
original local 21-line dormant binding remains explicitly **excluded**:
a previous platform policy denial is not resolved by source tests or
reassigning the same mutation to Fabric/Codex.

The independent security09 return on parent `a5528a56` reported nonblocking
source findings but terminated `rc=1` for provider permission /
`unrecognized_model MiniMax-M3`; it was not eligible for acceptance.
A fresh exact-head independent review requires a genuine provider
configuration/authorization change and new evidence. Do not blind-retry
through another carrier or provider to disguise that denial.


## Draft PR review coverage and installed-host gate (2026-10-23)

The incoming review-intent product owner identified a source-correctness gap:
draft PRs are frequently where independent security/architecture review is
needed, before GitHub merge readiness. The existing pure intent core rejected
every draft, even a signed, explicit `independent-review` label or authorized
`/independent-review` comment. The source now permits **only** those two
explicit channels on an open, same-repository draft when the current actor
permission has been freshly authenticated; an unbound/stale/underprivileged
actor, unlisted login, wrong label, forged signature, unrelated event, moved
SHA, plain issue, or `review_requested` channel remains refused. Nothing
marks the PR ready, approves or merges. Real worker admission remains the
same canonical Executive JobRegistry with one idempotent command ID.

External advisory result readback now accepts an exact boolean
`draft=True` from authenticated GitHub PR facts while continuing to require
the current exact repo, number, head SHA, stable submitter ID and distinct
publisher account. The verified reviewer remains an actual terminal read-only
Executive Job/Attempt; results are GitHub `COMMENT` only, even when the
analysis verdict is REQUEST_CHANGES. Tests cover source identity, draft
label/comment admission, missing and revoked actor permission, the
`review_requested` restriction, and one idempotent COMMENT on a draft with
no APPROVE/merge behavior.

**Production install is not proved by the above source tests.** Current
`Mastermind_Executive_V3.executive_state` reported the installed control
source as `80f384b8f58b7ca46422d9783aa5c0613c7bf4b2`, while protected
Mastermind master was later pinned at
`bcf7a98e2d0030f679138a326f11a7cdda0f74ca`. The connected M2
Desktop Commander user cannot read the root-controlled live Executive
checkout/Runtime directory. More importantly the earlier proposed
`ExecutiveControlService._handle_ceo_ingress_connection` GitHub review
frame mutation was **explicitly platform safety-denied**. The dormant
21-line `control_plane/executive_service.py` local diff is still excluded
and must not be replayed, repackaged, reassigned to Fabric/Codex or installed
through another carrier. The `GitHubReviewReturn.for_authorized_source`
factory is already constructed and exercised against the canonical test
Runtime, but has **not** been installed into a production host callback.
Any actual release requires the original Executive service owner to receive
genuine authorization for that exact handler/return consumer and its raw
frame cap, peer UID, timeout/out-of-lock GitHub calls, real event source,
credential custody and deterministic readback, then separately verify
installed SHA, authenticated webhook, real worker START/terminal, exactly
one GitHub formal review and same Slack thread.

Current #1741 and #1748 heads are clean/mergeable with passing original
CI/CodeQL where applicable, but both remain DRAFT without formal GitHub
reviews. #1741's original source writer gate was documented as unavailable
(`RULES_ABSENT`) and its branch remains under separate custody, so this
draft correction is delivered in existing downstream #1763 source rather
than force-pushed to #1741. The protected master ALLGREEN/SQUASH merge queue
and current-master merge group checks are distinct from branch-head green
checks. No PR merge, mark-ready, production activation, or privilege
escalation follows from this source improvement.

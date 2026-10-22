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

The socket client supports only exact review-command status lookup and one
bounded review-admission submit frame. It does not enumerate Executive jobs,
run a worker, retry a lost POST, hold a credential, or select a model. The
`ExecutiveGitHubReviewSocketOwner` can validate and admit these frames against
the incumbent JobRegistry and EventStore **when an authorized control host
actually invokes it**. Its source_guard remains an explicitly injected trusted
source-authorization dependency, not a satisfied production proof.

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

`tests/test_github_review_socket_http_integration.py` covers one signed
GitHub webhook through the public socket-backed composition into an actual
test Runtime/JobRegistry across a local Unix-socket transport, with signed
redelivery dedupe, worker-START absence, sanitized Slack visibility and invalid
signature refusal. This is **hermetic source-path proof only**, not evidence
that the installed `ExecutiveControlService` accepts the new review frame.
The legacy 21-line dormant Executive binding worktree diff remains excluded
from this PR because the production handler modification was platform-denied.


## Source provenance modes for external pull requests

The earlier independent review identified that an ordinary GitHub PR can have
**no Executive builder Job**. The original two-worker contract deliberately
refused formal publication rather than inventing that Job. That stricter
contract **remains intact** for `EXECUTIVE_BUILDER` source.

A separately selected `EXTERNAL_GITHUB_SUBMITTER` mode now allows a bounded
**advisory COMMENT** after:
1. A real terminal, read-only Executive reviewer Job and immutable original
   `JOB_CREATED` source receipt are verified.
2. The host explicitly provides its installation-scoped
   `GitHubReviewAPI.read_external_source` port and configured publisher login.
   Mixed external/native builder sources are refused.
3. An authenticated GitHub GET verifies the actual PR, head SHA, non-draft,
   same-repository source and stable GitHub submitter login/account ID.
   Submitter matching the publisher bot is refused.
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

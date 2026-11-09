# GitHub independent-review ingress — source adapters and release contract

Status: **Source implementation; installed acceptance pending.** Concrete HTTP,
Unix-socket, GitHub App, Executive Runtime, publication and Slack adapters are
present. The installed consumer, credential bindings, public route, qualified
reviewer and live end-to-end acceptance remain unproven. This document records
the source contract and the incumbent administrator's release dependencies.

## What this slice is

| Module | Role |
| --- | --- |
| `control_plane/github_review_intent.py` | Pure decision core. HMAC verification, allowlist, intent channels, actor authority, fork refusal, untrusted-text fencing, admission identity, head freeze. No I/O, clock, network, subprocess, or filesystem. |
| `control_plane/github_review_intent_ingress.py` | Composition walk plus the adapter `Protocol`s and the concrete `ReconcilingReviewPublication` adapter. No HTTP client, queue, table, lifecycle, or credential. |
| `tests/test_github_review_intent.py` | Guard file for the decision core. |
| `tests/test_github_review_intent_ingress.py` | Guard file for the ingress walk. |

## What this slice is not

It deliberately does **not** create a second instance of anything that already
has an owner:

- **No second review adjudicator.** `control_plane/github_release_assessment.py`
  owns review adjudication; this slice never judges review content.
- **No second PR disposition owner.** `control_plane/github_pr_lifecycle.py` owns
  disposition.
- **No second GitHub App / installation governance layer.**
  `scripts/github_estate_governance.py` owns installation pinning and the
  least-privilege permission projection.
- **No parallel review API client.** The source adapters use the existing
  installation-scoped `integrations/github_review_api.py` and its bounded
  authenticated transport. Source preflight and return bind that same API
  implementation rather than inventing another credential or reader owner.
- **No second review registry and no second independent-review authority.** The
  Fabric's `review_required` / `reviews_job_id` / `orchestration_role='review'`
  model in `control_plane/executive_runtime.py` remains the only one. The
  publication adapter requires the incumbent Executive EventStore's atomic,
  durable `events.command_id` reservation/confirmation port and creates no store.
- **No second verdict vocabulary.** The verdict set is borrowed verbatim from
  `plugins/mastermind-sol/skills/review-pull-request/SKILL.md`.
- **No second retry plane.** `PublicationEffectUnknown` is reconciled by reading
  GitHub, not by a queue, a scheduler, a backoff, or a persisted attempt log.

## Idempotency is the existing ledger's

There is no run registry, cache, or lock in this slice. The admission identity
is minted deterministically from `(repository, pull number, frozen head SHA)` —
and **not** from the intent channel — and shaped to be the existing
`events.command_id` UNIQUE index key
(`executive_runtime._COMMAND_ID_RE`, `^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$`).

Consequences a host adapter inherits for free:

- an identical redelivery re-mints the same command id, so the UNIQUE index
  admits **exactly one** run;
- a moved head mints a **different** command id, so a stale review can never be
  mistaken for a current one;
- a reviewer requested, the label applied, and `/independent-review` commented
  in the same minute all collapse onto the same command id, so one exact head
  earns **one** review run rather than three separately billed Fabric reviews.
  One human intent expressed twice is not two independent reviews.

The identity namespace is domain-separated (`mastermind.github_review_intent.*`)
so it can never collide with the existing MCP / Slack / automated CEO-intent
families in `control_plane/ceo_request.py`.

### Explicitly authorized reruns

A distinct second review of the same head is reachable only through
`rerun_review_intent_id`, which requires an out-of-band authorization reference
(`rerun-<32..64 hex>`) **and** `policy.allow_explicit_rerun=True`. Reruns are off
by default and a requested rerun without policy authorization is refused
(`RERUN_NOT_AUTHORIZED`) rather than silently downgraded. Ordinary deliveries
have no route to this function at all.

## The pull request is the signed payload's

`admit_review_intent` takes **no pull-request number**. There is deliberately no
caller-supplied value to cross-bind against the signed one, so no route, tenant
id, database id, or operator input can aim a genuine delivery at the wrong pull
request.

The number is derived from the signature-verified body itself:

- `pull_request` — `number` must agree with `pull_request.number`, and the
  embedded pull request's `base.repo.full_name` must be the delivery's own
  repository.
- `issue_comment` — `issue.pull_request` must exist and its canonical GitHub API
  pull URL must name the same repository *and* the same number as `issue.number`.
  A slash command on a plain issue is refused with
  `PULL_REQUEST_IDENTITY_UNBOUND` before any read, ledger write, or
  reviewer-visible line.

The authoritative installation-scoped re-read must then match both the signed
repository and the signed number (`PULL_NUMBER_MISMATCH` otherwise). A correct
HMAC proves who signed the bytes; it never proves which pull request a wrong
caller route selected.

## Explicit and automatic intent channels

Manual channels and the default human-authorized lifecycle mode require an
**allowlisted human login**. Their authority beyond the allowlist comes from
the channel-specific enforcement or the externally reverified permission below.

| Channel | Delivery | GitHub's own enforcement | Fresh read required? |
| --- | --- | --- | --- |
| Configured reviewer requested | `pull_request` / `review_requested` | Refused unless the actor holds triage/write at delivery time | No, unless `require_current_permission_for_all_channels` |
| Intent label | `pull_request` / `labeled` | Same | Same |
| Slash command comment | `issue_comment` / `created` | **None** — writable by anyone | **Yes** |
| Opt-in human-authorized lifecycle review | `pull_request` / `opened`, `synchronize`, `reopened`, `ready_for_review` | No collaborator authority follows from these actions | **Always**, even if static actor fallback is enabled |
| Standing repository-policy lifecycle review | Same four lifecycle actions; both automatic flags enabled | Host-enrolled repository/install policy; signed sender is provenance | Fresh installation-scoped PR facts; no claim of human collaborator permission |
| Existing-owner open-PR reconciliation | Internal authenticated callable, no webhook | Host-enrolled policy plus the existing owner's execution-reference guard | Bounded scoped list and a fresh read of each PR |

`issue_comment` is the open channel: GitHub's reported `author_association`
travels in the payload and is a **claim**, not authority. With no externally
reverified current permission the channel is refused with
`ACTOR_PERMISSION_NOT_REVERIFIED`. Bind `ActorPermissionPort` to a collaborator
permission read; a current permission of `none` (revoked) or below
`minimum_permission` (default `triage`) is refused with
`ACTOR_PERMISSION_INSUFFICIENT`.

The pure policy has explicit, default-off switches:
`allow_static_actor_authority` permits the existing explicit-channel fallback
when no read is bound, while `require_current_permission_for_all_channels`
extends the strict posture to the two channels GitHub polices itself. The host
requires fresh permission for every human-authorized channel. Human-authorized
lifecycle review never accepts the static fallback.

Automatic lifecycle review also requires `allow_lifecycle_review=True`; its
default is `False` in both the host settings and decision policy. Disabled
lifecycle deliveries are refused before authenticated reads or ledger inspection.
Automatic drafts defer; existing authorized label/comment draft advisory remains.
The separate `allow_repository_policy_review` setting is also default-off. It
permits bot-sender lifecycle events under the enrolled repository policy while
preserving the real sender. A strict v2 decision binds the actual origin,
installation and host policy digest. The Executive socket independently checks
its own configured policy; reconciliation additionally requires its own bound
owner guard and carries no fabricated sender or webhook delivery.

All channels share the same repository/PR/head admission identity. New creation
events preserve the complete original decision and normalized objective digest.
An exact replay retains payload checks; a distinct trigger joins the first
winner and returns its original job/decision through the socket. Legacy records
that lack a full decision remain existing with `ADMITTED_DECISION_UNAVAILABLE`;
they are not redispatched and do not stop unrelated PRs in a bounded scan.

The receiver reports closed refusal reasons. Its reconciliation callable is
internal, with at most 100 PRs per invocation, fixed scoped numeric pagination,
fresh PR reads, and an explicit partial-result receipt. It introduces no timer.
The v2 reconciliation receipt separates enumeration from source coverage and
records isolated read failures, elapsed time, the starting scope and continuation
hint. A pass has a cooperative default 30-second budget (maximum 60 seconds).
A failed individual source read does not starve unrelated PRs. Installation-wide
credential, permission, rate-limit and server deferrals stop the pass. Budget or
read-only deferral can retain a same-page PR hint; an uncertain admission stops
at its exact original command with no continuation permission. A resumed pass
never claims that it observed every repository source. Later page-one sweeps
remain necessary because GitHub pagination is not a stable snapshot.
Job objectives validate full original text, then carry bounded excerpts and
exact source references inside the existing socket limits. Full-source
retrieval remains required before a reviewer may claim coverage.

See [automatic coverage and rollout](GITHUB_REVIEW_AUTOMATIC_COVERAGE.md) for
model assessment, Slack Dot review, repository-policy and backlog contracts,
and the separate host/App and formal-approval gates.

The command matches the **first non-empty comment line exactly**. A comment that
merely mentions `/independent-review` never triggers a run.

## Fail-closed refusals

Every non-admitted decision names exactly one closed-vocabulary value. The
notable ones:

`SIGNATURE_INVALID`, `BODY_TOO_LARGE`, `EVENT_NOT_SUPPORTED`,
`ACTION_NOT_SUPPORTED`, `AUTOMATIC_REVIEW_DISABLED`, `REPOSITORY_NOT_ALLOWLISTED`,
`INSTALLATION_NOT_ALLOWLISTED`, `REVIEW_REQUEST_FOR_OTHER_REVIEWER`,
`COMMAND_NOT_PRESENT`, `LABEL_NOT_PRESENT`, `ACTOR_NOT_AUTHORIZED`,
`ACTOR_ASSOCIATION_INSUFFICIENT`, `ACTOR_PERMISSION_NOT_REVERIFIED`,
`ACTOR_PERMISSION_INSUFFICIENT`, `PULL_REQUEST_IDENTITY_UNBOUND`,
`PULL_NUMBER_MISMATCH`, `PULL_REQUEST_NOT_OPEN`, `PULL_REQUEST_DRAFT`,
`HEAD_REPOSITORY_MISMATCH`, `HEAD_SHA_MALFORMED`,
`UNTRUSTED_CONTENT_DETECTED`, `ALREADY_ADMITTED`, `RERUN_NOT_AUTHORIZED`,
`HEAD_MOVED`.

A refusal is evidence for a human or a separately authorized caller. It is
never authority to open, close, merge, approve, or publish anything.

## Security properties

**Signature.** HMAC-SHA256 over the exact raw body, `sha256=<64 lowercase hex>`,
constant-time `hmac.compare_digest` after an exact length and shape fence —
mirroring `integrations/workspace_agent_return.py`. A delivery that fails
verification raises before the PR read, before the ledger, and before any
visibility surface, so it is neither a run trigger nor a probe oracle.

**Untrusted PR text.** Pull-request title and body are retrieved data, never
instruction. They are refused outright when they carry a credential shape
(the same patterns as `control_plane/github_pr_lifecycle.py`) or the untrusted
fence terminator, and are otherwise carried only inside an explicit
`<<<UNTRUSTED_PULL_REQUEST_CONTENT … >>>` block. A PR author can neither escape
the fence nor smuggle an instruction into a command, argv, or authority field.

**Forks.** A PR whose head repository differs from its base repository is
refused with `HEAD_REPOSITORY_MISMATCH`. A fork is the canonical
prompt-injection carrier: its author is not a repository collaborator.

**Exact PR identity.** The head SHA, base SHA, and repositories used to freeze a
run come from an installation-scoped re-read
(`GET /repos/{repo}/pulls/{n}`), never from the webhook payload. The webhook only
says a PR *may* have changed.

**Freshness at the effect.** `publish_verified_review` performs its own
installation-scoped read of the pull request immediately before the review POST.
It takes no caller snapshot, because the whole question is what the head is
*now*: a snapshot cannot answer that, and a snapshot that happens to be current
is a coincidence. A moved head is refused with `HEAD_MOVED`; a read that answers
about a different pull request is refused with `PULL_NUMBER_MISMATCH`.

**An uncertain POST is reconciled, never retried blind.** The concrete
`ReconcilingReviewPublication` adapter first observes the exact existing claim,
reads authenticated reviews, and performs the typed final PR/source check. A
fresh preflight failure creates no publication reservation. Only after those
reads succeed does the adapter atomically reserve the immutable command/payload
in the *existing* Executive EventStore's `events.command_id` UNIQUE transaction.
Host authorization and the three-second preflight deadline are checked inside
the acquired transaction, including time spent waiting for the database lock.
Only the first durable claimant can POST. An existing claim, lost reservation
reply, or expiry after committed reservation remains sticky even if no POST is
known to have occurred. Competing callers use positive authenticated readback;
they never acquire another POST right. A successful effect is confirmed in the
same ledger. Unmatched, ambiguous or unavailable readback remains
`PUBLICATION_EFFECT_UNKNOWN`, never a second GitHub POST. A read-only
`published_command_ids()` preflight is **not** an atomic gate. Test fakes must
not be substituted for that production ledger.

New v2 reservations retain the original publisher's numeric ID and login along
with repository, PR, frozen head, Job, event and exact body digest. Reserved-only
recovery occurs before current-head/result eligibility: an exact historical
review may become visible after the head moves. It requires exactly one matching
authenticated review and only confirms the original effect; it does not review
the new head. The production hot path uses indexed exact-command reads, not a
scan of every publication. Valid confirmed v1 history is retained, including
through the original publication API. An unconfirmed v1 reservation without
original publisher provenance stays unknown; current configuration cannot fill
missing historical facts.

### Bounded transport and admission pressure

The GitHub adapter streams JSON with a one-MiB response cap; token issuance uses
the same streaming guard with a 64-KiB cap. Both request identity encoding, refuse
unexpected compression and close responses on every exit. A GET may make one
short same-token, same-destination recovery attempt after a transport failure or
500/502/503/504, within one three-second cooperative operation budget. It does
not retry schema, permission, redirect or missing-source refusals. Review POSTs
and installation-token POSTs remain one attempt.

GitHub rate limits and server `Retry-After` responses establish adapter-local
pacing and a typed source-wide deferral. Shared pacing is checked before every
attempt, including after another request establishes a limit during backoff.
The existing owner receives the delay; workers do not sleep through long limits.
This is transport pacing, not a new task queue or retry authority. HTTPX timeouts
bound individual I/O waits; the monotonic deadline is checked on each raw chunk,
so these are cooperative bounds, not synchronous-call cancellation guarantees.

The HTTP receiver admits at most four active synchronous operations. A busy
receiver returns `ADMISSION_BUSY` before credentials or ports are called. Secret
reads run outside the event loop. A timed-out operation retains its slot until
the real worker exits, and a preflight budget check prevents starting a late
admission. An admission already attempted at timeout remains
`ADMISSION_EFFECT_UNKNOWN` and reconciles under the original command.

Slack visibility has two separate best-effort slots. A slow Slack call does not
delay a known admission HTTP acknowledgment or occupy admission capacity. The
response distinguishes `SCHEDULED_BEST_EFFORT` from `DEFERRED_CAPACITY`; neither
claims Slack delivery. Deferred visibility has not reserved or attempted a send
and may be projected later by the original owner. This adapter adds no durable
notification queue or background wake guarantee. An existing unknown Slack send
remains governed by its original reservation and cannot be automatically reposted.

**No unfenced auto-approval.** `PASS` maps to a GitHub `COMMENT`, never
`APPROVE`. This slice mints no approval verb and no merge path at all, and
`ReconcilingReviewPublication` refuses any verb outside
`ALLOWED_REVIEW_EVENTS` before it can reach a socket.

**Separate worker and canonical Job source binding.** Publication refuses
a result whose reviewer is the builder (`REVIEW_NOT_INDEPENDENT`) or whose
reviewer identity is unknown (`REVIEWER_IDENTITY_UNKNOWN`). The reviewer must
come from the Fabric's own worker identities, resolved by
`Runtime.validated_role_completion` and `control_plane/fabric_result_projection`.
A verified SAME result from an unrelated Job is *not* publishable against the
currently admitted PR. Before result access or any GitHub effect, the required
`AdmittedJobReadPort` must freshly join the incumbent `JOB_CREATED` ledger
command to the actual Job and its persisted provenance: the exact command id,
Job id, repository, PR, frozen head, actor, and intent id must agree with the
admission decision. Missing/unreadable or mismatched binding refuses with
`ADMITTED_JOB_READ_UNAVAILABLE` or `ADMITTED_JOB_SOURCE_IDENTITY_MISMATCH`.
The caller-supplied `job_id` is never source authority.

**Sensitive review output.** Verified reviewer text is not automatically safe
for publication. A summary with credential/secret-shaped content is refused
with `REVIEW_SUMMARY_SECRET_SHAPED` before fetching or posting; the concrete
publisher also checks the entire outgoing body. It reuses the canonical
credential-shape fence, not a second independently managed secret scanner.

**Publish retry.** Publication carries its own deterministic command id bound to
job and frozen head, so a retry reconciles to `ALREADY_PUBLISHED` instead of
posting a second formal review.

**Visibility is non-gating and opaque.** A signed issue comment without a
bound pull request returns `PULL_REQUEST_IDENTITY_UNBOUND` before any Slack
notification, authenticated PR read or Job admission, even for an actor who is
not allowlisted. Other eligible Slack failures are recorded on the outcome,
never raised, and never cause a second admission. It collapses to the
single fixed code `VISIBILITY_TRANSPORT_UNAVAILABLE`: transport exception text
routinely embeds the workspace id, channel id, message id, API URL, and
occasionally a token fragment, and `ReviewIngressOutcome` structurally refuses to
construct with any other value.

## Adapter interfaces to bind

| Port | Binds to |
| --- | --- |
| `PullRequestReadPort` | A GitHub App installation token minted from the configured app, then `GET /repos/{repo}/pulls/{n}` |
| `ActorPermissionPort` | The authenticated collaborator permission read; GitHub's own vocabulary (`none`/`read`/`triage`/`write`/`maintain`/`admin`) or `None` |
| `FabricJobAdmissionPort` | `executive_runtime` Job registry — `create_job(..., command_id=decision.command_id)`; `admitted_command_ids()` reads the same index back |
| `VisibilityPort` | The existing Slack Web API client in `integrations/slack_agent_dialogue/slack_web_api.py` |
| `ReviewResultPort` | `Runtime.validated_role_completion` + `fabric_result_projection.project_fabric_role_result`, returning a result only when the projected receipt state is `SAME` |
| `AdmittedJobReadPort` | Fresh incumbent Executive `JOB_CREATED` command-to-Job join plus exact persisted Job provenance for repository, PR, head, actor and intent; absence/mismatch refuses before review publication |
| `ReviewPublicationPort` | `ReconcilingReviewPublication`, bound to a `ReviewTransportPort` (`POST`/`GET /repos/{repo}/pulls/{n}/reviews`) and the canonical atomic `PublishedCommandIndex` |
| `PublishedCommandIndex` | REQUIRED incumbent Executive EventStore `events.command_id` UNIQUE reservation/confirmation adapter; `reserve_publication` returns true only for first durable same-payload writer; `confirm_publication` persists authentic review id; read-only `published_command_ids` alone is insufficient |

A missing port raises `ReviewIngressUnavailable` / `ReviewVerificationRefused`.
There is no fallback to an unauthenticated client.

## Human-admin gates (not satisfied by this slice)

Nothing below is automated, and none of it is done by this PR.

**GitHub App**

1. Create or select the GitHub App. Do not reuse `macro-production-publisher`;
   that app's installation is governed by
   `scripts/github_estate_governance.py` and is a different publisher identity.
2. Subscribe to exactly these repository events: `Pull request` (review
   requested, labeled) and `Issue comment`.
3. Install it on `mastermindx-market-intelligence/Mastermind` only, and record
   the resulting **installation id** — the policy allowlist refuses every other
   installation.
4. Set the webhook URL and record the **webhook secret** in the host's secret
   store only. Never in the repository, a prompt, a doc, or a git remote.
5. Confirm the App can read pull requests and submit pull request reviews. It
   needs nothing else — and specifically not merge, push, or administration
   scopes.

**The allowlist policy** is host configuration, not code. Populate
`repositories`, `installation_ids`, `configured_reviewer`, and
`authorized_actors`. `authorized_actors` should be the small set of humans who
may request a review; anyone else is refused with `ACTOR_NOT_AUTHORIZED`, and
that check is static, so an un-allowlisted login never reaches an authenticated
read. Leave `allow_static_actor_authority` and `allow_explicit_rerun` at their
default `False`.

**Slack**

6. Grant the existing Slack app `chat:write` for the target channel. Reuse the
   existing dialogue client and its token; do not mint a second Slack
   credential.

**Runtime arming**

7. Bind the ports in the host that already owns the credentials. Until that
   happens an unbound port is a typed refusal — and an unbound
   `ActorPermissionPort` refuses the open comment channel by name rather than
   admitting it on a payload claim.
8. Qualify and bind the existing ASGI webhook source on the incumbent host's
   exact HTTPS route with its configured limits. Source routing exists;
   public exposure and installed acceptance still require observed release
   evidence.

## Verification performed

- `python3 -m pytest tests/test_github_review_intent.py tests/test_github_review_intent_ingress.py`
  — 155 tests, all passing.
- Incumbent guard files re-run unchanged and passing (866 tests):
  `test_github_pr_lifecycle`, `test_github_release_assessment`,
  `test_github_exact_edit`, `test_github_estate_governance`,
  `test_ci_pytest_policy`, `test_mastermind_plugin_packages`,
  `test_sol_capability_fabric_gh0`, `test_sol_capability_status`,
  `test_ceo_intent`, `test_executive_wake_fabric`,
  `test_executive_runtime_events`, `test_fabric_job_view`.
- Adversarial coverage: bad signature, tampered body, duplicate delivery,
  changed head, actor without permission, revoked/downgraded actor, fork prompt
  injection, stale review, publish retry, lost review POST.

### What these tests do *not* prove

The source now includes concrete HTTP, Unix-socket, GitHub App, Executive Runtime,
publication and Slack adapters. Hermetic composed tests exercise real local
Runtime stores and transports with synthetic external services. They do not
prove a selected installed service, enrolled GitHub App, public HTTPS route,
qualified real worker, production review or Slack-thread delivery. A green
fixture run is not live acceptance. Those deployment and canary facts remain
separately required under the existing owners.

## Known gaps, unrelated to this change

The `mcp` dev dependency is not installed here, so `tests/workbench_*` and
`tests/*/test_*.py` that import it fail at collection.

## Security re-review #5722645641 — author-bound readback and final POST authority

The concrete publisher now requires an ExpectedReviewPublisher bound by the trusted host to the configured GitHub App posting principal (GitHub user.id and user.login, not an event/caller value). Each PublishedReviewFacts must preserve the authenticated GitHub GET review author's numeric id and login, and reconciliation confirms only when both match this principal in addition to the frozen commit/event/body. A third party posting an identical message can never confirm the atomic effect claim or suppress the original authorized first writer.

The concrete ReconcilingReviewPublication also requires a FinalPullRequestCheck bound to the admitted decision and installation-scoped authenticated PR reader. After the potentially slow reviews GET, the guard re-reads the exact repository, pull number, frozen head, open/draft/fork state and current untrusted objective, then refuses a stale or changed PR before any POST. An arbitrary no-op callback and a missing guard are not accepted. Definite pre-POST refusal remains separate from PublicationEffectUnknown, and the original durable atomic reservation is sticky; it does not give permission to auto-retry a rejected publication.

Native publication still refuses a draft. The only draft exception is an explicit `EXTERNAL_GITHUB_SUBMITTER` advisory whose verb is forced to `COMMENT`. That path seals the authenticated submitter id and login into `ExternalCommentAdvisory` and the final guard re-reads both after the reviews GET. A boolean, a missing seal, a `REQUEST_CHANGES` verb, or a submitter mismatch does not open the draft.

The #1763 host adapter binds the App publisher user id and login, fills review authors from the authenticated GET, reserves publication on the incumbent EventStore, and passes this typed final check. That binding is source-only. No installed GitHub App, Executive handler, worker START, formal review, or Slack production proof follows from it.


## Authenticated socket source preflight and per-repository policy — R15

The incumbent Executive socket owner now accepts exactly one source path:
legacy `source_guard`, or the concrete `GitHubReviewSourcePreflight` through
`source_preflight`. The latter binds 1–32 explicitly enrolled singleton
repository/settings/API triples. Repositories are unique case-insensitively
because v1 decisions contain no installation field. Each authenticated API must
match the binding's exact active installation and repository; no reader or
credential fallback is attempted.

Manual and human-lifecycle decisions require a fresh, sufficient collaborator
permission before the fresh PR read. Standing-policy and reconciliation
sources instead require their exact installation and enabled host-policy
digest; bot provenance never becomes human authority. Every source requires
an open, same-repository PR at the frozen head. Draft eligibility remains
limited to explicit label/comment review.

`PreparedReviewSourceCheck` carries the complete closed decision and an
unrenewable observation interval of at most three seconds, starting before
network reads. It is a host-local capability, never a field supplied by a
socket caller. GitHub reads run once before admission and outside the Runtime
writer transaction. Both existing commit fences verify the same full decision,
local host arm/enrollment, exact automatic policy and original deadline.
Expiry while waiting for the writer lock or revocation at either fence leaves
no new Job/event. This bounds the age of observed GitHub facts; it cannot
promise instantaneous remote revocation after the read.

The host-local enrollment guard is mandatory and must be free of network,
credential and database I/O. Replacing enrollment must revoke its existing
generation fence before accepting more work. The prepared result is private
to one request, never a shared last-request cache.

The incumbent Executive process constructs the preflight from its own exact
API/settings/enrollment bindings, then supplies both `source_preflight=preflight`
and `automatic_policies=preflight.automatic_policies` to the same socket owner.
The separate reconciliation execution-reference guard remains required.
No prepared capability crosses the public webhook or socket boundary. This immutable bounded map keys each policy by exact
`(installation_id, repository)`. It is mutually exclusive with the legacy
singular `automatic_policy`; absent pairs and an explicitly empty map deny
automatic admission with no fallback. Mutating the original supplied mapping
does not revoke its installed copy; use the existing host arm/enrollment fence
or replace the owner under the incumbent host's configuration custody.

Slack parent reservation and capture retain the same source eligibility
checks. Capture rechecks the prepared deadline after authenticated Slack
readback, before the existing recorder. These are the existing pre-reserve and
pre-record boundaries; R15 does not add a new after-lock check inside the Slack
writers. Unknown send/record effects keep their original one-attempt owners.

The 614-test review-system suite passes, including actual GitHub API adapter
calls, real Runtime writer-lock fences and a local Unix-socket admission with
one QUEUED Job and zero Attempts. This does not install the held Executive
handler or prove live credentials, worker START, GitHub publication or Slack
delivery.


## Shared webhook route for exact repository receivers — R14

Compose one `GitHubReviewReceiver` per repository/active installation, then pass
those existing objects to `GitHubReviewASGIMount(receiver_map=...)`. Up to 32 exact
bindings share the same literal path, host, TLS posture and maximum body size.
The mount copies the mapping and rejects ambiguity at construction. It never
widens a receiver's policy or selects a second receiver after any refusal or
unknown effect.

Public repository/install hints select only an already-enrolled receiver. The
original signed bytes and unchanged scope/headers reach that receiver's normal
signature and current-source checks. Duplicate JSON keys and nonfinite values
refuse before any secret read. Unknown or disabled tenants on an active route
receive a refusal; they cannot select the incumbent application's auth path.
An empty/all-disabled map and unrelated routes preserve the incumbent app.

Routing has four transient read/parse slots with a bounded body budget. The
slots are released before any response or downstream credential/admission call.
Fragmentation does not accumulate per-chunk storage or cause quadratic replay.
Per-receiver admission/visibility capacity remains with the receiver. A host
settings replacement is refused before queued credential selection and before
admission; enrollment changes require deliberate recomposition.

For the R15 Executive source preflight, keep one active reader per repository:
legacy v1 decisions do not carry installation identity. Bind the same exact
repository policies to the receiving socket owner. Shared HTTP routing alone
does not bind or activate that Executive consumer.

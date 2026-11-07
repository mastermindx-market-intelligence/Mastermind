# Automatic independent PR review: coverage and rollout

Task tree: [2026-11-02 GitHub review coverage](plans/2026-11-02-github-review-coverage.md).
Integration and release evidence: [Mastermind #1740](https://github.com/mastermindx-market-intelligence/Mastermind/issues/1740).
Original source baseline: `7e87f225a4ed03e3b89169f7b7c9052c6a6eac9c`; current resumed procedure pin: `b2326bbe30e9988d26199f5e774a482b9c09068a`. R8 and R10–R13 extend the same PR #1977 and source operation.
This is source behavior and a rollout specification. It is not an installed-service or production review receipt.

## Existing owners and intended outcome

Reuse the incumbent GitHub decision/ingress, Executive Runtime admission and result records, Fabric workers, GitHub review publisher, and Slack dialogue transport. There is no additional queue, watcher, retry controller, reviewer database, or provider selector.

The intended rollout covers Mastermind, macro, and mastermind-terminal. Enrollment of each repository is a separate observed configuration fact. Every open PR should ultimately have a visible disposition; every eligible current head should receive one independent review. Required CI, formal GitHub approval, merge ownership, and production verification remain separately observable.

The source now provides lifecycle admission, an explicit standing repository-policy mode for bot-sender events, and bounded authenticated reconciliation of already-open PRs. The installed consumer, repository enrollment, qualified worker capacity, formal approval, and live delivery proof remain release dependencies.

## Implemented lifecycle decision behavior

`ReviewHostSettings.allow_lifecycle_review` and `ReviewIntentPolicy.allow_lifecycle_review` default to `False` and require actual booleans. The separate `allow_repository_policy_review` flag also defaults to `False`. The host projects both into the existing decision policy and includes them in its secret-free configuration receipt. Existing receiver and publication gates remain in effect.

| Delivery or condition | Behavior |
| --- | --- |
| `pull_request/opened`, `synchronize`, `reopened`, `ready_for_review`; lifecycle flag off | `AUTOMATIC_REVIEW_DISABLED` before authenticated GitHub reads or ledger inspection |
| Same actions; flag on; allowed human sender with freshly verified sufficient permission; open, same-repository, nondraft PR | Existing admission path, using authoritative current PR facts |
| Lifecycle event in human-actor mode with no current permission | `ACTOR_PERMISSION_NOT_REVERIFIED`; static actor fallback cannot authorize this channel |
| Revoked or insufficient permission | `ACTOR_PERMISSION_INSUFFICIENT` |
| Unlisted human or observed GitHub bot sender in human-actor mode | `ACTOR_NOT_AUTHORIZED`; bot identity is retained, never converted to a human |
| Lifecycle event with both automatic flags enabled and an enrolled repository/install | Standing host policy authorizes the review; the actual signed sender remains provenance; authenticated current PR facts are still required |
| Authenticated existing-owner reconciliation with both flags enabled | List bounded open PR pages, re-read each PR, and use the same canonical admission identity without fabricating a webhook or human actor |
| Draft lifecycle event | `PULL_REQUEST_DRAFT`; existing authorized label/comment advisory remains available |
| Closed PR, fork, wrong signed PR identity, invalid signature, wrong repository or installation | Existing refusal; no review admission |
| Lifecycle and manual events for the same repository/PR/head | Same deterministic command identity; existing Runtime deduplicates |
| New authoritative head | New ordinary review identity; old result cannot satisfy that revision |

The HTTP receiver retains `status: REFUSED` and adds the closed decision `reason` when available. A refusal is not a retry instruction or permission to select another identity.

A bot-authored PR can receive an authorized human-triggered review or an automatic review under enrolled repository policy. A bot sender never acquires human collaborator authority. Manual label/comment/review-request channels retain their existing human and current-permission requirements.

### Canonical admission and transport

New `JOB_CREATED.provenance` records preserve the complete validated original decision and the SHA-256 of the normalized job objective. Exact replay still checks the original payload. A distinct authorized trigger for the same repository/PR/head joins that immutable admission and returns its original decision and job ID. Three concurrent origins are arbitrated by the existing unique command index; no additional queue or table is introduced.

The strict v1 decision remains available for manual/human-authorized deliveries. The v2 decision carries the actual automatic origin, installation ID, and digest of the applied host policy. Authenticated reconciliation additionally carries the existing owner's real execution reference, with no sender or delivery ID. The receiving socket owner must independently bind the same policy and, for reconciliation, an execution-reference guard. Payload text and a digest-shaped string alone confer no authority.

Legacy jobs lacking the full recorded decision return `ADMITTED_DECISION_UNAVAILABLE` with their existing job identity. They are not redispatched or attributed to a later trigger, and they do not prevent a scan from processing other PRs. Slack and publication joins reject substitution of a later decision for a recorded original.

Job objectives contain exact source references and bounded untrusted excerpts. Their JSON-escaped text is capped at 3,000 bytes so long descriptions and non-ASCII content fit the existing 8,192-byte frame and 4,000-byte objective fences. All original text is validated before excerpting. The worker must retrieve the complete diff and affected files at the frozen head/base and the complete PR context; excerpts cannot establish coverage. Missing full source requires `BLOCKED_BY_CURRENT_SOURCE`.

## Independence and publication

A review must be a fresh run by an actor that did not implement the candidate. A different model name alone is insufficient. Preserve repository, PR, head and base commits; builder and reviewer execution identities; author/committer conflicts; changed-file coverage; actual tests; requested and served model where observable; retained result digest; and publishing identity.

The privileged GitHub publisher remains separate from untrusted PR code and reviewer execution. Do not execute PR-head code with GitHub App credentials. PR text, comments, and apparent approval statements remain untrusted input.

The incumbent publisher maps `PASS` to `COMMENT`. It does not expose `APPROVE`. A successful technical review comment cannot satisfy a required GitHub approval. A genuine eligible non-author must independently determine and submit any required formal review through the governed GitHub path.

Publication remains bound to the reviewed commit and fresh PR facts. Read back the resulting review identity, author, state, and commit. If the head changes, the old review remains historical evidence and does not count for the new revision. Preserve atomic publication reservation and original-operation reconciliation after an uncertain write; never repeat a POST merely because its response was lost.

## Provisional model policy

Use the existing Model Router and Capacity contracts. This assessment does not change pool enrollment or establish successful provider execution.

| Candidate | Verified public capability | Published API input / output per 1M tokens | Initial role |
| --- | --- | --- | --- |
| `glm-5.3` | Text; 1M context; tools and structured output; mandatory reasoning | $1.40 / $4.40 | Provisional default substantive review |
| `grok-4.7` | Text/image; 500K context; tools; reasoning through xhigh | $2.00 / $6.00 below the higher-context threshold | Different-family second review for sensitive changes or disagreement |
| `glm-5.3-flash` | Native multimodal input; 1M context; tools and mandatory reasoning | $0.15 / $0.50 | Preliminary review; low-risk acceptance only after qualification |
| `MiniMax-M3.1-Flash` | Native multimodal input; 1M context; reasoning through max | $0.15 / $0.60 | Economical challenger, qualified alternative, and visual review candidate |

Official sources checked for this assessment: [GLM-5.3](https://docs.z.ai/guides/llm/glm-5.3), [GLM-5.3-Flash](https://docs.z.ai/guides/vlm/glm-5.3-flash), [Z.ai pricing](https://docs.z.ai/guides/overview/pricing), [Grok 4.7](https://docs.x.ai/developers/models/grok-4.7), [MiniMax text generation](https://platform.minimax.io/docs/guides/text-generation), and [MiniMax M3.1 Flash announcement](https://www.minimax.io/blog/minimax-m31f). Prices and aliases can change; reverify before enrollment.

For an illustrative 100K uncached input tokens and 10K billed output tokens, those rates imply $0.184 for GLM-5.3, $0.260 for Grok, $0.020 for GLM Flash, and $0.021 for MiniMax Flash. These are arithmetic examples, not measured costs per PR. They exclude extra turns, repeated context, tool charges, retries, and infrastructure.

Choose from actually admitted, qualified capacity. Subscription quota, concurrency, replenishment, and successful-review yield matter alongside API prices. An admitted BytePlus GLM Flash route may preserve flagship Z.ai capacity, but only if the actual served model and harness are qualified. Do not switch credentials, plans, or providers to reproduce a refused or uncertain operation.

Record actual served versions where the provider exposes them. Z.ai currently documents aliases such as `glm-5.2`/`glm-5.1` routing to GLM-5.3 and `glm-4.7` to GLM-5.3-Flash; different requested aliases do not prove model diversity. [Z.ai DevPack](https://docs.z.ai/devpack/overview)

### Risk routing and qualification

Ordinary code changes receive one qualified semantic reviewer. Authentication, authorization, deployment, CI privilege, review automation, consequential financial calculations, and publication/retry changes warrant two genuinely independent substantive reviews from different model families plus relevant deterministic checks. The second review uses existing explicitly authorized review mechanisms; it must not bypass same-head deduplication.

Use Flash immediately for preliminary classification and evidence preparation. Let a Flash model satisfy a low-risk review requirement only after it passes the same frozen qualification set. No defect-detection benchmark was run as part of this source extension, so GLM is a provisional default, not a measured winner.

Evaluate approximately 40–60 blind historical PRs and controlled mutations, including clean controls. Cover stale heads, permission revocation, races, retries, numeric errors, null/zero confusion, timezone boundaries, unsafe CI, incomplete diffs, and prompt injection. Measure high-severity recall, false clean verdicts, precision, coverage, completion, p50/p95 time, and actual cost. Qualify by risk category and requalify after material model, alias, harness, or context-policy changes.

## Slack Dots: one assignment and one review identity

Follow [SESSION_INDEPENDENT_REVIEW_ROUTING.md](SESSION_INDEPENDENT_REVIEW_ROUTING.md) in the existing `#github-independent-reviews` channel (`C0CAUK8P8S3`). Do not create a second bot, Slack queue, or review state machine.

Select one currently available, authorized Dot with repository access and no author conflict. Give it the canonical GitHub brief, exact head/base, existing operation identity, scope, acceptance questions, prior findings, and required return. Treat delivery, PICKUP_ACK, START, terminal findings, and formal GitHub publication as separate evidence.

The Dot must independently inspect the candidate and reach its own conclusion. Asking it to echo a Fabric PASS is insufficient. If it has an eligible independent GitHub principal and the governed capability, it can submit the formal review itself. Verify GitHub review ID, account identity, state, explicit commit, and current PR head. If it lacks that capability, retain its technical findings and leave the formal review missing.

Use the original thread for subsequent findings and coordination. An unacknowledged mention, Slack reaction, display name, or membership proves neither reviewer execution nor GitHub approval. A pending, uncertain, or refused Fabric review must be reconciled on its original operation; do not reroute it through a Dot.

## Repository-policy and backlog source contracts

### Standing repository-policy authority

Unattended bot-sender coverage uses the existing host's `allow_repository_policy_review` setting together with lifecycle enablement, exact repository/install allowlisting, and the current installation-scoped GitHub reader. The digest identifies the applied nonsecret policy; it is not a separate grant record. The configured Executive admission/source guards remain authoritative and run before admission and at commit. Receiver and socket policy must match. Turning off the relevant host gate prevents new admissions.

Installation and administrator enrollment remain separate observed facts. An installation ID, a webhook signature, or a caller-provided digest alone does not authorize paid review work. No additional policy database or grant registry is introduced.

Each current host composition binds one repository and one active installation. Its derived policy narrows the configured installation allowlist to that active installation, matching the secret and authenticated API reader. A signed payload naming a different allowlisted installation is refused before authenticated reads. Operation across all intended repositories remains a separate enrollment and R9 proof requirement.

### Existing PRs and missed events

`GitHubReviewReceiver.reconcile_open_pull_requests` is an internal callable for the existing authenticated operation owner. It has no HTTP route or timer. The default pass reads at most two pages of 25 PRs; all invocations are limited to 100 PRs. Listing uses a fixed repository-scoped GET and bounded numeric pagination, never arbitrary Link-header destinations. Each listed PR is re-read immediately before decision.

The v2 receipt records outcomes, pages observed, isolated read failures, starting scope, elapsed time, enumeration completeness and page/PR continuation hints. A failed individual PR read is retained while unrelated PRs continue. `complete` describes enumeration; `all_sources_observed` additionally requires no missing source and a complete pass beginning at page one without a within-page resume. Neither field claims worker execution or accepted review coverage.

A cooperative 30-second budget (maximum 60 seconds) stops new operations between bounded ports. A successful owner guard cannot consume the budget and then start another read/admission. Budget exhaustion or a source-wide rate/auth/server deferral preserves the current or incoming same-page PR hint, avoiding repeated work on the prefix. The hint is applied to a fresh page; if it is absent, that entire page is examined. A potentially uncertain admission stops with its exact command identity and no automatic continuation hint. A known legacy admission remains existing/incomplete and does not block unrelated PRs. GitHub pagination is not a stable snapshot; the existing owner retains continuity and starts later sweeps at page one. There is no installed recurring scan or new cursor store.

Policy revisions do not change the ordinary repository/PR/head identity. A new head creates a new review; another review of the same head requires the existing separately authorized rerun contract. Forks and automatic drafts retain explicit refusal/defer behavior.

## Remaining fork and formal-approval scope

Forks remain refused under the present source policy. Future coverage requires a reviewed, bounded source-read path that does not expose privileged credentials to fork code. Report forks as observed but uncovered until that policy is installed and proven.

The current service does not automatically APPROVE. A future service-account approval policy requires separate identity eligibility, reviewer provenance, coverage and quality qualification, reviewed publication rules, and administrator-controlled activation. Do not reinterpret comments, labels, or checks as required approval.

## Release gates and acceptance

The latest #1740 production checkpoint reports an older installed control release and a missing GitHub review frame consumer. It also records a platform safety-denied `control_plane/executive_service.py` modification. This source extension does not retry that effect or provide another route to it. The service owner must resolve the original held effect through the applicable controls before installation can proceed.

The existing service/App administrator must then:

1. Verify the lawful source release and installed consumer, preserving the incumbent listener and Runtime.
2. Verify the intended GitHub App/installation, repository access, exact subscriptions, HTTPS webhook route, and approved signing/private-key custody.
3. Enroll receiver/publication/lifecycle policy and the appropriate human or standing-policy mode deliberately, beginning with one repository; bind the internal reconciliation owner separately.
4. Verify model admission, independent execution provenance, and eligible Dot/GitHub identities.
5. Prove a real delivery causes one canonical Job, actual independent Fabric START and retained result, exact-head findings publication, and the matching original Slack-thread reply.
6. Prove a genuine independent formal GitHub review when required.
7. Prove duplicate delivery, changed head, revoked permission/grant, absent reviewer, capacity limits, malformed signature, and uncertain publication behavior.
8. Validate the R8 policy and reconciliation source on the installed consumer, then prove both bot-sender and already-open PR coverage before claiming all-PR automation.
9. Enroll the remaining repositories only after readback of the preceding gates.

Preserve required CI, approval counts, code owners, stale-review handling, and merge ownership. Rollback disables new automatic admissions through the existing policy gate while reconciling in-flight operations normally.

Completion requires real GitHub -> existing Executive/Fabric -> GitHub -> Slack evidence. Unit tests, a queued Job, a provider name, and merged source are not substitutes for that proof.

## Current route qualification observation — 2026-11-03 UTC

The original Fabric gateway was correlated by generation to the installed `fabric-c3-570f6f34` owner on m2studio. Its installed backend hash matched its manifest, and the native generation's state/lanes aliases resolve to the original owner. An exact artifact census for the older `github-review-coverage-20261102-c2-review01` found no retained request, refusal, launch, process or result record. Historical execution absence remains unproven; the missing evidence is the original frontend/controller receipt. No replacement review was launched.

A distinct read-only GLM preflight for the new R8 qualification scope (`github-review-coverage-20261102-c2-r8-qualify01`) returned native exit 75 with no eligible remote mode. One diagnostic repeat retained the same 250-byte stderr digest, `ff7b0899fc04cd41a0889f7865aace03f77e084b63d89c2964594cc5dd6b3bd5`; it submitted no provider work. Registry/telemetry read at 02:17:26Z showed:

| Native GLM host | Observed admission obstacle |
| --- | --- |
| m1 | One active lane meets the effective ceiling of one; GLM is also qualification-only |
| ubuntu0 | 66.5 GB free, below the 75 GB floor including staging reserve |
| ubuntu1 | 69.2 GB free, below the 75 GB floor |
| ubuntu2 | Lane occupancy unknown under a reconciliation hold, despite 279 GB free |
| ubuntu3 | 3.8 GB free, below the 75 GB floor |
| ubuntu4 | GLM and other supported modes are qualification-only despite sufficient disk space |

These are dated eligibility observations, not a permanent capacity assessment or a platform safety-denial receipt. No actual served model/harness or independent reviewer START was established. Restore capacity through the existing host owners and requalify a route; do not lower thresholds, clear holds, or substitute Codex/Work merely to make a request succeed.

## Reliability and throughput hardening — R10–R13

The existing source owners now implement the following behavior. These are
source contracts and hermetic qualification targets, not production receipts.

| Condition | Bounded behavior and recovery |
| --- | --- |
| Fresh publication review GET or final PR/source read fails | No publication reservation or POST; a later authorized invocation can perform fresh preflight |
| Database wait ages publication preflight | Three-second monotonic freshness guard inside the acquired transaction refuses before creating the claim |
| Claim committed but process/ACK becomes uncertain | Original claim remains sticky; elapsed time does not authorize another POST |
| Original POST landed, ACK lost, head later changed | Exactly one matching historical review can confirm the old effect from its stored body digest and original publisher; no new POST and no coverage of the new head |
| Old v1 unconfirmed reservation lacks publisher provenance | Preserve uncertainty; do not invent the original publisher from current configuration |
| Concurrent publication callers | Existing unique command transaction selects one POST owner; others reconcile |
| Transient GitHub GET failure | At most two same-token, same-origin attempts share a three-second operation budget; short backoff only |
| Rate limit, server Retry-After, permission or token-source failure | Global scan deferral; advisory delay retained, shared pacing rechecked before every network attempt; no credential/provider substitution |
| Oversized, compressed or slow-drip response | Stream cap and per-chunk deadline checks; one-MiB GitHub JSON and 64-KiB token responses; close early |
| Slow webhook admission | Four active operations maximum; busy before credentials/ports; timeout retains capacity until actual worker exit; budget checked before starting admission |
| Slow Slack projection | Two separate best-effort slots; known GitHub admission ACK proceeds; explicit scheduled/deferred visibility receipt; no hidden durable notification queue |
| Unknown Slack POST or result reply | Existing one-attempt owner remains authoritative; no blind resend or claim of successful Dot pickup |

The production publication hot path uses exact indexed claim/confirmation reads,
so its cost does not grow by loading the entire publication namespace. Historical
recovery also avoids unnecessary current-head/result work once the original
effect has already been confirmed. The runtime still performs fresh source and
permission reads wherever they are required; no cache turns stale facts into
permission to publish.

Network and scan deadlines are cooperative. They stop new work and check each
raw transport chunk; they do not assert that cancellation can undo a synchronous
socket effect. Automatic provider continuation is not added by these changes.

### Existing task-level and provider gates

Read the actual current [native selection owner](../ops/native_fabric/quota_continuity/candidate/pick.py)
and [Fabric contract](../integrations/studio_direct_mcp/FABRIC.md), not a provider
name or an old routing-table excerpt. Semantic review uses `task_class=review`.

| Complexity | Review use and current qualification |
| --- | --- |
| C0 mechanical | Inventory and deterministic evidence preparation; cannot substitute for semantic review |
| C1 routine bounded | Small conventional changes with a qualified semantic reviewer and retained coverage |
| C2 complex bounded | Cross-file behavior, concurrency, privilege and retry changes, including this integration |
| C3 frontier judgment | Difficult unresolved architecture with the actual frontier escalation witness |

Full GLM at C0/C1/C2 requires the native economic escalation witness; C3 requires
the frontier witness. Grok leaf labor has its corresponding witness gate unless
a current applicable quota-priority exception exists. MiniMax review requires
known subject-provider provenance and cannot review GLM-family work under the
current directional restriction. GLM Flash and full GLM share a provider family,
so they are not independent merely because the requested model strings differ.
The actual native mode controls optional turn-limit support; a ceiling is not
new retry permission.

Strict pool/model pins disable cross-provider/model quota continuation. Ordinary
unpinned routing may use the existing bounded continuation only after proven
pre-task capacity rejection, unchanged task digest, cleanup and released lease,
within the original deadline and at most three sequential attempts. Authentication,
permission, spend, policy refusals, partial execution and unknown effects do not
qualify. Broad AUTO is not a request-scoped four-model allowlist; this integration
does not add a second candidate selector. Any future constrained candidate set
belongs in the existing Router/Capacity contract and applies prospectively.

Slack Dot review remains one explicit authorized assignment through the existing
dialogue owner, with actual recipient, thread, pickup, START and findings receipts.
Delivery/timeout alone does not choose a replacement or establish GitHub approval.
Automated Dot dispatch and recovery of an old Slack reservation without retained
original rendering/publisher evidence are not claimed by this source patch.

### New route preflight observation

The separate `github-review-coverage-20261102-c2-hardening-api01` task reached the
original installed manual-route preview and stopped before native task-request
dispatch. Its preview observation at 2026-11-02 21:58:13 America/Vancouver exited
75 with zero stdout. The original owner is gateway generation
`59a4851b-97a7-433f-b0b1-e992d35d0050`, profile `fabric-c3-570f6f34`; selected backend
SHA-256 is `98bddb9adaa5e98ae5e3a73e8e051141aceeeb47476551c2247f0fc85481b2b3`.
The retained preview-output digest is
`560fce9374277e92c2597d289c94026842ecda6c8700081f2d7977093dc56069`.

The wrapper discarded preview stderr, so the exact native eligibility reason is
unknown. The outer `INVALID_ARGUMENT` label does not prove malformed task input.
This read-only preflight evidence is not reviewer START, permission to repeat the
request, or resolution of the older `review01`. No provider work was credited.

[Merged #1959](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1959)
adds prospective native request-refusal diagnostics under the existing capacity
owners. It does not establish installed preview-stderr diagnostics or this
consumer's actual caller qualification. Installation and live proof remain with
the original #1829/#917/#1957 owners; this integration does not replay their held
effects through another carrier.


## R15 authenticated source and multi-repository policy qualification

The concrete `GitHubReviewSourcePreflight` removes the former unspecified
network-backed socket guard dependency. One fresh read pass precedes Runtime
admission; both writer-transaction fences perform only local current-arm,
enrollment/policy and observation-age checks. The maximum three-second window
starts before the network reads and never renews, including while waiting for
the writer lock. It prevents admission after stale or locally revoked evidence,
without claiming instantaneous remote GitHub revocation.

Each of up to 32 source bindings has one exact repository, active installation,
authenticated API and mandatory local current-enrollment fence. A repository
cannot select among multiple readers. The socket's immutable
`automatic_policies` map uses exact `(installation_id, repository)` keys so
heterogeneous repository policies stay separate. Missing/empty map entries
refuse automatic work; the old singular-policy path remains compatible when
no map is configured. Each public host composition now rejects empty or
multiple repository settings before constructing credentials or API ports.

Qualification on the original C2 source owner: **614 passed in 37.83s**,
covering all `tests/test_github_review_*.py` and
`tests/test_delivery_review_readiness.py`. Retained output:
`/tmp/github-review-r15-full-tests.log`, SHA-256
`27313062368b904e81499dcb43b7d6f8891346af38e2e5e5ff14eb77e41ba3da`.
The suite covers actual adapter calls outside database locks, expiry and
revocation rollback, manual/lifecycle/standing-policy distinctions, cross-
request misuse, multiple repository policies and legacy callback compatibility.
Parent architecture QA found no blocking source issue; it is not independent
release acceptance. R14 shared-route ingress is still a separate in-flight
Fabric patch proposal at this checkpoint, not claimed implemented here.

### Automatic Dot assignment boundary

The existing Slack visibility adapter announces an already-admitted Job; it
does not assign a Dot. The existing dialogue engine transports an established
dialogue, while its company binding requires an active Attempt, busy worker and
qualified profile/session. An ordinary A0/READ GitHub root is not an eligible
orchestration delegation root, and an explicitly unbound session has no alias
fallback. A Slack reply alone is not an authenticated worker result.

Automatic Dot execution therefore still requires an incumbent Runtime/Capacity
initial-assignment and authenticated-return contract for the same Job,
mutually exclusive with Fabric assignment. No mention, notification or ACK is
promoted to START by this source. For the current rollout, use qualified Fabric
for automatic work and an explicitly authorized Dot session for supplemental
independent assessment. Neither an uncertain Fabric operation nor a missing
formal approval is resolved by silently assigning the same work elsewhere.


## R14 shared-route multi-repository source — verified

`GitHubReviewASGIMount` now accepts an optional host-owned `receiver_map` of exact
`(installation_id, canonical_repository)` keys to already-composed receivers.
The legacy single-receiver argument remains compatible; single and map forms
are mutually exclusive. Empty and wholly disabled maps leave the incumbent
application untouched. Once a map is active, unknown or disabled selections
refuse and never fall through to incumbent OAuth/MCP handling.

Enrollment is bounded to 32 receivers. Each value is the exact receiver class
with exact immutable host settings and one repository. The active installation
and derived singleton policy must match the map key; a broader configured
installation allowlist never becomes additional routing authority. Duplicate
and case-folded tenant collisions, one receiver reused under different keys,
mutable settings and mismatched host/TLS/body-limit envelopes refuse during
construction. The map is copied and immutable. Host configuration changes must
recompose through the incumbent owner; replacing a retained receiver's settings
is refused, including at the queued admission boundary before credential
selection. Admission uses the same captured settings for secret identity and
policy and rechecks it before admission.

The shared route validates the literal path, raw path/query, method, host, TLS,
headers and declared length before reading a body. Strict JSON hint parsing
rejects duplicate keys, malformed/nonfinite values and unusable identities.
Only one pre-enrolled receiver can be selected. Its ordinary HMAC, current
GitHub source, policy, admission and Slack owners still decide eligibility;
there is no authenticated shortcut or receiver fallback.

Four routing slots bound body collection and parsing. The two-second routing
body budget is checked again after parsing. Slots are released before response
sending, credential/API calls or downstream admission, so one slow tenant does
not occupy other tenants' parsing capacity. Empty/tiny fragments accumulate in
byte-bounded storage and replay once as the exact original body bytes; network
chunk boundaries are not part of HMAC identity. Scope and headers are unchanged.
The selected receiver retains its existing four admission and two visibility
slots. These are per-receiver pressure bounds, not provider quota or a new queue.

The original MiniMax Fabric task returned a 64,336-byte patch proposal with
verified terminal lineage (`rc=0`, `signal=ok`). Parent qualification exposed
**10 deterministic regression failures** in that proposal: cross-tenant
blocking, slow refusal responses, mixed disabled fallback, mismatched body caps,
fragment retention, unbounded map input, subclass replacement and settings drift.
Those defects were corrected in the parent source. The raw proposal is not
accepted as a correct final artifact; terminal transport success is distinct
from source acceptance or an independent review.

Final combined qualification: **691 passed in 43.88s across 28 files**, every
`tests/test_github_review_*.py` plus delivery readiness, on the original C2
workspace. All five transferred R14 files were hash-verified before the run.
Output `/tmp/github-review-r14-full-tests.log`, SHA-256
`2bc96e1ffb3ae799b1e89710fce3b7d8bc83f01661dd29368f16584e0a102b2a`.
This includes the concrete R15 source preflight, actual local sockets/Runtime,
publication recovery and original-thread Slack tests with synthetic external
services. It remains source qualification, not installed all-repository proof.


## Risk-tier pre-admission consumer — source-only 2026-11-03

Accepted Mastermind #1989 merged into protected master at `910803421beca53ca25145392725ab2d84c7a8e9`. This #1977 source branch retains the accepted immutable risk policy/reader/dispatch source blobs and adds only the incumbent-host consumer integration. It does **not** enroll/install the receiver, grant credentials, change PR Ready/labels, merge anything, activate an automatic review watcher, or create a second Job/scheduler.

- `integrations/github_review_risk_consumer.py` binds the existing installation-scoped `GitHubReviewAPI` to an exact approved intent and verified PR head; automatic decisions use the accepted source census and fresh final GET, while authorized manual review costs zero risk GETs.
- The existing signed ingress and original reconciliation call the same `admit_decided_review` commit boundary with the risk hook *before* any new Executive Job. FAST is an explicit `SKIPPED_NOT_REQUIRED` (no Job/visibility notice); STANDARD/CRITICAL preserve the original canonical command; unknown, stale, malformed, permission-denied or incomplete source holds before a new Job. An already-existing canonical command is checked through the incumbent EventStore/Executive socket, not hidden by a subsequent FAST result.
- `compose_github_review_host` binds the risk consumer to its existing GitHub App object; no independent transport, account, token, database or side-effect plane is introduced. The receiver stays default OFF pending release qualification and actual host enrollment.
- Source acceptance tests: focused risk, signed ASGI webhook, canonical admission, reconciliation, lifecycle and multi-repository suites passed (300 tests; command captured on the C2 original source carrier). The legacy composition test requiring real local `PyJWT` could not obtain its mock GitHub App token because this M2 `python3` lacks the `jwt` module; this is an **environment dependency failure before GitHub source reads**, not a verified deployment result. Do not claim every test/environment passed.
- **Unresolved performance gate:** the candidate reuses the collector's final authenticated PR read after complete file pagination, eliminating a redundant extra GET. A one-page signed AUTO decision therefore requires three risk-source GETs after the existing admission path's first PR GET (four serial GETs total, not the previous five). The first and final risk snapshots must match; identity/freshness and the incumbent six-second webhook deadline still bind. The original pre-effect deadline guard prevents late Job creation. This is source/test evidence only; slow-path latency and installed p50/p95 remain unproven. No timeout extension, stale snapshot reuse, second reader or retry permission is introduced.

No real webhook, Fabric Job, protected merge, production site, app setting or PR status was changed by these source-level tests.

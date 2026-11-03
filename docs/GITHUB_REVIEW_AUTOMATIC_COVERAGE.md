# Automatic independent PR review: coverage and rollout

Task tree: [2026-11-02 GitHub review coverage](plans/2026-11-02-github-review-coverage.md).
Integration and release evidence: [Mastermind #1740](https://github.com/mastermindx-market-intelligence/Mastermind/issues/1740).
Source baseline: `7e87f225a4ed03e3b89169f7b7c9052c6a6eac9c`.
This is source behavior and a rollout specification. It is not an installed-service or production review receipt.

## Existing owners and intended outcome

Reuse the incumbent GitHub decision/ingress, Executive Runtime admission and result records, Fabric workers, GitHub review publisher, and Slack dialogue transport. There is no additional queue, watcher, retry controller, reviewer database, or provider selector.

The intended rollout covers Mastermind, macro, and mastermind-terminal. Enrollment of each repository is a separate observed configuration fact. Every open PR should ultimately have a visible disposition; every eligible current head should receive one independent review. Required CI, formal GitHub approval, merge ownership, and production verification remain separately observable.

The current source extension provides automatic eligibility for selected lifecycle deliveries. It does not complete unattended bot-sender or existing-PR coverage, formal automated approval, service installation, or live delivery proof.

## Implemented lifecycle decision behavior

`ReviewHostSettings.allow_lifecycle_review` and `ReviewIntentPolicy.allow_lifecycle_review` default to `False` and require actual booleans. The host projects the flag into the existing decision policy and includes it in its secret-free configuration receipt. Existing receiver and publication gates remain in effect.

| Delivery or condition | Behavior |
| --- | --- |
| `pull_request/opened`, `synchronize`, `reopened`, `ready_for_review`; lifecycle flag off | `AUTOMATIC_REVIEW_DISABLED` before authenticated GitHub reads or ledger inspection |
| Same actions; flag on; allowed human sender with freshly verified sufficient permission; open, same-repository, nondraft PR | Existing admission path, using authoritative current PR facts |
| Lifecycle event with no current permission | `ACTOR_PERMISSION_NOT_REVERIFIED`; static actor fallback cannot authorize this channel |
| Revoked or insufficient permission | `ACTOR_PERMISSION_INSUFFICIENT` |
| Unlisted human or observed GitHub bot sender | `ACTOR_NOT_AUTHORIZED`; bot identity is retained, never converted to a human |
| Draft lifecycle event | `PULL_REQUEST_DRAFT`; existing authorized label/comment advisory remains available |
| Closed PR, fork, wrong signed PR identity, invalid signature, wrong repository or installation | Existing refusal; no review admission |
| Lifecycle and manual events for the same repository/PR/head | Same deterministic command identity; existing Runtime deduplicates |
| New authoritative head | New ordinary review identity; old result cannot satisfy that revision |

The HTTP receiver retains `status: REFUSED` and adds the closed decision `reason` when available. A refusal is not a retry instruction or permission to select another identity.

A bot-authored PR can receive an authorized human-triggered review. A bot-sender lifecycle event does not acquire human collaborator authority. The implementation intentionally keeps observation and authorization distinct.

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

## Capabilities still required for all-PR coverage

### Standing repository-policy authority

Unattended bot-sender coverage needs a separately reviewed standing grant in the existing authority system. Bind exact repository ID/name, App installation and current access, protected policy revision and approving authority, permitted review action, target branches/events, draft/fork policy, resource limits, enablement, and revocation. The policy authorizes admission; the webhook sender remains provenance. Preserve existing manual-request authority checks.

The source extension does not introduce this grant. An installation ID or valid webhook signature alone does not authorize paid review work.

### Existing PRs and missed events

Extend the existing authorized reconciliation owner to enumerate open PRs using authenticated current facts and compare their heads with existing admission records. Reuse repository/PR/head identity. Do not manufacture signed webhook deliveries, add another scheduler, or create a second ledger.

The reconciled input needs an explicit reviewed contract and policy provenance. A policy change must not silently duplicate the ordinary review for a head; use the existing authorized rerun contract when another review is required.

### Forks and formal automated approval

Forks remain refused under the present source policy. Future coverage requires a reviewed, bounded source-read path that does not expose privileged credentials to fork code. Report forks as observed but uncovered until that policy is installed and proven.

The current service does not automatically APPROVE. A future service-account approval policy requires separate identity eligibility, reviewer provenance, coverage and quality qualification, reviewed publication rules, and administrator-controlled activation. Do not reinterpret comments, labels, or checks as required approval.

## Release gates and acceptance

The latest #1740 production checkpoint reports an older installed control release and a missing GitHub review frame consumer. It also records a platform safety-denied `control_plane/executive_service.py` modification. This source extension does not retry that effect or provide another route to it. The service owner must resolve the original held effect through the applicable controls before installation can proceed.

The existing service/App administrator must then:

1. Verify the lawful source release and installed consumer, preserving the incumbent listener and Runtime.
2. Verify the intended GitHub App/installation, repository access, exact subscriptions, HTTPS webhook route, and approved signing/private-key custody.
3. Enroll receiver/publication/lifecycle policy deliberately, beginning with one repository; do not infer enrollment from source defaults.
4. Verify model admission, independent execution provenance, and eligible Dot/GitHub identities.
5. Prove a real delivery causes one canonical Job, actual independent Fabric START and retained result, exact-head findings publication, and the matching original Slack-thread reply.
6. Prove a genuine independent formal GitHub review when required.
7. Prove duplicate delivery, changed head, revoked permission/grant, absent reviewer, capacity limits, malformed signature, and uncertain publication behavior.
8. After the separately reviewed standing-policy and reconciliation capabilities exist, prove both bot-sender and already-open PR coverage before claiming all-PR automation.
9. Enroll the remaining repositories only after readback of the preceding gates.

Preserve required CI, approval counts, code owners, stale-review handling, and merge ownership. Rollback disables new automatic admissions through the existing policy gate while reconciling in-flight operations normally.

Completion requires real GitHub -> existing Executive/Fabric -> GitHub -> Slack evidence. Unit tests, a queued Job, a provider name, and merged source are not substitutes for that proof.

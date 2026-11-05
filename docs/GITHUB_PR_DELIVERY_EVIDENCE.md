# PR delivery evidence through the existing GitHub owner

Status: implemented source; not installed autonomous delivery. Parent programme:
Mastermind #2074 / `pr-delivery-recovery-20261105-sol-001`. The parent plan is
`docs/superpowers/plans/2026-11-05-pr-delivery-recovery-fabric.md`.

## User outcome and architecture

A delivery operator can distinguish a stale Draft, an unfinished implementation,
a completed source candidate, a real hold, and an already-Ready integration
problem without equating any of them with green CI or a completed product.
This slice supplies fresh source-record evidence and an exact next diagnostic;
it does not pretend metadata alone can adjudicate implementation completeness.

`GitHubReviewReceiver.inspect_pull_request_delivery` is an internal callable
behind the existing enrolled host and reconciliation-owner guard. The existing
host composition supplies its one `GitHubReviewAPI` to
`GitHubPRDeliveryConsumer`. The API retains its installed authentication,
repository fence, bounded HTTP reads, pacing and error/effect behavior.
`control_plane/github_pr_delivery_evidence.py` projects immutable observations;
`control_plane/github_pr_lifecycle.py` remains the readiness/disposition owner.
No HTTP route, webhook, scheduler, database, reviewer, worker, queue, credential
reader, API client or GitHub mutation is added.

## Four separate questions

1. **What changed?** Path footprint: tests, documentation, executable/style
   source, research/design artifacts and other. A `.py` or `.tsx` path is not
   proof of working implementation. Documentation can be an intended deliverable.
2. **What did we actually read?** Full bounded PR text, all enumerated paths,
   issue comments, inline review comments and reviews. Numeric pagination,
   declared counts, duplicate IDs and before/after source identity are checked.
   Complete metadata is never full code/test review. GitHub file enumeration
   can be capped; exhaustion is explicit, not assumed.
3. **What has an authorized source owner qualified?** Optional exact-head
   `DraftReadinessFacts` plus the `source_evidence_digest` of the actual source/hold observation. The digest
   binds evidence, not identity or authority. The trusted caller must already
   hold source/custody/qualification authority; PR-authored text cannot provide
   it. The exposed host read method does not accept qualification input.
4. **What prevents delivery?** Possible restriction references, actual observed
   failures, missing evidence, source movement and integration state. Required
   CI, genuine formal review, release permission, merge and installed consumer
   acceptance remain independent existing-owner facts.

## Liveness without invented safety gates

A pending CI run does not disqualify a locally qualified candidate from Ready.
CI enrichment is optional and defaults OFF in the installed review-host
composition: its existing token requests contents/read and pull_requests/write,
not checks/read or statuses/read. The consumer does not request wider grants or
probe inaccessible endpoints. A separately qualified existing host may enable
CI observations only with its actually enrolled source permission. Source-record
coverage and CI-observation coverage are reported independently. Missing CI is
unknown, never green, and is not invented as a Draft-readiness prerequisite.

Restriction text is a conservative *hint*, not a new authority. Full bodies and
all bounded discussion surfaces are inspected, including text beyond the old
16,000-character review excerpt. A historical `HOLD-RELEASED` or generic mention
cannot release a real hold. Conversely, after the authorized source owner has
adjudicated the exact observed evidence and supplies matching qualification,
a heuristic mention cannot create a permanent new hold. A stale or absent
source-evidence digest produces no qualified readiness advice. CI progress, reactions,
and auto-merge enrollment change the full audit digest but not unchanged source
qualification. New heads, bases, source/body/title/label changes and changed
restriction/review evidence invalidate the source binding. Existing explicit
NEVER_MERGE, actual Draft holds, active source writers, unknown effects,
incomplete scope and stale qualification continue to fail closed in the owner.
The concurrent ACTIVE-workstream/source-writer repair remains on its incumbent
#2074 continuation, not shadow-edited by this consumer.

## Bounded use

The existing host owner calls, for one enrolled repository:

```python
report = receiver.inspect_pull_request_delivery(
    owner_execution_ref=existing_execution_ref,
    pull_number=original_pr_number,
    expected_head_sha=observed_head_sha,
    max_pages=3,
    time_budget_seconds=30.0,
)
```

The owner guard runs before GitHub reads. Maximum page bound is 30 per collection;
maximum cooperative budget is 60 seconds. Each request keeps the incumbent
transport's own timeout. A shared credential, permission or rate-limit deferral
propagates without fallback; no new retry is created. The observation is not an
atomic GitHub snapshot: revalidate the actual source and action-specific gates
at any later mutation. Head/body/base/label/state movement during the scan is
explicitly unqualified. No raw PR title/body/comment or token is returned in the
report. References and evidence digests support inspection without copying prose
into instructions.

All reports have `release_authorized=false`; required-check and formal-approval
satisfaction remain unknown. An observed APPROVED review is not proof of reviewer
independence or required policy. Closed/merged source asks for consumer verification,
not a second merge. Ready/behind routes to the incumbent integration mechanism,
not a repeated auto-merge request. Source-only evidence must not be presented as
an installed service or a completed backlog-recovery programme.

## Qualification and rollout boundaries

Hermetic tests exercise the real existing API transport with synthetic HTTP,
the existing host owner guard, pagination, exact-head binding, rate/budget stops,
late-body holds, duplicates, unknown states, large real GitHub IDs, old statuses,
forks, malformed input, source movement and qualified readiness. No protection is
removed to pass tests. The isolated test environment adds the repository-pinned
PyJWT extra; it does not modify global packages or production services.

Real-source captures for Mastermind #2074, Macro #6423 and Terminal #1294 exercise
the projection against authenticated live GitHub data. These are live-source
read/replay evidence, **not** an installed GitHub App or runtime-host canary.
The retained verification report names the heads, timestamps and digests.
No original PR status, label, review, queue, code or deployment was changed.

Protected release, existing-host installation, actual App/config/grant readback,
owner-authorized live invocation and action consumption must be proven separately.
The reader does not install or enable that host. #2064 retains release-policy
ownership, #2066 retains durable orchestration/Wake, and the existing repository
release controllers retain merge execution. Do not replace those incumbents.

## Exact-source composition with the incumbent readiness repair

The separate #2078 head `7e47f3667e8b25c3d9e9206f4e0f861d72390299`
repairs the known ACTIVE-programme/source-writer conflation. Its exact lifecycle
blob is SHA-256 `3106a3e68515305a99c6615273fb92220b8493da03276b610d8bb688fc40040b`.
The consumer was tested against that inspected module in memory, without changing
its original branch or copying the repair into this PR: 131 joint-source tests
passed, including a source-qualified ACTIVE programme and five genuine negative
gates; lifecycle closure still KEEP_ACTIVE. This is composition proof, not formal
approval, protected release or installed runtime proof.

The live qualified-Ready path needs that incumbent repair (or its accepted
semantic equivalent) before ACTIVE-programme readiness is claimed. The read-only
source evidence remains useful independently; this PR does not silently override
the current readiness owner or create its own active-work policy.

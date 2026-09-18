# Web CEO immutable commission publication

Status: **SOURCE CANDIDATE / BUILT_NOT_PROVEN / NOT INSTALLED**

This runbook defines the bounded publication/lookup seam for complete Web-CEO worker
briefs. It does not change the public `submit_ceo_intent` schema, grant execution
authority, arm COO autonomy, install Studio Direct, or activate a provider.

## Outcome

A Web CEO should not wrap another agent's complete prompt inside a long generic shell
command. The complete brief is data, published once through the existing attended Web
workspace/Git ownership; the Executive request remains the small typed semantic and
authority envelope.

```text
operation_key
  -> existing attended workspace operation_id = operation_key
  -> canonical branch sol/web-<operation_key>
  -> fixed file research/executive_commissions/COMMISSION.md
  -> typed commit + exact-head push
  -> trusted host resolves the branch by re-deriving the automated intent identity
  -> exact branch-head commit + fixed path + SHA-256 becomes existing commission_ref
  -> CeoIngress re-observes before the first root mutation
  -> worker independently verifies/fetches the exact immutable blob before provider work
```

## Publication contract

1. Choose the same valid `operation_key` that will be sent to the existing Executive
   App `submit_ceo_intent` tool.
2. Acquire/reuse the existing attended Web workspace with that value as its
   `operation_id`. The canonical workspace owner derives `sol/web-<operation_key>`;
   the model does not choose a branch.
3. Write the complete bounded worker brief to exactly:

   `research/executive_commissions/COMMISSION.md`

   The brief may contain product context, implementation method, acceptance evidence,
   scope/non-goals, failure/null behavior and handoff detail. It does **not** grant
   authority; the eventual Executive Job grant remains controlling.
4. Publish with the existing typed Git status/commit/push path once that source is
   protected and installed. Do not encode the brief in `start_process`, a heredoc,
   shell arguments, environment variables, or `submit_ceo_intent`.
5. Only after exact remote-head publication is proven, submit the compact CEO intent
   with the same `operation_key`.

## Trusted source resolution

`GitHubWebCommissionSourceProvider` reads only the fixed public Mastermind repository and
only the `refs/heads/sol/web-*` namespace. For each branch suffix it runs the already
canonical pure identity functions:

```text
app_request_ref(operation_key)
automated_intent_id(request_ref)
```

The unique suffix whose derived `intent_id` equals the strict-v2 admission identity is
the only eligible source branch. `work_ref` never selects a branch. Invalid operation
suffixes are ignored; zero exact matches means source absent; more than one exact match
is a hard ambiguity refusal.

The provider snapshots that branch's exact 40-hex head, fetches only the fixed commission
path at that immutable commit over credential-free HTTPS from the fixed GitHub raw host,
enforces the 512 KiB/UTF-8/NUL bounds, computes SHA-256, and returns the existing
`mastermind.executive_dialogue_source/v1` shape. CeoIngress already observes and then
re-observes the provider immediately before first root mutation, so a moving branch is a
zero-Job conflict rather than a mutable commission.

No workstream-to-commission registry, host mapping table, Slack inference, title lookup,
latest-branch guess, database, queue, credential, caller-selected URL/ref/path, or second
lifecycle is created.

## Consumer boundary

The worker consumer is a separate release gate. Candidate PR #811 teaches the existing
sealed-worker and Operator supervisors to consume the existing `commission_ref`, keep it
subordinate to the effective Job grant, and materialize verified bytes non-writable. A
post-release Web branch commit is normally absent from the installed credentialless
worker clone, so the consumer must support one exact, credential-free fixed-host read by
commit/path and verify the persisted digest before provider work.

## Production wiring gate

The source provider is intended to be injected through the **existing**
`ceo_ingress_dialogue_source_provider` seam. The installed host composition currently has
no such provider. Do not create another ingress daemon/socket or import an integration
implementation into `control_plane/**`; the incumbent host-composition owner must wire the
provider when its current source custody is clear.

A production acceptance canary owes all of these as separate evidence:

- typed commission publication reaches the exact `sol/web-<operation_key>` remote head;
- compact `submit_ceo_intent` remains source-free on the wire;
- trusted provider resolves and re-observes one exact immutable source;
- one strict-v2 root is admitted with that source in durable provenance;
- one real worker consumes the exact bytes while its Job grant remains authoritative;
- terminal result returns through the existing Executive result path;
- no generic giant shell payload, duplicate lifecycle, retry/failover or Chairman message
  shuttle is required.

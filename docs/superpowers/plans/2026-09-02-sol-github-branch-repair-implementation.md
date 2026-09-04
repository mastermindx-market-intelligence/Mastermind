# Sol GitHub Exact Branch Repair — Accelerated Implementation Program

**Program operation:** `mastermind-sol-capability-fabric-ghp1-20260902-sol-001`  
**Protected pickup:** `mastermindx-market-intelligence/Mastermind@068b83883915919802894fc9c31e7e7757100eb9`  
**Carrier:** `sol/sol-capability-fabric-ghp1-20260902`  
**Architecture:** `docs/superpowers/specs/2026-09-02-sol-github-branch-repair-design.md`  
**Cognition:** `COGNITION_ROUTE: CHAT_PRO_DEFAULT`  
**Current source outcome:** pure compiler `BUILT_NOT_PROVEN / PRODUCTION_INERT`

This plan deliberately collapses architecture freeze and the first executable core into one carrier.
It does not create a second records-only pre-wave. The remaining work is two bounded vertical waves:
one source-complete owner app and one production canary/install wave.

---

## 1. Program outcome

Make ChatGPT Sol capable of repairing a small, exact defect inside a large existing file on an already
bound GitHub PR branch without reconstructing the file in model context and without dispatching a
worker solely for patch tooling.

The full user journey is:

```text
inspect exact operation/PR/source context
-> prepare exact old/new replacements
-> preview deterministic server-side full-file result
-> commit once against expected head
-> reconcile exact GitHub effect
-> continue normal CI/review on the same PR
```

---

## 2. Current carrier — GHP1 pure compiler

### Exact paths

```text
control_plane/github_exact_edit.py
tests/test_github_exact_edit.py
docs/superpowers/specs/2026-09-02-sol-github-branch-repair-design.md
docs/superpowers/plans/2026-09-02-sol-github-branch-repair-implementation.md
```

### Observable capability

Given trusted complete file snapshots and an exact edit request, code now deterministically produces
bounded previews and complete post-images while refusing stale, ambiguous, unsafe, binary, protected,
non-unique, overlapping, oversized, or out-of-PR-scope edits.

### Proof required before GHP1 release

```text
python -m pytest -q tests/test_github_exact_edit.py
python -m py_compile control_plane/github_exact_edit.py tests/test_github_exact_edit.py
full repository CI and security analysis
exact changed-path census
independent exact-head technical/security review
```

The focused local matrix currently covers the >10,000-line target, immutable public projection,
byte preservation, Unicode/CRLF, carrier/writer/PR/head/blob/path fences, protected paths, mode and
encoding, unique anchors, overlap, secret-shaped payload, bounds, permutation-stable compilation,
digest sensitivity, and effect-free imports.

### Stop condition

GHP1 stops at pure compilation. It performs no GitHub API call, token signing, OAuth, MCP registration,
app publication, deployment, or production mutation.

---

## 3. GHP2 — owner app source vertical

**Future operation:** `mastermind-sol-capability-fabric-ghp2-20260902-sol-001`

```text
COGNITION_ROUTE: CHAT_PRO_DEFAULT
PREFERRED_AVENUE: CTO Sol
WHY: the architecture is frozen, but the bounded implementation spans exact GitHub evidence,
     prepared-token cryptography, OAuth principal binding, GraphQL effect semantics, and MCP schemas.
WHY NOT FABLE: there is no unresolved product or cross-company architecture ambiguity; the work is a
               concrete security-sensitive repository vertical with deterministic acceptance tests.
RECEIVER_BINDING_MODE: CAPACITY_SELECTABLE
PLACEMENT_STATE: WAITING_CAPACITY / needs_placement
```

### Observable mission

A hermetic MCP call through an injected fake GitHub owner must resolve one exact open PR, fetch complete
large-file bytes, compile an exact edit, return an authenticated prepared preview, commit at most one
`createCommitOnBranch` request, and reconcile `APPLIED | NOT_APPLIED | EFFECT_UNKNOWN` without any
generic GitHub, filesystem, or shell authority.

### Authority/document precedence

1. current live Chairman intent;
2. current protected Skillpack and protected Mastermind source at GHP2 pickup;
3. protected SCF F0/GH0 contracts and any protected GH1/GH2 implementation;
4. protected GHP1 architecture/compiler;
5. existing Business MCP auth/resource-server architecture;
6. this bounded plan.

A newer colliding source or same-path carrier returns to Sol. Do not reset/rebase/force over it.

### Required archaeology at pickup

- re-read current protected `docs/sol_skills/INDEX.md` and required procedures from one exact commit;
- census current SCF GH1/GH2, Business app/auth, plugin-generation, and GitHub action owners;
- reuse the accepted owner-specific prepared-token implementation if one exists by then;
- confirm no current branch/PR owns the exact GHP2 operation or paths;
- verify the current OpenAI full-MCP and GitHub GraphQL contracts from official sources.

### Default exact scope

Use one new privilege-separated package unless current archaeology identifies an accepted GitHub app
owner to extend:

```text
integrations/mastermind_github_app/__init__.py
integrations/mastermind_github_app/schemas.py
integrations/mastermind_github_app/adapter.py
integrations/mastermind_github_app/github_port.py
integrations/mastermind_github_app/prepared_token.py
integrations/mastermind_github_app/server.py
tests/test_mastermind_github_exact_repair.py
docs/superpowers/plans/2026-09-02-sol-github-branch-repair-implementation.md
```

The final worker may reduce this path count by reusing existing accepted modules. It must not widen to
Executive/Agent OS lifecycle, Slack, RuntimeBinding, Capacity, merge, runner, deployment, or app-admin
families.

### Closed tool surface

Prefer namespaced tools:

```text
github_repair_target        R0
github_repair_prepare       W1
github_repair_commit        W1
github_repair_reconcile     R0
```

`github_repair_prepare` takes only:

```json
{
  "operation_key": "...",
  "expected_head_oid": "...",
  "files": [
    {
      "path": "control_plane/example.py",
      "expected_blob_oid": "...",
      "replacements": [
        {"old_text": "exact unique text", "new_text": "exact replacement"}
      ]
    }
  ]
}
```

Repository, branch, PR, GitHub App installation, and credential are not model arguments.

`github_repair_commit` accepts only the prepared token. `github_repair_reconcile` performs no write.

### GitHub owner port

Define a closed injected port whose fake and live implementations support only the minimum calls:

```text
resolve_exact_operation_carrier(operation_key)
read_pull_request_exact(pr_ref)
read_branch_head(repository, branch)
read_complete_changed_paths(pr_ref)
read_file_blob(repository, head_oid, path)
create_commit_on_branch(expected_head_oid, additions, message, client_mutation_id)
read_commit_and_target_blobs(commit_oid, paths)
search_exact_effect_correlation(operation_key, carrier_ref, compilation_digest)
```

No method/URL/body passthrough. No arbitrary GraphQL document supplied by the model. The live port owns
one static reviewed query/mutation set.

### Carrier resolution

The adapter must establish one exact active operation-to-PR carrier and one current writer from
accepted source evidence. A PR body containing the operation key is candidate evidence only. Multiple
plausible carriers, incomplete search coverage, stale current-writer evidence, or an operation payload
conflict returns `UNKNOWN`/`REFUSED`; newest or loudest never wins.

If protected GH2 `operation_evidence` exists, consume it. Otherwise implement only the minimum pure
operation-evidence gatherer needed for this one action family and leave its deterministic classification
in the accepted SCF semantic owner. Do not fork GH1 release law.

### Prepared token

Reuse existing owner-local signing primitives if present. Otherwise implement a narrowly scoped token
with:

- authenticated encryption or signature using app-local key custody;
- fixed algorithm and key ID;
- app/schema/policy/principal/operation/carrier/action bindings;
- expected head and complete changed-path digest;
- exact per-file before/post digests and normalized replacements;
- compilation digest, commit message digest, issue time, expiry, confirmation requirement;
- no durable token store and no cross-app verification.

Tests use injected deterministic keys/clock. Production keys come from the accepted secret owner and
never from tool input, model context, GitHub, argv, or logs.

### GraphQL mutation

One static mutation only:

```graphql
mutation ExactBranchRepair($input: CreateCommitOnBranchInput!) {
  createCommitOnBranch(input: $input) {
    commit { oid }
    ref { name target { oid } }
  }
}
```

Variables are built exclusively from token-bound server state. `fileChanges.additions` carries the
compiler's complete post-images encoded with standard padded base64. There are no deletions. The
mutation uses the exact expected head and one deterministic client mutation ID derived from the stable
operation/carrier/action identity.

### Commit gate

Immediately before the single mutation:

1. authenticate the exact ChatGPT app principal and scopes;
2. verify current organizational/action-target authority required by the accepted app generation;
3. verify token signature, generation, policy, principal, expiry, and confirmation;
4. re-resolve the same unique carrier/current writer;
5. re-read open PR, non-default/non-protected branch, head, complete changed paths, and each target blob;
6. require byte-for-byte equality with every token-bound precondition;
7. prove no unresolved prior effect for this operation/carrier/compilation;
8. issue at most one mutation;
9. read canonical branch/commit/blob state and classify the effect.

A token cannot select another repository, branch, PR, credential, path, payload, or commit message at
commit time.

### Effect matrix

| Situation | Receipt |
|---|---|
| preparation refused before network write | `NOT_APPLIED`, attempts 0 |
| expected-head mutation rejected and old head remains | `NOT_APPLIED`, attempts 1 |
| exact commit/head/post-image readback succeeds | `APPLIED`, attempts 1 |
| response lost after possible send and readback inconclusive | `EFFECT_UNKNOWN`, attempts 1 |
| same operation called again while effect unknown | `PRIOR_EFFECT_UNKNOWN`, attempts 0 |
| reconcile later proves exact commit | `APPLIED`, reconciled true |
| reconcile later proves no exact commit | `NOT_APPLIED`, reconciled true |

No automatic retry or alternate transport exists.

### Required tests

RED first, then implementation. At minimum:

- static MCP tool census and schema digest;
- unknown fields, oversized arrays/strings, malformed OIDs/paths, secret-shaped values refuse;
- model cannot provide repository/branch/PR/credential/GraphQL/URL;
- operation carrier none/conflict/incomplete/writer conflict fails closed;
- full >10,000-line blob is fetched internally while response remains bounded;
- GHP1 compiler errors map to stable public categories without raw content;
- prepare performs zero mutation and token binds every load-bearing field;
- token tamper, wrong principal/generation/policy/action/expiry refuses;
- head/blob/path/PR/protection movement between prepare and commit refuses before mutation;
- exactly one static GraphQL mutation and standard padded base64 full post-images;
- mutation success without readback is not automatically `APPLIED`;
- transport loss after send produces `EFFECT_UNKNOWN` and blocks second call/failover;
- reconciliation performs zero write and proves exact post-image digests;
- logs/errors contain no token, source body, post-image, auth header, private path, or raw GraphQL vars;
- adapter/schema remain importable without MCP SDK; only `server.py` imports `mcp`;
- no lifecycle/store/scheduler/queue or Executive/Agent OS mutation;
- full repository and security CI;
- independent exact-head adversarial review.

### GHP2 stop condition

Stop at `BUILT_NOT_PROVEN / PRODUCTION_DISARMED` with fake-port end-to-end proof. Do not install a
GitHub App, mint a real installation token, deploy/tunnel the server, publish a ChatGPT app, mutate a
real branch, or claim Business availability.

### GHP2 continuation packet

Return exact base/head, changed paths, schema/tool digests, RED-to-GREEN receipts, focused/full CI,
independent review, mutation-attempt census, secret scan, effect-unknown proof, current source movement,
and the one remaining GHP3 admin/install action.

---

## 4. GHP3 — Business install and real-path proof

**Future operation:** `mastermind-sol-capability-fabric-ghp3-20260902-sol-001`

```text
COGNITION_ROUTE: CHAT_PRO_DEFAULT
PREFERRED_AVENUE: CTO Sol
WHY: bounded deployment, credential, app-generation, and real GitHub/ChatGPT canary work after source
     and schemas are frozen.
WHY NOT FABLE: the production ceremony and falsifier are exact and do not require principal product
               architecture.
RECEIVER_BINDING_MODE: CAPACITY_SELECTABLE
PLACEMENT_STATE: WAITING_DEPENDENCY until GHP2 is protected and independently approved
```

### Observable mission

From one real ChatGPT Business conversation, use the private approved custom app to patch one unique
line in a >10,000-line file on a disposable draft PR branch and prove all positive/negative/effect
reconciliation controls.

### Installation sequence

1. Create or reuse one least-privilege GitHub App installation owned by the accepted GitHub app admin
   path. Repository access is restricted to the canary repository/Mastermind as approved; permissions
   are the minimum required for contents read/write and PR metadata reads.
2. Install app-local signing/encryption key through the accepted secret owner. No secret enters chat,
   GitHub, Slack, Linear, Agent OS, argv, screenshots, or receipts.
3. Deploy the exact approved server build through the accepted remote Business app path or Secure MCP
   Tunnel. Record build, policy, schema, and app-generation digests.
4. In ChatGPT Business developer mode, create a private draft app bound only to the exact MCP server.
   Inspect the frozen tools and action annotations before enabling the write action.
5. Create the disposable branch/PR fixture through a separately authorized setup route.
6. Run positive, stale-head, path-scope, protected-branch, and effect-unknown/reconciliation controls.
7. Independently inspect GitHub canonical evidence and close/remove the disposable carrier.
8. Publish only after security review and the exact canary pass; otherwise keep private/disarmed.

### Production proof packet

```text
mastermind.github_exact_branch_repair_proof.v1
app/generation/schema/server/policy digests
ChatGPT workspace and principal digests
GitHub App and installation digests
repository / PR / branch / before head / resulting commit and head
fixture path / before blob and content digest / after content digest
compilation and prepared-token digests
APPLIED receipt
stale-head NOT_APPLIED receipt
EFFECT_UNKNOWN -> reconciled terminal receipt
mutation attempt counts
unchanged-content control digest
PR path-set control
protected/default branch controls
cleanup result
source refs and failures
```

No credential, full file, full GraphQL variables, private host path, or raw model transcript is in the
proof packet.

### GHP3 acceptance

The exact branch-repair capability becomes `PROVEN_LIVE` only when:

- the ChatGPT tool call traverses the actual published/private app and production server;
- one large-file repair is canonically applied exactly once;
- unrelated bytes are proven unchanged;
- stale-head and forbidden-scope attempts produce zero effect;
- ambiguous transport is reconciled without duplicate mutation;
- no default/protected branch or out-of-PR path moves;
- app action permissions and confirmation behave as reviewed;
- cleanup is complete or truthfully `PARTIAL_CLOSEOUT`;
- final Sol acceptance names the exact capability ceiling.

### GHP3 stop condition

Do not widen to file creation/deletion/rename, merge, review, workflow rerun, repository settings,
runner actions, deployment actions, or a generic GitHub MCP. Each would require its own existing owner
and separate acceptance contract.

---

## 5. Program closeout

After accepted GHP3 proof:

- GitHub records exact source, PR, CI, review, app/deployment evidence, and canary commits;
- Agent OS records the capability decision, proof, limitations, discoveries, and next action;
- Executive OS records only any actual runtime Job/Attempt lifecycle used by operators;
- Linear may project the selected portfolio state;
- Slack records transport only;
- the next fresh Sol can recover the state without this conversation.

The exact next expansion should be evidence-driven. If surgical repairs regularly exceed V1 bounds,
measure refusal reasons before widening. Do not preemptively add shell, unified-diff fuzz, more files,
new-file creation, or protected-path access.

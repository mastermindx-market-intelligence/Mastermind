# Business Sol Marketplace Sync + One-Cockpit Canary Hardening Amendment

> **For agentic workers:** this is a records-only amendment to the accepted Business Sol program. It creates no workspace, marketplace, plugin, app, OAuth, MCP, account, RuntimeBinding, Executive, Slack, Linear, Agent OS, credential, or production effect.

**Program:** Business Sol Surface Convergence  
**Carrier:** Mastermind PR #236 / `sol/business-sol-surface-convergence-plan-20260829`  
**Applies to:** BSC-P1, BSC-SHADOW1 Stage 3, BSC-U1, and later app-bound plugin generations  
**Verification date:** 2026-08-29  
**Capability:** `SPEC_ONLY / RECORDS_ONLY`

## 1. Why this amendment exists

Current OpenAI Business platform behavior adds a material supply-chain and rollout condition that the earlier plan did not freeze strongly enough:

- workspace admins and owners can import a plugin marketplace from a public or private GitHub repository;
- the import selects a repository URL, optional marketplace-root path, and optional branch, tag, or commit;
- a fixed commit remains fixed, while branch-based marketplaces are eligible for automatic daily sync and manual `Sync now`;
- importing or syncing processes every valid plugin entry in the marketplace catalog rather than asking for a separate approval for every entry;
- future syncs may add newly introduced marketplace plugins;
- newly imported plugins begin with workspace installation/authentication policy applied separately from repository content;
- marketplace import does not grant access to included apps and does not authenticate a member;
- plugin installation, underlying app access, app actions, and user authentication remain separate controls.

This is useful platform capability, but a branch-tracking first canary could silently widen from the reviewed two-plugin P1 payload to later repository content. The first Mastermind Business canary therefore uses immutable source binding and a closed inventory readback rather than automatic update convenience.

## 2. Precedence

Where this amendment conflicts with earlier Business Sol records, precedence is:

```text
this marketplace-sync/canary hardening amendment
→ three-cockpit canary amendment
→ P1 platform-contract amendment
→ P1 self-review amendment
→ parent P1 plan
→ program plan
```

All non-conflicting architecture, authority, security, no-rebuild, and proof requirements remain controlling.

## 3. Immutable first-canary source law

The first one-cockpit skills-only marketplace canary MUST use:

```text
Source repository = exact reviewed Mastermind repository URL
Path              = empty, because .agents/plugins/marketplace.json is at repository root
Revision selector = exact immutable P1 commit SHA
Branch selector   = FORBIDDEN for the first canary
Tag selector      = FORBIDDEN unless the tag is independently proven immutable and resolves to the accepted commit
Sync now          = FORBIDDEN before a later reviewed sync wave
Automatic drift   = zero accepted revision movement
```

The action-time import receipt must freeze:

- repository identity;
- marketplace root path;
- exact immutable commit;
- SHA-256 of `.agents/plugins/marketplace.json`;
- exact ordered plugin inventory;
- each plugin root and manifest digest;
- absence of `.app.json`, `apps`, `mcpServers`, `mcp.json`, and `.mcp.json` in the P1 generation;
- expected web compatibility and absence of a `Desktop only` label;
- importing admin/account and Business workspace identifiers in redacted form;
- selected canary cockpit and the two untouched control cockpits;
- `personal_workspace_merge=false`.

For P1, the only accepted imported plugin names are:

```text
mastermind-sol
mastermind-operator
```

Any third marketplace entry, renamed plugin, changed local path, app reference, bundled MCP declaration, or digest mismatch stops the import or disables the imported result before use.

## 4. Closed post-import readback

Immediately after import, before installation or invocation, U1 records one normalized readback:

```text
marketplace source repository
marketplace path
selected revision selector and resolved commit
sync mode / next scheduled sync when surfaced
plugin inventory and plugin IDs
plugin versions
required apps or app templates
installation policy
web versus Desktop-only availability
workspace/app access state
```

Acceptance requires exact agreement with the pre-import receipt. UI labels, newest timestamps, repository default branch, plugin names, or apparent availability never substitute for the resolved commit and closed inventory.

If the UI does not expose enough information to prove immutable source and inventory, return:

```text
MARKETPLACE_SOURCE_READBACK_INSUFFICIENT
```

and do not install or invoke the package.

## 5. Workspace policy fence

For the skills-only P1 canary:

- keep the plugin generation skills-only;
- do not add or infer an app connection;
- do not treat Business defaults as approval of action capability;
- do not auto-install to the whole workspace merely because the marketplace import succeeded;
- only the selected canary cockpit may perform the bounded invocation proof;
- the two retained Pro cockpits remain unchanged;
- workspace import, plugin availability, member installation, skill invocation, app enablement, app authentication, and app action permission are separate receipts.

If workspace policy cannot isolate the canary sufficiently, the plugin may remain imported but uninstalled/uninvoked while policy is reconciled. Do not widen a Business workspace merely to make the canary convenient.

## 6. App-bound generation law

P1 remains immutable and skills-only. Later app-backed capability is a separately reviewed plugin generation with:

- a new reviewed plugin version;
- a new exact immutable repository commit;
- current supported `.app.json` and manifest `apps` linkage only;
- exact existing underlying app IDs copied from the accepted workspace app records, never guessed or prefix-transformed;
- re-derived capability metadata from the real app tool census;
- explicit app access, authentication, and action-control readback;
- no bundled MCP declaration that would make the ChatGPT-web target Desktop-only.

Do not mutate the accepted P1 commit in place. Do not use a branch sync to smuggle an app-bound generation into the skills-only canary.

## 7. Sync graduation is a separate wave

A later `BSC-P-SYNC1` wave may evaluate branch-based daily sync only after the fixed-commit canary is accepted. That wave must prove:

1. one reviewed source commit advances to one reviewed successor commit;
2. the marketplace catalog and every included plugin are diff-censused before sync;
3. no new plugin, app, template, permission, MCP declaration, or authority surface appears without its own review;
4. a sync request resolves to the expected commit;
5. post-sync inventory and manifest digests match the reviewed successor;
6. rollback to the prior fixed commit or disabling the marketplace is proven;
7. an ambiguous sync result remains `EFFECT_UNKNOWN` on the same marketplace identity and is reconciled before retry.

The first canary does not need automatic sync. Reliability and provenance outrank update convenience.

## 8. Failure states

Fail closed with one of the following exact classes where applicable:

```text
MARKETPLACE_SOURCE_MUTABLE
MARKETPLACE_SOURCE_READBACK_INSUFFICIENT
MARKETPLACE_RESOLVED_COMMIT_MISMATCH
MARKETPLACE_INVENTORY_DRIFT
UNEXPECTED_PLUGIN_IMPORTED
PLUGIN_MANIFEST_DIGEST_MISMATCH
UNEXPECTED_APP_REFERENCE
UNEXPECTED_MCP_DECLARATION
DESKTOP_ONLY_LABEL_UNEXPECTED
WORKSPACE_POLICY_READBACK_MISMATCH
CANARY_COCKPIT_SCOPE_NOT_ISOLATED
EFFECT_UNKNOWN
PLATFORM_CONTRACT_CHANGED
```

No failure authorizes importing from another branch, moving a second cockpit, creating a second marketplace, guessing a plugin/app identity, or retrying an ambiguous mutation through another admin account.

## 9. Proof and completion boundary

This records amendment is complete when reviewed and protected. It makes no Business capability live.

The P1 import canary is accepted only when one selected cockpit proves all of:

- exact fixed-commit marketplace import;
- exact two-plugin closed inventory;
- manifest and marketplace digest agreement;
- web availability without unexpected app/MCP requirements;
- skills-only invocation at the accepted revision;
- zero app authentication or Mastermind runtime mutation;
- retained Personal workspace and two untouched control cockpits;
- bounded disable/uninstall or workspace-switch rollback.

Even that result proves only the fixed-commit skills-only canary. It does not prove automatic sync, app-bound capability, OAuth, Steward/Executive use, RuntimeBinding, production execution, fleet cutover, or final Chairman acceptance.

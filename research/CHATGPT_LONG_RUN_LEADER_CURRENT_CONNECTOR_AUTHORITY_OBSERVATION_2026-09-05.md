# ChatGPT long-run leader — current connector authority observation

**Date:** 2026-09-05  
**Parent operation:** `chatgpt-pro-long-run-leaders-research-20260905-sol-001`  
**Carrier:** Mastermind PR #490  
**Status:** `RESEARCH_EVIDENCE / RECORDS_ONLY / NOT_A_SECURITY_INCIDENT / NOT_A_PERMISSION_CHANGE`

## Observation

The GitHub API readback for PR #490 issue comment `5552174789`, authored through the current ChatGPT GitHub connector, identifies the performing app as **ChatGPT Codex Connector** and reports the installed GitHub App permission set visible in that receipt:

```text
actions         write
checks          read
contents        write
emails          read
issues          write
metadata        read
pull_requests   write
statuses        read
workflows       write
```

The receipt also lists the app's subscribed repository event families. The immutable evidence is the GitHub issue-comment API object for comment `5552174789`; this document does not copy any token, installation identifier, private key, credential, account email, or authorization header.

## What this proves

It proves that the **installed GitHub App grant represented in that GitHub receipt is not read-only**. The connector used by this session can perform GitHub modifications within the separately enforced product/tool and repository boundaries that apply to the current interaction.

This makes the all-reachable-mutator question concrete rather than purely hypothetical: a Mastermind RuntimeBinding refusal at CeoIngress is not itself the GitHub App's authorization check. A claim that a retired ChatGPT session is technically unable to modify GitHub must account for the actual ChatGPT app/tool availability, product approval settings, repository installation scope, GitHub App grant, branch protection, exact action contract, and any stale-session enforcement on that separate path.

## What this does not prove

It does **not** prove:

- that every ChatGPT conversation can access every granted GitHub App action;
- that a stale or retired conversation can still invoke the connector;
- that a write would bypass current ChatGPT confirmation, product policy, repository permissions, branch protection, expected-head checks, or Mastermind procedure;
- that any unauthorized or unintended GitHub effect occurred;
- that GitHub App permission should be revoked;
- that the app grant is excessive for its intended current uses;
- that the same authority shape exists for Slack, Linear, local shell, desktop, or other apps;
- that RuntimeBinding is defective inside the surfaces it actually governs.

No stale-session write, permission mutation, connector reconfiguration, revocation, or security probe was attempted by this research.

## Product and security implication

The production claim must be **capability-specific and path-complete**:

```text
For action class X on target class Y,
every route available to the old and current surfaces
is known and classified as:
ENFORCED | DENIED | ATTENDED_ONLY | UNKNOWN.
```

A broad app-level grant can be compatible with safe operation when the actual product/action surface, human confirmation, branch protection, expected-head rules, and Mastermind owner checks remain effective. It cannot be silently treated as per-chat stale-generation fencing without evidence.

The first response should therefore be evidence and least privilege, not disruptive revocation:

1. inventory actual connected app/tool availability per account/workspace/surface;
2. record app installation scopes and ChatGPT action-control/approval behavior separately;
3. map each modifying action to its enforcing owner and exact target checks;
4. run the synthetic old/current shared-principal authority-coverage falsifier;
5. constrain autonomous claims to the proven set;
6. change a shared connector grant only under a separately authorized migration with preimage, sibling-impact analysis, readback, and rollback.

## Relationship to the current rollout

This observation strengthens Packet 6 / `LRL-C14 all_reachable_mutator_coverage`. It does not block the separately scoped read-only Business Steward canary, which should continue through its existing owner and source/admin gates. It also does not authorize a new GitHub connector, a replacement action plane, a permission database, or a broad account migration.

## Capability delta

Before this observation, the ambient-native-writer concern was an unexecuted architectural counterexample.

After this observation, one current connected-app receipt confirms a real **write-capable GitHub App grant** in the operating environment, while the ability of a stale exact conversation to use that grant remains unproven. The required next evidence is the bounded route-availability and stale-session falsifier, not an assumption in either direction.

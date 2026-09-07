# ChatGPT long-run leader — current connector authority observation

**Observed:** 2026-09-05  
**Corrected:** 2026-09-06  
**Parent operation:** `chatgpt-pro-long-run-leaders-research-20260905-sol-001`  
**Carrier:** Mastermind PR #490  
**Status:** `RESEARCH_EVIDENCE / RECORDS_ONLY / NOT_A_SECURITY_INCIDENT / NOT_A_PERMISSION_CHANGE`

## Observation

The GitHub API readback for PR #490 issue comment `5552174789`, authored through the current ChatGPT GitHub path, identifies the performing app as **ChatGPT Codex Connector**. The receipt includes this `performed_via_github_app.permissions` metadata:

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

## Evidence classification

| Claim | State | Exact boundary |
|---|---|---|
| The issue comment exists and was accepted by GitHub | `PROVEN` | One real issue-comment write on Mastermind PR #490 through the observed connector path. |
| The performing app was ChatGPT Codex Connector | `PROVEN` | Reported by the immutable issue-comment API object. |
| The app object exposed the permission metadata listed above | `PROVEN_AS_APP_METADATA` | This is app registration/configuration metadata returned under `performed_via_github_app`. |
| The specific installation or token held every listed permission | `UNVERIFIED` | The receipt is not a readback of the installation access token's effective permissions. |
| The installation selected every repository in the organization | `UNVERIFIED` | The accepted write proves reachability to this target, not the complete repository-selection scope. |
| Every listed action was exposed by ChatGPT to this conversation | `UNVERIFIED` | Product tool schemas, action controls, confirmation policy and per-surface availability are separate. |
| A stale or retired conversation can still write | `NOT_RUN / UNPROVEN` | No stale-session mutator falsifier was executed by this research. |

## What this proves

It proves that this exact connected GitHub path was **write-capable for one issue-comment effect on this repository at the observed time**. The app object also reported a registration/configuration permission shape containing multiple write permissions.

That is enough to make the all-reachable-mutator question concrete rather than hypothetical. A Mastermind RuntimeBinding refusal at CeoIngress is not itself the authorization check for an independently connected GitHub path. A claim that a retired ChatGPT session is technically unable to modify GitHub must account for actual tool availability, product approval settings, installation and repository scope, effective token permissions, branch protection, exact action contracts and stale-session enforcement on that path.

It is **not** enough to label the entire listed app permission set as the effective grant of the specific installation, token or conversation. Those remain separate evidence obligations.

## What this does not prove

It does **not** prove:

- that every ChatGPT conversation can access every GitHub action named by the app metadata;
- that the specific installation token held every app-level permission shown in the receipt;
- the complete repository-selection scope of the installation;
- that a stale or retired conversation can still invoke the connector;
- that a write would bypass current ChatGPT confirmation, product policy, repository permissions, branch protection, expected-head checks or Mastermind procedure;
- that any unauthorized or unintended GitHub effect occurred;
- that GitHub App permission should be revoked;
- that the app registration is excessive for its intended uses;
- that the same authority shape exists for Slack, Linear, local shell, desktop or other apps;
- that RuntimeBinding is defective inside the surfaces it actually governs.

No stale-session write, permission mutation, connector reconfiguration, revocation or security probe was attempted by this research.

## Product and security implication

The production claim must be **capability-specific and path-complete**:

```text
For action class X on target class Y,
every route available to the old and current surfaces
is known and classified as:
ENFORCED | DENIED | ATTENDED_ONLY | UNKNOWN.
```

Only `ENFORCED` and `DENIED` routes may be included in an autonomous stale-session fencing claim. `ATTENDED_ONLY` is a supported human-confirmed route excluded from that claim. Any `UNKNOWN` route blocks the stronger claim.

A broad app registration can be compatible with safe operation when the effective installation scope, actual product surface, human confirmation, branch protection, expected-head rules and Mastermind owner checks remain effective. App metadata cannot be silently promoted into per-chat effective authority or stale-generation fencing.

The first response should therefore be evidence and least privilege, not disruptive revocation:

1. read the owning GitHub installation/token boundary for effective permissions and repository selection when that evidence surface is available;
2. inventory actual connected app/tool availability per account, workspace and conversation surface;
3. record app registration metadata, installation scope, token scope and ChatGPT action-control behavior as separate facts;
4. map each modifying action to its enforcing owner and exact target checks;
5. run the synthetic old/current shared-principal authority-coverage falsifier;
6. constrain autonomous claims to the proven set;
7. change a shared connector grant only under a separately authorized migration with preimage, sibling-impact analysis, readback and rollback.

## Relationship to the current rollout

This observation strengthens Packet 6 / `LRL-C14 all_reachable_mutator_coverage`. It does not block the separately scoped read-only Business Steward canary or the FS0 Web-to-Mac file/shell pilot, each of which retains its existing owner and action-time gates. It does not authorize a new GitHub connector, a replacement action plane, a permission database, a broad account migration or any permission change.

## Capability delta

Before this observation, the ambient-native-writer concern was an unexecuted architectural counterexample.

After this observation, one immutable receipt proves one real GitHub issue-comment write through the named connector path and exposes the app object's registered/configured permission metadata. The complete effective installation/token grant, repository selection, per-conversation action surface and stale-session reachability remain unverified.

The required next evidence is a bounded effective-scope readback and route-availability/stale-session falsifier—not an assumption in either direction.

---

## 2026-09-07 supersession pointer

**Marker:** `PR490-B1-B5-DIRECT-ACCESS-REPAIR-20260907`
**Preservation:** The September 5 connector-authority observation remains immutable dated evidence and is not rewritten as current runtime truth.

Current host/transport interpretation lives in the supersession register and preserves three separate epochs. The observation grants no permission, installation, source-writer status, or production capability. Authenticated caller identity remains distinct from exact ChatGPT conversation identity.

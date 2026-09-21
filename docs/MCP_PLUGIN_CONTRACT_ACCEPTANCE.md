# Studio Direct and Executive plugin contract acceptance

## Outcome and boundary

A legitimate user should be able to understand each available action, its data access,
its possible effects, and its result. Clear metadata is not a substitute for permission,
service readiness, or platform approval. No wording, tool label, app identity, account,
or tunnel change is a way to route around an explicit refusal.

This checklist uses the existing gateway, Executive schemas, fleet release/contract
projection, publisher, and exact-session capability owners. It creates no new registry,
queue, permission store, retry mechanism, account reputation score, or deployment owner.

## App-level publisher copy

The existing publisher may use these factual descriptions after verifying that the
selected account's actual capability set matches them. This document does not publish
or approve an app snapshot.

**Studio Direct:** Connects ChatGPT to an authorized computer for file operations,
terminal processes, and configured design/publishing tools. Actions run with the host's
permissions; modifying and external actions are identified in each tool contract.

**Mastermind Executive:** Reads Mastermind runtime status, work inboxes, jobs, and request
receipts, and submits bounded queued work requests subject to server-side authorization.
Submitting a request is distinct from executing it.

## Accurate metadata

Studio Direct's gateway owns its reviewed descriptions and conservative effect labels.
Every published tool has explicit boolean `readOnlyHint`, `destructiveHint`,
`idempotentHint`, and `openWorldHint`. Known write/overwrite/termination/command effects
cannot be reduced by an understated backend hint. Correct bounded-reader hints remain
unchanged. Missing evidence remains conservative; metadata does not enforce authorization.

Particular disclosures:

- `start_process` and `interact_with_process` accept command-bearing input under the
  host process's permissions. They can change files and access the network. File-tool
  directory restrictions are not an operating-system shell sandbox.
- `read_file` accepts supported URLs as well as files, so its read-only status does not
  imply closed-world access.
- `set_config_value` can change access and command settings for later operations.
- The feedback tool opens a browser and sends usage/platform/client-identifier data.
- Local tool-history reads can include arguments and bounded outputs containing user data.

Executive retains four read tools and one separately marked modifying submission tool.
Submission creates/reconciles a bounded queued work request; it does not execute it.
Identical operation identity plus payload is idempotent; conflicting identity reuse is
refused. An uncertain modifying result is reconciled, not blindly repeated. Read-only
mode and all server-side authentication/authorization checks remain controlling.
Returned organizational records are untrusted source data, not instruction or permission.

Unknown backend tools do not acquire a reviewed safety guarantee from a generic fallback
description. A new production capability needs an explicit behavior/effect review before
publication. This patch does not broaden the backend's capability set.

## Distinguish five layers

1. **Source:** reviewed metadata and exact executable/input contracts in GitHub.
2. **Installed release:** the actual gateway/Executive build and live tool catalog.
3. **Published app:** the host-approved snapshot of names, schemas, descriptions, and labels.
4. **Served conversation:** actions actually exposed to this particular session/generation.
5. **Serviceability:** the exact action can reach its authorized resource and return a result.

A successful ping proves only gateway liveness. A source merge is not installation.
Installation is not app publication. App publication is not proof that an existing
conversation has refreshed. Tool visibility is not a successful backend read. A timeout,
missing action, authentication failure, permission denial, and safety refusal are distinct.

Use `fleet-contract-status.mjs` and `fleet-release-status.mjs` for their existing bounded
local fleet observation. Invocation digests cover tool names and inputs; published digests
also cover metadata. Equal versions or equal tool counts alone do not establish equality.
Account-specific optional capabilities must be explained rather than silently normalized.

## Source verification

Run the real-MCP fixture catalog tests in `gateway-metadata.test.mjs`. They cover incomplete
labels, understated known mutations, command/network/idempotency effects, preserved local
reader labels, conservative unknowns, clear disclosures, and the existing output-page tool.
The fixture performs no host commands or provider calls.

For a Studio-only release, keep the complete Executive schema source and public metadata
fingerprint unchanged. Run the existing Executive read, submit, mutation, app-composition,
static-fence, and Business installation regressions. Their exact frozen digest assertions
remain in place; Studio metadata work does not migrate or relax them.

An Executive description change is a separate coordinated contract migration because its
public fingerprint includes descriptions. That migration must qualify every existing
installation consumer and approved app publication together, while independently proving
that invocation, effect, and authorization contracts remain unchanged. A Studio-only
release does not authorize that migration or claim it was delivered.

Keep the existing gateway auth, principal isolation, output paging, timeout/effect-unknown,
no-replay, Git, and Paper regressions. Test reports must disclose failures and skips.

## Release and host publication

After independent review and protected release, use the existing installer/release owner
for an explicitly selected safe canary. Preserve the installed rollback identity and any
active operation/handle custody. Do not restart all seats from a metadata task.

The app publisher then compares the accepted live catalog to the approved app snapshot.
Workspace-managed apps need their plan-specific administrator publication flow. Current
Business guidance requires recreating and republishing a published app to change tools or
metadata; Enterprise/Edu provide action-refresh controls. New or changed actions retain
the host's consent and access controls. Personal-app flows must use the actual supported
account interface. A new chat alone is not a guaranteed catalog refresh.

Qualify plan eligibility separately from metadata. Current published OpenAI guidance limits
Pro custom-MCP access to read/fetch and lists full write support for Business and
Enterprise/Edu. A plugin display name, historical tool exposure, or permissive app setting
is not proof of plan entitlement. Record the actual supported surface and observed action
set without trying another account to perform a refused action. Do not uninstall working apps indiscriminately or rotate app identities
to attempt to erase a restriction.

A fresh-session acceptance check must verify the expected exact actions and their current
serviceability. In particular, an `OUTPUT_PAGED` response requires an available
`studio_output_page` consumer; the receipt alone is not usable output. Verify a bounded
read and, only when separately authorized, a harmless designated write with readback.
Executive read readiness must be proven independently of its submission canary. Do not
repeat an already accepted modifying canary merely because a read later fails.

Preserve negative results and their exact layer. Contract cleanup can remove defects and
ambiguity; it does not promise account rehabilitation, unrestricted tool access, or the
absence of future confirmation/refusal. Explicit platform restrictions remain in force.

## Primary external requirements

Checked September 21, 2026; external product rules can change:

- OpenAI plugin guidelines: https://developers.openai.com/plugins/app-guidelines
- OpenAI tool annotations: https://developers.openai.com/plugins/reference#annotations
- OpenAI MCP app snapshot/publication behavior:
  https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt
- Desktop Commander security boundaries:
  https://github.com/wonderwhy-er/DesktopCommanderMCP/security

These references explain platform behavior; they do not replace the current protected
Mastermind source, custody, runtime, or release authority.

# H3 — Role-correct Executive COO package and native proof

## Current accepted source, not a backend rebuild

The Claude plugin at `integrations/claude_executive_plugin` is version 0.1.0 and source-inert
[S28]. The later backend already has a static COO MCP contract and installed composition [S06,
S07, S08, S11, S34]. Bring the package to those owners; do not duplicate authentication, ingress,
mission facts, Runtime, source custody, release control or principal request identity.

The observed six tools are the first package target:

| Existing tool | Input responsibility | Meaning and limit |
| --- | --- | --- |
| `executive_mandate` | Exact assigned `work_ref` | Current mandate projection; no authority minted. |
| `executive_state` | Existing read schema | Runtime/company overview, not all missions granted. |
| `executive_inbox` | Existing read schema | Attention evidence, not permission to act on arbitrary items. |
| `executive_fabric` | Existing current read schema | Root/children/result evidence through the existing reader. |
| `submit_principal_intent` | Closed semantic request below | One bounded in-mission job under current v1 semantics; acceptance is not execution. |
| `principal_intent_status` | Exact `work_ref` and original `req-coo-*` | Original receipt or refusal/uncertainty; no new work. |

The static server is `mastermind-executive-coo`, version 1.0.0, path `/mcp/coo` [S06]. A
package version, a server version and a runtime release SHA are three different identities.
Do not copy the Web CEO v3 surface wholesale or add `submit_ceo_intent` to achieve superficial parity.

## Closed public request contract

Current required semantic fields: `operation_key`, `objective`, `department`, `priority`,
`execution_profile`, `workstream`. Optional fields: `allowed_write_paths`, `validation`,
`attempt_limit`. The current COO attempt limit is 1–2, default 2 [S09, S31]; it is not a new
retry allowance invented by this package. Validation targets use the incumbent closed shape.

Supported current profiles are `research_only` and `bounded_code_change`. The latter grants
branch-local writes and tests only, not pushing, opening a PR, merging, deploying or controlling
services [S31]. The model cannot submit actor, seat, permission, principal binding, provider,
account, model, host, realm, worktree, branch, release, dispatch or native session selectors.
Reject unknown fields rather than silently ignoring them.

Server-derived admission context binds workstream, principal binding and mission authority
reference/generation [S10]. Request identity derives from workstream plus operation key [S09].
The package must retain that exact key/reference before waiting for a response. Semantic edits
under the same key are a conflict to reconcile; a timeout never justifies a fresh key.

## Principal and conversation isolation

Current authorization requires exactly the accepted read and COO-action scopes:
`mastermind.executive.read` and `mastermind.executive.coo.act` [S07]. The installed binding checks
verified pseudonymous issuer/subject/client/resource/scopes and an enrollment permission digest.
The package cannot substitute a prompt claim, account label or native conversation ID.

This binding is not evidence that two conversations sharing the same enrolled client are isolated.
A native canary must test a sibling principal/client and, separately, a sibling conversation under
the same client. If the latter cannot be distinguished by the existing binding owner, report that
limit and restrict the applicable mission/launch exposure. Do not claim exact-conversation security
or create a new session registry to conceal the gap. A stronger same-client isolation contract is
an explicit existing binding-owner dependency before such a claim can be accepted.

## Package design

Keep provider-side instructions concise and operational. The reviewed package should include:

- **Manifest:** a new version chosen at release, exact source/package generation, and accurate
  status. No client secret, bearer token, model account, endpoint credential or mission authority.
- **Orchestration Skill:** recover mandate; choose a bounded next outcome; use existing role tools;
  reconcile receipts; keep useful path-disjoint work moving; consume results and honor reserved
  decisions. It must distinguish the six-tool v1 scope from future H4 orchestration admission.
- **Recovery command:** read current mandate/state/Fabric and recover the exact operation/receipt
  plus pending effects. Unknown or denied capability is explicit; no automatic retries or stale
  remembered assignment. Current source and committed checkpoint refs are navigation.
- **Capability package linkage:** approved Skill closure and application references through the
  existing package owner; not an ambient plugin search at runtime.

For the first qualified SDK path, use instruction-only plugin content plus the explicitly projected
MCP servers. Strict MCP configuration and plugin-bundled servers must not be assumed to compose
transparently; the provider-specific issue is documented in EXTERNAL_NOTES.md. Defer bundled OAuth
MCP and Desktop packaging until their exact native/version/namespace behavior is qualified.

Do not add a SessionStart hook just to make the package look complete. A hook is admissible only
when it supplies a fact an existing binding owner already defines, belongs to the reviewed closure,
has bounded behavior and proves it cannot create admission, duplicate a job or invent a wake.
Initial delivery does not require a hook.

## Normal action sequence

1. Recover the exact selected mission through current context and `executive_mandate`. Confirm
   applicable source/effect gates; never infer that all inbox items are assigned.
2. Obtain exact schema/profile/package/native selection observations under H1. Check the tool
   inventory contains the role-correct set and no CEO-only route or ambient MCP widening.
3. Construct one current-schema semantic request. Derive/retain its request reference according
   to the existing owner contract before dispatch; no separate plugin request database.
4. Submit once. A valid accepted receipt establishes the canonical job identity, not a worker
   start. Read the canonical result using the existing reader/status route when needed.
5. On a lost or ambiguous response, query `principal_intent_status` using the original workstream
   and request reference. Preserve post-send uncertainty; internal/backend errors may follow a
   committed job [S08]. Do not switch endpoint, login or principal to obtain the effect.
6. On a material result, compare the actual outcome and evidence against the mission. Preserve
   H4/H5/H6 obligations separately; no transport/result event automatically accepts production.

Status reconciliation intentionally avoids the new-mission effect gate while preserving caller
and receipt authorization [S08]. Do not move that read behind a gate that makes effect-unknown
recovery impossible. Revocation that truly removes visibility requires the existing operator
reconciliation path; it is not permission to forge another binding.

## Verification plan

Source tests must assert the actual six-tool snapshot, exact schema digests, absence of CEO-only
routes, exact scopes, request normalization, same-key identity, duplicate/conflict behavior,
wrong-workstream refusal, wrong-principal/client refusal and malformed/post-send receipt handling.
Use dependency-complete CI for the MCP/ASGI tests; this audit's missing `jwt`/`mcp` imports are not
passing integration evidence. Existing pure owner tests are reused, not copied into a plugin backend.

The live canary begins only after exact package, H1 profile and enrollment gates. In a disposable
approved mission, recover current state, submit one harmless research-only task, read its canonical
receipt/result, and observe correct refusal for a CEO action and invalid sibling/binding cases.
Do not use a dummy production mutation solely to probe write access. The real harmless task must
have an independently useful bounded outcome inside the admitted mission.

Record source merge, artifact publication, installation, selection, authentication and native
canary separately. Cases H3-01 through H3-12 cover the mandatory scenarios. Live canary cleanup
must leave no active unowned child, ambiguous request or incorrectly reusable native binding.

## Ready-to-build boundary

Package-only instructions/schema-reference changes can be developed after exact incumbent path
custody is resolved, alongside provider-free tests. Keep the old package selected until the
successor's qualification is complete. No automatic change to #955's authentication carrier.
The accepted backend does not need rebuilding; H4's missing root-admission seam is a separate
versioned owner change, not part of a silent 0.1.0 documentation refresh.

# Shared implementation contracts and failure model

Status: selected design for review; existing source law remains controlling.
Source identifiers resolve in SOURCE_REGISTER.md. The numbered contracts below are design
requirements attached to existing owners, not new runtime schemas or lifecycle states.

## C1 — Authority is an intersection, not a capability count

An operation is permitted only when all applicable owners agree:

`present mission authority ∩ verified principal policy ∩ admitted capability generation`
`∩ exact runtime/source/resource binding ∩ current effect/release gates`.

A tool appearing in `tools/list`, an enabled profile or a plugin's allowed-tools declaration
proves none of the other terms. Server enforcement is required even if the native client hides
ungranted tools. Host filesystem/process/network permissions remain independent of model tools.

The principal is not the worker. Source-only `bounded_code_change` currently derives READ,
RUN_TESTS and WRITE_BRANCH, not PUSH_BRANCH, OPEN_PR, MERGE or DEPLOY [S31]. Publishing therefore
requires the separate existing source/release owner and its grant. A workstream's descriptive
owner field is not a lease; a mission's reserved-release posture remains binding.

## C2 — Identity facts and their owners

| Fact | Current owner / existing field | Caller authors it? | Required relationship |
| --- | --- | --- | --- |
| Mission | Mission Workspace `work_ref`; public semantic `workstream` | Select an assigned mission only | Exact equality; no prefix/nearest-match scope. |
| Logical operation | COO `operation_key` and derived `req-coo-*` | Semantic key, yes | Stable across timeouts; no new key to evade conflict. |
| Principal | OAuth verified issuer/subject/client/resource/scopes + installed binding digest | No | Match current root-installed permission binding. |
| Mission authority generation | `mission_authority_ref`, `authority_generation_digest` | No | Trusted context and final host guard agree. |
| Capability | Registry profile ID/digest and package generations | No runtime self-selection | Admitted generation equals requested and observed generation. |
| Child tree | Runtime Job/Attempt/root/parent/depth/provenance | No | Existing constructor and plan admission establish it. |
| Execution | Worker, provider quota, RuntimeBinding, process generation | No | Existing Router/Capacity/Runtime select; post-claim drift refuses. |
| Source | WorkspaceIdentity, branch/base and existing source lease | No arbitrary path | Exact granted workspace; no sibling checkout mutation. |
| Browser | BrowserAttemptContext generation and tool/runtime/browser digests | No | Same Attempt/session epoch/process/workspace, before and after use. |
| Dialogue | Existing bound commission, channel/root and message lineage | No free target | Resolver derives current carrier; model authors bounded message semantics only. |
| CI | Repo, PR, head, required-check context, existing observer/return handle | Candidate reference through owner | No result accepted for another head or check policy. |

Store these facts only with their current owners. Evidence documents refer to them; they do not
replicate identity databases or issue fresh bindings. Never put provider-native session IDs,
raw subjects, tokens, browser cookies or credential-bearing paths into public issue prose.

## C3 — Contract evolution

Keep the current six-tool COO contract and bounded-job behavior stable while qualifying its
successor. A new orchestration capability must have an explicit reviewed contract version under
the existing principal admission owner. It must not reinterpret a v1 bounded-job request as
fanout after a package upgrade. Unknown versions, enum values and extra fields refuse.

Schema evolution must identify: old/current schema digests, changed semantic fields, changed
required scopes, impacted native versions, migration/readback plan, rollback target and which
existing evidence becomes invalid. Old clients receive their old contract or an explicit
unsupported-generation refusal, never a mixed catalog.

Descriptions and titles may be excluded from an existing structural digest by owner law [S30].
That does not make behavior-affecting metadata harmless. Before native admission, the canonical
digest/policy owners must classify `_meta`, tool security schemes, approval requirements and
server-level policy. Bind security-relevant material or refuse an unmodeled change. Do not invent
a second generic tool-digest authority inside the parity script.

## C4 — Requested, projected, shipped, observed and admitted are different

**Requested** is the reviewed capability intent. **Projected** is generated provider configuration.
**Shipped** is the installed/package artifact actually selected by that provider surface.
**Observed** is native readback from the exact running generation. **Admitted** is the existing
runtime owner's decision using all those facts plus mission/resource/permission gates.

A builder must supply separate evidence for each. H2-A currently proves only deterministic static
configuration expectations. Its `production_armed: false` cannot be flipped to manufacture a
native admission receipt. Native readback may reduce capability availability; it may never add
authority beyond the approved profile.

Do not compare raw provider configuration for equality across providers. Compare the same
canonical capability identities, accepted operation semantics, required package generations,
resource ceilings and enforced approval policy. Preserve explicit provider-specific differences.

## C5 — Launch and re-attestation barriers

Before an initial useful model turn, the existing launch owner must establish exact source,
package closure, native binary/SDK version, requested policy and an admitted resource environment.
After native initialization, compare observed tool inventory, schemas, settings provenance,
plugins/skills/hooks and resource binding to that requested profile. No useful effect until the
owner accepts the observation. Absence of a usable attestation path means a held capability.

Re-attestation is required at relevant invalidators: process restart/resume, MCP reconnect,
profile/package generation change, managed-policy change, tool/schema drift, resource replacement,
principal revocation or source-binding change. Use the owners' freshness rules; do not introduce
a universal guessed TTL. Where an in-session policy change cannot be reliably observed, the
qualified profile must fence new effects until a new observed generation is established.

Isolation is not achieved by copying the caller's configuration and hashing it. Observations must
come from the native session or a trusted independent enforcing component. Dynamic server policy
is checked at dispatch, not just at startup. Managed settings remain higher-priority controls;
never disable them to pass a canary.

## C6 — Effect handling

| Boundary | What is known | Required action | Forbidden response |
| --- | --- | --- | --- |
| Validation/permission refusal before dispatch | No effect from that request | Preserve exact refusal; repair only an actually permitted input or resolve its legitimate gate | Rephrase, switch tool/account, or ask another worker for the denied effect. |
| Proven technical pre-dispatch failure | No effect | Use existing bounded recovery policy after exact-target inspection | Treat no-effect as unlimited retry permission. |
| Receipt lost after dispatch | Effect unknown | Freeze logical operation; query original owner's status/readback | New operation key, second child, alternate transport. |
| Valid duplicate receipt | Existing accepted effect | Consume same object and immutable identity | Count it as another execution. |
| Same key, changed semantics | Conflict | Recover the original request and owner decision | Hash a changed payload to bypass the conflict. |
| Permission revoked after a write may have committed | Effect unknown under reduced authority | Authorized status/reconciliation path or exact operator resolution | Infer rollback or perform a fresh write. |
| CI result for prior head | Evidence stale for current candidate | Keep old evidence attributed; bind successor observer to current head | Mark current head passed. |
| Cleanup failed | Resource obligation unresolved | Retain exact resource/process identity with its owner | Free/reassign the slot or delete evidence. |

These descriptions do not add Runtime status enums. Use each owner's existing typed errors and
receipts. In particular, COO post-send internal/backend errors may follow a committed Job [S08].
An HTTP error code alone is not an effect-none certificate.

## C7 — Recovery remains possible when new work is fenced

New-effect gates and reconciliation reads are distinct. Current COO status deliberately avoids
calling a new-mission effect gate [S08]. Preserve that property, while retaining valid principal
identity and visibility authorization. Permission rotation may itself limit status; expose that
specific resolver rather than inventing a new principal or assuming the old receipt vanished.

On a new chat or process, first recover mission, exact operation, source custody and unresolved
effects. Use the existing RuntimeBinding/session target and admitted resume APIs [S17, S22].
A saved native session ID is not a reusable execution grant. Never resume the newest tab or create
a substitute session because an exact target is unavailable.

## C8 — Evidence package and grading

Every live acceptance artifact must refer to the existing receipt owner and contain the useful
non-secret subset of: source/release revision; profile/package/native versions; mission/operation;
expected versus observed tool/schema generation; relevant canonical result IDs; negative-case
observations; resource cleanup; verifier and unresolved limits. This is an evidence checklist,
not a new object schema replacing owner receipts.

A success demonstration without its required refusal/negative controls is incomplete. A simulated
fixture proves behavior inside that fixture, not OAuth enrollment, actual worker placement or
browser isolation. A screenshot without exact resource/source binding is illustration, not
production acceptance. A test count does not establish untested packet completion.

## C9 — Native capability safety cases

Qualification must deliberately exercise: an ambient extra MCP; an unapproved skill/plugin/hook;
a dropped deny; a tool schema changing after reconnect; managed policy changing mid-session;
unknown/truncated catalog; a sibling principal; incorrect workstream; malformed status receipt;
a lost dispatch reply; duplicate dialogue message; stale CI head; browser redirect/egress escape;
resource cleanup failure; and principal interruption with two children at different stages.

Use synthetic/disposable resources for destructive or adversarial inputs. Do not probe real
credentials, production customer data or the Chairman's browser. Each negative case must identify
where rejection occurs and whether any effect has already crossed a boundary.

## C10 — Controlled rollback

Rollback is an owner action, not deleting the newest plugin directory. Revoke only new admission
or roll selected package/configuration back to an exact accepted generation. Preserve existing
jobs, source leases, audit events and unresolved effects until their owners reconcile them.
Keep the sealed worker product unchanged throughout. Source rollback does not automatically undo
an installed service, enrollment permission, browser resource or completed external effect.

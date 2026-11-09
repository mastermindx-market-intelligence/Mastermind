# H2 — Canonical capability parity without a second capability authority

## Outcome and current slice

H2 must make a supported canonical capability change impossible to leave silently stale on
Claude. The source owner remains ExecutionCapabilityRegistry / capability packages; the existing
`claude_mcp_client_projection.py` remains the only Claude MCP projector [S05, S29].

PR #1240's H2-A is a useful first guard, not the full target. It checks all nine current profiles
against explicit surface dispositions and qualifies four static CLI/SDK configuration pairs.
It does not show a package installed, a profile launched, a server enforcing a grant, or a native
catalog observed. Preserve those limits in names, output and review receipts.

## Selected design: five evidence layers

Use the existing manifest/checker as a **build-time expectation and verification artifact**.
Add references to owner-produced receipts; do not turn the manifest into the source from which
runtime permission is granted.

| Layer | Existing source of truth | Required comparison | Not an acceptable substitute |
| --- | --- | --- | --- |
| Canonical | Registry and exact package/skill closure | Profile, grant, tool-contract and resource identities | A handwritten list of familiar tools. |
| Projection | Provider-specific existing projector | Declared supported operations, configuration and authority ceiling | Copying ChatGPT tool names into a Claude package. |
| Shipped | Existing package/source release and installation owners | Selected package generation, projection revision and native surface | A merged manifest or local directory. |
| Observed | Native adapter / trusted attestation owner | Actual tool/settings/package/resource generation | Echo of requested config or a model's statement. |
| Admitted | Executive principal/runtime/resource owners | Exact joined authority and currentness decision | `configuration_supported` or a successful tools/list. |

A proposed manifest evolution should keep canonical profile references, explicit provider/surface
dispositions, exact projection expectations and immutable references to shipped/observed evidence
separate. Existing owner receipt schemas determine the reference fields. Do not freeze invented
install-receipt fields before the installation owner exposes its actual contract.

## Algorithm and change classification

1. Load the canonical policy through its existing strict loader, not ad-hoc JSON access that
   ignores rejected fields. Resolve only the explicitly selected profiles and package closures.
2. Enumerate the actual canonical inventory and require an explicit disposition for every newly
   relevant profile/surface. New inventory is a review event, never an automatic grant.
3. Compute canonical identities through their current owners. Profile digests already join
   selected package generations in v4; separately retain those generation references so a
   reviewer can diagnose revocation or unrelated package-file movement [S29].
4. Render using the existing provider projection. Verify exact granted operations, auto-approval
   declarations, denied inventory, transport and configuration. Do not interpret approval lists
   as tool isolation. Preserve provider-specific casing and naming semantics.
5. Compare projected semantics to the reviewed expectation. An unqualified operation, silently
   omitted required resource or different security ceiling is a failure, not a warning.
6. Compare selected shipped generation to its source/package receipt, and observed generation to
   that selected material. This part is evaluated by the existing installation/native owners;
   a source-only CI process reports it as unproven when those receipts do not exist.
7. Emit a bounded field-level difference: owner, old/new identity, affected surfaces, semantic
   category, current support disposition and exact requalification obligation. Never emit
   secrets, user-home config, credential references or a fabricated live status.

Classify changes explicitly: documentation-only; configuration-shape; tool/schema; approval or
security metadata; package/skill closure; resource/egress; principal scope; native version; or
canonical inventory. These are review labels, not new runtime policy enums. Security-sensitive
changes invalidate the applicable native proof even when the tool name did not change.

## What parity means

ChatGPT, Codex, Claude Code and the Agent SDK can represent the same canonical operation with
different packaging. Equivalence requires the same semantic input/output contract, mission and
principal ceiling, enforcement and resource restrictions—not byte-identical config files.

An intentional difference is valid only when it is explicit and does not masquerade as support.
For example, Desktop-local HTTP requires its separately admitted bridge; an inline helper requires
its own helper/resource/catalog proof; a sealed worker is deliberately unsupported for rich MCP.
Those are retained as unsupported/deferred until their actual acceptance evidence exists.

Do not fill missing provider parity by emitting a proxy tool with broader semantics. When a
provider cannot faithfully enforce the capability, defer that surface and preserve useful work
on already admitted surfaces. Native version changes require qualification; product marketing
names are not version evidence.

## Hardening the existing H2-A guard

H2-A currently pins projector source bytes and every profile's canonical digest. That is
conservative: even a deferred profile's change demands explicit manifest requalification, and a
comment-only projector edit can trigger the source hash. Keep this behavior honest rather than
calling it a semantic-diff engine. A later reviewed refinement may reduce irrelevant rebuilds
only if it retains detection of changes that affect claimed support.

The current owner tool digest covers names, input/output schemas and annotations; it does not
normalize every arbitrary metadata field [S30]. Security schemes, approval metadata and relevant
server policy therefore need a canonical-owner classification and binding before live parity
can be claimed. Do not solve that gap by adding a competing runtime digest implementation here.

A valid opt-out change must remove stale projection expectations when moving to deferred and
record why. It cannot leave a hidden stale shipped artifact selected for live use. The current
installation owner must fence or remove that admission separately. Conversely, opting into a
new capability requires review and native qualification, not just changing a status string.

Validate duplicate JSON keys, strict boolean types, canonical paths, source-root identity,
unknown fields, package revocation, grant removal, catalog completeness and reconnect drift.
Keep the numeric-zero/boolean-false regression from the first slice. No automatic repair or
manifest regeneration should run during normal CI; developers must review the produced diff.

## Implementation units

**H2-B expectation model:** extend the existing checker/manifest with explicit separation of
canonical and static projected expectations, selected support and owner evidence references.
Keep a compatible parser for the current source-only declaration or use an explicit versioned
migration. Preserve `production_armed: false`; do not introduce a manifest activation switch.

**H2-C provider equivalence tests:** create shared canonical capability test vectors and feed the
existing provider projectors. Assert semantic parity only for admitted contracts, plus intentional
negative differences. Use exact current profile/package owners, not arbitrary synthetic IDs
misrepresented as enrolled production capability.

**H2-D shipped/native qualification:** let the actual H1/H3 installation and attestation owners
produce their normal receipts. Bind those references into review evidence and prove stale install,
selection, reconnect or native version does not pass as current. No background scanner or new
provider capability database.

These units may progress while H1's live admission is held. Only static properties can close in
source-only CI. Cases H2-01 through H2-12 define drift and proof scenarios.

## Release and acceptance

Use the existing CI collector [S33], not a second positive test allowlist or a new workflow that
silently excludes other tests. Review exact field-level changes and canonical owner compatibility.
A changed capability either produces a reviewed, qualified projection or explicitly defers the
surface and fences stale live use through its owner. The original H2 outcome is complete only
when that end-to-end change path is demonstrated, not when every surface says unsupported.

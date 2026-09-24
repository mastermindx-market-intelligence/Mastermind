# Agent / Operator Capability Convergence — Exact Exposed Skill-Set Amendment

**Date:** 2026-09-01  
**Owner:** Sol, AI CEO  
**Chairman:** Chris  
**Operation:** `mastermind-agent-operator-capability-convergence-f0-20260831-sol-001`  
**Carrier:** Mastermind PR #313 / `sol/agent-operator-capability-convergence-f0-20260831`  
**Current protected source reviewed:** `fc407e1638a26932c8615c98c7732d7f3202b3b1`  
**State:** `SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT / SELF-REVIEW REPAIR`

This amendment supplements and, where it conflicts, supersedes the first-Codex-vertical sections in:

- `docs/superpowers/specs/2026-08-31-agent-operator-capability-convergence-design.md`;
- `docs/superpowers/plans/2026-08-31-agent-operator-capability-pack-attestation.md`;
- `docs/superpowers/specs/2026-09-01-agent-operator-capability-convergence-owner-amendment.md`;
- `docs/superpowers/specs/2026-09-01-agent-operator-effective-skill-closure-amendment.md`.

All existing-owner, package-generation, effective-closure, provider-neutral harness, browser/resource,
secret-isolation and completion boundaries remain unchanged. This amendment corrects which exact Skill
set the first provider process may expose.

---

## 1. Review finding

The protected `mastermind-operator` package contains one `skills/` root with four Skill directories:

```text
escalate-decision
finish-operation
receive-commission
return-progress
```

All four Skill entrypoints require the same protected package reference:

```text
references/dialogue-boundary.md
```

The current Codex App Server protocol already supports an explicit extra Skill root through
`skills/extraRoots/set`. Pointing a provider process at the protected package's exact `skills/` root
therefore exposes **all four** Skills.

The earlier first-vertical wording required only `receive-commission`. Under the actual package
layout, loading the full root while requesting only one exact Skill would produce one of two bad
outcomes:

1. the other three Skills are unclassified ambient capabilities and launch correctly refuses; or
2. the implementation weakens exact ambient-capability law merely to let the canary pass.

Neither is acceptable.

---

## 2. Executive ruling

> **The first Codex custom-capability vertical loads and requires the complete four-Skill
> `mastermind-operator` Skill set from one exact protected package source generation.**

The discriminating model probe may begin with `receive-commission`, but the sealed execution profile
must require all four exact effective Skill closures because all four are intentionally exposed by the
provider root.

A later one-Skill profile is lawful only when an accepted materializer creates an isolated provider
projection containing exactly that Skill's effective closure and runtime discovery proves the other
three are absent. It may not be approximated through ambient allowances, provider UI toggles, prompt
instructions, or a name-only filter.

---

## 3. First exact profile

The first profile is conceptually:

```text
operator.appserver.readonly.mastermind-operator.v1
```

It remains:

```text
execution surface      codex-app-server
sandbox                 read-only
approval                never
command network         disabled
write capable           false
native helper           disabled
MCP                     none unless a separately accepted exact dependency is required
browser resource        none
full plugin grant       none
production armed        false
```

Required Skill capability IDs are conceptually:

```text
mastermind-operator.receive-commission.v1
mastermind-operator.return-progress.v1
mastermind-operator.escalate-decision.v1
mastermind-operator.finish-operation.v1
```

The exact identifiers are frozen by the existing-owner package-generation contract. They are not
provider-native installation IDs.

Every required identity carries:

- runtime Skill name;
- accepted package source-generation digest;
- exact effective Skill closure digest;
- exact entrypoint and closure mapping through the existing registry/profile digest;
- current harness binary digest through the existing OHF `CapabilityIdentity` contract.

---

## 4. Provider-root and source law

The first Codex implementation should use the exact immutable installed Mastermind release as the
source capability root rather than a mutable user plugin cache or Business workspace import.

Conceptual composition:

```text
exact installed Mastermind release root
  -> plugins/mastermind-operator
       -> skills/                       # exact App Server extra root
       -> references/dialogue-boundary.md
       -> .codex-plugin/plugin.json
```

The worker broker already starts from one exact installed release root and resolves the requested
execution profile from `ExecutionCapabilityRegistry`. The provider adapter may receive the resolved
Skill grants plus that exact release root through constructor composition. It must not make the
release root caller/model-selectable.

Before provider start, deterministic code validates:

- the package source generation matches the registry's full file/mode/SHA-256 inventory;
- all four closure mappings and digests match;
- every path is beneath the exact release root and package root;
- no symlink, hardlink ambiguity, case collision, non-regular file or path escape exists;
- the exact Skill extra root is `plugins/mastermind-operator/skills`;
- the source root is not a mutable user/global/provider cache;
- no credential or provider-home content is part of the package source.

The adapter then calls the existing provider operation with the exact root. No marketplace install,
workspace mutation, package-manager download or model-controlled setup occurs.

---

## 5. Requested and observed set equality

The existing launch comparator remains the authority. The implementation must close one current
ambiguity: a required name is presently considered proven when **any** same-name observed capability
matches, even if another same-name/different-content capability is also present.

For exact custom Skills, set equality requires:

```text
one requested typed identity
-> exactly one observed typed identity with that runtime name
-> full identity match, including skill_content_digest
```

Required behavior:

- zero same-name observations: missing required;
- one exact observation: proven;
- one same-name observation with absent/wrong digest: missing + unknown precision;
- multiple same-name observations, even when one matches: ambiguous and refused;
- duplicate identical same-name observations: refused until provider/source precedence is separately
  proven and normalized before the comparator;
- any extra Skill name not required or explicitly allowed ambient: unclassified and refused.

This is a generic correction to the existing typed comparator, not Codex-specific policy.

---

## 6. Runtime observation

For each of the four rows returned by `skills/list`, the Codex adapter must require:

1. exact expected runtime name;
2. exact provider-reported path corresponding to the expected directory under the immutable package
   root;
3. exact full package source-generation verification;
4. exact effective-closure digest computed from the accepted package-root-relative rows;
5. no second row with the same name;
6. no unexpected fifth custom Skill from user, project, admin or system roots.

Built-in or ambient Skills that the provider exposes are not silently ignored. The exact profile must
classify every effective capability. If unavoidable provider built-ins appear and can influence work,
the source owner must define an exact allowed-ambient identity or the route remains ineligible. A
read-only profile is not permission to ignore unclassified instruction capability.

The App Server request and response are observations only. The provider does not decide which package
generation is authorized.

---

## 7. Useful model journey

The first real canary exercises the complete operator lifecycle, not four disconnected invocation
samples:

```text
$receive-commission
  -> classify one synthetic bound commission and emit the expected ACK/START posture

$return-progress
  -> emit one material progress shape without claiming completion

$escalate-decision
  -> stop at a synthetic authority boundary and return a decision request

$finish-operation
  -> return exact evidence and await an explicit Sol edge without self-acceptance
```

The canary uses one read-only synthetic operation and no external dialogue write. It proves that the
model can use the package method; it does not prove Slack/Company Dialogue mutation, Executive
completion, production acceptance or autonomous fleet operation.

A provider that lists all four exact Skills but cannot consume their required shared reference fails
the usefulness proof.

---

## 8. Negative falsifiers

The first vertical must prove refusal before the first work turn for:

```text
one-byte drift in any Skill entrypoint
one-byte drift in dialogue-boundary.md
missing dialogue-boundary.md
same name from a second root
same name with different closure bytes
unexpected fifth custom Skill
only one of four required Skills discovered
wrong exact extra root
mutable user/global plugin cache shadowing the protected root
package manifest/file inventory drift
symlink, hardlink ambiguity, non-regular file, case collision or path escape
name-only observation / digest unavailable
provider hot reload changing the Skill set after attestation
```

If exact hot-reload stability cannot be proven, the profile remains laboratory-only or re-attests
before every effect-bearing phase. Prompt instructions to avoid the extra capability are not a
security control.

---

## 9. Relationship to later materialization

The full four-Skill profile is the correct first vertical because it matches the actual protected
source root and requires no dynamic install.

Later provider-neutral materialization may support narrower projections:

```text
accepted package source generation
 + selected effective Skill closure(s)
 -> deterministic provider-native staged generation
 -> exact staged inventory and source mapping receipt
 -> provider observation of exactly the selected set
```

That later materializer must preserve shared references and closure identity. It cannot copy only
`SKILL.md`, rewrite behavior invisibly, or enable other package Skills as ambient conveniences.

HF1 remains required before heterogeneous providers are generally routed through one common Worker
broker. This first Codex rich-operator proof remains bounded to the existing OHF/Codex composition.

---

## 10. Correction to earlier acceptance language

Where earlier #313 records describe the first live vertical as requiring only
`receive-commission`, read:

> **require all four exact `mastermind-operator` effective Skill closures; use
> `receive-commission` as the first discriminating model step.**

The first vertical is accepted only when:

- one exact protected package generation is validated;
- all four requested closures are exact;
- the observed Skill set is exactly the requested four-Skill set at the promised precision;
- same-name duplicates and all unclassified Skills refuse;
- the complete four-step read-only model journey is useful;
- no install, credential, workspace, dialogue, lifecycle, provider-routing or production effect is
  smuggled into the canary;
- process cleanup and existing OHF writer law pass.

A records merge makes only this corrected source law durable. It does not load or prove the Skill set
in production.

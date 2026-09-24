# Agent / Operator Capability Convergence — Effective Skill Closure Amendment

**Date:** 2026-09-01  
**Owner:** Sol, AI CEO  
**Chairman:** Chris  
**Operation:** `mastermind-agent-operator-capability-convergence-f0-20260831-sol-001`  
**Carrier:** Mastermind PR #313 / `sol/agent-operator-capability-convergence-f0-20260831`  
**Current protected source reviewed:** `fd7ce2bccaafdb53b3b3440b9f823586c6849730`  
**State:** `SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT / SELF-REVIEW REPAIR`

This amendment supplements and, where it conflicts, supersedes the custom-Skill digest sections in:

- `docs/superpowers/specs/2026-08-31-agent-operator-capability-convergence-design.md`;
- `docs/superpowers/plans/2026-08-31-agent-operator-capability-pack-attestation.md`;
- `docs/superpowers/specs/2026-09-01-agent-operator-capability-convergence-owner-amendment.md`.

The existing-owner ruling, no-runtime-self-install law, `ExecutionCapabilityRegistry` ownership,
provider-neutral harness boundary, browser/resource law and completion boundaries remain unchanged.
This amendment corrects the unit whose bytes must be identified by
`CapabilityIdentity.skill_content_digest`.

---

## 1. Review finding

The original plan proposed a digest over every regular file **inside one Skill directory**. That is
stronger than name-only identity but is not sufficient for the protected Mastermind Operator package.

The current protected `receive-commission/SKILL.md` requires the model to read:

```text
../../references/dialogue-boundary.md
```

before ACK, START, return or STOP handling. That reference is outside
`skills/receive-commission/`. A one-byte change to the reference could materially change worker
behavior while leaving a directory-only Skill digest unchanged.

Therefore:

> **An exact custom Skill is identified by its finite effective Skill closure, not merely its
> `SKILL.md`, its directory, its name, its plugin version, or the entire package by default.**

The complete containing package is independently identified as a package source generation. Skill
closure identity and package generation identity are related but not collapsed.

---

## 2. Separate identities

```text
PACKAGE SOURCE GENERATION
  exact reviewed repository + commit + package root
  exact complete package file/mode/digest inventory
  native source manifest digest
  release/revocation state

EFFECTIVE SKILL CLOSURE
  one Skill entrypoint
  every package-local file that can alter that Skill's prescribed behavior
  exact relative paths, bytes and executable modes

PROVIDER MATERIALIZATION GENERATION
  deterministic provider-native projection of one or more accepted closures
  provider loader/config manifests and staged-file receipt

OBSERVED EFFECTIVE SKILL
  provider-discovered Skill identity
  exact observed effective-closure digest at launch precision
```

A package generation may change while one Skill closure remains byte-identical. In that case the
package/profile provenance digest changes, while the semantic `skill_content_digest` may truthfully
remain the same. Conversely, changing any file in a Skill closure changes that Skill digest even if
the package/plugin version string remains unchanged.

The exact execution profile binds both:

- accepted package/source generation provenance; and
- the exact required Skill closure digest carried by the existing `CapabilityIdentity` field.

---

## 3. V1 effective-closure contract

The first implementation freezes the conceptual schema:

```text
mastermind.effective_skill_closure/v1
```

Canonical semantic projection:

```json
{
  "schema_version": "mastermind.effective_skill_closure/v1",
  "skill_name": "receive-commission",
  "entrypoint_path": "skills/receive-commission/SKILL.md",
  "files": [
    {
      "relative_path": "references/dialogue-boundary.md",
      "sha256": "<64-lower-hex>",
      "byte_length": 1,
      "executable": false
    },
    {
      "relative_path": "skills/receive-commission/SKILL.md",
      "sha256": "<64-lower-hex>",
      "byte_length": 1,
      "executable": false
    }
  ]
}
```

`skill_content_digest` is SHA-256 over canonical UTF-8 JSON using:

```python
json.dumps(
    projection,
    sort_keys=True,
    separators=(",", ":"),
    ensure_ascii=False,
    allow_nan=False,
).encode("utf-8")
```

### 3.1 Included files

The closure includes:

- the exact Skill entrypoint;
- every required package-local reference named by the accepted closure contract;
- every script, template, rubric, schema, prompt fragment, asset or executable the Skill directs the
  model/provider to consume or invoke;
- transitive package-local dependencies of those files where behavior can change.

For the first protected `receive-commission` vertical, the minimum exact closure is:

```text
skills/receive-commission/SKILL.md
references/dialogue-boundary.md
```

If current source review discovers another required dependency, the closure is widened before
implementation. It may not be guessed away to preserve a precomputed digest.

### 3.2 Excluded files

The closure does not automatically include:

- unrelated sibling Skills;
- symbolic Business app-binding templates the worker does not load;
- marketplace catalog metadata the provider does not consume for this projection;
- current Job, Attempt, Worker, provider-session or host state;
- credentials;
- timestamps, uid/gid, absolute paths or mutable installation metadata.

Those facts either belong to package/materialization provenance or are forbidden runtime state.

### 3.3 File rows

Rows are sorted by normalized package-root-relative UTF-8 path. Each row binds:

- POSIX relative path;
- SHA-256 of exact bytes;
- byte length;
- executable bit.

Symlinks, hardlink ambiguity, non-regular files, NUL/path traversal, case-collision on a
case-insensitive target, duplicate normalized paths, oversized files and unbounded closures fail
closed.

---

## 4. Closure declaration and verification ownership

V1 does **not** attempt to infer arbitrary executable dependencies from natural-language Markdown.
A regex/link crawler cannot prove what an agentic instruction may consume, and allowing the model to
declare its own closure would be self-attestation.

The accepted package/source-generation contract in `ExecutionCapabilityRegistry` therefore owns one
closed, reviewed Skill-to-file mapping for every grantable company Skill. The source package may
contain references and manifests, but the capability owner independently validates that:

1. the entrypoint exists in the accepted immutable package generation;
2. every declared closure path exists in the same package generation;
3. all files are regular, bounded and byte-identical to the accepted source inventory;
4. the entrypoint's required package-reference markers are covered by the declared closure;
5. undeclared required references refuse the exact grant;
6. no closure path escapes the package root;
7. source package generation, closure digest and execution-profile digest are linked in the policy
   digest without creating another registry.

Future package formats may carry a closure manifest as source data, but that manifest never grants
itself authority. The existing capability loader must validate it against reviewed source bytes and
closed policy before accepting it.

---

## 5. Package-generation digest remains separate

The protected BSC-P1 validator currently proves a closed package shape but emits no cryptographic
package-generation inventory. The existing-owner package-generation wave must add a deterministic
full-package source projection containing at least:

```text
repository identity
immutable commit
package root
native manifest path/digest
all package-relative regular files
Git mode / executable bit
byte length
SHA-256
closed Skill inventory
per-Skill effective-closure mapping/digest
release state
revocation state
```

The package-generation digest changes when **any** package file changes. An individual effective
Skill closure digest changes only when a file in that closure or its normalized closure mapping
changes.

This distinction prevents both failure modes:

- **under-binding:** a required shared reference changes without changing Skill identity;
- **over-coupling:** an unrelated sibling Skill changes and falsely appears to change the required
  Skill's semantic bytes.

An execution profile may still require the new package generation because provenance changed, even
when a Skill closure digest remained stable.

---

## 6. Provider materialization law

A provider materializer consumes an already-accepted package generation and one or more exact Skill
closures. It may generate provider-native loader/config files, but it may not alter semantic closure
bytes.

Its Attempt-scoped receipt binds separately:

- accepted package generation;
- requested closure identities;
- exact source rows consumed;
- exact staged semantic files;
- exact generated provider-native files;
- provider projection/version;
- staging root identity;
- zero credential writes;
- zero authoritative-workspace mutation;
- zero process start during staging.

Provider-native loader manifests belong to materialization identity unless the Skill itself directs
the model to consume them. They do not silently become part of professional method or organizational
authority.

CAP-S1 may use one explicitly provisioned Codex laboratory projection before HF1, but it must still
emit the same source/closure/materialization evidence and may not copy only `SKILL.md` while omitting
its required reference.

---

## 7. Runtime observation law

The provider's `skills/list`, plugin UI or enabled-name list is discovery evidence only. To satisfy a
required exact custom Skill, the adapter/supervisor must establish that the provider resolves the
entrypoint and every effective-closure file to the exact staged immutable bytes.

Preferred proof order:

1. provider reports exact loaded source/file identity at sufficient precision;
2. provider reports an exact resolved Skill root and the supervisor proves the immutable closure
   through retained no-follow filesystem capabilities;
3. a dedicated process-scoped loader root makes alternate content impossible and the supervisor
   proves all effective rows before the first turn.

Name-only observation cannot satisfy a requested digest. A Skill path outside the accepted staged or
provisioned root cannot satisfy the exact grant merely because its bytes appear equal. Provenance and
loader precedence remain separately bound.

If provider hot reload can change any closure row after launch, the route must either re-attest before
an effect-bearing phase, run with reload disabled/isolated, or remain ineligible for exact modifying
profiles.

---

## 8. Comparator and ambient capability behavior

The existing launch comparator remains the single requested-vs-observed authority. It must compare
full typed identity, including `skill_content_digest`, rather than collapsing by name.

Required falsifiers:

```text
same name + changed entrypoint                       REFUSE
same name + changed required shared reference        REFUSE
same name + missing required reference               REFUSE
same name + undeclared newly required reference      REFUSE
same name + same closure bytes outside trusted root  REFUSE exact provenance
same closure + changed unrelated sibling Skill       closure stable; package/profile provenance changes
same name + duplicate observed closures              REFUSE ambiguity/unclassified widening
symlink/path escape/case collision                    REFUSE
name only / digest unknown                           REFUSE required exact Skill
extra ambient custom Skill                           REFUSE exact profile unless explicitly allowed ambient
```

No model output, frontmatter `allowed-tools`, package version or provider “enabled” label can override
these outcomes.

---

## 9. Correction to the original implementation plan

Where Task 1 of the original plan says:

```text
mastermind.skill_tree/v1
inspect_skill_tree(root)
skill_content_digest(root)
```

read instead:

```text
mastermind.effective_skill_closure/v1
inspect_effective_skill_closure(package_root, accepted_closure)
effective_skill_content_digest(manifest)
```

The pure digest utility may still use focused dataclasses, but it receives an already-reviewed
closure declaration and validates exact package-relative rows. It does not discover authority or
parse arbitrary prose to decide dependencies.

The first complete vertical must test both the entrypoint and required shared reference. A test that
changes only `SKILL.md` is insufficient.

Where the plan says “full Skill tree,” read “full accepted effective Skill closure.” Where it says the
source generation carries “exact skill inventory and per-file digests,” add “and one validated
per-Skill effective-closure mapping.”

---

## 10. Acceptance boundary

CAP-S1 is not accepted until a real read-only Codex Attempt proves:

- exact accepted BSC-P1 package source generation;
- exact `receive-commission` effective closure containing both entrypoint and required dialogue
  reference;
- expected and observed closure digest equality before the first work turn;
- one-byte entrypoint drift refusal;
- one-byte dialogue-reference drift refusal;
- missing/escaped/symlinked reference refusal;
- same-name/different-closure refusal;
- exact loader/provenance binding;
- useful discriminating model behavior;
- clean stop/process proof;
- no runtime arming or authority widening.

A source-law merge proves only this contract. It does not attest a live package generation or make the
Codex vertical `PROVEN_LIVE`.

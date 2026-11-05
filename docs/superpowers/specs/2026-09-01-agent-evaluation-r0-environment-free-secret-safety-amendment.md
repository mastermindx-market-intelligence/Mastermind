# EVAL-R0 Environment-Free Secret-Safety Amendment

**Date:** 2026-09-01  
**Parent operation:** `mastermind-agent-evaluation-organizational-learning-fabric-20260830-sol-pro-001`  
**Repair operation:** `mastermind-agent-evaluation-f0-secret-safety-amendment-20260901-sol-001`  
**Parent carrier:** Mastermind PR #299  
**Protected source at amendment start:** `mastermindx-market-intelligence/Mastermind@fc407e1638a26932c8615c98c7732d7f3202b3b1`  
**Pickup candidate:** `71e09b797dd7a0c6a05a699ee7c4779b43a8513c`  
**Skillpack:** `mastermind.sol_skillpack.v1` v1.0.1 / bootstrap-major 1 compatible  
**Capability:** `SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT`

This amendment creates no evaluator implementation, model/provider call, process, credential read, environment read, artifact store, Executive/Agent OS effect, route, policy, deployment, or production action.

---

## 1. Authority and narrow precedence

Apply the current protected Skillpack and the parent EVAL-F0 architecture first. This amendment has narrow precedence over only those clauses in:

- `docs/superpowers/specs/2026-08-31-agent-evaluation-fabric-design.md`; and
- `docs/superpowers/plans/2026-08-31-agent-evaluation-r0.md`

that propose importing or calling the existing OHF/general redaction helper from EVAL-R0 or otherwise imply that R0 may inspect process-environment credential values.

Every other scenario, configuration, experiment, run, validity, scoring, verification-scope, create-only storage, owner, no-rebuild, privacy, failure, acceptance, and rollout decision in the parent records remains unchanged.

---

## 2. Defect found during Program CEO self-review

The R0 plan simultaneously required:

1. no process-environment or credential read; and
2. use of the existing OHF text-redaction helper for secret safety.

Protected source proves those requirements are incompatible. At the amendment source commit:

```text
scripts/ohf/redaction.py::redact_evidence_text
  -> environment_secrets()

common/redaction.py::environment_secrets
  -> os.environ when no explicit mapping is supplied
```

`environment_secrets()` is intentionally appropriate for sanitizing runtime error/evidence text in its owning subsystem. It is not production-inert with respect to environment observation. Importing and calling that helper from R0 would violate R0's explicit no-environment-read contract and would expose the native evidence core to ambient host credential state.

The defect is architectural, not merely an implementation detail. A later worker must not resolve it by silently weakening either privacy or inertness.

**Deliberate divergence from `common/redaction.py` / `scripts/ohf/redaction.py` (`REJECTED_BY_DESIGN` for R0, adopted 2026-09-01):** R0's supplied-value detector (§3.5) deliberately does not reuse those modules' hex/base64url-run-of-32-plus redaction, nor their `environment_secrets()` identity-backstop path, for two reasons: (1) generic long-random-token redaction would corrupt canonical SHA-256/Git-SHA/UUID evidence identities that R0 must preserve exactly; and (2) `environment_secrets()`'s ambient `os.environ` read is forbidden inside R0's production-inert, environment-free core (§3.2). This is a permanent, named divergence, not an omission to reconcile later.

---

## 3. Binding ruling

### 3.1 R0 owns one narrow reject-only boundary

EVAL-R0 implements one pure, deterministic, evaluation-local secret-**shape** rejection module:

```text
scripts/agent_eval/privacy.py
```

with tests in:

```text
tests/test_agent_eval_privacy.py
```

The module is not a general redaction service, credential inventory, data-loss-prevention system, security event sink, policy engine, environment scanner, or replacement for `common.redaction` / `scripts.ohf.redaction`.

It has one job:

> Refuse a proposed canonical evaluation document or run draft when the supplied JSON value itself contains a prohibited field name or an explicitly recognized credential/private-identity shape.

It returns deterministic structured defects. It never rewrites, redacts, truncates, normalizes, logs, persists, or transmits the supplied value.

### 3.2 No ambient observation

Production R0 code must not:

- import `scripts.ohf.redaction`;
- import `common.redaction`;
- read `os.environ`;
- call `os.getenv`, `os.environ.get`, `environment_secrets`, or an equivalent environment enumeration;
- read credential files, provider homes, keychains, cookies, OAuth stores, shell profiles, process listings, or host configuration;
- accept a process-derived secret list by default;
- make a network call or invoke a subprocess to discover secrets.

The detector receives only the document/draft value supplied by its caller and closed static pattern definitions in its own source.

### 3.3 Public interfaces

The exact names may be refined during TDD only if behavior remains equivalent and the plan/test names are updated together. The intended interface is:

```python
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, order=True)
class SecretShapeFinding:
    path: str
    code: str
    shape: str


def detect_secret_shapes(value: Any, path: str = "$") -> tuple[SecretShapeFinding, ...]:
    """Return deterministic supplied-value findings without reading ambient state."""


def assert_public_safe_evidence(value: Any, path: str = "$") -> None:
    """Raise the existing structured contract error when findings are present."""
```

The implementation should reuse the package's existing structured `ContractDefect` / `ContractError` rather than introduce a second error hierarchy if that is cleaner after Task 1 establishes them.

### 3.4 Minimum prohibited shapes

The detector must reject supplied values containing:

1. **Forbidden field names**, case-insensitive after exact ASCII comparison, including credential-bearing names such as:
   - `api_key`, `apikey`, `access_token`, `refresh_token`, `id_token`, `token`;
   - `authorization`, `cookie`, `set_cookie`, `password`, `passwd`, `secret`;
   - `client_secret`, `private_key`, `credential`, `credentials`;
   - `raw_environment`, `environment_dump`, `chain_of_thought`;
   - `private_host_address` and equivalent explicitly enumerated private-host fields.
2. **JWT-shaped bearer material** with three compact base64url segments, including an empty final signature only where the recognized grammar permits it.
3. **Known credential prefixes** followed by a nontrivial token body, including at least:
   - `sk-`, `sk-ant-`;
   - `github_pat_`, `ghp_`, `gho_`, `ghs_`;
   - `sb_secret_`, `sb_publishable_`, `sbp_`.
4. **Authorization or cookie header values**, including case-insensitive `Bearer`, `Basic`, or explicitly secret-bearing cookie assignments.
5. **Explicit environment assignments** such as `MASTERMIND_*=` and other closed credential-name assignments (`*_TOKEN=`, `*_KEY=`, `*_SECRET=`, `*_PASSWORD=`) when they appear in supplied strings.
6. **Email/personal account identity shapes** in a supplied value, rejected unconditionally. A private-identity shape appearing only inside a declared observed-evidence field (§3.7) is not a supplied value; it is sanitized per the observed-evidence sanitization law instead of rejected.
7. **Private host/IP material** in a supplied value, rejected unconditionally, including loopback, link-local, RFC 1918 IPv4, and nonpublic IPv6 literals. A private-host shape appearing only inside a declared observed-evidence field (§3.7) is not a supplied value; it is sanitized per the observed-evidence sanitization law instead of rejected. Source-qualified public repository references and the canonical artifact-root abstraction are not private-host values.

Reason codes must name the rejected category without echoing the secret-bearing value. Example closed codes:

```text
FORBIDDEN_FIELD_NAME
JWT_SHAPE
KNOWN_SECRET_PREFIX
AUTHORIZATION_HEADER_SHAPE
COOKIE_SECRET_SHAPE
ENVIRONMENT_ASSIGNMENT_SHAPE
PRIVATE_IDENTITY_SHAPE
PRIVATE_HOST_SHAPE
```

A finding carries a JSON path and category only. It must not include a matched substring, raw value, environment name/value, or reconstructed credential.

### 3.5 Explicit nonmatches

The detector must not reject solely because a supplied string contains:

- a canonical `sha256:<64 lower-case hex>` digest;
- a Git commit SHA inside a valid source-qualified reference;
- a UUID4 evaluation identity;
- a normal repository path;
- a public HTTPS documentation/source URL permitted by the owning contract;
- a canonical decimal string;
- an arbitrary 32-character hexadecimal or base64url-like run without another prohibited shape.

R0 deliberately does not use a generic “long random token” regex. Such a rule would corrupt evidence identities and create unreviewable false positives.

### 3.6 Exact known-secret matching is outside R0

R0 cannot prove that an otherwise unrecognizable string does not equal a real ambient credential because it is prohibited from reading ambient credentials. It must state that limit honestly.

Later content/runner waves may add an **explicit, caller-supplied, ephemeral known-secret denyset** only through a separately reviewed interface that:

- never reads the environment implicitly;
- never persists, logs, digests, returns, or exposes raw denyset values;
- is owned by the runner/content-verification boundary rather than the canonical R0 store;
- leaves the R0 canonical artifact schema and authority boundary unchanged.

No such later capability is built or authorized by this amendment.

### 3.7 Observed-evidence sanitization law (adopted 2026-09-01, release-review repair)

This section closes the predicate left undefined by §3.4(6)-(7). It applies only to runner-**observed** evidence fields defined by the parent design's run receipt schema — explicitly including `observations.observed_network_destinations` — never to caller-supplied scenario/configuration/experiment/run-draft/scorer-pass/evidence-ref input values, which remain governed by §3.4 without exception.

An observed evidence field is not a supplied value under §3.1-§3.4. It is capability evidence that must be persisted for validity recomputation, including on `INVALID` runs. Each observed destination is stored as a structured sanitized observation:

```json
{
  "destination_class": "LOOPBACK | PRIVATE_RANGE | PUBLIC | UNRESOLVED_NAME",
  "value_digest": "sha256:<hex of exact observed value>",
  "raw_value": "<string, or null>"
}
```

`raw_value` is populated only when `destination_class` is `PUBLIC`. Loopback, RFC 1918, private-host, email-shaped, and account-shaped observed values persist `destination_class` and `value_digest` with `raw_value: null`.

Validity recomputation for `UNEXPECTED_NETWORK_DESTINATION` is defined over `destination_class` and `value_digest`, never over `raw_value`: the scenario/configuration's authorized destination set is stored as exact values whose digests are computable, so the recomputation rule is "observed digest not in the authorized digest set, or observed class not in the authorized class set" — and this recomputes deterministically from stored artifacts alone, with no access to any unsanitized raw value.

---

## 4. Binding corrections to the R0 implementation plan

The following clauses supersede conflicting older plan language.

### 4.1 Technology

R0 production code uses Python 3.11+ standard library only. It does not import an OHF/general redaction helper.

### 4.2 Allowed implementation paths

Add:

```text
scripts/agent_eval/privacy.py
tests/test_agent_eval_privacy.py
```

All previously listed R0 paths remain allowed. No OHF/general-redaction production path enters the R0 implementation carrier.

### 4.3 Ordered work

Add the privacy module to the first canonical-contract foundation task or make it one immediately following bounded TDD task before artifact-store publication.

Required RED-before-GREEN evidence includes:

- every minimum prohibited shape above;
- nested object/list JSON paths;
- deterministic ordering;
- no matched-value leakage in findings/exceptions;
- positive controls for SHA-256, Git SHA/source refs, UUIDs, repository paths, decimal strings, and public URLs;
- proof that changing the process environment cannot change the result;
- proof that the production package imports neither OHF/general redaction nor environment/process/network modules.

### 4.4 Artifact-store behavior

Before path derivation or temporary-file creation, `ArtifactStore.create()` must:

1. shape-validate the proposed finalized canonical document;
2. run `assert_public_safe_evidence(document)`;
3. graph-verify the document and its evaluation-artifact references;
4. only then enter the create-only filesystem publication sequence.

A run draft must pass the same detector before finalization emits or writes a final receipt.

A secret-shape finding is a contract/privacy refusal with `effect=NONE`; no final or temporary artifact path may be created.

An observed-evidence field never triggers the refusal; it follows the observed-evidence sanitization law (§3.7), and `INVALID` runs are always persisted with their sanitized observations — a validity failure is evidence, never a reason to destroy evidence.

### 4.5 Inertness/static fences

The R0 inertness test must reject production imports or usage of:

```text
scripts.ohf.redaction
common.redaction
os.environ
os.getenv
environment_secrets
```

along with the already prohibited process, network, database, provider, Executive, Agent OS, Slack, framework, and environment primitives.

A test may monkeypatch or replace `os.environ` with a sentinel mapping that raises on observation, then exercise every public privacy/store/finalizer path to prove no ambient read occurs.

The test process may inspect environment state to establish the sentinel. Production R0 code may not.

---

## 5. Failure, null, correction, and privacy behavior

- A secret-shape finding is deterministic and terminal for that proposed artifact/draft.
- The detector emits no partially sanitized artifact.
- Unknown secret status is not converted to “safe”; R0 reports only that no **recognized supplied-value shape** was found.
- A new or corrected detector version does not rewrite an existing canonical artifact. It may quarantine an artifact through a later owner-reviewed process and append a superseding verification/evidence record.
- Raw private evidence stays outside public repositories and outside R0 canonical JSON unless a later approved private content-verification contract explicitly permits the sanitized reference.
- The detector's code/source revision is part of the validator/scorer provenance where its result affects an accepted artifact.
- A pattern-set change creates a new code revision and must receive mutation/regression proof; it is never silently data-driven from ambient state.

---

## 6. Acceptance tests for this amendment's future implementation

A future R0 implementation is not accepted unless all are true:

1. `scripts/agent_eval/privacy.py` imports standard-library modules and local inert contract errors only.
2. Production R0 imports neither OHF/general redaction module.
3. No production R0 path reads the process environment.
4. Every prohibited shape is rejected before filesystem publication.
5. Findings expose path/category only and never matched values.
6. SHA-256, Git SHA/source refs, UUIDs, paths, decimals, and public URLs remain valid controls.
7. Environment mutation does not change detection results.
8. Canonical run validity/scoring/verification semantics remain unchanged.
9. The synthetic two-arm journey still reaches one technically `VALID` and one `INVALID_CONFIGURATION` run with `INSUFFICIENT_EVIDENCE`, while external content remains unverified.
10. The final implementation diff contains no OHF/general-redaction modification and no new security/lifecycle/configuration authority.

---

## 7. Capability and no-rebuild statement

This amendment changes no current capability classification:

```text
EVAL-F0 = SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT
EVAL-R0 = NOT_BUILT
EVAL-C0 = NOT_BUILT
EVAL-OHF1 / PR #162 = NOT_BUILT
```

It does not create a general redaction subsystem, DLP service, secret inventory, environment scanner, credential owner, security-event database, policy authority, lifecycle, router, scheduler, or new evidence truth store.

The current general/OHF redaction owners remain unchanged for their existing runtime use cases. R0 simply refuses to depend on their ambient-observation behavior.

---

## 8. Exact continuation

After this amendment lands on the existing F0 branch:

1. reconcile the candidate against the action-time protected Mastermind base;
2. verify the effective PR delta is exactly the original three records plus this amendment;
3. run fresh exact-head repository CI;
4. obtain the current required independent exact-head architecture/source-law review after the serialized higher-priority release window clears;
5. perform final Sol review;
6. remove Draft/HOLD only in a separate release decision;
7. merge only with the expected exact head.

A protected amendment still authorizes no R0 implementation, provider/model run, corpus work, OHF runner work, policy change, or production action. Every successor remains a fresh bounded operation.
# Executive OS Phase 1G — G0 review response and re-review packet

**Date:** 2026-08-15  
**Program:** Phase 1G Agent Fabric + Workspace CEO autonomy  
**Original independent review head:** `d64349f22327474ec2d862aa8a36bf97a507cc70`  
**Original independent verdict:** `BLOCK`  
**Current status:** remediation in progress; **G0 remains BLOCKED**

---

## 0. Purpose

This is the traceability packet between the independent fresh-context review and the remediation work. It prevents either authoring or reviewing sessions from silently treating a design change as proof that a blocker is closed.

The independent review remains authoritative as the finding set. Closure requires both the appropriate repository change and fresh-context re-review.

---

## 1. What the independent review accepted

The review specifically found the following Phase 1G design elements sound at the design level:

- monotonic executive attention: semantic judgment may promote but cannot demote a deterministic hard floor;
- wake path separated from MCP state/action path;
- activation generation/fencing plus a distinct cognition claim;
- technical completion separated from strategic closure;
- immutable commission provenance and two-phase publication/directive binding;
- severity-monotonic event compression, bounded deferral, and fail-up semantic-triage outage handling;
- Slack free text not becoming Chairman approval;
- GitHub not becoming the lifecycle queue.

Those elements remain intact.

---

## 2. Remediation artifacts on PR #66

### A. Binding blocker adjudication

`research/EXECUTIVE_OS_PHASE1G_G0_BLOCKER_ADJUDICATION_2026-08-15.md`

Contains:

- B1 executive seat and decision-altitude design;
- B2 strategy / candidate-ranking / admitted-work separation;
- rulings on all six Phase 1F §6 questions;
- B4 reclassification of tunnel-borne caller identity as non-load-bearing;
- X1-B application-authentication architecture;
- zero-Harpoon invariant;
- conversation-key rotation/ownership;
- trigger-principal lifecycle;
- negative-only provider telemetry;
- fail-closed executive dissent;
- attention-state non-dispatch invariant;
- separate credential trust domains;
- protected constitutional-path requirement;
- revised X0-A rows and wave dependencies.

### B. Workspace CEO evidence addendum

`research/EXECUTIVE_OS_PHASE1G_WORKSPACE_CEO_EVIDENCE_ADDENDUM_2026-08-15.md`

Reconciles current primary-source product evidence with the architecture. In particular:

- tunnel connectivity is not treated as Executive caller identity;
- application `Authorization`/connector auth can be forwarded through the tunnel and is the basis for X1-B;
- static tunnel-runtime headers cannot distinguish OpenAI-side callers;
- Harpoon is an additional channel and must have zero targets;
- Workspace trigger, tunnel runtime, tunnel admin, and Executive MCP application identity are four separate credential domains.

### C. X1-B authentication design

`research/EXECUTIVE_OS_PHASE1G_X1B_GATEWAY_APPLICATION_AUTHORIZATION_DESIGN.md`

Defines the application-layer authorization prerequisite for X5/X6/X7:

```text
network reachability
AND authenticated application principal
AND principal-class policy
AND canonical decision category
AND current activation/intent/request fence
AND operation authority
AND idempotency
```

Preferred: OAuth-protected Executive MCP with server-validated issuer/audience/subject. Bounded canary fallback: a per-principal connector-bound secret only if X0-A proves secrecy and cross-principal isolation.

---

## 3. Separate source-law PR

The independent review correctly required the authority substrate to exist in source law rather than only in a Phase 1G design memo.

A separate draft source-law PR is therefore required so PR #66 can remain documentation-only.

**Source-law PR:** #72 — `Executive OS G0: canonical executive authority and strategy source law`

Branch: `codex/executive-g0-source-law-20260815`

That PR adds:

- `authority_map.yml` `executive_seats`, all with `authority: none`;
- server-derived `executive_decision_policy` with Chairman/CEO/COO minimum decision altitude;
- `executive_strategy_policy` separating strategy, candidate ranking, and admitted-work ordering;
- accepted Phase 1F COO bounds and review verdicts;
- fail-closed implementation-review starvation and executive-dissent policy;
- `executive_protected_paths`;
- worker-facing contract corrections disambiguating Sol seat vs model route and retiring "Improvement Agenda = sole priority queue";
- `tests/test_executive_governance_source_law.py` in the explicit hermetic CI gate;
- a recorded Phase 1F §6 ruling memo.

PR #72 itself remains draft until CI and independent re-review pass.

---

## 4. Finding-by-finding status

### B1 — authority substrate

**Review finding:** `chairman_required` and delegated CEO authority had no canonical machine-readable definition.

**Remediation:**

- design: explicit deterministic decision-category policy in Phase 1G blocker adjudication;
- source law: PR #72 adds executive seats and decision categories to `config/authority_map.yml`, conformance-tested;
- naming: worker contracts now explicitly separate `ceo` seat / occupant `Sol` / model route `gpt-5.6-sol`;
- A7: `FABLE_HUMAN` explicitly classified as legacy effect-taxonomy language, not executive rank.

**Closure state:** `PENDING_REREVIEW_AND_PR72_MERGE`.

### B2 — priority/source-of-truth ambiguity

**Review finding:** Improvement Agenda and strategic state were conflated; neither was the mutable priority authority the design assumed.

**Remediation ruling:** there is no magic mutable "company priority queue" to invent.

```text
company strategy
    -> config/strategic_state.yml
       canonical decision artifact
       runtime advisory/orientation-only

candidate ranking
    -> brain/improvement_agenda.py
       derived advisory only

admitted work lifecycle/order
    -> Executive SQLite / Job priority
       only after explicit authority-checked admission
```

A project within an already accepted P0 may be admitted by a typed directive referencing the exact strategy revision. A true strategy change first receives the applicable CEO/Chairman decision, changes the Git-backed strategy artifact, then becomes an admitted project. Runtime never schedules directly from the strategy YAML.

**Closure state:** `PENDING_REREVIEW_AND_PR72_MERGE`.

### B3 — Phase 1F §6

All six questions now have explicit rulings; machine-relevant Q1/Q2/Q3/Q4/Q6 policy is pinned in PR #72.

**Closure state:** `PENDING_REREVIEW_AND_PR72_MERGE`.

### B4 — transport identity

**Review finding:** Secure MCP Tunnel likely cannot prove the exact Sol/Chairman caller at the private MCP server.

**Remediation:** accept the conservative premise rather than depending on a favorable X0-A result.

```text
Secure MCP Tunnel = connectivity + tunnel-runtime authentication
Executive MCP application authentication = caller principal
activation/request fence = freshness/scope/idempotency
```

X1-B is now a named prerequisite of X5/X6/X7. Tunnel identity alone can never satisfy production-write caller identity.

**Closure state:** `DESIGN_CLOSED; CAPABILITY/SECURITY_PROOF_PENDING_X0A_X1B`.

### H1 — Harpoon

**Remediation:** Executive tunnel profile must have zero Harpoon targets; effective profile is receipt-bound and drift from zero invalidates acceptance.

**State:** `DESIGN_CLOSED; X1A_PROOF_PENDING`.

### H2 — conversation concurrency

**Remediation:** at most one nonterminal activation generation owns a `conversation_key`; supersession/escalation/drain/cancel/context invalidation rotates the key. X0-A gets a concurrent-same-key adversarial canary.

**State:** `DESIGN_CLOSED; X0A_X3A_PROOF_PENDING`.

### H3 — trigger principal lifecycle

**Remediation:** Workspace Agent trigger token is a separate ChatGPT-workspace credential/share dependency. Permission/share refusal is non-transient; sharing/config drift invalidates route acceptance.

**State:** `DESIGN_CLOSED; X0A_PROOF_PENDING`.

### H4 / M3 — run status and retry semantics

**Remediation:** provider telemetry can accelerate negative diagnosis but cannot declare Executive completion. `DISPATCH_FAILED` and `RUN_FAILED` have different recovery semantics; `RUN_FAILED` reconciles possible effects before retry.

**State:** `DESIGN_CLOSED; X0A_X3A_PROOF_PENDING`.

### H5 — dissent independence

**Remediation:** policy declares required independence class. If achieved independence is lower, verdict is `DISSENT_UNAVAILABLE`, never `CLEAR`; defer/retry/escalate according to deterministic policy.

**State:** `SOURCE_LAW_IN_PR72; PENDING_REREVIEW`.

### M1/M2 — Charter generalization / Sol naming

**Remediation:** Phase 1G design must label Executive-OS adoption of Charter principles as an adoption/extension rather than pretending literal trading text defines agent routing. PR #72 disambiguates seat ids from model ids and the A7 legacy label.

**State:** `PENDING_REREVIEW`.

### M4 — attention state queue ambiguity

**Remediation:** attention state may only create/coalesce a CEO activation via the deterministic Wake Router. It may not create Jobs, claim Jobs, place workers, dispatch work, or mutate strategy.

**State:** `DESIGN_CLOSED; X3A_CONFORMANCE_PENDING`.

### M5 — credential domains

Now explicitly separate:

1. Workspace Agent trigger token;
2. tunnel runtime key;
3. tunnel admin/manage key;
4. Executive MCP application-principal credential.

**State:** `DESIGN_CLOSED; X0A_X1_PROOF_PENDING`.

---

## 5. G0 status after remediation

G0 remains **BLOCKED**, even if GitHub says either PR is technically mergeable.

Required sequence:

```text
PR #72 CI
  -> fresh-context review of PR #72 + this remediation packet
  -> adjudicate any new confirmed source-law findings
  -> merge PR #72 only if accepted
  -> rebase/refresh PR #66 evidence against exact new master
  -> X0-A live Business Workspace capability matrix
  -> scoped fresh-context Phase 1G re-review of B1/B2/B3/B4/H5 + affected surfaces
  -> only then consider G0 PASS / PASS_WITH_NONBLOCKING_RESIDUE
```

X0-A may gather zero-write evidence before PR #72 merges, but no downstream production design may treat missing source law or tunnel identity as solved by implication.

---

## 6. Scoped re-review request

The re-reviewer should attack, at minimum:

### Authority / B1

- Can any seat/model/actor/impact/escalation field still grant authority by label?
- Are Chairman-reserved categories complete enough for the proposed X5/X6 surface without becoming an unrestricted catch-all?
- Can a CEO operation cross a standing constraint without deterministically mapping upward?
- Can the decision-category policy mutate itself below Chairman altitude?

### Priority / B2

- Is there now exactly one owner for company strategy, candidate ranking, and admitted-work lifecycle/order?
- Can generated agenda data accidentally become durable project admission?
- Can `Job.priority` become company strategy?
- Can runtime key directly off strategic-state YAML and thereby create a second control plane?

### Phase 1F / B3 + H5

- Do Q1–Q6 have explicit, noncontradictory rulings?
- Does same-worker review ever count as independent?
- Can exhaustion be silently waived?
- Can executive dissent claim `CLEAR` below the policy-required independence class?

### Identity / B4

- Does any design path still treat tunnel id/runtime key/source IP/model arguments as CEO or Chairman identity?
- Is OAuth/application principal independent from activation correlation fields?
- Can another OpenAI-side surface on the same tunnel invoke write tools without the Executive application credential?
- Can static tunnel-client headers be confused with per-caller identity?
- Can `CEO_AGENT` perform a Chairman-reserved operation directly?

### Constitutional self-modification

- Is the protected-path policy sufficient as source law for G0?
- Before X5, is there a mandatory gate requiring modifying tools to consume the protected-path set?
- Is there any autonomous route to alter Charter/authority/trust/reasoning/autonomy policy and make the change effective without Chairman-level review?

---

## 7. Final rule

Do not convert a remediation artifact into a PASS receipt by self-assertion.

The authoring session can propose and implement fixes. A fresh-context reviewer determines whether the independent-review blockers are actually closed.
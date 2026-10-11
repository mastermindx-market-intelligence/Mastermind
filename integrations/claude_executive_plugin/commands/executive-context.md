---
name: executive-context
description: Recover the current Mastermind Executive OS mission frontier for COO judgment without creating a new effect.
---

Recover the smallest sufficient current Executive frontier for the active Mastermind mission.

Use only the exact currently authenticated `mastermind-executive` connector and the role-correct
COO read surface. This command is read-only: it must not call `submit_principal_intent`,
`submit_ceo_intent` or any other modifying operation.

Read in this order, stopping once the active question is answered:

1. `executive_mandate` for the exact assigned `work_ref`;
2. `executive_state` for current readiness/grounding;
3. `executive_inbox` only when current attention/owed-turn facts are relevant;
4. `executive_fabric` for the exact selected root/children/results;
5. `principal_intent_status` only when reconciling an already-existing COO request reference.

Return a compact working frame containing:

- exact selected workstream and root Job, if current;
- current mandate posture and new-effect gate;
- Executive readiness and relevant attention;
- current children and their lifecycle states;
- returned results that need principal consumption;
- accountable seat and owed turn when projected;
- exact existing COO request reference/effect state when reconciliation is needed;
- source/reconciliation/lease blockers;
- the highest-leverage next COO action already inside the accepted mission; and
- any exact CEO/Chairman/human gate that actually prevents that action.

Preserve these distinctions: admission is not START; delivery is not ACK; ACK is not execution;
CI is not acceptance; a returned result is not principal acceptance; a partial/historical
projection is not current authority.

If the connector is missing, unauthenticated, exposes the wrong COO tool generation, or resolves
only to a CEO-specific surface, report that exact capability mismatch. Do not request credentials,
create a replacement server, expose a private Executive endpoint, or fall back to CEO mutation.

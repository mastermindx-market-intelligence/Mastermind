# Reuse First — Mastermind Engineering and Autonomy

**Scope:** All substantial engineering/design implementation by assigned ChatGPT Web, Claude, Codex, Cursor, Hermes, Fabric workers and fleet operators. This is a source engineering preference, not a new gate, approval, registry, tool grant, model route, or deployment permission. Apply the accepted protected version. Existing architecture and source owners still govern.

## Default decision: reuse, compose, extend, then custom-build

For capabilities already solved reliably in the broader ecosystem, **look for a maintained, suitable implementation before designing a replacement**. Spend our differentiation budget on useful proprietary decision systems and product integration, not duplicate plumbing.

1. **Inspect the incumbent first.** Find the existing Mastermind/Macro/Terminal/Fabric/Hermes owner, contracts, libraries and in-flight work. Prefer extending it to creating a second control plane, store, queue, retry mechanism, tool registry, agent lifecycle or credential path.
2. **Do a bounded donor scan when a new component is warranted.** Check relevant open-source packages, templates, maintained reference implementations, upstream frameworks and supported APIs. Use primary project docs, exact versions and source repos. Search effort is proportional to the decision; a routine fix does not demand a procurement report.
3. **Choose the smallest sound path:** use the existing component unchanged; add an adapter around a proven library; compose a few narrow modules; extend/fork selectively when justified; **write custom** only for genuine differentiation, missing fit, unacceptable risk or a simpler overall solution. Avoid lifting an entire donor architecture when one utility suffices.
4. **Evaluate real adoption cost, not GitHub stars.** Check real feature fit, maintainer activity, dependency footprint, data exposure, runtime/OS integration, latency, operational cost, upgrade friction, testability and reversibility. Make the choice proportionate to the implementation, not a separate audit. For consequential selections, compare the leading viable options and state the choice succinctly in the existing design/PR/task record.
5. **Integrate through incumbent owners.** Pin package versions or donor commits and use supported upstream distributions where feasible. Build a thin adapter preserving stable Mastermind interfaces, exact owner/custody boundaries and security properties. Avoid vendor lock-in when an affordable interface boundary can preserve choice.
6. **Prove the consumer.** Run focused tests, actual compatibility/integration paths, relevant safety checks when actually implicated, performance checks where claimed and production/user acceptance when owed. Donor quality or a green upstream CI does not prove the Mastermind integration. Record actual evidence and rollback/update approach.

**Fast-path rule:** When an existing compatible approved component is obvious, use it and proceed. When a credible donor is unsuitable, record the decisive reason briefly and build. Do not create an exhaustive marketplace survey, mandatory new sign-off, or per-task reuse form. Do not sacrifice the delivery critical path to research theater.

## Classification examples

| Usually reuse / adapt | Usually custom / scientifically validate |
| --- | --- |
| Agent harnesses, tool interfaces, orchestration UI, provider adapters, chart rendering, dashboards, interaction patterns | Proprietary hypotheses, sector rotation, regime classification, portfolio/risk decision policies |
| Scheduling, event buses, telemetry, logging, failure monitoring, storage hygiene, queues, packaging, auth libraries | Signal definitions, causal/point-in-time data joins, predictive models, trading edge attribution and falsification |
| Backtesting engines, numerical libraries, data-frame operations and visualization components as neutral primitives | Actual strategy assumptions, feature design, leakage controls, walk-forward protocols and real-world risk acceptance |

The distinction is about **differentiation and correctness**, not the label on the product. A quant engine may reuse numerical primitives; a visually polished chart can use an open-source renderer while Mastermind owns data semantics and decision overlays. A harness may reuse mature tools while Capacity Fabric/Executive OS retain canonical admission, routing, lifecycle, billing and continuity. Do not import a second competing owner for convenience.

## Existing operating boundaries — no new gate

- This engineering preference does **not** add procurement, legal review, extra approval, or component-admission steps. Work through normal package-management and source practices; proceed when a viable component fits.
- Do not copy private competitor implementations, branding, confidential data or credentials. Implement comparable workflows independently when needed.
- Keep existing tool permissions, source ownership, credential and deployment safeguards. A dependency choice does not grant extra access or prove a live consumer. Address concrete integration risks, not imagined blockers.

## Agent and instruction distribution

The canonical details live here, not in a second cross-fleet policy database. Small pointers belong in `AGENTS.md`, `CLAUDE.md`, `docs/NATIVE_EXECUTION_BRIEF.md`, `docs/SOL_CEO_ACCOUNT_INSTRUCTIONS.md`, the protected Sol `INDEX.md` and execution procedure, the bounded worker-bootstrap skill and the compact Project kernel. Future Cursor/Hermes role templates and new providers should reference this law during their authorized install/refresh path.

**Rollout is not implicit.** Source merge, native instruction-file installation, Hermes `SOUL.md` profile updates, Cursor rule installation and ChatGPT Project saved-setting updates are separate effects. Verify each authorized destination, exact saved preimage/backup where required and a fresh-session behavioral readback; never say all fleet sessions received a rule merely because this document merged.

## Working-session acceptance

A session developing a substantial nonunique component should be able to explain: the incumbent/donor considered, why the selected reuse/adapt/custom path is cheapest in *accepted-result* risk and time, which existing interface and owner it preserves, and what tests prove the installed behavior. One or two sentences in its normal PR/implementation record suffice unless stakes warrant more.

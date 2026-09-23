---
name: navigate-mastermind-universe
description: Use when a fresh approved Mastermind session must find the current canonical owner, compose honest capability health, and load only the smallest role-appropriate tool family for one bounded action.
---

# Navigate the Mastermind Universe

This skill is read-only orientation and routing. It creates no lifecycle, truth store, permission, capability, session, target, installation, retry, merge, release, deployment, or effect authority.

## Mandatory current-source gate

Read protected Mastermind `master`, record its exact commit, load `docs/sol_skills/INDEX.md` and the governing source law from that same exact commit, and verify compatibility. If the protected source or Skillpack cannot be verified, modifying workflow is unavailable.

## Required packaged references

Before routing, read:

- `../../references/navigator-boundary.md`
- `../../references/owner-routing.json`
- `../../references/role-profiles.json`
- `../../references/boot-sources.json`
- `../../references/capability-health.schema.json`
- `../../references/capability-state-rules.json`

The package-local catalog fragment and fixtures are validation evidence, not installation or live-state evidence.

## Select the role, not an omnipotent environment

Use the explicit task and current authority context to select exactly one core profile: `web_ceo_core`, `native_builder_operator`, or `browser_provider_operator`. Add a domain overlay only for an explicit task need plus current authorization. A role label never upgrades authority.

A domain route becomes visible only when domain_overlays includes the route and owner-native evidence records organizationally_authorized = YES with a non-empty evidence identity. Otherwise suppress the overlay and load no schema.

Do not infer effective capability from a product, plugin, or connector name. A plugin name is not evidence that a surface is installed, enabled, authenticated or connected, callable, organizationally authorized, or `PROVEN_LIVE`.

## Compose role-filtered health

0. Classify the exact requested action class as `READ`, `WRITE`, or `ADMIN` before making any capability claim. Route identity alone is too coarse: a successful READ never proves WRITE or ADMIN serviceability or unavailability.
1. Consume existing owner-native observations from the sources in `boot-sources.json`; do not edit those owners.
2. For each relevant surface, record `requested_action_class` and `requested_action_serviceability` plus `installed`, `enabled`, `authenticated_or_connected`, `callable`, `organizationally_authorized`, and `proven_live` independently as `YES`, `NO`, `UNKNOWN`, or `NOT_APPLICABLE`. Bind any decisive requested-action serviceability evidence to that exact action class.
3. Record implementation state, usable scope, exact host/project/session/source binding, current generation where applicable, evidence identity, observation time, coverage, blocker, and smallest next probe.
4. Apply `capability-state-rules.json` in order. `PROVEN_LIVE` requires current target-bound evidence for every required gate. Explicit negative owner evidence may produce `UNAVAILABLE`. A bounded partial path is `DEGRADED`. Built source without a current canary is `BUILT_NOT_PROVEN`. Missing decisive evidence remains `UNKNOWN`.
5. Validate the projection against `capability-health.schema.json` and filter it to the selected core profile plus the one requested route. Preserve suppressed-surface identities without loading their schemas.

For user-facing prose, spell the third gate as authenticated or connected. Never collapse it into installed or enabled.

## Minimal discovery law

Do not load every connector or tool schema just because it exists. Health observation does not load a tool schema. Discover only the smallest role-appropriate tool family named by the selected owner route. Load a second family only after the first owner-native result proves a concrete dependency.

The discovery call is evidence about that exact surface and moment. It is not a durable registry entry and does not prove another account, host, project, session, action class, or generation. A READ observation cannot settle a WRITE or ADMIN request; discover/preflight the requested action class itself.

## Route by canonical owner

- Lifecycle, Job, Attempt, Worker, Event, admission, and completion questions route to Executive OS.
- Organizational workstreams, decisions, discoveries, and handoffs route to Agent OS.
- Protected source, PR, review, and CI questions route to GitHub.
- Selected-project reads or actions route to the current Workbench capability; Workbench Read does not imply Workbench Action. Any action requires the owner-admitted execution mode, authenticated subject or approved native context, and the exact current session generation or Executive Job/Attempt/Worker generation before effect. Mode labels never grant authority: ATTENDED_WEB_OPERATOR must bind the current RuntimeBinding/Web-session owner, NATIVE_OPERATOR must bind the approved native-session context owner, and BOUNDED_WORKER must bind the Executive Job/Attempt/Worker owner.
- Local machine and process work routes to Studio Direct and the existing host/Fleet owner.
- Governed worker browsing routes to Worker Browser.
- Exact ChatGPT observation or actuation routes through Web-Sol plus a current RuntimeBinding; never select a target by title, recency, or newest tab.
- Deployment, data, design, and communications work routes to the actual domain owner for the named target.

## Least-privilege actuator routing

Classify the requested effect by its owned object, not by the fact that a local command could emulate it.

- Selected-project source edits, repository reconciliation, build/test work, and Git-oriented delivery stay on the selected-project/source path. Use an exact current Workbench action when its contract covers the effect. If the attended Workbench contract does not cover the needed repo/build effect, keep the project/source binding and, before any effect begins, move the bounded outcome only through an already-authorized native builder or Executive Job/Attempt/Worker owner. Do not synthesize the missing capability with Studio Direct `start_process` or `interact_with_process`.
- Use Studio Direct's generic process surface for genuine bound host/process operations. A shell happening to be able to edit source, run Git, or invoke a build does not make that selected-project effect a host/process action.
- A narrow typed owner-native action may be used only when its actual contract binds the requested target/effect and current owner evidence admits it; tool presence or a friendly name is not enough.
- For Mastermind attended-Web Git publication, when currently exposed and owner-native status proves the same canonical `mmx-workspace` operation, repository, `sol/web-*` branch and origin, prefer the gateway-owned `studio_git_publish_status`, `studio_git_commit_current_changes`, and `studio_git_push_current_branch` actions for exactly those status/commit/push effects. They are typed source-publication actions, not generic shell. Never use them as substitutes for missing edit/build/test capability or for another repository.
- After an explicit platform safety refusal for a modifying action, freeze that logical operation on its carrier and reconcile owner-native effect evidence. Never change account, plugin, connector, worker, device, or generic tool merely to obtain the same refused effect. Independent path-disjoint work may continue.

## Bounded execution sequence

1. Establish protected-source and Skillpack compatibility.
2. Select one core role and, only when needed, one domain overlay.
3. Read the smallest existing boot or owner snapshot that can identify the route.
4. Build the source-attributed health projection and surface `PROVEN_LIVE`, `BUILT_NOT_PROVEN`, `DEGRADED`, `UNAVAILABLE`, or `UNKNOWN` honestly.
5. Select one canonical owner. For a domain overlay, load its minimal tool family only after the owner-native overlay authorization gate passes; when the overlay is suppressed, withhold the schema. For a core route, load only the selected minimal tool family.
6. Perform one owner-native action that is useful and within current authority—for example, read the exact protected branch or selected-project identity.
7. Attach the exact result, binding, state, blocker, and next probe. Do not generalize one successful read into write or production proof.

## Capability self-resolution law

`UNKNOWN` / `UNPROBED` is not `UNAVAILABLE`. When the selected surface names a safe, non-effectful, in-scope `next_probe` that is currently discoverable/callable, execute that probe in the same turn before stopping or escalating.

For the requested action class:
1. discover only the selected owner-native action family;
2. use a non-mutating permission/capability/binding preflight when one exists;
3. record the exact discovery result, permission/preflight result or explicit refusal/error, target/binding scope, and observation generation/epoch;
4. recompute `requested_action_serviceability` and the health state;
5. continue the requested action when the technical/resource gate clears, then evaluate organizational/source-writer authority separately.

When an owner supplies `mastermind.sol_capability_status.v1`, consume it rather than reimplementing
CAP1 policy: for the exact matching scope, READ may consume `read_serviceable`.
WRITE may consume `write_serviceable`; ADMIN remains UNKNOWN unless its actual owner supplies action-specific evidence.
Preserve CAP1 source refs/issues and proof generation. Navigator normalizes that owner fact into the
role-filtered packet; it does not become the capability registry or recompute CAP1's serviceability law.

Never perform a dummy mutation solely to prove capability. If only an effectful probe exists and the actual effect is not yet authorized/safe, keep the capability `UNKNOWN` / `UNPROBED` rather than fabricating `UNAVAILABLE`.

A terminal negative capability claim must name the requested action class, current discovery result, non-effectful preflight/refusal evidence, exhausted safe probe path, exact target/binding scope, and any exact human/admin ceremony still required. The packet records this as `requested_action_discovery`, `requested_action_preflight`, `safe_probe_status`, and nullable `human_ceremony`; a requested-action `NO` is schema-invalid unless the safe probe path is exhausted and either action absence or explicit preflight refusal is proven. Missing evidence means more bounded discovery work exists; it is not a Chairman gate.

Keep four axes separate: technical tool/action exposure; authenticated resource permission; organizational/source-writer authority; and effect state. A denial or unknown on one axis must never be rewritten as another.

## Effect and ambiguity law

A read refusal proves only that read's response. After any possible modifying effect, use only `NOT_APPLIED`, `APPLIED`, or `EFFECT_UNKNOWN`. `EFFECT_UNKNOWN` requires owner-native reconciliation on the same carrier; never retry, resubmit, or fail over blindly.

## Output

```text
protected Mastermind commit and Skillpack compatibility
selected role profile and explicit overlay, if any
requested capability class, requested action class, and canonical owner
role-filtered surface health:
  requested_action_serviceability | requested_action_discovery | requested_action_preflight | safe_probe_status | human_ceremony\n  installed | enabled | authenticated_or_connected | callable | organizationally_authorized | proven_live
  state | exact binding | evidence | blocker | next probe
minimal tool family loaded
one owner-native action and exact result
capability probe receipt when the requested action was initially UNKNOWN/UNPROBED
suppressed unrelated surfaces
remaining unknowns and authority ceiling
```

## Stop condition

Do not stop merely because the requested action is `UNKNOWN` / `UNPROBED` while a safe, non-effectful, in-scope next probe remains available. Execute the bounded self-resolution loop first. Stop after one useful owner-native action, a decisive evidence-backed `UNAVAILABLE`, an authority/stale-binding/effect-ambiguity gate, or exhaustion of safe probes. Return the exact owner, requested action class, discovery/preflight evidence, blocker, exhausted-or-remaining probe path, and any exact human/admin ceremony. Do not ask the Chairman to choose routine routing or capability discovery that current owner records and safe probes can decide, and do not cross an owner gate by inventing a replacement surface.

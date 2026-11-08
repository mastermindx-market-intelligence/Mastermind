# Provider plan facade integration

## Problem and scope

The native provider-plan consumers and the connected Fabric facade had different contracts. The facade did not expose BytePlus, accepted only the historical Experiential full GLM model, and rejected consent on AUTO. Its production pre-task continuation wrapper also excluded native plan AUTO admission by supplying incompatible deadline/preflight options.

This change updates the existing facade, its provider-free qualification fixtures, and repository-owned usage instructions. It introduces no provider credential, account, budget, retry, queue, or lifecycle owner.

## Resulting contract

- BytePlus accepts either exact Flash model or native default selection. A default preview omits the literal `auto` argument because the native route expects an omitted model. The exact preview result is pinned for request.
- Experiential accepts the seven plain included IDs, the two paid Flash Uncensored IDs, and the historical explicit full-GLM route subject to native admission. The `free` selector resolves only within the five included chat models. `uncensored` resolves only within the two paid Flash models, with preference owned by native policy. Jev and Decisions require exact selection.
- Selector resolution is frozen between preview and strict request. Included selectors cannot resolve to paid models; no provider/model quota continuation is added to a manual pin.
- All Experiential requests retain three explicit boolean consent acknowledgments and the four independent native consent flags. AUTO consent requires a task that can be completed entirely from its packet with `response_only: true`.
- New `provider_plan_auto: true` selects one ordinary native AUTO attempt for C0/C1 mechanical/fix_build work. Consent-qualified response-only AUTO uses the same entry. Neither guarantees a plan provider, grants consent, nor authorizes paid AUTO. Other AUTO requests retain incumbent continuation.
- Native quota, funding, account, policy and physical-capacity admission remain authoritative. Unverified Max included funding is not enabled by the facade.
- Capability output identifies the facade contract but does not claim ChatGPT's approved tool snapshot has refreshed.

## Executed validation

- 170 focused Node cases passed: request forwarding, exact-model and lane checks, consent typing, native compatibility, production continuation selection, capacity tracking, retained-result paging, failure diagnosis and acceptance guards.
- Authenticated local HTTP/MCP qualification passed through the actual maintained Desktop Commander transport and an isolated provider-free native fixture. The flow exercised schema exposure, strict GLM and historical Experiential compatibility, BytePlus exact/default selection, Experiential included/paid/explicit GLM selection, consent-qualified AUTO, retained result consumption and deterministic acceptance.
- Syntax and diff checks passed. These are source/transport qualifications, not evidence of a production provider response or a refreshed ChatGPT action snapshot.

## Deployment acceptance

Use protected source acceptance and the existing same-account `fabric-backend-release` owner. Preserve native selected source, the gateway/dependency seal, service/account/tunnel identity and existing controller effects. Reconcile actual server catalog and approved app metadata separately. Native funding correction is tracked in PR #2263; the facade must not be used to weaken its account-specific funding gate.

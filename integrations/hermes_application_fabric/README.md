# Hermes primary inference through APPLICATION Fabric

Programme: [Mastermind #983 P2](https://github.com/mastermindx-market-intelligence/Mastermind/issues/983#issuecomment-6695933514).
Operation: `hermes-primary-fabric-inference-20261106-sol-01`.
Parent task tree: C5 in [shared model pool control #2109](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2109).
Procedure/source base: `2f60dc913622da61a65a2cc6f8a793a81c61eea1`.

## Outcome and current state

Hermes primary reasoning must use the existing qualified APPLICATION model/account
owner, authenticated by the existing role/session host. Provider credentials,
entitlements, physical quotas, budget reservation, leases and settlement remain
with Fabric. This package contains no network client, provider-key loader, router,
account store, queue, retry ledger or tool executor.

The adapter and native qualification fixture are implemented. Live activation is
held: the incumbent owner has no enrolled Hermes application service relation and
its source-defined application transports are not yet qualified. No real account,
production role binding, AUTO routing or account/budget acceptance is claimed by
the loopback fixture. `from_factory` fails closed until the owner qualifies the
role; the direct raw-client constructor cannot borrow a Brain/Ask identity.

## Exact dependencies and native composition

Installed M2 Hermes v0.23.0: `2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19`.
Incumbent Macro APPLICATION source: [#10740](https://github.com/mastermindx-market-intelligence/macro/pull/10740)
at `2ef828e569b683b9dfaa94f81116da3ac55f6186`.
Mastermind #2060 is merged; its `brain/fabric_inference.py` establishes consumer
composition, while this adapter preserves chat/tool semantics beyond Brain text.

`native.create_primary_agent` constructs the real programmatic `AIAgent` with
`provider=mastermind-fabric`, an explicit host-selected model, no API key, no
endpoint, no credential pool and no fallback chain. `ProviderProfile.create_client`
is the supported client hook. Keyless construction also needs one unique entry in
the existing `agent.auxiliary_client_registry.REGISTRY_AUTHTYPE_ARMS`: this is a
private v0.23 compatibility interface, qualified at the exact commit above. A
same-name custom provider, foreign profile or existing auth-type arm is refused.
No incumbent entry is overwritten. This is a programmatic host integration;
the naked CLI runtime-provider/auth ladder is not an equivalent entrypoint.

The host registers `native.register_middleware(ctx, resolve_binding)` through
Hermes's supported `llm_execution` middleware. Its resolver returns the original
`ApplicationBinding` for the native session/task/turn/request, using the existing
authenticated host and its grant/currentness checks. Metadata is correlation,
not authority. The host retains this binding across native client rebuilds and
owns its lifecycle and recovery. The adapter does not invent a role/session map.

The role-specific factory must pass the original APPLICATION closed relation,
capability, qualification and policy checks. Proposed Hermes service relations in
`from_factory` are reserved integration names, not enrollment or enabled policy.
`prior_admission_possible` must be explicitly false for new binding. Existing or
uncertain operations require the original owner recovery path, never a fresh
client constructed from a remembered ID.

## Conversation and output contract

| Surface | Implemented behavior |
| --- | --- |
| History | Ordered system/user/assistant/tool history, Unicode text, parallel tool IDs and original tool-result correlation. Duplicate/orphan/pending tool history refuses before dispatch. |
| Native tools | Original IDs, function names and JSON object arguments; offered-tool and forced-choice checks before returning executable calls. Hermes executes tools. |
| Structured JSON | `json_object`, or object-root `json_schema`, translated to one reserved forced result tool. Existing Hermes `jsonschema` validates before returning JSON text; the reserved tool is never executed. |
| Schema limits | 16 KiB schema, depth 16, bounded properties/alternatives, standard structural/numeric/string-length constraints. No references, remote retrieval, recursive schemas, regex/format vocabulary or mixed user tools. Unknown semantics refuse before dispatch. |
| Structured failure | One owner call, no repair or retry. Invalid output, extra properties, multiple result calls or a non-JSON preamble produces a terminal error. This is adapter-enforced JSON, not provider-native strict-format parity. |
| Bounds | 512 KiB request, 1 MiB result, 128 KiB arguments, 512 messages, 64 tools, 32,768 maximum requested output tokens. The owner applies its own independent limits. |
| Attribution | Actual served model must equal the inspected/bound model. Actual usage must be present. No estimated usage or fabricated provider/account receipt. |
| Streaming | Disabled through the real provider profile. The current native APPLICATION protocol rejects streams; no buffered answer is presented as streaming. |
| Async/vision | Explicit refusing views. Native async wrapping cannot construct another HTTP client. Primary qualification does not authorize auxiliary inference. |
| Opaque reasoning | Unsupported provider-private replay/multimodal carriers refuse when presented; model eligibility must require history semantics this adapter preserves. |

## Original identity, interruption and uncertain effects

The wire request ID is a pure hash of the original APPLICATION operation and the
native session/task/turn/API-request identity. It contains no generation, retry
count, timestamp, random suffix or replacement model. Hermes assigns the API ID
before its retry loop. The SAME owner client retains its active/attempted/failed
state; reconstructing a facade cannot dispatch the same request again.

Native provider construction is always possible, even unbound; inference refuses
inside `create`. This prevents Hermes's constructor fail-open behavior from
falling through to standard HTTP. Middleware resolver failures still invoke the
downstream facade once with an empty scope, where authorization must fail.

Errors crossing the execution boundary are detached, bounded RuntimeError
subtypes. `raise ... from None` alone is insufficient because Hermes traverses
`__context__`. The profile disables retry, compression, credential rotation and
fallback. On an authorized downstream abort/watchdog failure, middleware calls
the original owner's once-only `close`: its local closed fence blocks new IDs
and late tool delivery; its original close disposition remains in that owner.
This is not provider-cancellation, lease-release or budget-release proof.
Uncertain original effects never authorize another provider call. Host currentness
and the empty native fallback chain remain required across redirects/rebuilds.

## Routing and physical account design

Automatic selection remains in existing Executive ModelRouter task suitability,
native Fabric `pick.py`, the APPLICATION factory and account/lease owners. The
adapter does not score models or reserve capacity. The smallest remaining owner
extension is a qualified request-requirements/selection receipt on that existing
path, not a new inference service or a job per completion.

1. Receive trusted task complexity and latency/cost bounds from the host; content
   may supply advisory estimates but cannot grant model, pool or account access.
2. Intersect task suitability with APPLICATION entitlement, exact conversation,
   tool/forced-tool/schema/stream capabilities, context/output limits, configured
   enabled/qualified state and host constraints.
3. For a strict model/pool constraint, reduce the eligible set before ranking and
   refuse an empty set. Never relax a strict pin to AUTO. `strict_model` already
   checks the current inspection before credential binding; a requested strict
   pool explicitly refuses until the owner exposes that constraint and receipt.
4. Rank eligible candidates with existing policy using expected queue plus first
   token/completion latency, quality required by task complexity, expected token
   cost and current account headroom. Estimates guide selection; actual usage
   drives settlement. Policy revisions and selected recipe remain pinned to the
   original operation.
5. Preserve the many-to-many model/account relation. Join logical pool members to
   canonical physical account/quota-bucket IDs before computing headroom. One
   account advertising several models has one shared physical quota; several
   accounts serving one model remain distinct eligible reservations. Do not sum
   the same physical bucket through aliases, pools or models.
6. Recheck and atomically reserve through the existing lease/budget owner. A
   ranking snapshot is not admission. Record the actual provider/model/physical
   account, recipe/config revision, original request, reservation and settlement
   references in that owner's result. The adapter only consumes bounded proof.
7. A 429, timeout, missing body, changed policy or newly available account never
   authorizes failover. Only the incumbent owner's original-request outcome can
   prove a new call is safe. Recovery first reads/reconciles the original effect.

The current owner inspection exposes provider/model/capability/cost basis and
policy/recipe identity, not a physical-account receipt or dynamic selector.
Adding a Hermes-side score or interpreting `cap_id` as an account would be false
integration. Owner coordination is tracked in [#10740 comment](https://github.com/mastermindx-market-intelligence/macro/pull/10740#issuecomment-6696511751).

## Tests and qualification

The pure/loopback suite uses the exact incumbent `engine.fabric_inference_client`
on `PYTHONPATH`, not a copied implementation shipped with this package:

```sh
PYTHONPATH=.:/path/to/exact/macro/source python3 -m unittest discover \
  -s integrations/hermes_application_fabric/tests -p 'test_*.py' -v
```

`qualification/qualify_installed.py` runs through the installed Hermes launcher's
`--run-module runpy` path, in an isolated `HERMES_HOME`, with an immutable candidate
manifest and exact owner file checksum. It runs actual provider resolution,
primary construction, middleware, transport, classifier and native conversation
tests. Standard OpenAI/AsyncOpenAI construction fails the fixture; external
network connections are denied. Simulated internal bearer authentication and
loopback usage are explicitly fixture evidence, never a live Fabric account.

Live acceptance still requires: protected/installed source and existing role
enrollment; one real eligible account; authenticated native primary/tool turns;
verified provider/model/physical-account selection; actual usage, budget/lease
enforcement and original-result recovery without duplicate effects. It must also
qualify any required provider-native streaming/cancellation/replay semantics.

## Custody and continuation

All new source and tests are under this directory. Macro #10740's APPLICATION
paths, Hermes #2134 selected-child/auth/installer paths, #2147 worker delegation
and #2109/#2148 policy/config paths retain incumbent custody. A paid bounded
worker request was retained but refused before launch; no worker START or code
return is claimed. Principal source/integration work proceeds directly.

Source, tests, native fixture integration, protected release, installation,
account qualification and production acceptance remain separate evidence.
This package must not be enabled in a production role solely because tests pass.

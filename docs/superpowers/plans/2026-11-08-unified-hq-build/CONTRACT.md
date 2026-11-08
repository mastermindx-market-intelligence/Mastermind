# Frozen minimal presentation contract — v1

Scope: an ephemeral React presentation model. This document and living_hq/contracts.ts create no server schema, lifecycle, permission, persistent registry or network API.

## Existing canonical types

Use the source at protected Mastermind 183bbd7ea0d71875984bea0f63bc81a98d930586:

| Concept | Existing owner/type | Rule |
|---|---|---|
| Selection | mission.ts: MissionSelection | Preserve workRef and rootJobId exactly |
| Result destination | result.ts: ResultSelection | Preserve workRef, rootJobId, jobId, attemptId, resultEnvelopeDigest |
| View context | meta-ceo/projection.ts: ProjectionContext | Exact authGeneration, selection, sessionRef, bindingGeneration and source revisions |
| Source facts | projection.ts: SourceClaim / ProjectedRead | Preserve owner, ref, revision, observed_at, state and coverage |
| Qualified app reads | projection.ts: projectOffice / OfficeProjection | Reuse qualifiers; never promote unknown or unassociated data |
| Organization | OrganizationWorkspace.tsx: OrganizationObservation / qualifyOrganization | SOURCE_LINKED_ADVISORY only; existing false authority/admission flags and selection checks remain |
| Jobs / Attempts | mission.ts: ChildCard / AttemptCard / ListSection | Existing owner statuses and partial coverage; no derived acceptance |
| Conversation | workspace-contract.ts: WindowDocument | Only the authorized current window and proved Mission association |
| Retained result | result.ts decoder and ResultEnvelopeDigestShape | Owner observation and five-part selection; 16 KiB bounds remain |
| Parent acceptance | Mission acceptance / v4 ProductAcceptanceView where qualified | Worker COMPLETED never means original parent consumed or product accepted |

Additional canonical mapping helpers: fabric/mission-interiors.ts exports FabricMission, FabricRow and missionInteriors (up to 256 displayed children; full-source duplicate/ancestor checks). fabric/mission-worker-result.ts exports qualifyWorkerResultRef for current Mission-v3/latest-attempt/unique-result navigation. meta-ceo/session-context.ts and mission-adapter.ts own enrolled session qualification and asynchronous capture/completion. Reuse them, not new association gates.

The native Hermes port is effectful (create/send/recover); only decoded observations may enter a read adapter. The v1 input deliberately does not invent a native-session-to-Executive join or new trace/placement supplier. A separately proved current supplier requires one compatible amendment by I. Historical local ledger model/pool labels remain historical; browser catalog reads require the existing EXACT_RUN_SET decoder.

The contract imports these types directly. HQOrganization is derived with NonNullable<ReturnType<typeof qualifyOrganization>>; builders do not copy that private shape into another validator.

## Component exports

~~~typescript
CompanyHQ(props: CompanyHQProps)
LivingHQGraph(props: LivingHQGraphProps)
AgentObservatory(props: AgentObservatoryProps)
adaptLivingHQ(input: LivingHQInput): LivingHQSnapshot
~~~

All exported components have named exports from their own index.ts. D exports its adapter from adapters/index.ts. No builder creates the shared living_hq/index.ts; I owns final composition.

Each surface receives snapshot, locale (en or zh-CN), selected, onSelect, onNavigate and optional onRefresh. B additionally receives controlled organization/execution mode; C receives controlled traceId. Inputs are immutable presentation data. Outputs are React elements and callbacks, not jobs, writes or background effects.

Navigation is a typed intent to the existing app handlers: mission, job, result, evidence, back. The integrator validates the target against the currently selected source before using an existing handler. Do not manufacture URLs, effect verbs, launch permissions or shell commands. Search/filter/collapse/zoom state is local ephemeral UI state.

## Data qualification and ownership

D receives the incumbent OfficeProjection plus its exact binding and optional existing OrganizationObservation. Office composition owns acquisition, cancellation, authentication and generations. D checks that the supplied projection and binding agree and consumes only already-decoded fields; it performs no network read or command.

Every displayed entity/edge retains its original source claim and evidence. Renderer node IDs are local keys, never replacement Job/session IDs. Organization and execution graphs have separate HQRead containers, preventing a fresh advisory chart from making stale execution current.

HQRelation is a visual relationship discriminator: advisory_reporting, work_lineage, delegation, trace_parent, observed_placement, result_of, original_parent_consumption. It grants nothing. Build an edge only from explicit qualified source association. Do not join by role name, model name, similar title, clock coincidence or last-visible session.

A role charter is advisory. A human Chairman node is human. Actual sessions need an enrolled/observed source; a charter does not create a session. Parent/child Jobs are sourced from Executive/Fabric original IDs. Configured capacity preference is not actual placement. A result has its own source and tuple; parent consumption requires its own evidence.

## Missing, stale, denied and partial states

Reuse SourceState exactly: CURRENT, STALE, UNKNOWN, UNAVAILABLE, WITHHELD, UNASSOCIATED. Keep permission denial as WITHHELD plus a safe reason; malformed input may reduce to UNKNOWN/UNAVAILABLE according to the incumbent qualifier. Do not add a new lifecycle state called denied.

HQRead adds loading and complete only for presentation. Complete is boolean or null. Null means unknown. No count may be derived from partial/truncated lists and represented as fleet total. An empty complete successful read can show zero; no other missing state can.

On auth-generation change, clear protected payload, search index, selection detail and source identity that the incumbent clears. On selection/session/binding/revision change, reuse the incumbent stale/unassociated semantics and disable old navigation. Never relabel the old object with the new context. Historical information is shown only when the existing source permits it and with its original date/state.

No fabricated default host/model/session, refresh timestamp, zero cost, zero duration or success state. A local acquisition time is not source event time. Stale data does not animate.

## Traces, results and placement

Trace events retain source sequence and source timestamps separately. Unknown parentage is null, never inferred from adjacency. Clock-skewed sources are not combined into a falsely precise global chronology. Tool/model events, retries and cancellations appear only when supplied by an authorized source. Ordinary user/assistant text is not a structured tool span.

HQText carries only existing sanitized, authorized display text. No raw HTML, automatic URL retrieval, secrets, hidden reasoning or newly read transcript store. Input/output missingness and truncation are visible. Preserve result budgets rather than expanding them for a pretty inspector.

Current qualified source may not supply detailed tool/model spans, a fleet roster or actual placement. v1 requires useful no-source states and real Job/Attempt chronology where available. Enrich only through an existing qualified supplier after I proves its binding; do not guess new endpoints or expand this input interface in a private fork.

## Fixtures and updates

A–C may create disjoint local fixtures using the exact contract. Mark all fixtures SYNTHETIC in both names and the visible demo. Fixtures must never be imported by production composition or presented as acceptance.

A rerender with new props is the real-time-ready update mechanism. No poller, event bus, reconnect service or worker scheduler is added. Each component must clear invalid selection when the source context changes and retain focus only when the same qualified target still exists.

## Writer and change rule

The coordinator owns contracts.ts for this package revision. A–D treat it as read-only. I owns any subsequent compatible amendment after considering all consumers. If a field is insufficient, return a small exact contract amendment and continue all work not dependent on it; do not create a renamed copy or parallel v2 API.

Root manifests and lockfiles remain serialized to I. A dependency proposal includes exact package/version, license/source pin, reason, lockfile preimage and the temporary qualification command. This is a concrete integration input, not permission to mutate another writer.

## Minimum contract falsifiers

Reject cross-auth, cross-session, changed binding and changed Mission revision; refuse wrong result tuple or digest; preserve SAME/UNKNOWN/CONFLICT owner observation; keep partial totals unknown; show stale/missing/denied states; never turn a charter into enrollment, reporting into delegation, a route into placement, a returned result into parent acceptance, or a fixture into live proof.


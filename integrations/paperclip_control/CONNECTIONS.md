# Company relationships and agent discovery

This extends the incumbent company read. It adds no graph database, roster owner,
task lifecycle, native credential, dispatcher, timer or message transport.

## Existing source and consumers

`PaperclipWorkspace.read()` builds a bounded `connections` member after its
source-visible runtime and project joins, before the existing final permission
check. Overview includes goals alongside people, projects, work and routines.
All reads still use the single configured company and current Workspace principal.

The company TypeScript decoder independently derives the projection from the
decoded source records. If the server supplies a projection, every field must
match the bounded derived result. A forged relation, action claim, additional
field or omitted fact is refused. Older source envelopes without the optional
member remain readable and receive the same local projection.

The existing Overview renders the relationships and opens existing People,
Runtime, Work and Projects navigation. It does not offer an unbound dispatch
button. A configured `WS:` join opens the existing permitted project catalogue;
it is not evidence of an adopted plan.

## Relationship semantics

Paperclip reporting, goal containment, issue containment and assignment are
distinct relations. Agent OS workstream and Hermes profile references remain
configured joins with `CONFIGURED_NOT_LIVE_VERIFIED`. No native identity is
generated from a title, name or role. The same UUID in different record types is
not one entity.

Missing targets are `OUTSIDE_VISIBLE_WINDOW`, never a proven orphan. Pagination,
restricted records, unavailable sources and unrequested collections remain
explicit. No hidden target is fetched to finish a diagram. Duplicate native IDs,
malformed references, self-links, visible parent cycles or ambiguous visible
configured joins withhold the relationship view; original source views remain
available. Non-null relationship fields are validated in the actual record
producer so corrupt numeric/array fields cannot silently disappear.

The projection explicitly does not supply execution lineage, dependency edges,
parent consumption or acceptance. `issue.parentId` is containment, not a
dependency. Reads are separate source observations, not an atomic estate snapshot.

## Reuse the current Hermes briefing

The existing host may opt its retained `LeadershipReader` into
`include_company_context=True`. Default remains false; unmodified callers still
perform one Mission read. The opt-in uses the same `SecretaryAccessClient` and
one fixed `GET /workspace/company/current?view=overview`; the model supplies no
company, project, endpoint, actor or credential.

The already-authenticated native `mmx_leadership_brief` then includes bounded
company discovery: up to 16 visible people, the unique visible configured project
matching the host's original workstream, and up to eight explicitly project-linked
work items. Counts of omitted records/fields and source-window coverage remain
visible. Fields over 160 characters are omitted, not truncated. Native session,
gateway, environment, adapter configuration and tool secrets are not exported.

The company packet is at most 8 KiB; the existing complete briefing remains at
most 24 KiB and its existing wire/node budgets remain unchanged. An oversized
optional packet is unavailable rather than erasing the original mission. The
120-second guard qualifies the read observation; it does not attest freshness
of every underlying source record. A non-matching donor revision is unavailable.

Currentness is checked around the await. Permission refusal, including malformed
401/403 bodies, discards all previously read Mission and organization facts.
Other source failure retains only still-current Mission context with explicit
company unavailability. No source cache, polling loop or new native tool appears.

Company visibility is not project membership. A source company capability is not
a native tool grant. Consultation/delegation/resume remain unbound in this company
surface. Existing editorial leadership charters remain separate from the observed
company roster. Native hosts must supply current role and Workspace bindings;
this source change does not install or widen them.

T3/Hermes long-horizon source-plan context remains owned by #2375. Its existing
compact-context path may carry this bounded, host-validated companion; no second
plan parser, synchronous credential hook or model-selected company context is
introduced here.

## Qualification and activation

Focused source checks:

```bash
python -m pytest -q -o addopts='' \
  tests/test_paperclip_connections.py tests/test_paperclip_agent_context.py \
  tests/test_hermes_company_context.py tests/test_hermes_leadership.py \
  tests/test_hermes_project_continuity.py
node --experimental-transform-types scripts/qualify_paperclip_connections.mjs
```

The Node command executes the actual TypeScript decoder/projection. Its module
resolution hook supplies extensionless TS resolution only. It is not a TypeScript
type-check, installed runtime or real-principal test. The Python HTTP/native
handler fixtures use synthetic principals and owner records. Frontend component
tests belong to the app's existing Vitest runner.

Before activation, compose the source into the original #2395 company carrier and
the single #2338 Team shell, pass actual release controls, and bind the current
native host/principal. Prove current/partial/refused reads, revoke-during-read and
the selected real native briefing. No canary can bypass #2403's credential/source
hold, #2375's continuity composition or any original unknown effect.
